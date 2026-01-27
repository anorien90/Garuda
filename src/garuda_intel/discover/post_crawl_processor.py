"""
Post-crawl processing module for comprehensive deduplication and aggregation.

This module handles:
1. Entity deduplication and merging
2. Relationship deduplication and validation
3. Intelligence data aggregation
4. Cross-entity inference
5. Data quality improvements
"""

import logging
from typing import Dict, List, Set, Tuple, Optional, Any
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select

from ..database.store import PersistenceStore
from ..database.relationship_manager import RelationshipManager
from ..extractor.llm import LLMIntelExtractor


logger = logging.getLogger(__name__)


class PostCrawlProcessor:
    """
    Comprehensive post-crawl processing to ensure all gathered intel is:
    - Deduplicated (remove redundant entities and relationships)
    - Aggregated (combine related information)
    - Validated (ensure data quality and consistency)
    - Complete (fill gaps through inference where possible)
    """
    
    def __init__(
        self,
        store: PersistenceStore,
        relationship_manager: Optional[RelationshipManager] = None,
        llm: Optional[LLMIntelExtractor] = None
    ):
        self.store = store
        self.relationship_manager = relationship_manager
        self.llm = llm
        self.logger = logger
        
    def process(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Run comprehensive post-crawl processing.
        
        Args:
            session_id: Optional session identifier to track this processing run
            
        Returns:
            Dictionary with processing statistics
        """
        stats = {
            "session_id": session_id or str(datetime.now().timestamp()),
            "entities_before": 0,
            "entities_after": 0,
            "entities_merged": 0,
            "relationships_before": 0,
            "relationships_after": 0,
            "relationships_removed": 0,
            "intel_items_aggregated": 0,
            "data_quality_improvements": 0,
        }
        
        self.logger.info("=" * 60)
        self.logger.info("Starting comprehensive post-crawl processing...")
        self.logger.info("=" * 60)
        
        # Step 1: Entity deduplication and merging
        self.logger.info("Step 1/5: Deduplicating and merging entities...")
        entity_stats = self._deduplicate_entities()
        stats.update(entity_stats)
        
        # Step 2: Relationship deduplication and validation
        self.logger.info("Step 2/5: Deduplicating and validating relationships...")
        rel_stats = self._deduplicate_relationships()
        stats.update(rel_stats)
        
        # Step 3: Intelligence data aggregation
        self.logger.info("Step 3/5: Aggregating intelligence data...")
        intel_stats = self._aggregate_intelligence()
        stats.update(intel_stats)
        
        # Step 4: Cross-entity inference
        self.logger.info("Step 4/5: Running cross-entity inference...")
        inference_stats = self._cross_entity_inference()
        stats.update(inference_stats)
        
        # Step 5: Data quality improvements
        self.logger.info("Step 5/5: Applying data quality improvements...")
        quality_stats = self._improve_data_quality()
        stats.update(quality_stats)
        
        self.logger.info("=" * 60)
        self.logger.info("Post-crawl processing completed!")
        self.logger.info(f"  Entities: {stats['entities_before']} -> {stats['entities_after']} "
                        f"(merged {stats['entities_merged']})")
        self.logger.info(f"  Relationships: {stats['relationships_before']} -> {stats['relationships_after']} "
                        f"(removed {stats['relationships_removed']})")
        self.logger.info(f"  Intel aggregations: {stats['intel_items_aggregated']}")
        self.logger.info(f"  Quality improvements: {stats['data_quality_improvements']}")
        self.logger.info("=" * 60)
        
        return stats
        
    def _deduplicate_entities(self) -> Dict[str, int]:
        """
        Deduplicate entities by identifying and merging similar ones.
        Uses fuzzy matching on entity names and types.
        """
        stats = {
            "entities_before": 0,
            "entities_after": 0,
            "entities_merged": 0,
        }
        
        try:
            from ..database.models import Entity
            from sqlalchemy import func
            
            # Get entity count without loading all entities
            with self.store.Session() as session:
                stats["entities_before"] = session.execute(
                    select(func.count()).select_from(Entity)
                ).scalar()
                
                if stats["entities_before"] == 0:
                    self.logger.info("  No entities to deduplicate")
                    return stats
            
            # Use store's deduplication method
            merge_map = self.store.deduplicate_entities(threshold=0.85)
            stats["entities_merged"] = len(merge_map)
            
            # Recount after deduplication
            with self.store.Session() as session:
                stats["entities_after"] = session.execute(
                    select(func.count()).select_from(Entity)
                ).scalar()
            
            self.logger.info(f"  Entities: {stats['entities_before']} -> {stats['entities_after']} "
                           f"(merged {stats['entities_merged']})")
            
        except Exception as e:
            self.logger.error(f"  Entity deduplication failed: {e}")
            stats["entities_after"] = stats["entities_before"]
            
        return stats
        
    def _deduplicate_relationships(self) -> Dict[str, int]:
        """
        Deduplicate relationships and validate them.
        """
        stats = {
            "relationships_before": 0,
            "relationships_after": 0,
            "relationships_removed": 0,
        }
        
        if not self.relationship_manager:
            self.logger.info("  Relationship manager not available, skipping")
            return stats
            
        try:
            from ..database.models import Relationship
            from sqlalchemy import func
            
            # Get relationship count without loading all relationships
            with self.store.Session() as session:
                stats["relationships_before"] = session.execute(
                    select(func.count()).select_from(Relationship)
                ).scalar()
                
                if stats["relationships_before"] == 0:
                    self.logger.info("  No relationships to process")
                    return stats
            
            # Deduplicate relationships
            duplicates_removed = self.relationship_manager.deduplicate_relationships()
            
            # Validate and fix relationships
            validation_report = self.relationship_manager.validate_relationships(fix_invalid=True)
            
            # Recount after processing
            with self.store.Session() as session:
                stats["relationships_after"] = session.execute(
                    select(func.count()).select_from(Relationship)
                ).scalar()
            stats["relationships_removed"] = stats["relationships_before"] - stats["relationships_after"]
            
            self.logger.info(f"  Relationships: {stats['relationships_before']} -> {stats['relationships_after']}")
            self.logger.info(f"    Duplicates removed: {duplicates_removed}")
            self.logger.info(f"    Validation: {validation_report['valid']}/{validation_report['total']} valid, "
                           f"{validation_report['fixed']} fixed")
            
        except Exception as e:
            self.logger.error(f"  Relationship processing failed: {e}")
            stats["relationships_after"] = stats["relationships_before"]
            
        return stats
        
    def _aggregate_intelligence(self) -> Dict[str, int]:
        """
        Aggregate intelligence data to remove redundancy and consolidate information.
        Groups similar intelligence items and merges them.
        """
        stats = {
            "intel_items_aggregated": 0,
        }
        
        try:
            from ..database.models import Intelligence, Entity
            from sqlalchemy.orm.attributes import flag_modified
            
            with self.store.Session() as session:
                # Group intelligence by entity
                entity_intel_map = defaultdict(list)
                
                all_intel = session.execute(select(Intelligence)).scalars().all()
                for intel in all_intel:
                    if intel.entity_id:
                        entity_intel_map[intel.entity_id].append(intel)
                
                # For each entity, aggregate similar intel items
                for entity_id, intel_list in entity_intel_map.items():
                    if len(intel_list) <= 1:
                        continue
                        
                    # Group by data keys
                    data_key_groups = defaultdict(list)
                    for intel in intel_list:
                        if intel.data:
                            for key in intel.data.keys():
                                data_key_groups[key].append(intel)
                    
                    # Merge intelligence with the same keys
                    for key, group in data_key_groups.items():
                        if len(group) > 1:
                            # Keep the one with highest confidence or most recent
                            group_sorted = sorted(
                                group,
                                key=lambda x: (
                                    x.confidence or 0.0,
                                    x.created_at or datetime.min
                                ),
                                reverse=True
                            )
                            
                            # Merge data from lower confidence items into the best one
                            best = group_sorted[0]
                            data_modified = False
                            for other in group_sorted[1:]:
                                if other.data and best.data:
                                    # Merge unique values
                                    for k, v in other.data.items():
                                        if k not in best.data and v:
                                            best.data[k] = v
                                            stats["intel_items_aggregated"] += 1
                                            data_modified = True
                            
                            # Mark data as modified so SQLAlchemy tracks the change
                            if data_modified:
                                flag_modified(best, 'data')
                
                session.commit()
                self.logger.info(f"  Aggregated {stats['intel_items_aggregated']} intelligence data items")
            
        except Exception as e:
            self.logger.error(f"  Intelligence aggregation failed: {e}")
            
        return stats
        
    def _cross_entity_inference(self) -> Dict[str, int]:
        """
        Infer missing information from related entities.
        For example, if Entity A works at Company B, and Company B has location X,
        then Entity A's location might also be X.
        """
        stats = {
            "inferences_made": 0,
        }
        
        if not self.relationship_manager:
            self.logger.info("  Cross-entity inference requires relationship manager, skipping")
            return stats
            
        try:
            # Use relationship manager to infer missing fields
            inferred_count = self.relationship_manager.infer_missing_fields()
            stats["inferences_made"] = inferred_count
            
            self.logger.info(f"  Made {stats['inferences_made']} cross-entity inferences")
            
        except Exception as e:
            self.logger.error(f"  Cross-entity inference failed: {e}")
            
        return stats
        
    def _improve_data_quality(self) -> Dict[str, int]:
        """
        Apply general data quality improvements:
        - Normalize field values
        - Remove empty/null intelligence entries
        - Standardize entity types
        - Clean up malformed data
        """
        stats = {
            "data_quality_improvements": 0,
        }
        
        try:
            from ..database.models import Intelligence, Entity
            
            with self.store.Session() as session:
                # 1. Remove intelligence entries with no meaningful data
                stmt = select(Intelligence).where(
                    (Intelligence.data.is_(None)) | (Intelligence.data == {})
                )
                empty_intel = session.execute(stmt).scalars().all()
                
                for intel in empty_intel:
                    session.delete(intel)
                    stats["data_quality_improvements"] += 1
                
                # 2. Normalize entity types
                all_entities = session.execute(select(Entity)).scalars().all()
                type_mapping = {
                    "organisation": "organization",
                    "org": "organization",
                    "company": "organization",
                    "corporation": "organization",
                    "corp": "organization",
                }
                
                for entity in all_entities:
                    if entity.kind and entity.kind.lower() in type_mapping:
                        old_type = entity.kind
                        entity.kind = type_mapping[entity.kind.lower()]
                        if old_type != entity.kind:
                            stats["data_quality_improvements"] += 1
                
                # 3. Ensure all entities have normalized names
                for entity in all_entities:
                    if entity.name:
                        # Check if entity has normalized_name attribute
                        if hasattr(entity, 'normalized_name'):
                            expected_normalized = entity.name.lower().strip()
                            if entity.normalized_name != expected_normalized:
                                entity.normalized_name = expected_normalized
                                stats["data_quality_improvements"] += 1
                
                session.commit()
                self.logger.info(f"  Applied {stats['data_quality_improvements']} data quality improvements")
            
        except Exception as e:
            self.logger.error(f"  Data quality improvements failed: {e}")
            
        return stats
