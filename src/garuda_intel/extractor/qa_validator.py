"""
QA validation and verification of extracted intelligence.
Handles reflection and quality control of findings.
"""

import json
import logging
import requests
from typing import Tuple, Dict, Any

from ..types.entity import EntityProfile
from .text_processor import TextProcessor


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
        
        Args:
            profile: Entity profile being researched
            finding: Intelligence finding to verify
            
        Returns:
            Tuple of (is_verified, confidence_score)
        """
        prompt = f"""
        You are a strict QA auditor. Validate the following intelligence extracted for the entity "{profile.name}" (Type: {profile.entity_type}).

        Finding to Verify:
        {json.dumps(finding, indent=2)}

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
