import json
import logging
import requests
from typing import Tuple


class SemanticFilter:
    def __init__(self, ollama_url: str, model: str):
        self.ollama_url = ollama_url
        self.model = model
        self.logger = logging.getLogger(__name__)
    
    def is_relevant(self, text: str, context: dict) -> Tuple[bool, float]:
        target_name = context.get("name", "")
        entity_type = context.get("entity_type", "")
        location_hint = context.get("location_hint", "")
        prompt = f"""
        You are a data validator. Determine if the following entity is relevant to the target:
        Target: "{target_name}" (type: {entity_type}) {f"based in {location_hint}" if location_hint else ""}
        Entity/Text: "{text}"
        Return JSON only: {{"relevant": true/false, "score": 0-100}}
        """
        try:
            response = requests.post(
                self.ollama_url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                },
                timeout=30,
            )
            result = json.loads(response.json().get("response", "{}"))
            return result.get("relevant", False), result.get("score", 0) / 100.0
        except Exception as e:
            self.logger.warning(f"Relevance check failed: {e}")
            return True, 0.5
