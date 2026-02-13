"""
QA validation and verification of extracted intelligence.
Handles reflection and quality control of findings.
"""

import json
import logging
import requests
from typing import Tuple, Dict, Any, List

from ..types.entity import EntityProfile
from .text_processor import TextProcessor


# Maximum characters for a finding payload sent to the LLM in one pass.
# Findings larger than this are split into sub-findings for separate verification.
_MAX_FINDING_CHARS = 6000


class QAValidator:
    """Handles reflection and verification of extracted intelligence."""

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434/api/generate",
        model: str = "granite3.1-dense:8b",
        reflect_timeout: int = 300,  # 5 minutes default
    ):
        self.ollama_url = ollama_url
        self.model = model
        self.reflect_timeout = reflect_timeout
        self.logger = logging.getLogger(__name__)
        self.text_processor = TextProcessor()

    def reflect_and_verify(self, profile: EntityProfile, finding: Dict[str, Any]) -> Tuple[bool, float]:
        """
        Validate extracted intelligence for quality and relevance.

        For large findings the payload is split into sub-sections that are
        each verified independently.  The final score is the average
        confidence of all verified sub-sections, and the finding is
        accepted when at least one sub-section passes.
        
        Args:
            profile: Entity profile being researched
            finding: Intelligence finding to verify
            
        Returns:
            Tuple of (is_verified, confidence_score)
        """
        finding_json = json.dumps(finding, indent=2, ensure_ascii=False)

        # If the finding is small enough, verify in a single pass
        if len(finding_json) <= _MAX_FINDING_CHARS:
            return self._verify_single(profile, finding_json)

        # Large finding – split into sub-sections and verify each
        self.logger.info(
            f"Finding too large ({len(finding_json)} chars), splitting for multi-step verification"
        )
        sub_findings = self._split_finding(finding)
        if not sub_findings:
            return self._verify_single(profile, finding_json[:_MAX_FINDING_CHARS])

        any_verified = False
        total_conf = 0.0
        count = 0

        for sub in sub_findings:
            sub_json = json.dumps(sub, indent=2, ensure_ascii=False)
            verified, conf = self._verify_single(profile, sub_json)
            if verified:
                any_verified = True
            total_conf += conf
            count += 1

        avg_conf = total_conf / count
        return any_verified, avg_conf

    # ------------------------------------------------------------------

    def _verify_single(self, profile: EntityProfile, finding_json: str) -> Tuple[bool, float]:
        """Run the LLM verification prompt for a single (sub-)finding."""
        prompt = f"""
        You are a strict QA auditor. Validate the following intelligence extracted for the entity "{profile.name}" (Type: {profile.entity_type}).

        Finding to Verify:
        {finding_json}

        Criteria:
        - Is the information specific to {profile.name}? (Reject generic text)
        - Is it likely to be factually accurate based on the context?
        - Is it useful intelligence (not just navigation links or cookie warnings)?

        Return JSON ONLY:
        {{
            "is_verified": true/false,
            "confidence_score": <int 0-100>,
            "reason": "<short explanation>"
        }}
        """
        try:
            payload = {"model": self.model, "prompt": prompt, "stream": False, "format": "json"}
            resp = requests.post(self.ollama_url, json=payload, timeout=self.reflect_timeout)
            result_raw = resp.json().get("response", "{}")
            result = self.text_processor.safe_json_loads(result_raw, fallback={})
            is_verified = bool(result.get("is_verified", False))
            confidence = result.get("confidence_score", 0) or 0
            if not is_verified or confidence < 70:
                self.logger.debug(f"Reflection rejected intel: {result.get('reason')} (Score: {confidence})")
            return is_verified, float(confidence)
        except Exception as e:
            self.logger.warning(f"Reflection failed: {e}")
            return False, 0.0

    @staticmethod
    def _split_finding(finding: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Split a large finding dict into smaller sub-finding dicts.

        Each top-level list field (persons, products, locations, …) is
        grouped into its own sub-finding while ``basic_info`` is always
        included to maintain context.
        """
        basic = finding.get("basic_info", {})
        subs: List[Dict[str, Any]] = []

        # Always include basic_info as its own sub-finding if non-empty
        if basic:
            subs.append({"basic_info": basic})

        list_keys = [
            "persons", "jobs", "metrics", "locations",
            "financials", "products", "events",
            "relationships", "organizations",
        ]
        for key in list_keys:
            items = finding.get(key)
            if items and isinstance(items, list) and len(items) > 0:
                subs.append({"basic_info": basic, key: items})

        return subs if subs else [finding]
