"""
LLM-assisted pattern/domain augmentation (outline).
"""
import json
import requests
from typing import List, Dict
from ..types.entity import EntityType


def refresh_patterns(entity: str, entity_type: EntityType, seeds: List[str], ollama_url: str, model: str) -> Dict[str, List[Dict]]:
    prompt = f"""
    Given the target "{entity}" (type: {entity_type}), propose regex URL patterns and domains
    that are high-signal for valuable content (profiles, news, filings, bios).
    Return JSON: {{"patterns": [{{"pattern": "...", "weight": 30}}], "domains": [{{"domain": "example.com", "weight": 40}}]}}
    Avoid social share and generic spam.
    """
    try:
        response = requests.post(
            ollama_url,
            json={"model": model, "prompt": prompt, "stream": False, "format": "json"},
            timeout=60,
        )
        result = json.loads(response.json().get("response", "{}"))
        return {
            "patterns": result.get("patterns", []),
            "domains": result.get("domains", []),
        }
    except Exception:
        return {"patterns": [], "domains": []}


class RefreshRunner:
    def __init__(self, ollama_url: str, model: str):
        self.ollama_url = ollama_url
        self.model = model

    def run(self, entity: str, entity_type: EntityType, seeds: List[str]) -> Dict[str, List[Dict]]:
        return refresh_patterns(entity, entity_type, seeds, self.ollama_url, self.model)
