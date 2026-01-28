"""
Adaptive Crawler Service.

Intelligently adapts crawling strategy based on entity gaps, learned patterns,
and real-time feedback.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from urllib.parse import urlparse

from ..database.store import PersistenceStore
from ..discover.crawl_learner import CrawlLearner
from ..discover.crawl_modes import EntityAwareCrawler, CrawlMode
from ..extractor.llm import LLMIntelExtractor
from .entity_gap_analyzer import EntityGapAnalyzer


logger = logging.getLogger(__name__)


# Registry domains to avoid marking as official
REGISTRY_DOMAINS = [
    'google.com', 'wikipedia.org', 'linkedin.com',
    'facebook.com', 'twitter.com', 'youtube.com',
    'instagram.com', 'reddit.com'
]


class AdaptiveCrawlerService:
    """
    Orchestrates intelligent, adaptive crawling based on entity analysis
    and learned patterns.
    """
    
    def __init__(
        self, 
        store: PersistenceStore,
        llm: LLMIntelExtractor,
        crawl_learner: CrawlLearner,
        vector_store=None
    ):
        """
        Initialize the adaptive crawler.
        
        Args:
            store: Database store
            llm: LLM extractor for intelligence gathering
            crawl_learner: Learner tracking crawl patterns
            vector_store: Optional vector store for embeddings
        """
        self.store = store
        self.llm = llm
        self.crawl_learner = crawl_learner
        self.vector_store = vector_store
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
        from ..search import collect_candidates_simple
        from ..explorer.engine import IntelligentExplorer
        from ..types.entity.profile import EntityProfile, EntityType
        
        self.logger.info(f"Starting intelligent crawl for '{entity_name}'")
        
        # Step 1: Generate crawl plan
        plan = self.gap_analyzer.generate_crawl_plan(entity_name, entity_type)
        
        self.logger.info(f"Crawl mode: {plan['mode']}, strategy: {plan['strategy']}")
        
        # Step 2: Select appropriate crawl mode and entity
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
        
        # Step 4: Initialize results tracking
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
            "learning_stats": {},
            "seed_urls": [],
            "official_domains": []
        }
        
        # For gap-filling mode, track which gaps we're targeting
        if plan['mode'] == 'gap_filling':
            target_gaps = plan['analysis'].get('missing_fields', [])
            results['target_gaps'] = [g['field'] for g in target_gaps]
        
        # Step 5: Execute intelligent crawl using IntelligentExplorer
        try:
            # Map entity type string to EntityType enum
            entity_type_enum = EntityType.COMPANY  # Default
            if entity_type:
                type_str = entity_type.upper()
                if hasattr(EntityType, type_str):
                    entity_type_enum = EntityType[type_str]
            elif plan.get('entity_type'):
                type_str = plan['entity_type'].upper()
                if hasattr(EntityType, type_str):
                    entity_type_enum = EntityType[type_str]
            
            # Create entity profile
            profile = EntityProfile(
                name=entity_name,
                entity_type=entity_type_enum,
                location_hint=plan.get('location', ''),
                official_domains=[]
            )
            
            # Collect seed URLs from queries
            seed_urls = []
            official_domains = []
            
            if queries:
                self.logger.info(f"Collecting seed URLs from {len(queries)} queries")
                # Use first 3-5 queries to generate seeds
                for query in queries[:5]:
                    try:
                        candidates = collect_candidates_simple([query], limit=5)
                        self.logger.debug(f"Received {len(candidates)} candidates for query '{query}'")
                        
                        for candidate in candidates:
                            # Handle both dict and string candidates defensively
                            url = None
                            if isinstance(candidate, dict):
                                url = candidate.get('href')
                            elif isinstance(candidate, str):
                                # Direct URL string
                                url = candidate
                            else:
                                self.logger.debug(
                                    f"Skipping candidate with unexpected type {type(candidate)} "
                                    f"for query '{query}'"
                                )
                                continue
                            
                            if url and url not in seed_urls:
                                seed_urls.append(url)
                                # Extract domain for official domain detection
                                try:
                                    domain = urlparse(url).netloc.lower()
                                    # Remove www. prefix if present
                                    if domain.startswith('www.'):
                                        domain = domain[4:]
                                    # Avoid registry domains (exact match or subdomain)
                                    is_registry = any(
                                        domain == reg or domain.endswith('.' + reg)
                                        for reg in REGISTRY_DOMAINS
                                    )
                                    if domain and not is_registry:
                                        if domain not in official_domains:
                                            official_domains.append(domain)
                                except Exception:
                                    pass
                    except Exception as e:
                        self.logger.warning(f"Failed to collect candidates for query '{query}': {e}")
            
            results['seed_urls'] = seed_urls[:max_pages]  # Limit seeds
            results['official_domains'] = official_domains
            profile.official_domains = official_domains
            
            if not seed_urls:
                self.logger.warning("No seed URLs found, crawl cannot proceed")
                return results
            
            # Initialize explorer with intelligent features
            explorer = IntelligentExplorer(
                profile=profile,
                use_selenium=False,  # Use requests by default for speed
                max_pages_per_domain=min(10, max_pages // max(1, len(official_domains))),
                max_total_pages=max_pages,
                max_depth=max_depth,
                score_threshold=30.0,  # Moderate threshold
                persistence=self.store,
                vector_store=self.vector_store,  # Use the vector store for embeddings
                llm_extractor=self.llm,
                enable_llm_link_rank=False  # Disable for speed
            )
            
            # Execute exploration
            self.logger.info(f"Starting exploration with {len(seed_urls)} seed URLs")
            explored_data = explorer.explore(seed_urls[:max_pages], browser=None)
            
            results['pages_discovered'] = len(explored_data)
            results['explored_data_summary'] = {
                'total_pages': len(explored_data),
                'domains': list(set(urlparse(url).netloc for url in explored_data.keys()))
            }
            
            # Step 6: Analyze extraction results
            intel_count = 0
            relationships_count = 0
            
            with self.store.Session() as session:
                from ..database.models import Intelligence, Relationship
                
                # Count newly extracted intelligence
                if entity_id:
                    intel_records = session.query(Intelligence).filter(
                        Intelligence.entity_id == entity_id
                    ).all()
                    intel_count = len(intel_records)
                
                # Count relationships
                relationships = session.query(Relationship).all()
                relationships_count = len(relationships)
            
            results['intel_extracted'] = intel_count
            results['relationships_found'] = relationships_count
            
            # Step 7: Post-crawl gap analysis for gap-filling mode
            if plan['mode'] == 'gap_filling' and entity_id:
                post_analysis = self.gap_analyzer.analyze_entity_gaps(entity_id)
                pre_completeness = plan['analysis'].get('completeness_score', 0)
                post_completeness = post_analysis.get('completeness_score', 0)
                
                results['completeness_improvement'] = post_completeness - pre_completeness
                results['gaps_filled'] = [
                    gap['field'] for gap in target_gaps 
                    if gap['field'] not in [g['field'] for g in post_analysis.get('missing_fields', [])]
                ]
                results['new_gaps'] = post_analysis.get('missing_fields', [])
            
            self.logger.info(f"Crawl completed: {results['pages_discovered']} pages, "
                           f"{results['intel_extracted']} intel records")
            
        except Exception as e:
            self.logger.exception(f"Intelligent crawl execution failed: {e}")
            results['error'] = str(e)
        
        # Step 8: Update learning stats
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
