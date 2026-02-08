"""
Agent Service for intelligent data exploration and refinement.

Provides two main operation modes:
1. Reflect & Refine: Merge entities, validate and clean data
2. Explore & Prioritize: Analyze relations, find high-priority entities to explore

Also provides multidimensional RAG search combining embedding and graph-based search.
"""

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select, func, desc, and_, or_
from sqlalchemy.orm import Session

from ..database.store import PersistenceStore
from ..database.models import Entity, Relationship, Intelligence, Page
from ..extractor.llm import LLMIntelExtractor
from ..extractor.entity_merger import EntityMerger, SemanticEntityDeduplicator, GraphSearchEngine, ENTITY_TYPE_HIERARCHY, ENTITY_TYPE_CHILDREN
from ..vector.base import VectorStore


logger = logging.getLogger(__name__)


class AgentService:
    """
    Intelligent agent for data exploration and refinement.
    
    Modes:
    - reflect: Analyze and merge entities, validate data quality
    - explore: Traverse entity graph, prioritize exploration based on relation depth
    - search: Multidimensional RAG search combining embedding and graph traversal
    """
    
    def __init__(
        self,
        store: PersistenceStore,
        llm: LLMIntelExtractor,
        vector_store: Optional[VectorStore] = None,
        entity_merge_threshold: float = 0.85,
        max_exploration_depth: int = 3,
        priority_unknown_weight: float = 0.7,
        priority_relation_weight: float = 0.3,
    ):
        """
        Initialize the agent service.
        
        Args:
            store: Database persistence store
            llm: LLM extractor for semantic operations
            vector_store: Optional vector store for RAG
            entity_merge_threshold: Similarity threshold for entity merging
            max_exploration_depth: Maximum depth for relation exploration
            priority_unknown_weight: Weight for unknown entities in priority scoring
            priority_relation_weight: Weight for relation count in priority scoring
        """
        self.store = store
        self.llm = llm
        self.vector_store = vector_store
        self.entity_merge_threshold = entity_merge_threshold
        self.max_exploration_depth = max_exploration_depth
        self.priority_unknown_weight = priority_unknown_weight
        self.priority_relation_weight = priority_relation_weight
        self.logger = logging.getLogger(__name__)
        
        # Process tracking for autonomous modes
        self._running_processes: Dict[str, Dict[str, Any]] = {}
        self._process_counter: int = 0
        
        # Initialize sub-components
        if hasattr(store, 'Session'):
            self.entity_merger = EntityMerger(store.Session, self.logger)
            self.graph_engine = GraphSearchEngine(store.Session, llm, self.logger)
            self.deduplicator = SemanticEntityDeduplicator(store.Session, llm, self.logger)
        else:
            self.entity_merger = None
            self.graph_engine = None
            self.deduplicator = None
    
    # =========================================================================
    # MODE 1: REFLECT & REFINE
    # =========================================================================
    
    def reflect_and_refine(
        self,
        target_entities: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Reflect on existing data and refine it by merging duplicate entities.
        
        This mode:
        1. Identifies similar entities (e.g., "Microsoft Corp" vs "Microsoft Corporation")
        2. Merges duplicates while preserving all relationships and data
        3. Validates data quality and reports issues
        
        Args:
            target_entities: Optional list of entity names to focus on
            dry_run: If True, only report what would be merged without executing
            
        Returns:
            Report of merge operations and data quality findings
        """
        self.logger.info("Starting reflect & refine mode")
        
        report = {
            "mode": "reflect_and_refine",
            "started_at": datetime.now().isoformat(),
            "duplicates_found": [],
            "entities_merged": [],
            "data_quality_issues": [],
            "statistics": {
                "entities_before": 0,
                "entities_after": 0,
                "merges_performed": 0,
                "quality_issues_found": 0,
            },
            "dry_run": dry_run,
        }
        
        try:
            with self.store.Session() as session:
                # Count entities before
                report["statistics"]["entities_before"] = session.execute(
                    select(func.count()).select_from(Entity)
                ).scalar()
                
                # Step 1: Find duplicate candidates
                duplicate_groups = self._find_duplicate_entities(session, target_entities)
                report["duplicates_found"] = duplicate_groups
                
                # Step 2: Merge duplicates (unless dry run)
                if not dry_run:
                    for group in duplicate_groups:
                        merge_result = self._merge_entity_group(session, group)
                        if merge_result:
                            report["entities_merged"].append(merge_result)
                            report["statistics"]["merges_performed"] += 1
                    session.commit()
                
                # Step 3: Validate data quality
                quality_issues = self._validate_data_quality(session, target_entities)
                report["data_quality_issues"] = quality_issues
                report["statistics"]["quality_issues_found"] = len(quality_issues)
                
                # Count entities after
                report["statistics"]["entities_after"] = session.execute(
                    select(func.count()).select_from(Entity)
                ).scalar()
                
        except Exception as e:
            self.logger.error(f"Reflect & refine failed: {e}", exc_info=True)
            report["error"] = str(e)
        
        report["completed_at"] = datetime.now().isoformat()
        return report
    
    def _find_duplicate_entities(
        self,
        session: Session,
        target_entities: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Find groups of potentially duplicate entities."""
        duplicate_groups = []
        
        # Get all entities or filter by target
        stmt = select(Entity)
        if target_entities:
            # Match any of the target names (case-insensitive partial match)
            conditions = [
                func.lower(Entity.name).like(f"%{name.lower()}%")
                for name in target_entities
            ]
            stmt = stmt.where(or_(*conditions))
        
        entities = session.execute(stmt).scalars().all()
        
        # Group by normalized name patterns
        name_groups = defaultdict(list)
        for entity in entities:
            # Create normalized key for grouping
            normalized = self._normalize_entity_name(entity.name)
            name_groups[normalized].append(entity)
        
        # Find groups with potential duplicates
        for normalized_name, group_entities in name_groups.items():
            if len(group_entities) > 1:
                duplicate_groups.append({
                    "normalized_name": normalized_name,
                    "count": len(group_entities),
                    "entities": [
                        {
                            "id": str(e.id),
                            "name": e.name,
                            "kind": e.kind,
                            "relation_count": self._count_relations(session, str(e.id)),
                        }
                        for e in group_entities
                    ],
                })
        
        # Also use semantic similarity if LLM is available
        if self.llm and len(entities) > 1:
            semantic_dupes = self._find_semantic_duplicates(session, entities)
            for dupe in semantic_dupes:
                # Avoid duplicating groups already found
                existing_ids = set()
                for group in duplicate_groups:
                    for e in group["entities"]:
                        existing_ids.add(e["id"])
                
                new_entities = [e for e in dupe["entities"] if e["id"] not in existing_ids]
                if len(new_entities) >= 2:
                    duplicate_groups.append({
                        "normalized_name": f"semantic:{dupe['entities'][0]['name']}",
                        "count": len(new_entities),
                        "entities": new_entities,
                        "similarity_score": dupe.get("similarity_score", 0),
                    })
        
        return duplicate_groups
    
    def _normalize_entity_name(self, name: str) -> str:
        """Normalize entity name for duplicate detection."""
        if not name:
            return ""
        
        # Common company suffixes to remove
        suffixes = [
            "corporation", "corp", "inc", "incorporated", "llc", "ltd",
            "limited", "co", "company", "plc", "ag", "gmbh", "sa"
        ]
        
        normalized = name.lower().strip()
        
        # Remove common suffixes
        for suffix in suffixes:
            if normalized.endswith(f" {suffix}"):
                normalized = normalized[:-len(suffix) - 1]
            if normalized.endswith(f" {suffix}."):
                normalized = normalized[:-len(suffix) - 2]
        
        # Remove punctuation and extra whitespace
        import re
        normalized = re.sub(r'[^\w\s]', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    def _find_semantic_duplicates(
        self,
        session: Session,
        entities: List[Entity],
    ) -> List[Dict[str, Any]]:
        """Find semantically similar entities using embeddings."""
        duplicates = []
        
        # Get embeddings for all entity names
        embeddings = {}
        for entity in entities:
            vec = self.llm.embed_text(entity.name)
            if vec:
                embeddings[str(entity.id)] = (entity, vec)
        
        # Compare all pairs
        checked_pairs = set()
        for id1, (entity1, vec1) in embeddings.items():
            for id2, (entity2, vec2) in embeddings.items():
                if id1 >= id2:  # Skip self and already checked pairs
                    continue
                
                pair_key = tuple(sorted([id1, id2]))
                if pair_key in checked_pairs:
                    continue
                checked_pairs.add(pair_key)
                
                similarity = self.llm.calculate_similarity(vec1, vec2)
                if similarity >= self.entity_merge_threshold:
                    duplicates.append({
                        "similarity_score": similarity,
                        "entities": [
                            {
                                "id": id1,
                                "name": entity1.name,
                                "kind": entity1.kind,
                                "relation_count": self._count_relations(session, id1),
                            },
                            {
                                "id": id2,
                                "name": entity2.name,
                                "kind": entity2.kind,
                                "relation_count": self._count_relations(session, id2),
                            },
                        ],
                    })
        
        return duplicates
    
    def _count_relations(self, session: Session, entity_id: str) -> int:
        """Count relationships for an entity."""
        return session.execute(
            select(func.count()).select_from(Relationship).where(
                or_(
                    Relationship.source_id == entity_id,
                    Relationship.target_id == entity_id,
                )
            )
        ).scalar() or 0
    
    def _merge_entity_group(
        self,
        session: Session,
        group: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Merge a group of duplicate entities into one.
        
        Ensures:
        - The entity with the most specific kind is selected as primary
        - The richest data (most fields) is preserved
        - The longest name (most complete) is used
        - All data from secondary entities is merged into the primary
        - No entity information is lost during deduplication
        """
        entities = group.get("entities", [])
        if len(entities) < 2:
            return None
        
        # Select the primary entity using kind specificity, data richness, relation count, name length
        def entity_priority(e):
            kind = (e.get("kind") or "").lower()
            kind_rank = self._get_kind_specificity_rank(kind)
            data_count = e.get("data_count", 0)
            rel_count = e.get("relation_count", 0)
            name_len = len(e.get("name", "").strip())
            return (kind_rank, data_count, rel_count, name_len)
        
        # Enrich entities with data_count using a single batch query
        entity_ids = [e["id"] for e in entities]
        entity_objs = {
            str(obj.id): obj
            for obj in session.execute(
                select(Entity).where(Entity.id.in_(entity_ids))
            ).scalars().all()
        }
        for e in entities:
            obj = entity_objs.get(e["id"])
            e["data_count"] = len(obj.data) if obj and obj.data else 0
        
        sorted_entities = sorted(entities, key=entity_priority, reverse=True)
        
        primary_id = sorted_entities[0]["id"]
        secondary_ids = [e["id"] for e in sorted_entities[1:]]
        
        # Get actual entity objects
        primary_entity = session.get(Entity, primary_id)
        if not primary_entity:
            return None
        
        merged_count = 0
        for secondary_id in secondary_ids:
            secondary_entity = session.get(Entity, secondary_id)
            if not secondary_entity:
                continue
            
            # Upgrade kind if secondary has a more specific type
            secondary_kind = (secondary_entity.kind or "").lower()
            primary_kind = (primary_entity.kind or "").lower()
            if self._get_kind_specificity_rank(secondary_kind) > self._get_kind_specificity_rank(primary_kind):
                primary_entity.kind = secondary_kind
            
            # Pick the longest name (richest / most complete)
            if secondary_entity.name and primary_entity.name and len(secondary_entity.name.strip()) > len(primary_entity.name.strip()):
                primary_entity.name = secondary_entity.name.strip()
            
            # Merge data fields (secondary fills gaps in primary)
            if secondary_entity.data:
                if not primary_entity.data:
                    primary_entity.data = {}
                for key, value in secondary_entity.data.items():
                    if value and (key not in primary_entity.data or not primary_entity.data.get(key)):
                        primary_entity.data[key] = value
            
            # Merge metadata
            if secondary_entity.metadata_json:
                if not primary_entity.metadata_json:
                    primary_entity.metadata_json = {}
                for key, value in secondary_entity.metadata_json.items():
                    if key not in primary_entity.metadata_json and value:
                        primary_entity.metadata_json[key] = value
            
            # Update relationships to point to primary entity
            for rel in session.execute(
                select(Relationship).where(Relationship.source_id == secondary_id)
            ).scalars().all():
                rel.source_id = primary_id
            
            for rel in session.execute(
                select(Relationship).where(Relationship.target_id == secondary_id)
            ).scalars().all():
                rel.target_id = primary_id
            
            # Update intelligence references
            for intel in session.execute(
                select(Intelligence).where(Intelligence.entity_id == secondary_id)
            ).scalars().all():
                intel.entity_id = primary_id
            
            # Delete secondary entity
            session.delete(secondary_entity)
            merged_count += 1
        
        return {
            "primary_entity": {
                "id": primary_id,
                "name": primary_entity.name,
                "kind": primary_entity.kind,
            },
            "merged_count": merged_count,
            "merged_ids": secondary_ids,
        }
    
    def _validate_data_quality(
        self,
        session: Session,
        target_entities: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Validate data quality and find issues."""
        issues = []
        
        # Get entities to validate
        stmt = select(Entity)
        if target_entities:
            conditions = [
                func.lower(Entity.name).like(f"%{name.lower()}%")
                for name in target_entities
            ]
            stmt = stmt.where(or_(*conditions))
        
        entities = session.execute(stmt).scalars().all()
        
        for entity in entities:
            entity_issues = []
            
            # Check for missing name
            if not entity.name or not entity.name.strip():
                entity_issues.append("Missing or empty name")
            
            # Check for missing kind/type
            if not entity.kind:
                entity_issues.append("Missing entity kind/type")
            
            # Check for orphan entities (no relationships)
            rel_count = self._count_relations(session, str(entity.id))
            if rel_count == 0:
                entity_issues.append("Orphan entity (no relationships)")
            
            if entity_issues:
                issues.append({
                    "entity_id": str(entity.id),
                    "entity_name": entity.name,
                    "issues": entity_issues,
                })
        
        return issues
    
    def _get_kind_specificity_rank(self, kind: str) -> int:
        """Return a numeric rank for entity kind specificity.
        
        Higher rank means more specific:
        - 0: generic types (entity, general, empty)
        - 1: parent types (person, address, company, organization)
        - 2: specialized child types (ceo, founder, headquarters, etc.)
        """
        kind = (kind or "").lower().strip()
        if kind in ("", "entity", "general"):
            return 0
        if kind in ENTITY_TYPE_HIERARCHY:
            return 2  # child/specialized types
        if kind in ENTITY_TYPE_CHILDREN:
            return 1  # parent types
        return 1  # any other concrete type
    
    # =========================================================================
    # MODE 2: EXPLORE & PRIORITIZE
    # =========================================================================
    
    def explore_and_prioritize(
        self,
        root_entities: List[str],
        max_depth: Optional[int] = None,
        top_n: int = 20,
    ) -> Dict[str, Any]:
        """
        Explore entity graph and prioritize entities for further research.
        
        This mode:
        1. Starts from root entities (e.g., "Microsoft Corporation")
        2. Traverses relations to find connected entities (e.g., "Bill Gates")
        3. Calculates priority scores based on:
           - Number of relations (more relations = more important)
           - Unknown depth (less known entities = higher priority)
        4. Returns prioritized list of entities to explore
        
        Args:
            root_entities: Starting entity names for exploration
            max_depth: Maximum relation depth to explore
            top_n: Number of top-priority entities to return
            
        Returns:
            Exploration report with prioritized entities
        """
        if max_depth is None:
            max_depth = self.max_exploration_depth
        
        self.logger.info(f"Starting explore & prioritize mode with {len(root_entities)} root entities")
        
        report = {
            "mode": "explore_and_prioritize",
            "started_at": datetime.now().isoformat(),
            "root_entities": root_entities,
            "max_depth": max_depth,
            "exploration_tree": {},
            "prioritized_entities": [],
            "statistics": {
                "total_entities_found": 0,
                "unique_entities": 0,
                "max_depth_reached": 0,
                "relations_traversed": 0,
            },
        }
        
        try:
            with self.store.Session() as session:
                # Step 1: Find root entity IDs
                root_entity_ids = []
                root_entity_map = {}
                
                for name in root_entities:
                    entity = session.execute(
                        select(Entity).where(
                            func.lower(Entity.name).like(f"%{name.lower()}%")
                        )
                    ).scalar()
                    
                    if entity:
                        root_entity_ids.append(str(entity.id))
                        root_entity_map[str(entity.id)] = {
                            "name": entity.name,
                            "kind": entity.kind,
                        }
                
                if not root_entity_ids:
                    report["error"] = "No matching root entities found"
                    return report
                
                # Step 2: Traverse graph from root entities
                all_entities: Dict[str, Dict[str, Any]] = {}  # id -> entity info
                depth_map: Dict[str, int] = {}  # id -> min depth from root
                relation_counts: Dict[str, int] = defaultdict(int)  # id -> relation count
                
                # Initialize with root entities
                for entity_id in root_entity_ids:
                    all_entities[entity_id] = root_entity_map[entity_id]
                    depth_map[entity_id] = 0
                
                current_level = set(root_entity_ids)
                
                for depth in range(1, max_depth + 1):
                    next_level = set()
                    
                    for entity_id in current_level:
                        # Find all related entities
                        related = self._get_related_entities(session, entity_id)
                        
                        for rel_entity_id, rel_info in related.items():
                            report["statistics"]["relations_traversed"] += 1
                            relation_counts[rel_entity_id] += 1
                            
                            if rel_entity_id not in all_entities:
                                all_entities[rel_entity_id] = rel_info
                                depth_map[rel_entity_id] = depth
                                next_level.add(rel_entity_id)
                                report["statistics"]["max_depth_reached"] = max(
                                    report["statistics"]["max_depth_reached"], depth
                                )
                    
                    current_level = next_level
                    if not current_level:
                        break
                
                report["statistics"]["unique_entities"] = len(all_entities)
                
                # Step 3: Calculate priority scores
                prioritized = []
                for entity_id, entity_info in all_entities.items():
                    if entity_id in root_entity_ids:
                        continue  # Skip root entities
                    
                    depth = depth_map.get(entity_id, max_depth)
                    rel_count = relation_counts.get(entity_id, 0)
                    
                    # Calculate priority:
                    # - Higher priority for deeper entities (less known)
                    # - Higher priority for entities with many relations (more important)
                    unknown_score = depth / max_depth  # Normalized 0-1
                    
                    # Get total relation count for this entity
                    total_relations = self._count_relations(session, entity_id)
                    relation_score = min(total_relations / 10.0, 1.0)  # Cap at 10 relations
                    
                    priority_score = (
                        self.priority_unknown_weight * unknown_score +
                        self.priority_relation_weight * relation_score
                    )
                    
                    prioritized.append({
                        "entity_id": entity_id,
                        "name": entity_info.get("name"),
                        "kind": entity_info.get("kind"),
                        "depth_from_root": depth,
                        "relation_count": total_relations,
                        "references_from_root": rel_count,
                        "priority_score": round(priority_score, 3),
                    })
                
                # Sort by priority score descending
                prioritized.sort(key=lambda x: x["priority_score"], reverse=True)
                report["prioritized_entities"] = prioritized[:top_n]
                report["statistics"]["total_entities_found"] = len(prioritized)
                
                # Build exploration tree for visualization
                report["exploration_tree"] = self._build_exploration_tree(
                    root_entity_ids, all_entities, depth_map
                )
                
        except Exception as e:
            self.logger.error(f"Explore & prioritize failed: {e}", exc_info=True)
            report["error"] = str(e)
        
        report["completed_at"] = datetime.now().isoformat()
        return report
    
    def _get_related_entities(
        self,
        session: Session,
        entity_id: str,
    ) -> Dict[str, Dict[str, Any]]:
        """Get all entities related to the given entity."""
        related = {}
        
        # Get entities where this is the source
        for rel in session.execute(
            select(Relationship).where(Relationship.source_id == entity_id)
        ).scalars().all():
            target = session.get(Entity, rel.target_id)
            if target:
                related[str(target.id)] = {
                    "name": target.name,
                    "kind": target.kind,
                    "relation_type": rel.relation_type,
                    "direction": "outgoing",
                }
        
        # Get entities where this is the target
        for rel in session.execute(
            select(Relationship).where(Relationship.target_id == entity_id)
        ).scalars().all():
            source = session.get(Entity, rel.source_id)
            if source and str(source.id) not in related:
                related[str(source.id)] = {
                    "name": source.name,
                    "kind": source.kind,
                    "relation_type": rel.relation_type,
                    "direction": "incoming",
                }
        
        return related
    
    def _build_exploration_tree(
        self,
        root_ids: List[str],
        all_entities: Dict[str, Dict[str, Any]],
        depth_map: Dict[str, int],
    ) -> Dict[str, Any]:
        """Build a tree structure for visualization."""
        tree = {
            "roots": [],
            "depths": defaultdict(list),
        }
        
        for entity_id, entity_info in all_entities.items():
            depth = depth_map.get(entity_id, 0)
            node = {
                "id": entity_id,
                "name": entity_info.get("name"),
                "kind": entity_info.get("kind"),
            }
            
            if entity_id in root_ids:
                tree["roots"].append(node)
            else:
                tree["depths"][depth].append(node)
        
        # Convert defaultdict to regular dict for JSON serialization
        tree["depths"] = dict(tree["depths"])
        return tree
    
    # =========================================================================
    # MODE 3: MULTIDIMENSIONAL RAG SEARCH
    # =========================================================================
    
    def multidimensional_search(
        self,
        query: str,
        top_k: int = 10,
        include_graph: bool = True,
        graph_depth: int = 2,
    ) -> Dict[str, Any]:
        """
        Multidimensional RAG search combining embedding and graph-based search.
        
        This search method:
        1. Performs traditional RAG embedding search
        2. Extracts entities from query and traverses their graph relations
        3. Combines and ranks results from both methods
        
        Args:
            query: Search query string
            top_k: Number of top results to return
            include_graph: Whether to include graph traversal results
            graph_depth: Depth for graph traversal
            
        Returns:
            Combined search results with source information
        """
        self.logger.info(f"Multidimensional search: {query[:50]}...")
        
        result = {
            "query": query,
            "embedding_results": [],
            "graph_results": [],
            "combined_results": [],
            "statistics": {
                "embedding_hits": 0,
                "graph_hits": 0,
                "unique_results": 0,
            },
        }
        
        try:
            # Step 1: Embedding-based RAG search
            if self.vector_store and self.llm:
                vec = self.llm.embed_text(query)
                if vec:
                    try:
                        vector_results = self.vector_store.search(vec, top_k=top_k * 2)
                        for r in vector_results:
                            result["embedding_results"].append({
                                "source": "embedding",
                                "score": r.score,
                                "url": r.payload.get("url"),
                                "text": r.payload.get("text"),
                                "entity": r.payload.get("entity"),
                                "kind": r.payload.get("kind"),
                                "page_id": r.payload.get("page_id"),
                                "entity_id": r.payload.get("entity_id"),
                            })
                        result["statistics"]["embedding_hits"] = len(result["embedding_results"])
                    except Exception as e:
                        self.logger.warning(f"Embedding search failed: {e}")
            
            # Step 2: Graph-based search (entity traversal)
            if include_graph:
                graph_results = self._graph_based_search(query, graph_depth, top_k)
                result["graph_results"] = graph_results
                result["statistics"]["graph_hits"] = len(graph_results)
            
            # Step 3: Combine and deduplicate results
            combined = self._combine_search_results(
                result["embedding_results"],
                result["graph_results"],
                top_k
            )
            result["combined_results"] = combined
            result["statistics"]["unique_results"] = len(combined)
            
        except Exception as e:
            self.logger.error(f"Multidimensional search failed: {e}", exc_info=True)
            result["error"] = str(e)
        
        return result
    
    def _graph_based_search(
        self,
        query: str,
        depth: int,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Search by traversing entity graph from query-mentioned entities."""
        results = []
        
        try:
            with self.store.Session() as session:
                # Extract entity candidates from query
                # Use simple word matching to find entities
                query_words = set(query.lower().split())
                
                # Find entities that match words in query
                matching_entities = []
                for word in query_words:
                    if len(word) > 2:  # Skip short words
                        entities = session.execute(
                            select(Entity).where(
                                func.lower(Entity.name).like(f"%{word}%")
                            ).limit(5)
                        ).scalars().all()
                        matching_entities.extend(entities)
                
                # Deduplicate
                seen_ids = set()
                unique_entities = []
                for e in matching_entities:
                    if str(e.id) not in seen_ids:
                        seen_ids.add(str(e.id))
                        unique_entities.append(e)
                
                # Traverse relations for each matched entity
                all_related_ids = set()
                for entity in unique_entities[:3]:  # Limit starting points
                    related = self._traverse_relations(session, str(entity.id), depth)
                    all_related_ids.update(related)
                
                # Get intelligence and page data for related entities
                for entity_id in list(all_related_ids)[:limit]:
                    entity = session.get(Entity, entity_id)
                    if not entity:
                        continue
                    
                    # Get related intelligence
                    intel = session.execute(
                        select(Intelligence).where(Intelligence.entity_id == entity_id).limit(1)
                    ).scalar()
                    
                    result_item = {
                        "source": "graph",
                        "score": 0.5,  # Base score for graph results
                        "entity": entity.name if entity.name else "",
                        "entity_id": entity_id,
                        "kind": entity.kind if entity.kind else "unknown",
                        "text": "",
                        "url": "",
                    }
                    
                    if intel and intel.data:
                        # Convert nested data structures to readable JSON format
                        try:
                            if isinstance(intel.data, (dict, list)):
                                result_item["text"] = json.dumps(intel.data, ensure_ascii=False, separators=(',', ':'))[:500]
                            else:
                                result_item["text"] = str(intel.data)[:500]
                        except (TypeError, ValueError):
                            # Fallback to string conversion if JSON serialization fails
                            result_item["text"] = str(intel.data)[:500]
                        
                        if intel.page_id:
                            page = session.get(Page, intel.page_id)
                            if page and page.url:
                                result_item["url"] = page.url
                    
                    results.append(result_item)
                    
        except Exception as e:
            self.logger.warning(f"Graph search failed: {e}")
        
        return results
    
    def _traverse_relations(
        self,
        session: Session,
        entity_id: str,
        max_depth: int,
    ) -> Set[str]:
        """Traverse relations from entity up to max_depth."""
        visited = set()
        current_level = {entity_id}
        
        for _ in range(max_depth):
            next_level = set()
            for eid in current_level:
                if eid in visited:
                    continue
                visited.add(eid)
                
                # Get related entities
                for rel in session.execute(
                    select(Relationship).where(
                        or_(
                            Relationship.source_id == eid,
                            Relationship.target_id == eid,
                        )
                    )
                ).scalars().all():
                    related_id = rel.target_id if rel.source_id == eid else rel.source_id
                    if related_id not in visited:
                        next_level.add(str(related_id))
            
            current_level = next_level
            if not current_level:
                break
        
        return visited
    
    def _combine_search_results(
        self,
        embedding_results: List[Dict[str, Any]],
        graph_results: List[Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Combine and deduplicate results from different sources.
        
        Merges embedding and graph results, deduplicating by URL/entity_id/text,
        and combining scores for items found in multiple sources.
        """
        combined = {}
        
        # Add embedding results with boost
        for r in embedding_results:
            # Create a unique key for deduplication
            key = r.get("url") or r.get("entity_id") or r.get("text", "")[:50]
            if key:
                # Create a clean copy to avoid modifying original
                result_copy = {
                    "source": r.get("source", "embedding"),
                    "score": r.get("score", 0),
                    "url": r.get("url", ""),
                    "text": r.get("text", ""),
                    "entity": r.get("entity", ""),
                    "kind": r.get("kind", ""),
                    "page_id": r.get("page_id", ""),
                    "entity_id": r.get("entity_id", ""),
                }
                combined[key] = result_copy
                combined[key]["combined_score"] = result_copy["score"] * 1.2  # Boost embedding results
                combined[key]["source_types"] = "embedding"
        
        # Add graph results
        for r in graph_results:
            key = r.get("url") or r.get("entity_id") or r.get("text", "")[:50]
            if key:
                if key in combined:
                    # Merge scores if already exists
                    combined[key]["combined_score"] += r.get("score", 0)
                    combined[key]["source_types"] = "embedding+graph"
                else:
                    # Create a clean copy
                    result_copy = {
                        "source": r.get("source", "graph"),
                        "score": r.get("score", 0),
                        "url": r.get("url", ""),
                        "text": r.get("text", ""),
                        "entity": r.get("entity", ""),
                        "kind": r.get("kind", ""),
                        "page_id": r.get("page_id", ""),
                        "entity_id": r.get("entity_id", ""),
                    }
                    combined[key] = result_copy
                    combined[key]["combined_score"] = result_copy["score"]
                    combined[key]["source_types"] = "graph"
        
        # Sort by combined score
        sorted_results = sorted(
            combined.values(),
            key=lambda x: x.get("combined_score", 0),
            reverse=True
        )
        
        return sorted_results[:limit]
    
    # =========================================================================
    # ASYNC CHAT RESPONSE
    # =========================================================================
    
    async def chat_async(
        self,
        question: str,
        entity: Optional[str] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """
        Async chat response with agent capabilities.
        
        Always uses deep RAG search (embedding + graph) automatically.
        Reflect insights are included as supplementary metadata.
        
        Args:
            question: User question
            entity: Optional entity context
            stream: Whether to stream the response
            
        Returns:
            Chat response with relevant data
        """
        self.logger.info(f"Async chat: question={question[:50]}...")
        
        response = {
            "mode": "deep_rag",
            "question": question,
            "entity": entity,
            "answer": "",
            "context": [],
            "metadata": {},
        }
        
        try:
            # Always run deep RAG search (embedding + graph combined)
            search_result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.multidimensional_search(
                    query=question,
                    top_k=10,
                    include_graph=True
                )
            )
            response["context"] = search_result.get("combined_results", [])
            response["metadata"]["search_stats"] = search_result.get("statistics", {})
            
            # Synthesize answer from context
            if self.llm and response["context"]:
                answer = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.llm.synthesize_answer(question, response["context"])
                )
                response["answer"] = answer
            else:
                response["answer"] = "No relevant information found."
            
            # Automatically add reflect insights if entities are found
            entities_in_question = self._extract_entity_mentions(question)
            if entities_in_question:
                try:
                    reflect_result = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self.reflect_and_refine(
                            target_entities=entities_in_question,
                            dry_run=True
                        )
                    )
                    response["metadata"]["reflect_report"] = reflect_result
                except Exception as e:
                    self.logger.debug(f"Reflect insights failed: {e}")
                    
        except Exception as e:
            self.logger.error(f"Async chat failed: {e}", exc_info=True)
            response["error"] = str(e)
            response["answer"] = f"Error processing request: {str(e)}"
        
        return response
    
    def _extract_entity_mentions(self, text: str) -> List[str]:
        """Extract potential entity mentions from text."""
        # Simple extraction: look for capitalized phrases
        import re
        
        # Find capitalized words/phrases
        pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b'
        matches = re.findall(pattern, text)
        
        # Filter common words that shouldn't be entities
        stop_words = {"I", "The", "This", "What", "Who", "When", "Where", "How", "Why"}
        entities = [m for m in matches if m not in stop_words and len(m) > 2]
        
        return list(set(entities))
    
    def _summarize_reflect_report(self, report: Dict[str, Any]) -> str:
        """Summarize reflection report into readable answer."""
        duplicates = report.get("duplicates_found", [])
        issues = report.get("data_quality_issues", [])
        
        parts = []
        if duplicates:
            parts.append(f"Found {len(duplicates)} potential duplicate entity groups that could be merged.")
        if issues:
            parts.append(f"Found {len(issues)} data quality issues to address.")
        
        if not parts:
            parts.append("Data looks clean - no duplicates or quality issues found.")
        
        return " ".join(parts)
    
    def _summarize_explore_report(self, report: Dict[str, Any]) -> str:
        """Summarize exploration report into readable answer."""
        prioritized = report.get("prioritized_entities", [])
        stats = report.get("statistics", {})
        
        if not prioritized:
            return "No related entities found to explore."
        
        top_entities = ", ".join([e["name"] for e in prioritized[:5]])
        return (
            f"Found {stats.get('unique_entities', 0)} related entities. "
            f"Top priorities for exploration: {top_entities}"
        )

    # =========================================================================
    # MODE 4: AUTONOMOUS EXPLORATION
    # =========================================================================

    def autonomous_discover(
        self,
        max_entities: int = 10,
        priority_threshold: float = 0.3,
        max_depth: int = 3,
        auto_crawl: bool = False,
        max_pages: int = 25,
    ) -> Dict[str, Any]:
        """
        Autonomous discovery mode.

        Identifies dead-end entities and knowledge gaps, then generates
        targeted crawl plans to fill those gaps.

        Flow:
        1. Find dead-end entities (few outgoing relationships)
        2. Find entities with incomplete data (knowledge gaps)
        3. Use explore_and_prioritize to rank candidates
        4. Generate crawl queries for top candidates
        5. Optionally trigger crawls automatically

        Args:
            max_entities: Maximum entities to process per cycle
            priority_threshold: Minimum priority score to include
            max_depth: Max graph traversal depth
            auto_crawl: Whether to actually execute crawls
            max_pages: Max pages per entity crawl

        Returns:
            Discovery report with dead-ends, gaps, crawl plans, and results
        """
        self.logger.info("Starting autonomous discovery cycle")

        report: Dict[str, Any] = {
            "mode": "autonomous_discover",
            "started_at": datetime.now().isoformat(),
            "dead_ends": [],
            "knowledge_gaps": [],
            "crawl_plans": [],
            "crawl_results": [],
            "statistics": {
                "dead_ends_found": 0,
                "gaps_found": 0,
                "crawl_plans_generated": 0,
                "crawls_executed": 0,
                "entities_analyzed": 0,
            },
        }

        try:
            with self.store.Session() as session:
                # Step 1: Find dead-end entities (few outgoing relations)
                dead_ends = self._find_dead_end_entities(session, max_entities * 2)
                report["dead_ends"] = dead_ends
                report["statistics"]["dead_ends_found"] = len(dead_ends)

                # Step 2: Find entities with knowledge gaps
                knowledge_gaps = self._find_knowledge_gaps(session, max_entities * 2)
                report["knowledge_gaps"] = knowledge_gaps
                report["statistics"]["gaps_found"] = len(knowledge_gaps)

                # Step 3: Build a combined candidate list
                candidate_names: List[str] = []
                seen: Set[str] = set()
                for de in dead_ends:
                    name = de.get("name", "")
                    if name and name not in seen:
                        candidate_names.append(name)
                        seen.add(name)
                for gap in knowledge_gaps:
                    name = gap.get("entity_name", "")
                    if name and name not in seen:
                        candidate_names.append(name)
                        seen.add(name)

                report["statistics"]["entities_analyzed"] = len(candidate_names)

                if not candidate_names:
                    report["message"] = "No dead-ends or knowledge gaps found"
                    report["completed_at"] = datetime.now().isoformat()
                    return report

                # Step 4: Run explore from dead-end entities to find prioritized targets
                explore_report = self.explore_and_prioritize(
                    root_entities=candidate_names[:max_entities],
                    max_depth=max_depth,
                    top_n=max_entities,
                )

                prioritized = explore_report.get("prioritized_entities", [])

                # Step 5: Generate crawl plans for high-priority entities
                from .entity_gap_analyzer import EntityGapAnalyzer
                gap_analyzer = EntityGapAnalyzer(self.store)

                for entity_info in prioritized:
                    if entity_info.get("priority_score", 0) < priority_threshold:
                        continue

                    entity_name = entity_info.get("name", "")
                    entity_kind = entity_info.get("kind")
                    if not entity_name:
                        continue

                    plan = gap_analyzer.generate_crawl_plan(entity_name, entity_kind)
                    plan["priority_score"] = entity_info.get("priority_score", 0)
                    plan["relation_count"] = entity_info.get("relation_count", 0)
                    plan["depth_from_root"] = entity_info.get("depth_from_root", 0)
                    report["crawl_plans"].append(plan)
                    report["statistics"]["crawl_plans_generated"] += 1

                # Step 6: Optionally execute crawls
                if auto_crawl and report["crawl_plans"]:
                    for plan in report["crawl_plans"][:max_entities]:
                        crawl_result = self._execute_autonomous_crawl(
                            plan, max_pages=max_pages
                        )
                        if crawl_result:
                            report["crawl_results"].append(crawl_result)
                            report["statistics"]["crawls_executed"] += 1

        except Exception as e:
            self.logger.error(f"Autonomous discovery failed: {e}", exc_info=True)
            report["error"] = str(e)

        report["completed_at"] = datetime.now().isoformat()
        return report

    def _find_dead_end_entities(
        self, session: Session, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Find entities with few or no outgoing relationships (dead-ends)."""
        dead_ends = []

        # Get entities and their outgoing relation counts
        stmt = (
            select(
                Entity.id,
                Entity.name,
                Entity.kind,
                func.count(Relationship.id).label("outgoing_count"),
            )
            .outerjoin(Relationship, Relationship.source_id == Entity.id)
            .group_by(Entity.id, Entity.name, Entity.kind)
            .order_by(func.count(Relationship.id).asc())
            .limit(limit)
        )

        for row in session.execute(stmt).all():
            entity_id, name, kind, outgoing_count = row
            # Also get incoming count for context
            incoming_count = (
                session.execute(
                    select(func.count()).select_from(Relationship).where(
                        Relationship.target_id == str(entity_id)
                    )
                ).scalar()
                or 0
            )

            dead_ends.append({
                "entity_id": str(entity_id),
                "name": name,
                "kind": kind,
                "outgoing_relations": outgoing_count,
                "incoming_relations": incoming_count,
                "total_relations": outgoing_count + incoming_count,
                "is_dead_end": outgoing_count == 0,
            })

        return dead_ends

    def _find_knowledge_gaps(
        self, session: Session, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Find entities with missing or incomplete data."""
        gaps = []

        entities = (
            session.execute(
                select(Entity).order_by(Entity.updated_at.asc()).limit(limit)
            )
            .scalars()
            .all()
        )

        for entity in entities:
            # Count intelligence records for this entity
            intel_count = (
                session.execute(
                    select(func.count())
                    .select_from(Intelligence)
                    .where(Intelligence.entity_id == str(entity.id))
                ).scalar()
                or 0
            )

            # Check for missing critical fields
            missing_fields = []
            if not entity.kind:
                missing_fields.append("kind")
            data = entity.data or {}
            meta = entity.metadata_json or {}
            combined = {**data, **meta}

            if not combined.get("description") and not combined.get("bio"):
                missing_fields.append("description")
            if not combined.get("website") and not combined.get("url"):
                missing_fields.append("website")

            if missing_fields or intel_count == 0:
                gaps.append({
                    "entity_id": str(entity.id),
                    "entity_name": entity.name,
                    "entity_kind": entity.kind,
                    "intelligence_count": intel_count,
                    "missing_fields": missing_fields,
                    "gap_score": len(missing_fields) + (1 if intel_count == 0 else 0),
                })

        # Sort by gap_score descending (most gaps first)
        gaps.sort(key=lambda x: x["gap_score"], reverse=True)
        return gaps[:limit]

    def _execute_autonomous_crawl(
        self, plan: Dict[str, Any], max_pages: int = 25
    ) -> Optional[Dict[str, Any]]:
        """Execute a crawl from an autonomous plan."""
        entity_name = plan.get("entity_name", "")
        if not entity_name:
            return None

        try:
            from .adaptive_crawler import AdaptiveCrawlerService
            from ..discover.crawl_learner import CrawlLearner

            crawl_learner = CrawlLearner(store=self.store)
            crawler = AdaptiveCrawlerService(
                store=self.store,
                llm=self.llm,
                crawl_learner=crawl_learner,
                vector_store=self.vector_store,
            )

            result = crawler.intelligent_crawl(
                entity_name=entity_name,
                entity_type=plan.get("entity_type"),
                max_pages=max_pages,
                max_depth=2,
            )

            return {
                "entity_name": entity_name,
                "plan_mode": plan.get("mode", "unknown"),
                "result": result,
            }
        except Exception as e:
            self.logger.warning(f"Autonomous crawl failed for '{entity_name}': {e}")
            return {
                "entity_name": entity_name,
                "error": str(e),
            }

    # =========================================================================
    # REFINED AUTONOMOUS MODES
    # =========================================================================

    def reflect_relate(
        self,
        target_entities: Optional[List[str]] = None,
        max_depth: int = 2,
        top_n: int = 20,
    ) -> Dict[str, Any]:
        """
        Reflect & Relate mode: Find indirect connections and create investigation tasks.
        
        This mode:
        1. Runs reflect_and_refine to get current data quality
        2. Analyzes entity graph to find indirect connections
        3. Suggests potential relations based on shared neighbors
        4. Creates investigation tasks for gaps and potential relations
        
        Args:
            target_entities: Optional list of entity names to focus on
            max_depth: Maximum depth for graph traversal
            top_n: Maximum number of potential relations to suggest
            
        Returns:
            Report with reflection results, potential relations, and investigation tasks
        """
        # Create process entry
        self._process_counter += 1
        process_id = f"reflect_relate_{self._process_counter}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        self._running_processes[process_id] = {
            "process_id": process_id,
            "action": "reflect_relate",
            "status": "running",
            "started_at": datetime.now().isoformat(),
        }
        
        self.logger.info(f"Starting reflect & relate mode (process {process_id})")
        
        report: Dict[str, Any] = {
            "mode": "reflect_relate",
            "process_id": process_id,
            "started_at": datetime.now().isoformat(),
            "reflect_report": {},
            "potential_relations": [],
            "investigation_tasks": [],
            "statistics": {
                "entities_analyzed": 0,
                "potential_relations_found": 0,
                "investigation_tasks_created": 0,
            },
        }
        
        try:
            # Step 1: Run reflect and refine to get current data quality
            reflect_result = self.reflect_and_refine(
                target_entities=target_entities,
                dry_run=True,
            )
            report["reflect_report"] = reflect_result
            
            # Check for stop request
            if self._running_processes.get(process_id, {}).get("status") == "stopping":
                report["status"] = "stopped"
                self._running_processes[process_id]["status"] = "stopped"
                self._running_processes[process_id]["completed_at"] = datetime.now().isoformat()
                return report
            
            with self.store.Session() as session:
                # Step 2: Get entities to analyze
                if target_entities:
                    entities_query = select(Entity).where(Entity.name.in_(target_entities))
                else:
                    entities_query = select(Entity).limit(100)
                
                entities = list(session.execute(entities_query).scalars().all())
                report["statistics"]["entities_analyzed"] = len(entities)
                
                # Step 3: Find indirect connections
                entity_neighbors: Dict[str, Set[str]] = {}
                entity_map: Dict[str, Entity] = {}
                
                for entity in entities:
                    entity_id = str(entity.id)
                    entity_map[entity_id] = entity
                    related = self._get_related_entities(session, entity_id)
                    entity_neighbors[entity_id] = set(related.keys())
                
                # Check for stop request
                if self._running_processes.get(process_id, {}).get("status") == "stopping":
                    report["status"] = "stopped"
                    self._running_processes[process_id]["status"] = "stopped"
                    self._running_processes[process_id]["completed_at"] = datetime.now().isoformat()
                    return report
                
                # Step 4: Find potential indirect relations
                potential_relations = []
                seen_pairs = set()
                
                for entity_id_a, neighbors_a in entity_neighbors.items():
                    for entity_id_b, neighbors_b in entity_neighbors.items():
                        if entity_id_a >= entity_id_b:  # Skip self and duplicates
                            continue
                        
                        pair_key = (entity_id_a, entity_id_b)
                        if pair_key in seen_pairs:
                            continue
                        seen_pairs.add(pair_key)
                        
                        # Check if they're NOT directly connected
                        if entity_id_b not in neighbors_a and entity_id_a not in neighbors_b:
                            # Find shared neighbors
                            shared = neighbors_a & neighbors_b
                            if len(shared) >= 1:  # At least one shared neighbor
                                entity_a = entity_map[entity_id_a]
                                entity_b = entity_map[entity_id_b]
                                
                                # Calculate confidence based on shared neighbor count
                                confidence = min(0.95, 0.3 + (len(shared) * 0.15))
                                
                                potential_relations.append({
                                    "entity_a": entity_a.name,
                                    "entity_a_kind": entity_a.kind,
                                    "entity_b": entity_b.name,
                                    "entity_b_kind": entity_b.kind,
                                    "shared_neighbors": len(shared),
                                    "confidence": confidence,
                                    "reason": f"Share {len(shared)} common connection(s)",
                                })
                
                # Sort by confidence and take top N
                potential_relations.sort(key=lambda x: x["confidence"], reverse=True)
                potential_relations = potential_relations[:top_n]
                report["potential_relations"] = potential_relations
                report["statistics"]["potential_relations_found"] = len(potential_relations)
                
                # Check for stop request
                if self._running_processes.get(process_id, {}).get("status") == "stopping":
                    report["status"] = "stopped"
                    self._running_processes[process_id]["status"] = "stopped"
                    self._running_processes[process_id]["completed_at"] = datetime.now().isoformat()
                    return report
                
                # Step 5: Create investigation tasks
                investigation_tasks = []
                
                # Tasks from potential relations
                for pr in potential_relations:
                    investigation_tasks.append({
                        "task_type": "investigate_relation",
                        "entity_name": pr["entity_a"],
                        "related_to": pr["entity_b"],
                        "reason": pr["reason"],
                        "priority": pr["confidence"],
                    })
                
                # Tasks from knowledge gaps (from reflect report)
                merge_candidates = reflect_result.get("merge_candidates", [])
                for candidate in merge_candidates[:10]:  # Top 10 merge candidates
                    investigation_tasks.append({
                        "task_type": "verify_connection",
                        "entity_name": candidate.get("entity_1", ""),
                        "related_to": candidate.get("entity_2", ""),
                        "reason": f"Potential duplicate (similarity: {candidate.get('similarity', 0):.2f})",
                        "priority": candidate.get("similarity", 0.5),
                    })
                
                # Tasks from data quality issues
                quality_report = reflect_result.get("quality_report", {})
                entities_missing_kind = quality_report.get("entities_missing_kind", 0)
                entities_missing_data = quality_report.get("entities_missing_data", 0)
                
                if entities_missing_kind > 0 or entities_missing_data > 0:
                    # Get some entities with missing data
                    missing_data_query = select(Entity).where(
                        or_(Entity.kind.is_(None), Entity.data.is_(None))
                    ).limit(5)
                    missing_entities = list(session.execute(missing_data_query).scalars().all())
                    
                    for entity in missing_entities:
                        investigation_tasks.append({
                            "task_type": "fill_gap",
                            "entity_name": entity.name,
                            "related_to": None,
                            "reason": f"Missing {'kind' if not entity.kind else 'data'}",
                            "priority": 0.6,
                        })
                
                report["investigation_tasks"] = investigation_tasks
                report["statistics"]["investigation_tasks_created"] = len(investigation_tasks)
            
            report["completed_at"] = datetime.now().isoformat()
            self._running_processes[process_id]["status"] = "completed"
            self._running_processes[process_id]["completed_at"] = datetime.now().isoformat()
            
        except Exception as e:
            self.logger.exception(f"Reflect & relate failed: {e}")
            report["error"] = str(e)
            report["status"] = "failed"
            self._running_processes[process_id]["status"] = "failed"
            self._running_processes[process_id]["error"] = str(e)
            self._running_processes[process_id]["completed_at"] = datetime.now().isoformat()
        
        return report

    def investigate_crawl(
        self,
        investigation_tasks: Optional[List[Dict[str, Any]]] = None,
        max_entities: int = 10,
        max_pages: int = 25,
        max_depth: int = 3,
        priority_threshold: float = 0.3,
    ) -> Dict[str, Any]:
        """
        Investigate Crawl mode: Execute crawls based on investigation tasks.
        
        This mode:
        1. Takes investigation tasks (or generates them via reflect_relate)
        2. Filters tasks by priority threshold
        3. Generates crawl plans for each task
        4. Executes crawls to gather missing information
        
        Args:
            investigation_tasks: List of investigation task dicts (or None to auto-generate)
            max_entities: Maximum number of entities to crawl
            max_pages: Maximum pages per entity crawl
            max_depth: Maximum crawl depth
            priority_threshold: Minimum task priority to process
            
        Returns:
            Report with crawl plans and results
        """
        # Create process entry
        self._process_counter += 1
        process_id = f"investigate_crawl_{self._process_counter}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        self._running_processes[process_id] = {
            "process_id": process_id,
            "action": "investigate_crawl",
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "tasks_total": 0,
            "tasks_completed": 0,
        }
        
        self.logger.info(f"Starting investigate crawl mode (process {process_id})")
        
        report: Dict[str, Any] = {
            "mode": "investigate_crawl",
            "process_id": process_id,
            "started_at": datetime.now().isoformat(),
            "investigation_tasks_used": [],
            "crawl_plans": [],
            "crawl_results": [],
            "statistics": {
                "tasks_received": 0,
                "tasks_processed": 0,
                "crawl_plans_generated": 0,
                "crawls_executed": 0,
                "pages_discovered": 0,
            },
        }
        
        try:
            # Step 1: Get investigation tasks
            if investigation_tasks is None:
                self.logger.info("No investigation tasks provided, generating via reflect_relate...")
                reflect_result = self.reflect_relate()
                investigation_tasks = reflect_result.get("investigation_tasks", [])
            
            report["statistics"]["tasks_received"] = len(investigation_tasks)
            
            # Check for stop request
            if self._running_processes.get(process_id, {}).get("status") == "stopping":
                report["status"] = "stopped"
                self._running_processes[process_id]["status"] = "stopped"
                self._running_processes[process_id]["completed_at"] = datetime.now().isoformat()
                return report
            
            # Step 2: Filter tasks by priority threshold
            filtered_tasks = [
                task for task in investigation_tasks
                if task.get("priority", 0) >= priority_threshold
            ]
            filtered_tasks.sort(key=lambda x: x.get("priority", 0), reverse=True)
            filtered_tasks = filtered_tasks[:max_entities]
            
            report["investigation_tasks_used"] = filtered_tasks
            self._running_processes[process_id]["tasks_total"] = len(filtered_tasks)
            
            # Step 3: Generate crawl plans
            from .entity_gap_analyzer import EntityGapAnalyzer
            
            gap_analyzer = EntityGapAnalyzer(self.store)
            crawl_plans = []
            
            for task in filtered_tasks:
                entity_name = task.get("entity_name", "")
                if not entity_name:
                    continue
                
                # Check for stop request
                if self._running_processes.get(process_id, {}).get("status") == "stopping":
                    report["status"] = "stopped"
                    break
                
                # Get entity from DB
                with self.store.Session() as session:
                    entity = session.execute(
                        select(Entity).where(Entity.name == entity_name)
                    ).scalar_one_or_none()
                    
                    if entity:
                        plan = gap_analyzer.generate_crawl_plan(
                            entity=entity,
                            task_type=task.get("task_type", "fill_gap"),
                            context=task.get("reason", ""),
                        )
                        if plan:
                            plan["investigation_task"] = task
                            crawl_plans.append(plan)
            
            report["crawl_plans"] = crawl_plans
            report["statistics"]["crawl_plans_generated"] = len(crawl_plans)
            
            # Check for stop request
            if self._running_processes.get(process_id, {}).get("status") == "stopping":
                report["status"] = "stopped"
                self._running_processes[process_id]["status"] = "stopped"
                self._running_processes[process_id]["completed_at"] = datetime.now().isoformat()
                return report
            
            # Step 4: Execute crawls
            crawl_results = []
            for idx, plan in enumerate(crawl_plans):
                # Check for stop request
                if self._running_processes.get(process_id, {}).get("status") == "stopping":
                    report["status"] = "stopped"
                    break
                
                self._running_processes[process_id]["current_task"] = plan.get("entity_name", "")
                self._running_processes[process_id]["tasks_completed"] = idx
                
                result = self._execute_autonomous_crawl(plan, max_pages=max_pages)
                if result:
                    crawl_results.append(result)
                    
                    # Count pages discovered
                    crawl_result = result.get("result", {})
                    if isinstance(crawl_result, dict):
                        pages = crawl_result.get("pages_crawled", 0)
                        report["statistics"]["pages_discovered"] += pages
                
                self._running_processes[process_id]["tasks_completed"] = idx + 1
            
            report["crawl_results"] = crawl_results
            report["statistics"]["tasks_processed"] = len(filtered_tasks)
            report["statistics"]["crawls_executed"] = len(crawl_results)
            
            report["completed_at"] = datetime.now().isoformat()
            self._running_processes[process_id]["status"] = "completed"
            self._running_processes[process_id]["completed_at"] = datetime.now().isoformat()
            
        except Exception as e:
            self.logger.exception(f"Investigate crawl failed: {e}")
            report["error"] = str(e)
            report["status"] = "failed"
            self._running_processes[process_id]["status"] = "failed"
            self._running_processes[process_id]["error"] = str(e)
            self._running_processes[process_id]["completed_at"] = datetime.now().isoformat()
        
        return report

    def combined_autonomous(
        self,
        target_entities: Optional[List[str]] = None,
        max_entities: int = 10,
        max_pages: int = 25,
        max_depth: int = 3,
        priority_threshold: float = 0.3,
    ) -> Dict[str, Any]:
        """
        Combined Autonomous mode: Run reflect_relate then investigate_crawl.
        
        This mode runs both phases in sequence:
        1. Reflect & Relate to find gaps and potential relations
        2. Investigate Crawl to fill those gaps
        
        Args:
            target_entities: Optional list of entity names to focus on
            max_entities: Maximum entities to crawl
            max_pages: Maximum pages per entity crawl
            max_depth: Maximum crawl depth
            priority_threshold: Minimum task priority to process
            
        Returns:
            Combined report with both sub-reports
        """
        # Create process entry
        self._process_counter += 1
        process_id = f"combined_autonomous_{self._process_counter}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        self._running_processes[process_id] = {
            "process_id": process_id,
            "action": "combined_autonomous",
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "current_phase": "reflect_relate",
        }
        
        self.logger.info(f"Starting combined autonomous mode (process {process_id})")
        
        report: Dict[str, Any] = {
            "mode": "combined_autonomous",
            "process_id": process_id,
            "started_at": datetime.now().isoformat(),
            "reflect_relate_report": {},
            "investigate_crawl_report": {},
            "statistics": {
                "total_entities_analyzed": 0,
                "total_crawls_executed": 0,
                "total_pages_discovered": 0,
            },
        }
        
        try:
            # Phase 1: Reflect & Relate
            self.logger.info("Phase 1: Reflect & Relate")
            reflect_report = self.reflect_relate(target_entities=target_entities)
            report["reflect_relate_report"] = reflect_report
            
            # Check for stop request
            if self._running_processes.get(process_id, {}).get("status") == "stopping":
                report["status"] = "stopped"
                self._running_processes[process_id]["status"] = "stopped"
                self._running_processes[process_id]["completed_at"] = datetime.now().isoformat()
                return report
            
            # Phase 2: Investigate Crawl
            self._running_processes[process_id]["current_phase"] = "investigate_crawl"
            self.logger.info("Phase 2: Investigate Crawl")
            
            investigation_tasks = reflect_report.get("investigation_tasks", [])
            investigate_report = self.investigate_crawl(
                investigation_tasks=investigation_tasks,
                max_entities=max_entities,
                max_pages=max_pages,
                max_depth=max_depth,
                priority_threshold=priority_threshold,
            )
            report["investigate_crawl_report"] = investigate_report
            
            # Combine statistics
            report["statistics"]["total_entities_analyzed"] = (
                reflect_report.get("statistics", {}).get("entities_analyzed", 0)
            )
            report["statistics"]["total_crawls_executed"] = (
                investigate_report.get("statistics", {}).get("crawls_executed", 0)
            )
            report["statistics"]["total_pages_discovered"] = (
                investigate_report.get("statistics", {}).get("pages_discovered", 0)
            )
            
            report["completed_at"] = datetime.now().isoformat()
            self._running_processes[process_id]["status"] = "completed"
            self._running_processes[process_id]["completed_at"] = datetime.now().isoformat()
            
        except Exception as e:
            self.logger.exception(f"Combined autonomous mode failed: {e}")
            report["error"] = str(e)
            report["status"] = "failed"
            self._running_processes[process_id]["status"] = "failed"
            self._running_processes[process_id]["error"] = str(e)
            self._running_processes[process_id]["completed_at"] = datetime.now().isoformat()
        
        return report

    # =========================================================================
    # PROCESS MANAGEMENT
    # =========================================================================

    def get_process_status(self, process_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get status of one or all running processes.
        
        Args:
            process_id: Optional specific process ID to check
            
        Returns:
            Process status dict or list of all processes
        """
        if process_id:
            return self._running_processes.get(process_id, {"error": "Process not found"})
        return {"processes": list(self._running_processes.values())}

    def stop_process(self, process_id: str) -> Dict[str, Any]:
        """
        Mark a process for stopping.
        
        Args:
            process_id: ID of the process to stop
            
        Returns:
            Result dict with success or error
        """
        if process_id in self._running_processes:
            self._running_processes[process_id]["status"] = "stopping"
            self._running_processes[process_id]["stop_requested_at"] = datetime.now().isoformat()
            return {"success": True, "process_id": process_id, "status": "stopping"}
        return {"error": "Process not found", "process_id": process_id}
