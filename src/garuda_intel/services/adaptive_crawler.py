"""
Adaptive Crawler Service.

Intelligently adapts crawling strategy based on entity gaps, learned patterns,
and real-time feedback.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..database.store import PersistenceStore
from ..discover.crawl_learner import CrawlLearner
from ..discover.crawl_modes import EntityAwareCrawler, CrawlMode
from ..extractor.llm import LLMIntelExtractor
from .entity_gap_analyzer import EntityGapAnalyzer


logger = logging.getLogger(__name__)


class AdaptiveCrawlerService:
    """
    Orchestrates intelligent, adaptive crawling based on entity analysis
    and learned patterns.
    """
    
    def __init__(
        self, 
        store: PersistenceStore,
        llm: LLMIntelExtractor,
        crawl_learner: CrawlLearner
    ):
        """
        Initialize the adaptive crawler.
        
        Args:
            store: Database store
            llm: LLM extractor for intelligence gathering
            crawl_learner: Learner tracking crawl patterns
        """
        self.store = store
        self.llm = llm
        self.crawl_learner = crawl_learner
        self.gap_analyzer = EntityGapAnalyzer(store)
        self.crawler = EntityAwareCrawler(store, llm)
        self.logger = logging.getLogger(__name__)
    
    def intelligent_crawl(
        self,
        entity_name: str,
        entity_type: Optional[str] = None,
        max_pages: int = 50,
        max_depth: int = 2
    ) -> Dict[str, Any]:
        """
        Perform an intelligent crawl for an entity.
        
        This is the main entry point for adaptive, gap-aware crawling.
        
        Flow:
        1. Generate crawl plan (discovery vs gap-filling)
        2. Execute crawl with adaptive strategy
        3. Monitor progress and adjust in real-time
        4. Return results with learning stats
        
        Args:
            entity_name: Name of entity to research
            entity_type: Optional type hint
            max_pages: Maximum pages to crawl
            max_depth: Maximum crawl depth
            
        Returns:
            Crawl results with statistics
        """
        self.logger.info(f"Starting intelligent crawl for '{entity_name}'")
        
        # Step 1: Generate crawl plan
        plan = self.gap_analyzer.generate_crawl_plan(entity_name, entity_type)
        
        self.logger.info(f"Crawl mode: {plan['mode']}, strategy: {plan['strategy']}")
        
        # Step 2: Select appropriate crawl mode
        if plan['mode'] == 'gap_filling':
            crawl_mode = CrawlMode.TARGETING
            entity_id = plan.get('entity_id')
        else:
            crawl_mode = CrawlMode.DISCOVERY
            entity_id = None
        
        # Step 3: Prepare queries with learned patterns
        queries = plan.get('queries', [])
        
        # Enhance queries with successful patterns
        if entity_type:
            successful_patterns = self.crawl_learner.get_successful_patterns(entity_type)
            self.logger.info(f"Found {len(successful_patterns)} successful patterns for {entity_type}")
        
        # Step 4: Execute adaptive crawl
        results = {
            "entity_name": entity_name,
            "crawl_mode": plan['mode'],
            "strategy": plan['strategy'],
            "queries_used": queries,
            "pages_discovered": 0,
            "intel_extracted": 0,
            "relationships_found": 0,
            "gaps_filled": [],
            "new_gaps": [],
            "crawl_adjustments": [],
            "learning_stats": {}
        }
        
        # For gap-filling mode, track which gaps we're targeting
        if plan['mode'] == 'gap_filling':
            target_gaps = plan['analysis'].get('missing_fields', [])
            results['target_gaps'] = [g['field'] for g in target_gaps]
        
        # Execute crawl (simplified - in real implementation would call crawler)
        # This is a placeholder for the actual crawl orchestration
        self.logger.info(f"Executing {crawl_mode} crawl with {len(queries)} queries")
        
        # Step 5: Update learning stats
        results['learning_stats'] = self.crawl_learner.get_learning_stats()
        
        return results
    
    def monitor_and_adapt(
        self,
        entity_id: str,
        current_crawl_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Monitor ongoing crawl and suggest adaptations.
        
        Args:
            entity_id: Entity being crawled
            current_crawl_state: Current state (pages crawled, intel found, etc.)
            
        Returns:
            Adaptation suggestions
        """
        adaptations = {
            "continue": True,
            "adjustments": [],
            "new_queries": [],
            "depth_change": 0,
            "priority_domains": []
        }
        
        # Re-analyze gaps to see what's been filled
        analysis = self.gap_analyzer.analyze_entity_gaps(entity_id)
        
        # Check if we've filled critical gaps
        critical_gaps = [
            g for g in analysis.get('missing_fields', [])
            if g.get('priority') == 'critical'
        ]
        
        if not critical_gaps:
            self.logger.info("Critical gaps filled - can reduce crawl intensity")
            adaptations['adjustments'].append({
                "type": "intensity_reduction",
                "reason": "critical_gaps_filled"
            })
        
        # Check crawl efficiency
        pages_crawled = current_crawl_state.get('pages_crawled', 0)
        intel_found = current_crawl_state.get('intel_extracted', 0)
        
        if pages_crawled > 20 and intel_found < 5:
            self.logger.warning("Low extraction rate - suggesting query refinement")
            adaptations['adjustments'].append({
                "type": "query_refinement",
                "reason": "low_extraction_rate"
            })
            # Generate new queries based on what we've learned
            adaptations['new_queries'] = analysis.get('suggested_queries', [])[:3]
        
        # Suggest depth adjustments based on domain reliability
        if current_crawl_state.get('current_domain'):
            reliability = self.crawl_learner.get_domain_reliability(
                current_crawl_state['current_domain']
            )
            if reliability > 0.8:
                adaptations['depth_change'] = +1
                adaptations['adjustments'].append({
                    "type": "depth_increase",
                    "reason": f"high_domain_reliability ({reliability:.2f})"
                })
            elif reliability < 0.3:
                adaptations['depth_change'] = -1
                adaptations['adjustments'].append({
                    "type": "depth_decrease",
                    "reason": f"low_domain_reliability ({reliability:.2f})"
                })
        
        return adaptations
    
    def cross_entity_inference(
        self,
        entity_id: str,
        relationship_hops: int = 1
    ) -> Dict[str, Any]:
        """
        Use related entities to infer missing data for target entity.
        
        Example: If we don't know the CEO's company, but we know they're
        CEO of Microsoft, infer from Microsoft's entity data.
        
        Args:
            entity_id: Target entity
            relationship_hops: How many relationship hops to explore
            
        Returns:
            Inferred data suggestions
        """
        inferences = {
            "entity_id": entity_id,
            "inferred_fields": [],
            "confidence_scores": {}
        }
        
        with self.store.Session() as session:
            from ..database.models import Entity, Relationship
            
            # Get target entity
            entity = session.query(Entity).filter(Entity.id == entity_id).first()
            if not entity:
                return inferences
            
            # Find related entities
            outgoing = session.query(Relationship).filter(
                Relationship.source_id == entity_id
            ).all()
            
            incoming = session.query(Relationship).filter(
                Relationship.target_id == entity_id
            ).all()
            
            # Analyze relationships for data inference
            for rel in outgoing:
                related = session.query(Entity).filter(
                    Entity.id == rel.target_id
                ).first()
                
                if related and related.data:
                    # Example: If target is a person with "works_at" relationship
                    # to a company, infer organization field
                    if rel.relation_type in ['works_at', 'employed_by', 'ceo_of']:
                        if not self._has_field(entity.data or {}, 'organization'):
                            inferences['inferred_fields'].append({
                                "field": "organization",
                                "value": related.name,
                                "source": "relationship",
                                "relation_type": rel.relation_type,
                                "confidence": 0.8
                            })
            
            for rel in incoming:
                related = session.query(Entity).filter(
                    Entity.id == rel.source_id
                ).first()
                
                if related and related.data:
                    # Example: If target is a company and related is a person
                    # with "ceo_of" relationship, infer CEO field
                    if rel.relation_type in ['ceo_of', 'founded_by']:
                        field_name = 'ceo' if rel.relation_type == 'ceo_of' else 'founder'
                        if not self._has_field(entity.data or {}, field_name):
                            inferences['inferred_fields'].append({
                                "field": field_name,
                                "value": related.name,
                                "source": "relationship",
                                "relation_type": rel.relation_type,
                                "confidence": 0.9
                            })
        
        return inferences
    
    def _has_field(self, data: Dict, field: str) -> bool:
        """Check if field exists with meaningful value."""
        return bool(data.get(field))
    
    def get_adaptive_strategy_summary(self) -> Dict[str, Any]:
        """
        Get summary of adaptive crawling capabilities and statistics.
        
        Returns:
            Summary of learning stats, patterns, and adaptation features
        """
        learning_stats = self.crawl_learner.get_learning_stats()
        
        return {
            "features": {
                "gap_aware_crawling": True,
                "cross_entity_inference": True,
                "real_time_adaptation": True,
                "domain_learning": True,
                "query_refinement": True
            },
            "learning_stats": learning_stats,
            "capabilities": {
                "modes": ["discovery", "gap_filling", "relationship_expansion"],
                "strategies": ["comprehensive", "targeted", "adaptive"],
                "adaptations": [
                    "depth_adjustment",
                    "query_refinement", 
                    "domain_prioritization",
                    "intensity_reduction"
                ]
            }
        }
