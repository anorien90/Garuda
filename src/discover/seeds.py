# src/modules/crawl/discovery/seeds.py

from typing import List
import logging
from ..models.entities import EntityType, EntityProfile
from ..extract.llm_extractor import LLMIntelExtractor 

logger = logging.getLogger(__name__)

def generate_seeds(profile: EntityProfile, llm: LLMIntelExtractor) -> List[str]:
    """
    Ensures a non-empty seed list by combining heuristics, 
    LLM queries, and similarity-based filtering with fallbacks.
    """
    base_queries = []
    
    # 1. Apply Type-Specific Heuristics
    if profile.entity_type == EntityType.COMPANY:
        base_queries = [f"{profile.name} official site", f"{profile.name} investor relations"]
    elif profile.entity_type == EntityType.PERSON:
        base_queries = [f"{profile.name} biography", f"{profile.name} linkedin"]
    elif profile.entity_type == EntityType.TOPIC:
        # Better topic heuristics
        base_queries = [f"{profile.name} wiki", f"{profile.name} research paper", f"{profile.name} explained"]
    else:
        base_queries = [f"{profile.name} overview"]

    # 2. Integrate LLM Intelligence
    llm_queries = llm.generate_search_queries(
        profile.name, 
        known_location=profile.location_hint or ""
    )
    
    # 3. Merge and Filter (with a safety net)
    target_emb = llm.embed_text(profile.name)
    candidates = list(dict.fromkeys(base_queries + llm_queries))
    final_queries = []

    for q in candidates:
        if not target_emb: # Fallback if embedding is disabled
            final_queries.append(q)
            continue
            
        sim = llm.calculate_similarity(target_emb, llm.embed_text(q))
        # Be more lenient with topics (0.4 vs 0.6)
        threshold = 0.4 if profile.entity_type == EntityType.TOPIC else 0.5
        
        if sim >= threshold:
            final_queries.append(q)

    # 4. Critical Safety: Ensure we never return 0 queries
    if not final_queries:
        logger.warning("All queries filtered out. Falling back to base query.")
        final_queries = [profile.name]

    return final_queries
