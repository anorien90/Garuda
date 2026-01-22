import json
import logging
import requests
import numpy as np
import re
import uuid
from typing import List, Dict, Any, Tuple
from ..models.entities import EntityProfile, EntityType
from ..filter import SemanticFilter

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None


class LLMIntelExtractor:
    """
    The cognitive core of the crawler.
    Handles:
    1. Semantic Embedding (for redundancy checks)
    2. Search Query Generation & Result Ranking
    3. Link Prioritization (Navigation)
    4. Intelligence Extraction (Data Gathering)
    5. Reflection & Verification (Quality Control)
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434/api/generate",
        model: str = "granite3.1-dense:8b",
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    ):
        self.ollama_url = ollama_url
        self.model = model
        self.logger = logging.getLogger(__name__)
        self.relevance_filter = SemanticFilter(ollama_url, model)
        self.embedding_model_name = embedding_model
        self._embedder = None

        if SentenceTransformer:
            try:
                self._embedder = SentenceTransformer(embedding_model)
                self.logger.info(f"Loaded embedding model: {embedding_model}")
            except Exception as e:
                self.logger.warning(f"Could not load embedding model {embedding_model}: {e}")
        else:
            self.logger.warning("sentence-transformers not installed; semantic features disabled.")

    def summarize_page(self, text: str) -> str:
        if not text:
            return ""
        prompt = f"Summarize the following text in 3-5 sentences, focusing on key facts and entities:\n\n{text[:8000]}"
        try:
            payload = {"model": self.model, "prompt": prompt, "stream": False}
            resp = requests.post(self.ollama_url, json=payload, timeout=60)
            return resp.json().get("response", "").strip()
        except Exception as e:
            self.logger.warning(f"Summarization failed: {e}")
            return ""

    def embed_text(self, text: str) -> List[float]:
        if not self._embedder or not text:
            return []
        try:
            return self._embedder.encode(text, normalize_embeddings=True).tolist()
        except Exception as e:
            self.logger.error(f"Embedding generation failed: {e}")
            return []

    def calculate_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        if not vec_a or not vec_b:
            return 0.0
        try:
            a = np.array(vec_a)
            b = np.array(vec_b)
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return float(np.dot(a, b) / (norm_a * norm_b))
        except Exception as e:
            self.logger.warning(f"Similarity calculation error: {e}")
            return 0.0

    def reflect_and_verify(self, profile: EntityProfile, finding: Dict[str, Any]) -> Tuple[bool, float]:
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
            resp = requests.post(self.ollama_url, json=payload, timeout=30)
            result = json.loads(resp.json().get("response", "{}"))

            is_verified = result.get("is_verified", False)
            confidence = result.get("confidence_score", 0)

            if not is_verified or confidence < 70:
                self.logger.debug(f"Reflection rejected intel: {result.get('reason')} (Score: {confidence})")

            return is_verified, float(confidence)
        except Exception as e:
            self.logger.warning(f"Reflection failed: {e}")
            return False, 0.0

    def extract_intelligence(self, profile: EntityProfile, text: str, page_type: str, url: str, existing_intel: Any) -> dict:
        existing_context = self._build_existing_context(existing_intel)

        caution_instruction = ""
        if any(x in url.lower() for x in ["northdata", "opencorporates", "company-information", "register", "directory"]):
            caution_instruction = """
            CRITICAL: This appears to be a registry or directory page.
            It may list multiple entities. Extract ONLY data matching the exact target name.
            Ignore similar/other companies or unrelated search results on the page.
            """

        prompt = f"""
        You are an expert intelligence analyst. Extract NEW information about "{profile.name}" (type: {profile.entity_type}, location: "{profile.location_hint}").

        PAGE CONTEXT:
        - Type: {page_type}
        - URL: {url}
        {caution_instruction}

        === EXISTING KNOWLEDGE (Do not duplicate) ===
        {existing_context}

        === TEXT TO ANALYZE (Truncated) ===
        {text[:12000]}

        Return ONLY JSON with the following schema (omit empty fields):
        {{
          "basic_info": {{"official_name":"","ticker":"","industry":"","description":"","founded":"","website":""}},
          "persons": [ {{"name":"","title":"","role":"","bio":""}} ],
          "jobs": [ {{"title":"","location":"","description":""}} ],
          "metrics": [ {{"type":"","value":"","unit":"","date":""}} ],
          "locations": [ {{"address":"","city":"","country":"","type":""}} ],
          "financials": [ {{"year":"","revenue":"","currency":"","profit":""}} ],
          "products": [ {{"name":"","description":"","status":""}} ],
          "events": [ {{"title":"","date":"","description":""}} ]
        }}
        """

        max_retries = 3
        for attempt in range(max_retries):
            try:
                payload = {"model": self.model, "prompt": prompt, "stream": False, "format": "json"}
                response = requests.post(self.ollama_url, json=payload, timeout=120)
                result = response.json().get("response", "{}")
                return json.loads(result)
            except (json.JSONDecodeError, Exception) as e:
                if attempt < max_retries - 1:
                    self.logger.warning(f"Extraction JSON parse error (attempt {attempt+1}): {e}")
                    continue
                else:
                    self.logger.error(f"Failed to extract intelligence after {max_retries} attempts.")
                    return {}

    def rank_links(self, profile: EntityProfile, page_url: str, page_text: str, links: List[Dict]) -> List[Dict]:
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
                result = json.loads(resp.json().get("response", "{}"))

                link["llm_score"] = result.get("score", 0)
                link["llm_reason"] = result.get("reason", "")
            except Exception:
                link["llm_score"] = 0
            ranked.append(link)

        return sorted(ranked, key=lambda x: x.get("llm_score", 0), reverse=True)

    def generate_search_queries(self, name: str, known_location: str = "") -> List[str]:
        prompt = f"""
        Generate 5 specific, high-signal search queries to find information about "{name}"{f" located in {known_location}" if known_location else ""}.
        Focus on: Official Site, LinkedIn/Profiles, News/Press, Regulatory Filings.
        Return ONLY a JSON array of strings: ["query1", "query2", ...]
        """
        try:
            payload = {"model": self.model, "prompt": prompt, "stream": False, "format": "json"}
            response = requests.post(self.ollama_url, json=payload, timeout=60)
            queries = json.loads(response.json().get("response", "[]"))
            return queries if isinstance(queries, list) else [f"{name} official website"]
        except Exception:
            return [f"{name} official website", f"{name} news", f"{name} contact"]

    def rank_search_results(self, profile: EntityProfile, search_results: List[dict]) -> List[dict]:
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
            result = json.loads(response.json().get("response", "{}"))

            rankings_map = {r["id"]: r for r in result.get("rankings", [])}

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

    # ---------- New entity helpers ----------
    def extract_entities_from_finding(self, finding: Dict[str, Any]) -> List[Dict[str, Any]]:
        entities: List[Dict[str, Any]] = []
        if not isinstance(finding, dict):
            return entities

        basic_info = finding.get("basic_info") or {}
        if basic_info.get("official_name"):
            entities.append(
                {
                    "name": basic_info["official_name"],
                    "kind": "company" if basic_info.get("ticker") or basic_info.get("industry") else "entity",
                    "attrs": basic_info,
                }
            )
        
            
        for p in finding.get("persons") or []:
            if not isinstance(p, dict):
                try:
                    p = json.loads(p)
                except Exception:
                    p = {"name": p}

            if p.get("name"):
                entities.append({"name": p["name"], "kind": "person", "attrs": p})

        for prod in finding.get("products") or []:
            if not isinstance(prod, dict):
                try:
                    prod = json.loads(prod)
                except Exception:
                    prod = {"name": prod}

            if prod.get("name"):
                entities.append({"name": prod["name"], "kind": "product", "attrs": prod})

        for loc in finding.get("locations") or []:
            if not isinstance(loc, dict):
                try:
                    loc = json.loads(loc)
                except Exception:
                    loc = {"address": loc}

            label = loc.get("address") or loc.get("city") or loc.get("country")
            if label:
                entities.append({"name": label, "kind": "location", "attrs": loc})

        for evt in finding.get("events") or []:
            if not isinstance(evt, dict):
                try:
                    evt = json.loads(evt)
                except Exception:
                    evt = {"title": evt}

            if evt.get("title"):
                entities.append({"name": evt["title"], "kind": "event", "attrs": evt})

        return entities

    # ---------- New embedding helpers ----------
    def build_embeddings_for_page(
        self,
        url: str,
        metadata: Dict,
        summary: str,
        text_content: str,
        findings_with_ids: List[Tuple[Dict, Any]],
        page_type: str,
        entity_name: str,
        entity_type: EntityType,
        max_sentences: int = 40,
    ) -> List[Dict[str, Any]]:
        """
        Produce multiple semantic views (title/description/summary/url/sentences + findings).
        Each entry: {"id", "vector", "payload"} ready for vector_store.upsert.
        Findings carry sql_intel_id when available.
        """
        entries = []
        views = [
            ("title", metadata.get("title", "")),
            ("description", metadata.get("description", "") or metadata.get("og_title", "")),
            ("summary", summary),
            ("url", url),
        ]

        for name, text in views:
            if not text:
                continue
            vec = self.embed_text(text)
            if vec:
                entries.append(
                    self._make_entry(
                        base_id=url,
                        suffix=f"page-{name}",
                        vector=vec,
                        kind="page",
                        url=url,
                        page_type=page_type,
                        entity_name=entity_name,
                        entity_type=entity_type,
                        text=text,
                    )
                )

        sentences = self._split_sentences(text_content)[:max_sentences]
        for idx, sent in enumerate(sentences):
            vec = self.embed_text(sent)
            if vec:
                entries.append(
                    self._make_entry(
                        base_id=url,
                        suffix=f"sentence-{idx}",
                        vector=vec,
                        kind="page_sentence",
                        url=url,
                        page_type=page_type,
                        entity_name=entity_name,
                        entity_type=entity_type,
                        text=sent,
                    )
                )

        for idx, (finding, sql_id) in enumerate(findings_with_ids or []):
            text = self._format_finding(finding)
            vec = self.embed_text(text)
            if vec:
                entries.append(
                    self._make_entry(
                        base_id=url,
                        suffix=f"finding-{idx}",
                        vector=vec,
                        kind="finding",
                        url=url,
                        page_type=page_type,
                        entity_name=entity_name,
                        entity_type=entity_type,
                        text=text,
                        data=finding,
                        sql_id=sql_id,
                    )
                )

        return entries

    def build_embeddings_for_entities(
        self,
        entities: List[Dict[str, Any]],
        source_url: str,
        entity_type: EntityType,
        entity_id_map: Dict[tuple, int],
    ) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for ent in entities:
            text = json.dumps({"name": ent.get("name"), **(ent.get("attrs") or {})}, ensure_ascii=False)
            vec = self.embed_text(text)
            if not vec:
                continue
            ent_kind = ent.get("kind", "entity")
            suffix = f"entity-{ent_kind}-{ent.get('name','')}"
            sql_ent_id = entity_id_map.get((ent.get("name"), ent_kind))
            entries.append(
                self._make_entry(
                    base_id=source_url,
                    suffix=suffix,
                    vector=vec,
                    kind="entity",
                    url=source_url,
                    page_type=ent_kind,
                    entity_name=ent.get("name", ""),
                    entity_type=ent_kind,
                    text=text,
                    data=ent,
                    sql_entity_id=sql_ent_id,
                )
            )
        return entries

    def _make_entry(
        self,
        base_id: str,
        suffix: str,
        vector: List[float],
        kind: str,
        url: str,
        page_type: str,
        entity_name: str,
        entity_type: Any,
        text: str,
        data: Any = None,
        sql_id: Any = None,
        sql_entity_id: Any = None,
    ) -> Dict[str, Any]:
        pid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{base_id}#{suffix}"))
        payload = {
            "kind": kind,
            "url": url,
            "page_type": page_type if isinstance(page_type, str) else getattr(page_type, "value", str(page_type)),
            "entity": entity_name,
            "entity_type": getattr(entity_type, "value", str(entity_type)) if hasattr(entity_type, "value") else str(entity_type),
            "entity_kind": page_type,
            "text": text,
            "data": data,
        }
        if sql_id is not None:
            payload["sql_intel_id"] = sql_id
        if sql_entity_id is not None:
            payload["sql_entity_id"] = sql_entity_id
        return {
            "id": pid,
            "vector": vector,
            "payload": payload,
        }

    def _split_sentences(self, text: str) -> List[str]:
        if not text:
            return []
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if s.strip()]

    def _format_finding(self, finding: Dict[str, Any]) -> str:
        try:
            parts = []
            bi = finding.get("basic_info", {}) if isinstance(finding, dict) else {}
            if bi:
                parts.append("basic_info: " + json.dumps(bi, ensure_ascii=False))
            for key in ["persons", "jobs", "metrics", "locations", "financials", "products", "events"]:
                if finding.get(key):
                    parts.append(f"{key}: " + json.dumps(finding[key], ensure_ascii=False))
            return " | ".join(parts) or json.dumps(finding, ensure_ascii=False)
        except Exception:
            return json.dumps(finding, ensure_ascii=False)

    def _build_existing_context(self, intel: Any) -> str:
        if not intel:
            return "No existing knowledge."

        intel_list = intel if isinstance(intel, list) else [intel]

        parts = []
        for item in intel_list:
            if not item:
                continue
            bi = item.get("basic_info", {}) if isinstance(item, dict) else {}
            if bi.get("official_name"):
                parts.append(f"Name: {bi['official_name']}")
            if bi.get("description"):
                parts.append(f"Desc: {bi['description'][:120]}...")
            people = item.get("persons", []) if isinstance(item, dict) else []
            names = [p.get("name") for p in people if p.get("name")]
            if names:
                parts.append(f"Known People: {', '.join(names[:10])}")

        return "\n".join(parts) if parts else "No existing knowledge."
    
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
            data = json.loads(resp.json().get("response", "[]"))
            return data if isinstance(data, list) else [f"{entity_name} {user_question}"]

        except Exception:
            return [f"{entity_name} {user_question}"]  

    def synthesize_answer(self, question: str, context_hits: List[Dict]) -> str:
        if not context_hits:
            return "INSUFFICIENT_DATA"
   
        context_str = "\n---\n".join([
            f"Source: {h.get('url', 'Unknown')}\nSnippet: {h.get('snippet', '')}" 
            for h in context_hits
        ])
        
        prompt = f"""
        Answer the question using ONLY the context below. 
        If the context is empty or irrelevant, say "INSUFFICIENT_DATA".
   
        Question: {question}
        Context:
        {context_str}
        """
        
        payload = {"model": self.model, "prompt": prompt, "stream": False}
        
        try:
            resp = requests.post(self.ollama_url, json=payload, timeout=60)
            resp.raise_for_status()
            ans = resp.json().get("response", "").strip()
            return ans if ans else "INSUFFICIENT_DATA"
        except Exception as e:
            self.logger.error(f"Synthesis error: {e}")
            return f"Error: {e}"   
    
    def build_embeddings_for_page(self, **kwargs) -> List[Dict]:
        """Helper for explorer persistence."""
        text = kwargs.get("text_content", "")
        vector = self.embed_text(text[:2000])
        return [{
            "id": kwargs.get("url"),
            "vector": vector,
            "payload": {"url": kwargs.get("url"), "text": text[:1000], "kind": "page"}
        }]

    def build_embeddings_for_entities(self, **kwargs) -> List[Dict]:
        return [] # Simplified for integration

    def evaluate_sufficiency(self, answer: str) -> bool:
        """Checks if the LLM flagged the data as missing."""
        return "INSUFFICIENT_DATA" not in answer and len(answer) > 20
