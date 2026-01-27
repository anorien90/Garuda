"""
Search query generation and result ranking.
Handles LLM-based search strategy and link prioritization.
"""

import json
import logging
import requests
from typing import List, Dict, Any

from ..types.entity import EntityProfile
from .text_processor import TextProcessor


class QueryGenerator:
    """Handles search query generation, result ranking, and answer synthesis."""

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434/api/generate",
        model: str = "granite3.1-dense:8b",
    ):
        self.ollama_url = ollama_url
        self.model = model
        self.logger = logging.getLogger(__name__)
        self.text_processor = TextProcessor()

    def generate_search_queries(self, name: str, known_location: str = "") -> List[str]:
        """Generate search queries for finding entity information."""
        prompt = f"""
        Generate 5 specific, high-signal search queries to find information about "{name}"{f" located in {known_location}" if known_location else ""}.
        Focus on: Official Site, LinkedIn/Profiles, News/Press, Regulatory Filings.
        Return ONLY a JSON array of strings: ["query1", "query2", ...]
        """
        try:
            payload = {"model": self.model, "prompt": prompt, "stream": False, "format": "json"}
            response = requests.post(self.ollama_url, json=payload, timeout=60)
            queries = self.text_processor.safe_json_loads(response.json().get("response", "[]"), fallback=[])
            return queries if isinstance(queries, list) else [f"{name} official website"]
        except Exception:
            return [f"{name} official website", f"{name} news", f"{name} contact"]

    def rank_search_results(self, profile: EntityProfile, search_results: List[dict]) -> List[dict]:
        """Rank search results by relevance and identify official sources."""
        if not search_results:
            return []

        prompt_data = [
            {"id": i, "url": r.get("href"), "title": r.get("title"), "snippet": r.get("body")}
            for i, r in enumerate(search_results[:10])
        ]

        prompt = f"""
        Analyze these search results for "{profile.name}" ({profile.entity_type}).
        Identify the OFFICIAL website and rank others by information richness.

        Search Results:
        {json.dumps(prompt_data, indent=2)}

        Return JSON:
        {{
            "rankings": [
                {{"id": <int>, "score": <0-100>, "is_official": <bool>, "reason": "..."}}
            ]
        }}
        """

        try:
            payload = {"model": self.model, "prompt": prompt, "stream": False, "format": "json"}
            self.logger.debug(f"Ranking search results with payload: {payload}")
            response = requests.post(self.ollama_url, json=payload, timeout=60)
            result = self.text_processor.safe_json_loads(response.json().get("response", "{}"), fallback={})

            rankings_map = {r["id"]: r for r in result.get("rankings", []) if isinstance(r, dict)}

            ranked_results = []
            for i, res in enumerate(search_results[:10]):
                rank = rankings_map.get(i, {})
                self.logger.debug(f"Result {i} ranking: {rank}")
                res["llm_score"] = rank.get("score", 0)
                res["is_official"] = rank.get("is_official", False)
                res["llm_reason"] = rank.get("reason", "")
                ranked_results.append(res)

            return sorted(ranked_results, key=lambda x: x.get("llm_score", 0), reverse=True)

        except Exception as e:
            self.logger.warning(f"Result ranking failed: {e}")
            return search_results

    def rank_links(self, profile: EntityProfile, page_url: str, page_text: str, links: List[Dict]) -> List[Dict]:
        """Rank navigation links for relevance to entity research."""
        if not links:
            return []

        ranked = []
        for link in links:
            prompt = f"""
            Navigational Decision: We are researching "{profile.name}".
            Current Page: {page_url}
            Candidate Link: "{link.get('text', '')}" -> {link.get('href', '')}

            Is this link likely to lead to high-value intelligence (profiles, financials, contacts)?
            Return JSON: {{"score": 0 <= score <= 100 , "reason": "short rationale"}}
            """
            try:
                payload = {"model": self.model, "prompt": prompt, "stream": False, "format": "json"}
                resp = requests.post(self.ollama_url, json=payload, timeout=20)
                result_raw = resp.json().get("response", "{}")
                result = self.text_processor.safe_json_loads(result_raw, fallback={})
                link["llm_score"] = result.get("score", 0)
                link["llm_reason"] = result.get("reason", "")
            except Exception:
                link["llm_score"] = 0
            ranked.append(link)

        return sorted(ranked, key=lambda x: x.get("llm_score", 0), reverse=True)

    def generate_seed_queries(self, user_question: str, entity_name: str) -> List[str]:
        """Generates 3-4 specific search strings to find new data online."""
        prompt = f"""
        Goal: Find information to answer '{user_question}' about '{entity_name}'.
        Generate 3 distinct, highly targeted search engine queries.
        Include terms like "official", "news", or "biography" where appropriate.
        Return ONLY a JSON list of strings.
        """
        try:
            payload = {"model": self.model, "prompt": prompt, "stream": False, "format": "json"}
            resp = requests.post(self.ollama_url, json=payload, timeout=20)
            data = self.text_processor.safe_json_loads(resp.json().get("response", "[]"), fallback=[])
            return data if isinstance(data, list) else [f"{entity_name} {user_question}"]

        except Exception:
            return [f"{entity_name} {user_question}"]

    def synthesize_answer(self, question: str, context_hits: List[Dict]) -> str:
        """Synthesize an answer from context snippets."""
        if not context_hits:
            return "INSUFFICIENT_DATA"

        context_str = "\n---\n".join(
            [f"Source: {h.get('url', 'Unknown')}\nSnippet: {h.get('snippet', '')}" for h in context_hits]
        )

        prompt = f"""
        Answer the question using ONLY the context below.
        If the context is empty or irrelevant, say "INSUFFICIENT_DATA".

        Question: {question}
        Context:
        {context_str}
        """

        payload = {"model": self.model, "prompt": prompt, "stream": False}

        try:
            resp = requests.post(self.ollama_url, json=payload, timeout=120)
            resp.raise_for_status()
            ans = resp.json().get("response", "").strip()
            return ans if ans else "INSUFFICIENT_DATA"
        except Exception as e:
            self.logger.error(f"Synthesis error: {e}")
            return f"Error: {e}"

    def evaluate_sufficiency(self, answer: str) -> bool:
        """Checks if the LLM flagged the data as missing."""
        return "INSUFFICIENT_DATA" not in answer and len(answer) > 20
