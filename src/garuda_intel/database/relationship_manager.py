"""
Relationship Graph Enhancement Module

This module provides advanced relationship management capabilities including:
- Relationship inference using LLM and context
- Deduplication of relationships
- Entity clustering by relationship types
- Confidence scoring and validation
- Graph analysis and traversal
"""

import logging
import json
import requests
from typing import List, Dict, Optional, Any, Tuple
from collections import defaultdict

from sqlalchemy import select, func

from .store import PersistenceStore
from .models import Entity, Relationship, BasicDataEntry
from ..extractor.llm import LLMIntelExtractor


class RelationshipManager:
    """
    Advanced relationship management for entity knowledge graphs.
    
    Features:
    - Infer implicit relationships from context using LLM
    - Deduplicate relationships with confidence-based merging
    - Cluster entities by relationship patterns
    - Validate relationship integrity
    - Graph analysis and export
    
    Example:
        >>> store = SQLAlchemyStore()
        >>> llm = LLMIntelExtractor()
        >>> manager = RelationshipManager(store, llm)
        >>> 
        >>> # Infer missing relationships
        >>> new_rels = manager.infer_relationships(
        ...     entity_ids=["id1", "id2", "id3"],
        ...     context="Apple Inc. CEO Tim Cook announced..."
        ... )
        >>> 
        >>> # Clean up duplicates
        >>> removed = manager.deduplicate_relationships()
        >>> 
        >>> # Find clusters
        >>> clusters = manager.cluster_entities_by_relation(["works_at", "ceo_of"])
    """
    
    def __init__(self, store: PersistenceStore, llm_extractor: Optional[LLMIntelExtractor] = None):
        """
        Initialize RelationshipManager.
        
        Args:
            store: PersistenceStore instance for database operations
            llm_extractor: Optional LLMIntelExtractor for AI-powered inference
        """
        self.store = store
        self.llm_extractor = llm_extractor
        self.logger = logging.getLogger(__name__)
    
    def _call_llm(self, prompt: str, json_mode: bool = True, timeout: int = 30) -> Optional[str]:
        """
        Call LLM with a prompt.
        
        Args:
            prompt: The prompt to send
            json_mode: Whether to expect JSON response
            timeout: Request timeout in seconds
            
        Returns:
            Response text or None on error
        """
        if not self.llm_extractor:
            return None
        
        try:
            response = requests.post(
                self.llm_extractor.ollama_url,
                json={
                    "model": self.llm_extractor.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json" if json_mode else None,
                },
                timeout=timeout,
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("response", "").strip()
        except Exception as e:
            self.logger.warning(f"LLM call failed: {e}")
        
        return None
        
    def infer_relationships(
        self, 
        entity_ids: List[str], 
        context: Optional[str] = None,
        min_confidence: float = 0.5,
    ) -> List[Tuple[str, str, str, float]]:
        """
        Infer unstated relationships between entities using LLM and existing data.
        
        Uses the LLM to analyze entity information and context to discover
        implicit relationships that weren't explicitly stated.
        
        Args:
            entity_ids: List of entity UUIDs to analyze
            context: Optional text context to help infer relationships
            min_confidence: Minimum confidence threshold (0.0-1.0)
            
        Returns:
            List of tuples: (source_id, target_id, relation_type, confidence)
            
        Example:
            >>> # Given entities: "Apple Inc.", "Tim Cook", "Cupertino"
            >>> # And context: "Tim Cook leads Apple from Cupertino"
            >>> rels = manager.infer_relationships(
            ...     entity_ids=["apple_id", "tim_id", "cupertino_id"],
            ...     context="Tim Cook leads Apple from Cupertino"
            ... )
            >>> # Returns: [
            >>> #   ("tim_id", "apple_id", "ceo_of", 0.85),
            >>> #   ("apple_id", "cupertino_id", "headquartered_in", 0.90)
            >>> # ]
        """
        if not entity_ids or len(entity_ids) < 2:
            self.logger.warning("Need at least 2 entities to infer relationships")
            return []
        
        if not self.llm_extractor:
            self.logger.warning("No LLM extractor available for relationship inference")
            return []
        
        inferred_relationships = []
        
        try:
            # Fetch entity details
            entities_info = []
            with self.store.Session() as session:
                for eid in entity_ids:
                    entity = session.execute(
                        select(Entity).where(Entity.id == eid)
                    ).scalar_one_or_none()
                    
                    if entity:
                        entities_info.append({
                            "id": str(entity.id),
                            "name": entity.name,
                            "kind": entity.kind,
                            "data": entity.data or {},
                        })
            
            if len(entities_info) < 2:
                return []
            
            # Build prompt for LLM
            entities_desc = "\n".join([
                f"- {e['name']} (ID: {e['id']}, Type: {e['kind']})"
                for e in entities_info
            ])
            
            prompt = f"""Analyze the following entities and infer potential relationships between them.

Entities:
{entities_desc}

Context: {context if context else "No additional context provided"}

For each potential relationship, provide:
1. Source entity ID
2. Target entity ID  
3. Relationship type (e.g., "works_at", "located_in", "subsidiary_of", "ceo_of")
4. Confidence score (0.0 to 1.0)

Return ONLY a JSON array of relationships, no other text:
[
  {{"source_id": "...", "target_id": "...", "relation_type": "...", "confidence": 0.XX}}
]

Only include relationships where confidence >= {min_confidence}.
"""
            
            # Query LLM
            response = self._call_llm(
                prompt, 
                json_mode=True,
                timeout=30,
            )
            
            if response:
                try:
                    # Parse response
                    relationships = json.loads(response)
                    if isinstance(relationships, dict):
                        relationships = relationships.get("relationships", [])
                    
                    for rel in relationships:
                        if not isinstance(rel, dict):
                            continue
                        
                        source_id = rel.get("source_id")
                        target_id = rel.get("target_id")
                        relation_type = rel.get("relation_type", "related")
                        confidence = float(rel.get("confidence", 0.5))
                        
                        # Validate
                        if (source_id in entity_ids and 
                            target_id in entity_ids and 
                            source_id != target_id and
                            confidence >= min_confidence):
                            
                            inferred_relationships.append(
                                (source_id, target_id, relation_type, confidence)
                            )
                
                except json.JSONDecodeError as e:
                    self.logger.warning(f"Failed to parse LLM response: {e}")
                except Exception as e:
                    self.logger.warning(f"Error processing relationships: {e}")
        
        except Exception as e:
            self.logger.error(f"Relationship inference failed: {e}")
        
        self.logger.info(f"Inferred {len(inferred_relationships)} relationships")
        return inferred_relationships
    
    def deduplicate_relationships(self, auto_fix: bool = True) -> int:
        """
        Find and remove duplicate relationships, keeping highest confidence.
        
        Duplicates are defined as relationships with the same:
        - source_id
        - target_id  
        - relation_type
        
        When duplicates are found, the one with the highest confidence score
        (if available) is kept, and others are deleted.
        
        Args:
            auto_fix: If True, automatically remove duplicates (default: True)
            
        Returns:
            Number of duplicates removed
            
        Example:
            >>> # Before: 3 relationships "apple_ceo_tim" with different confidences
            >>> removed = manager.deduplicate_relationships()
            >>> # After: 1 relationship with highest confidence
            >>> print(f"Removed {removed} duplicates")
        """
        duplicates_removed = 0
        
        try:
            with self.store.Session() as session:
                # Find all relationships
                relationships = session.execute(
                    select(Relationship)
                ).scalars().all()
                
                # Group by (source_id, target_id, relation_type)
                rel_groups = defaultdict(list)
                for rel in relationships:
                    key = (str(rel.source_id), str(rel.target_id), rel.relation_type)
                    rel_groups[key].append(rel)
                
                # Process each group
                for key, group in rel_groups.items():
                    if len(group) <= 1:
                        continue  # No duplicates
                    
                    # Sort by confidence (highest first), then by created_at (newest first)
                    def get_confidence(r):
                        meta = r.metadata_json or {}
                        return meta.get("confidence", 0.0)
                    
                    sorted_group = sorted(
                        group, 
                        key=lambda r: (get_confidence(r), r.created_at or 0),
                        reverse=True
                    )
                    
                    # Keep the first one (highest confidence), delete the rest
                    to_keep = sorted_group[0]
                    to_delete = sorted_group[1:]
                    
                    if auto_fix:
                        for rel in to_delete:
                            session.delete(rel)
                            duplicates_removed += 1
                        
                        self.logger.debug(
                            f"Removed {len(to_delete)} duplicates for relationship "
                            f"{key[0][:8]} -> {key[1][:8]} ({key[2]})"
                        )
                
                if auto_fix and duplicates_removed > 0:
                    session.commit()
                    self.logger.info(f"Removed {duplicates_removed} duplicate relationships")
        
        except Exception as e:
            self.logger.error(f"Deduplication failed: {e}")
        
        return duplicates_removed
    
    def cluster_entities_by_relation(
        self, 
        relation_types: Optional[List[str]] = None
    ) -> Dict[str, List[Tuple[str, str]]]:
        """
        Group entities by relationship type.
        
        Returns entity pairs grouped by the relationships connecting them.
        Useful for finding patterns like "all CEOs", "all subsidiaries", etc.
        
        Args:
            relation_types: Optional list of specific relation types to cluster.
                          If None, clusters all relation types.
        
        Returns:
            Dictionary mapping relation_type to list of (source_id, target_id) tuples
            
        Example:
            >>> clusters = manager.cluster_entities_by_relation(["works_at", "ceo_of"])
            >>> print(f"Found {len(clusters['works_at'])} 'works_at' relationships")
            >>> print(f"Found {len(clusters['ceo_of'])} CEO relationships")
        """
        clusters = defaultdict(list)
        
        try:
            with self.store.Session() as session:
                stmt = select(Relationship)
                
                if relation_types:
                    stmt = stmt.where(Relationship.relation_type.in_(relation_types))
                
                relationships = session.execute(stmt).scalars().all()
                
                for rel in relationships:
                    clusters[rel.relation_type].append(
                        (str(rel.source_id), str(rel.target_id))
                    )
                
                self.logger.info(f"Found {len(clusters)} relationship types")
        
        except Exception as e:
            self.logger.error(f"Clustering failed: {e}")
        
        return dict(clusters)
    
    def validate_relationships(self, fix_invalid: bool = False) -> Dict[str, Any]:
        """
        Validate all relationships and optionally fix issues.
        
        Checks for:
        - Circular relationships (node relating to itself)
        - Orphaned relationships (missing source or target node in any table)
        - Invalid confidence scores
        - Missing required fields
        
        Note: Validates relationships between ALL node types (Entity, Page, 
        Intelligence, Seed, etc.), not just Entity↔Entity relationships.
        
        Args:
            fix_invalid: If True, attempts to fix or remove invalid relationships
            
        Returns:
            Validation report containing:
            - total: Total number of relationships
            - valid: Number of valid relationships
            - circular: Number of circular relationships
            - orphaned: Number of orphaned relationships
            - invalid_confidence: Number with invalid confidence scores
            - fixed: Number of issues fixed (if fix_invalid=True)
            - issues: List of issue details
            
        Example:
            >>> report = manager.validate_relationships(fix_invalid=True)
            >>> print(f"Valid: {report['valid']}/{report['total']}")
            >>> print(f"Fixed: {report['fixed']} issues")
        """
        report = {
            "total": 0,
            "valid": 0,
            "circular": 0,
            "orphaned": 0,
            "invalid_confidence": 0,
            "fixed": 0,
            "issues": [],
        }
        
        try:
            with self.store.Session() as session:
                relationships = session.execute(
                    select(Relationship)
                ).scalars().all()
                
                report["total"] = len(relationships)
                
                for rel in relationships:
                    is_valid = True
                    
                    # Check for circular relationship
                    if rel.source_id == rel.target_id:
                        report["circular"] += 1
                        is_valid = False
                        report["issues"].append({
                            "id": str(rel.id),
                            "type": "circular",
                            "message": f"Entity {rel.source_id} relates to itself"
                        })
                        
                        if fix_invalid:
                            session.delete(rel)
                            report["fixed"] += 1
                        continue
                    
                    # Check for orphaned relationships
                    # Check against BasicDataEntry (entries table) to support all node types
                    # (Entity, Page, Intelligence, Seed, etc.), not just Entity
                    source_exists = session.execute(
                        select(BasicDataEntry.id).where(BasicDataEntry.id == rel.source_id)
                    ).scalar_one_or_none()
                    
                    target_exists = session.execute(
                        select(BasicDataEntry.id).where(BasicDataEntry.id == rel.target_id)
                    ).scalar_one_or_none()
                    
                    if not source_exists or not target_exists:
                        report["orphaned"] += 1
                        is_valid = False
                        missing = []
                        if not source_exists:
                            missing.append("source")
                        if not target_exists:
                            missing.append("target")
                        
                        report["issues"].append({
                            "id": str(rel.id),
                            "type": "orphaned",
                            "message": f"Missing {', '.join(missing)} node"
                        })
                        
                        if fix_invalid:
                            session.delete(rel)
                            report["fixed"] += 1
                        continue
                    
                    # Check confidence score
                    meta = rel.metadata_json or {}
                    confidence = meta.get("confidence")
                    if confidence is not None:
                        if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
                            report["invalid_confidence"] += 1
                            is_valid = False
                            report["issues"].append({
                                "id": str(rel.id),
                                "type": "invalid_confidence",
                                "message": f"Invalid confidence: {confidence}"
                            })
                            
                            if fix_invalid:
                                # Clamp to valid range
                                meta["confidence"] = max(0.0, min(1.0, float(confidence) if isinstance(confidence, (int, float)) else 0.5))
                                rel.metadata_json = meta
                                report["fixed"] += 1
                                is_valid = True
                    
                    if is_valid:
                        report["valid"] += 1
                
                if fix_invalid and report["fixed"] > 0:
                    session.commit()
                    self.logger.info(f"Fixed {report['fixed']} relationship issues")
        
        except Exception as e:
            self.logger.error(f"Validation failed: {e}")
        
        return report
    
    def backfill_relationship_types(self) -> int:
        """
        Backfill source_type and target_type for existing relationships.
        
        This is useful for migrating old relationships that were created before
        the type fields were added. Queries the entries table to determine the
        actual type of each source/target node.
        
        Returns:
            Number of relationships updated with type information
            
        Example:
            >>> # Backfill types for all existing relationships
            >>> updated = manager.backfill_relationship_types()
            >>> print(f"Updated {updated} relationships with type information")
        """
        updated_count = 0
        
        try:
            with self.store.Session() as session:
                # Get all relationships that are missing type information
                relationships = session.execute(
                    select(Relationship)
                ).scalars().all()
                
                for rel in relationships:
                    needs_update = False
                    
                    # Check if source_type is missing
                    if not rel.source_type:
                        source_entry = session.execute(
                            select(BasicDataEntry.entry_type).where(
                                BasicDataEntry.id == rel.source_id
                            )
                        ).scalar_one_or_none()
                        
                        if source_entry:
                            rel.source_type = source_entry
                            needs_update = True
                    
                    # Check if target_type is missing
                    if not rel.target_type:
                        target_entry = session.execute(
                            select(BasicDataEntry.entry_type).where(
                                BasicDataEntry.id == rel.target_id
                            )
                        ).scalar_one_or_none()
                        
                        if target_entry:
                            rel.target_type = target_entry
                            needs_update = True
                    
                    if needs_update:
                        updated_count += 1
                
                if updated_count > 0:
                    session.commit()
                    self.logger.info(f"Backfilled types for {updated_count} relationships")
        
        except Exception as e:
            self.logger.error(f"Type backfill failed: {e}")
        
        return updated_count
    
    def infer_missing_fields(self) -> int:
        """
        Infer missing entity fields from related entities through relationships.
        
        For example:
        - If Entity A works at Company B, and Company B has location X,
          then Entity A's location might also be X.
        - If Person P is CEO of Company C, and Company C is in Industry I,
          then Person P might be associated with Industry I.
        
        This method traverses the relationship graph and propagates information
        from related entities to fill in missing fields.
        
        Returns:
            Number of fields inferred and filled
            
        Example:
            >>> # Infer missing fields from relationships
            >>> inferred = manager.infer_missing_fields()
            >>> if inferred > 0:
            ...     print(f"Successfully inferred {inferred} missing fields")
        """
        inferences_made = 0
        
        try:
            from sqlalchemy.orm.attributes import flag_modified
            
            with self.store.Session() as session:
                # Get all entities and relationships
                entities = session.execute(select(Entity)).scalars().all()
                relationships = session.execute(select(Relationship)).scalars().all()
                
                # Build a map of entity_id -> entity for quick lookup
                # Ensure consistent string type for IDs
                entity_map = {str(e.id): e for e in entities}
                
                # For each relationship, try to infer missing fields
                for rel in relationships:
                    # Ensure IDs are strings for consistent lookup
                    source_id = str(rel.source_id)
                    target_id = str(rel.target_id)
                    
                    if source_id not in entity_map or target_id not in entity_map:
                        continue
                    
                    source = entity_map[source_id]
                    target = entity_map[target_id]
                    
                    # Track if source.data was modified
                    source_modified = False
                    
                    # Infer based on relationship type
                    if rel.relation_type in ["works_at", "employed_by", "employee_of"]:
                        # If person works at company, they might share location
                        if target.entity_type in ["organization", "company"]:
                            target_data = target.data or {}
                            source_data = source.data or {}
                            
                            # Propagate location
                            if "location" in target_data and "location" not in source_data:
                                if source.data is None:
                                    source.data = {}
                                source.data["location"] = target_data["location"]
                                inferences_made += 1
                                source_modified = True
                            
                            # Propagate industry
                            if "industry" in target_data and "industry" not in source_data:
                                if source.data is None:
                                    source.data = {}
                                source.data["industry"] = target_data["industry"]
                                inferences_made += 1
                                source_modified = True
                    
                    elif rel.relation_type in ["ceo_of", "founder_of", "president_of"]:
                        # If person is CEO/founder of company, they might share location
                        if target.entity_type in ["organization", "company"]:
                            target_data = target.data or {}
                            source_data = source.data or {}
                            
                            if "location" in target_data and "location" not in source_data:
                                if source.data is None:
                                    source.data = {}
                                source.data["location"] = target_data["location"]
                                inferences_made += 1
                                source_modified = True
                    
                    elif rel.relation_type in ["subsidiary_of", "part_of", "owned_by"]:
                        # Subsidiary might share parent's industry/location
                        target_data = target.data or {}
                        source_data = source.data or {}
                        
                        if "industry" in target_data and "industry" not in source_data:
                            if source.data is None:
                                source.data = {}
                            source.data["industry"] = target_data["industry"]
                            inferences_made += 1
                            source_modified = True
                    
                    elif rel.relation_type in ["located_in", "based_in", "headquarters_in"]:
                        # Propagate country/region info
                        target_data = target.data or {}
                        source_data = source.data or {}
                        
                        if "country" in target_data and "country" not in source_data:
                            if source.data is None:
                                source.data = {}
                            source.data["country"] = target_data["country"]
                            inferences_made += 1
                            source_modified = True
                    
                    # Mark data as modified so SQLAlchemy tracks the change
                    if source_modified:
                        flag_modified(source, 'data')
                
                if inferences_made > 0:
                    session.commit()
                    self.logger.info(f"Inferred {inferences_made} missing fields")
        
        except Exception as e:
            self.logger.error(f"Field inference failed: {e}")
        
        return inferences_made
    
    def add_relationship_confidence(
        self, 
        relationship_id: str, 
        confidence: float
    ) -> bool:
        """
        Add or update confidence score for a relationship.
        
        Args:
            relationship_id: UUID of the relationship
            confidence: Confidence score (0.0 to 1.0)
            
        Returns:
            True if successful, False otherwise
            
        Example:
            >>> success = manager.add_relationship_confidence(
            ...     relationship_id="abc-123",
            ...     confidence=0.95
            ... )
        """
        if not (0.0 <= confidence <= 1.0):
            self.logger.warning(f"Invalid confidence score: {confidence}")
            return False
        
        try:
            with self.store.Session() as session:
                rel = session.execute(
                    select(Relationship).where(Relationship.id == relationship_id)
                ).scalar_one_or_none()
                
                if not rel:
                    self.logger.warning(f"Relationship not found: {relationship_id}")
                    return False
                
                meta = rel.metadata_json or {}
                meta["confidence"] = confidence
                rel.metadata_json = meta
                
                session.commit()
                self.logger.debug(f"Updated confidence for relationship {relationship_id}")
                return True
        
        except Exception as e:
            self.logger.error(f"Failed to update confidence: {e}")
            return False
    
    def get_relationship_graph(
        self, 
        entity_ids: Optional[List[str]] = None,
        min_confidence: float = 0.0,
        include_metadata: bool = True,
    ) -> Dict[str, Any]:
        """
        Get relationship graph in networkx-compatible format.
        
        Returns a graph structure that can be easily converted to networkx
        or other graph libraries for visualization and analysis.
        
        Args:
            entity_ids: Optional list of entity IDs to include. If None, includes all.
            min_confidence: Minimum confidence threshold for relationships
            include_metadata: Include full metadata in edges
            
        Returns:
            Dictionary with:
            - nodes: List of node dictionaries with entity info
            - edges: List of edge dictionaries with relationship info
            - metadata: Graph-level metadata
            
        Example:
            >>> graph = manager.get_relationship_graph(
            ...     entity_ids=["id1", "id2"],
            ...     min_confidence=0.7
            ... )
            >>> 
            >>> # Convert to networkx
            >>> import networkx as nx
            >>> G = nx.DiGraph()
            >>> for node in graph['nodes']:
            ...     G.add_node(node['id'], **node)
            >>> for edge in graph['edges']:
            ...     G.add_edge(edge['source'], edge['target'], **edge)
        """
        graph = {
            "nodes": [],
            "edges": [],
            "metadata": {
                "min_confidence": min_confidence,
                "filtered": entity_ids is not None,
            }
        }
        
        try:
            with self.store.Session() as session:
                # Get entities
                entity_stmt = select(Entity)
                if entity_ids:
                    entity_stmt = entity_stmt.where(Entity.id.in_(entity_ids))
                
                entities = session.execute(entity_stmt).scalars().all()
                entity_id_set = {str(e.id) for e in entities}
                
                # Build nodes
                for entity in entities:
                    node = {
                        "id": str(entity.id),
                        "name": entity.name,
                        "kind": entity.kind,
                    }
                    if include_metadata:
                        node["data"] = entity.data or {}
                        node["metadata"] = entity.metadata_json or {}
                    
                    graph["nodes"].append(node)
                
                # Get relationships
                rel_stmt = select(Relationship)
                if entity_ids:
                    rel_stmt = rel_stmt.where(
                        Relationship.source_id.in_(entity_ids),
                        Relationship.target_id.in_(entity_ids)
                    )
                
                relationships = session.execute(rel_stmt).scalars().all()
                
                # Build edges
                for rel in relationships:
                    # Filter by confidence
                    meta = rel.metadata_json or {}
                    confidence = meta.get("confidence", 1.0)
                    if confidence < min_confidence:
                        continue
                    
                    # Only include if both endpoints are in our entity set
                    if str(rel.source_id) not in entity_id_set:
                        continue
                    if str(rel.target_id) not in entity_id_set:
                        continue
                    
                    edge = {
                        "source": str(rel.source_id),
                        "target": str(rel.target_id),
                        "relation_type": rel.relation_type,
                        "confidence": confidence,
                    }
                    
                    if include_metadata:
                        edge["metadata"] = meta
                        edge["id"] = str(rel.id)
                    
                    graph["edges"].append(edge)
                
                graph["metadata"]["num_nodes"] = len(graph["nodes"])
                graph["metadata"]["num_edges"] = len(graph["edges"])
        
        except Exception as e:
            self.logger.error(f"Failed to build graph: {e}")
        
        return graph
    
    def find_entity_clusters(
        self,
        min_cluster_size: int = 2,
        relation_types: Optional[List[str]] = None,
    ) -> List[List[str]]:
        """
        Find clusters of connected entities using graph connectivity.
        
        Uses connected components algorithm to find groups of entities
        that are connected through relationships.
        
        Args:
            min_cluster_size: Minimum number of entities in a cluster
            relation_types: Optional filter for specific relationship types
            
        Returns:
            List of clusters, where each cluster is a list of entity IDs
            
        Example:
            >>> clusters = manager.find_entity_clusters(min_cluster_size=3)
            >>> print(f"Found {len(clusters)} clusters")
            >>> for i, cluster in enumerate(clusters):
            ...     print(f"Cluster {i}: {len(cluster)} entities")
        """
        clusters = []
        
        try:
            with self.store.Session() as session:
                # Get all relevant relationships
                stmt = select(Relationship)
                if relation_types:
                    stmt = stmt.where(Relationship.relation_type.in_(relation_types))
                
                relationships = session.execute(stmt).scalars().all()
                
                # Build adjacency list (undirected graph)
                adjacency = defaultdict(set)
                all_entities = set()
                
                for rel in relationships:
                    source = str(rel.source_id)
                    target = str(rel.target_id)
                    adjacency[source].add(target)
                    adjacency[target].add(source)  # Undirected
                    all_entities.add(source)
                    all_entities.add(target)
                
                # Find connected components using DFS
                visited = set()
                
                def dfs(node, component):
                    visited.add(node)
                    component.append(node)
                    for neighbor in adjacency.get(node, []):
                        if neighbor not in visited:
                            dfs(neighbor, component)
                
                for entity in all_entities:
                    if entity not in visited:
                        component = []
                        dfs(entity, component)
                        if len(component) >= min_cluster_size:
                            clusters.append(component)
                
                self.logger.info(f"Found {len(clusters)} entity clusters")
        
        except Exception as e:
            self.logger.error(f"Cluster finding failed: {e}")
        
        return clusters
