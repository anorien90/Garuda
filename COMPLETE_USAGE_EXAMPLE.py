"""
Complete Usage Example: Garuda Intelligence Enhancement
Demonstrates all new features from Phases 1-4

This example shows how to:
1. Start a crawl from a known entity (e.g., Bill Gates)
2. Use entity-aware crawling to fill data gaps
3. Leverage relationship graphs and deduplication
4. Use adaptive learning for improved crawling
"""

from src.garuda_intel.types.entity import EntityProfile, EntityType
from src.garuda_intel.database.engine import SQLAlchemyStore
from src.garuda_intel.extractor.llm import LLMIntelExtractor
from src.garuda_intel.explorer.engine import IntelligentExplorer
from src.garuda_intel.discover.crawl_modes import EntityAwareCrawler, CrawlMode
from src.garuda_intel.database.relationship_manager import RelationshipManager
from src.garuda_intel.discover.crawl_learner import CrawlLearner
from src.garuda_intel.extractor.iterative_refiner import IterativeRefiner
from src.garuda_intel.extractor.strategy_selector import StrategySelector


# ============================================================================
# EXAMPLE 1: Starting with a Known Entity (Bill Gates)
# ============================================================================

def example_1_known_entity_crawl():
    """Crawl starting from a known entity to fill data gaps."""
    
    # Initialize components
    store = SQLAlchemyStore(db_url="sqlite:///garuda_intel.db")
    llm_extractor = LLMIntelExtractor(
        ollama_url="http://localhost:11434/api/generate",
        model="granite3.1-dense:8b"
    )
    
    # Create entity profile for Bill Gates
    bill_gates = EntityProfile(
        name="Bill Gates",
        entity_type=EntityType.PERSON,
        location_hint="Seattle, Washington",
        aliases=["William Henry Gates III", "William Gates"],
        official_domains=["gatesfoundation.org", "gatesnotes.com"]
    )
    
    # Step 1: Check if entity exists and analyze gaps
    entity_crawler = EntityAwareCrawler(store, llm_extractor)
    
    # Try to find existing entity
    existing_entities = store.find_similar_entities("Bill Gates", threshold=0.8)
    
    if existing_entities:
        print(f"Found existing entity: {existing_entities[0].name}")
        # Analyze what data is missing
        gaps = entity_crawler.analyze_entity_gaps(str(existing_entities[0].id))
        print(f"Data gaps: {gaps['missing_fields']}")
        print(f"Completeness: {gaps['completeness_score']:.1%}")
        
        # Generate targeted queries to fill gaps
        queries = entity_crawler.generate_targeted_queries(bill_gates, gaps)
        print(f"Generated {len(queries)} targeted queries")
        
        # Execute targeted crawl
        result = entity_crawler.crawl_for_entity(bill_gates, mode=CrawlMode.TARGETING)
        print(f"Crawled {len(result['urls'])} URLs to fill gaps")
    else:
        print("Entity not found, starting discovery crawl...")
        # New entity - do discovery crawl
        result = entity_crawler.crawl_for_entity(bill_gates, mode=CrawlMode.DISCOVERY)
        print(f"Discovered {len(result['urls'])} URLs")


# ============================================================================
# EXAMPLE 2: Relationship Graph Analysis
# ============================================================================

def example_2_relationship_graphs():
    """Analyze entity relationships and build knowledge graphs."""
    
    store = SQLAlchemyStore(db_url="sqlite:///garuda_intel.db")
    llm_extractor = LLMIntelExtractor()
    
    # Initialize relationship manager
    rel_manager = RelationshipManager(store, llm_extractor)
    
    # Find Bill Gates entity
    entities = store.find_similar_entities("Bill Gates", threshold=0.8)
    if not entities:
        print("Entity not found")
        return
    
    bill_gates_id = str(entities[0].id)
    
    # Get all relationships
    relations = store.get_entity_relations(
        bill_gates_id, 
        direction="both",  # incoming and outgoing
        max_depth=2         # 2 levels deep
    )
    
    print(f"Found {len(relations['outgoing'])} outgoing relationships")
    print(f"Found {len(relations['incoming'])} incoming relationships")
    
    # Infer additional relationships from context
    related_entity_ids = [r['target_id'] for r in relations['outgoing']]
    inferred = rel_manager.infer_relationships(
        entity_ids=[bill_gates_id] + related_entity_ids[:5]
    )
    print(f"Inferred {len(inferred)} additional relationships")
    
    # Cluster entities by relationship type
    clusters = rel_manager.cluster_entities_by_relation(relation_types=["employs", "founded"])
    for rel_type, entity_pairs in clusters.items():
        print(f"{rel_type}: {len(entity_pairs)} connections")
    
    # Export as graph for visualization
    graph_data = rel_manager.get_relationship_graph(
        entity_ids=[bill_gates_id],
        min_confidence=0.7
    )
    print(f"Graph has {len(graph_data['nodes'])} nodes and {len(graph_data['edges'])} edges")


# ============================================================================
# EXAMPLE 3: Entity Deduplication and Merging
# ============================================================================

def example_3_deduplication():
    """Demonstrate entity deduplication and merging."""
    
    store = SQLAlchemyStore(db_url="sqlite:///garuda_intel.db")
    
    # Find potential duplicates
    duplicates = store.find_similar_entities("Microsoft Corporation", threshold=0.75)
    print(f"Found {len(duplicates)} similar entities")
    
    for dup in duplicates:
        print(f"  - {dup.name} (ID: {dup.id})")
    
    # Automatic deduplication
    merge_map = store.deduplicate_entities(threshold=0.85)
    print(f"Automatically merged {len(merge_map)} duplicate entities")
    
    # Manual merge if needed
    if len(duplicates) >= 2:
        # Merge second into first (keeping first as canonical)
        success = store.merge_entities(
            source_id=str(duplicates[1].id),
            target_id=str(duplicates[0].id)
        )
        if success:
            print(f"Merged {duplicates[1].name} into {duplicates[0].name}")


# ============================================================================
# EXAMPLE 4: Adaptive Learning from Crawls
# ============================================================================

def example_4_adaptive_learning():
    """Demonstrate how the system learns from crawl history."""
    
    store = SQLAlchemyStore(db_url="sqlite:///garuda_intel.db")
    llm_extractor = LLMIntelExtractor()
    
    # Initialize learner
    learner = CrawlLearner(store)
    
    # Check domain reliability
    domain = "gatesfoundation.org"
    reliability = learner.get_domain_reliability(domain)
    print(f"Domain {domain} reliability: {reliability:.2%}")
    
    # Get successful patterns for person entities
    patterns = learner.get_successful_patterns(EntityType.PERSON.value)
    print(f"Found {len(patterns)} successful patterns for PERSON entities")
    
    for pattern in patterns[:3]:
        print(f"  - {pattern['page_type']}: {pattern['avg_quality']:.2f} quality")
    
    # Get extraction strategy suggestion
    strategy = learner.suggest_page_strategy(
        url="https://en.wikipedia.org/wiki/Bill_Gates",
        page_type="bio"
    )
    print(f"Suggested strategy: {strategy}")


# ============================================================================
# EXAMPLE 5: Iterative Refinement
# ============================================================================

def example_5_iterative_refinement():
    """Demonstrate iterative extraction refinement."""
    
    store = SQLAlchemyStore(db_url="sqlite:///garuda_intel.db")
    llm_extractor = LLMIntelExtractor()
    
    # Initialize refiner
    refiner = IterativeRefiner(llm_extractor, store)
    
    # Find an entity
    entities = store.find_similar_entities("Bill Gates", threshold=0.8)
    if not entities:
        print("Entity not found")
        return
    
    entity_id = str(entities[0].id)
    
    # Get existing intelligence
    intel_records = store.get_intelligence_for_entity(entity_id)
    print(f"Found {len(intel_records)} intelligence records")
    
    # Detect contradictions
    contradictions = refiner.detect_contradictions(
        [{"data": r.data} for r in intel_records if r.data]
    )
    if contradictions:
        print(f"Found {len(contradictions)} contradictions:")
        for contra in contradictions:
            print(f"  - {contra['field']}: {contra['description']}")
    
    # Validate consistency of new data
    new_intel = {
        "basic_info": {
            "founded": "1975",  # Microsoft founding
            "industry": "Technology"
        }
    }
    
    is_valid, issues = refiner.validate_consistency(
        new_intel,
        [{"data": r.data} for r in intel_records if r.data]
    )
    print(f"New intel valid: {is_valid}")
    if issues:
        print(f"Issues: {', '.join(issues)}")


# ============================================================================
# EXAMPLE 6: Complete End-to-End Workflow
# ============================================================================

def example_6_complete_workflow():
    """Complete workflow demonstrating all features together."""
    
    print("=" * 70)
    print("COMPLETE GARUDA INTELLIGENCE WORKFLOW")
    print("=" * 70)
    
    # 1. Initialize all components
    store = SQLAlchemyStore(db_url="sqlite:///garuda_intel.db")
    llm_extractor = LLMIntelExtractor(
        ollama_url="http://localhost:11434/api/generate",
        model="granite3.1-dense:8b"
    )
    
    # 2. Define target entity
    target = EntityProfile(
        name="Satya Nadella",
        entity_type=EntityType.PERSON,
        location_hint="Redmond, Washington",
        aliases=["Satya Narayana Nadella"],
        official_domains=["microsoft.com"]
    )
    
    # 3. Check for existing data
    print("\n[1] Checking for existing entity...")
    existing = store.find_similar_entities(target.name, threshold=0.8)
    
    if existing:
        print(f"    Found existing entity: {existing[0].name}")
        entity_id = str(existing[0].id)
        
        # 4. Analyze gaps
        print("\n[2] Analyzing data gaps...")
        entity_crawler = EntityAwareCrawler(store, llm_extractor)
        gaps = entity_crawler.analyze_entity_gaps(entity_id)
        print(f"    Completeness: {gaps['completeness_score']:.1%}")
        print(f"    Missing fields: {', '.join(gaps['missing_fields'][:5])}")
        
        # 5. Execute targeted crawl
        print("\n[3] Executing targeted crawl to fill gaps...")
        result = entity_crawler.crawl_for_entity(target, mode=CrawlMode.TARGETING)
        print(f"    Crawled {len(result['urls'])} URLs")
    else:
        print("    No existing entity found")
        
        # 4. Discovery crawl
        print("\n[2] Executing discovery crawl...")
        entity_crawler = EntityAwareCrawler(store, llm_extractor)
        result = entity_crawler.crawl_for_entity(target, mode=CrawlMode.DISCOVERY)
        print(f"    Discovered {len(result['urls'])} URLs")
        entity_id = result.get('entity_id')
    
    if not entity_id:
        print("    Failed to get entity ID")
        return
    
    # 6. Deduplicate entities
    print("\n[4] Deduplicating entities...")
    merge_map = store.deduplicate_entities(threshold=0.85)
    print(f"    Merged {len(merge_map)} duplicates")
    
    # 7. Validate relationships
    print("\n[5] Validating relationships...")
    rel_manager = RelationshipManager(store, llm_extractor)
    report = rel_manager.validate_relationships(fix_invalid=True)
    print(f"    Valid: {report['valid']}/{report['total']}")
    print(f"    Fixed: {report['fixed']} issues")
    
    # 8. Build relationship graph
    print("\n[6] Building relationship graph...")
    relations = store.get_entity_relations(entity_id, direction="both", max_depth=1)
    print(f"    Outgoing: {len(relations['outgoing'])} relationships")
    print(f"    Incoming: {len(relations['incoming'])} relationships")
    
    # 9. Infer additional relationships
    print("\n[7] Inferring additional relationships...")
    related_ids = [r['target_id'] for r in relations['outgoing'][:5]]
    inferred = rel_manager.infer_relationships([entity_id] + related_ids)
    print(f"    Inferred: {len(inferred)} new relationships")
    
    # 10. Check learning metrics
    print("\n[8] Checking learning metrics...")
    learner = CrawlLearner(store)
    patterns = learner.get_successful_patterns(EntityType.PERSON.value)
    print(f"    Learned patterns: {len(patterns)}")
    
    print("\n[COMPLETE] Workflow finished successfully!")
    print("=" * 70)


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    import sys
    
    examples = {
        "1": ("Known Entity Crawl", example_1_known_entity_crawl),
        "2": ("Relationship Graphs", example_2_relationship_graphs),
        "3": ("Entity Deduplication", example_3_deduplication),
        "4": ("Adaptive Learning", example_4_adaptive_learning),
        "5": ("Iterative Refinement", example_5_iterative_refinement),
        "6": ("Complete Workflow", example_6_complete_workflow),
    }
    
    print("\n" + "=" * 70)
    print("GARUDA INTELLIGENCE ENHANCEMENT - USAGE EXAMPLES")
    print("=" * 70)
    print("\nAvailable examples:")
    for key, (name, _) in examples.items():
        print(f"  {key}. {name}")
    print("\nUsage: python COMPLETE_USAGE_EXAMPLE.py [example_number]")
    print("       python COMPLETE_USAGE_EXAMPLE.py 6  # Run complete workflow")
    print("=" * 70 + "\n")
    
    if len(sys.argv) > 1:
        example_num = sys.argv[1]
        if example_num in examples:
            name, func = examples[example_num]
            print(f"\nRunning Example {example_num}: {name}\n")
            func()
        else:
            print(f"Error: Example '{example_num}' not found")
    else:
        print("No example specified. Running complete workflow (Example 6)...\n")
        example_6_complete_workflow()
