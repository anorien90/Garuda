"""
Phase 2: Dynamic Entity Management - Usage Examples
"""

# ============================================================
# Task 1: Crawl Modes and Entity-Aware Crawler
# ============================================================

from garuda_intel.discover.crawl_modes import CrawlMode, EntityAwareCrawler
from garuda_intel.types.entity.profile import EntityProfile
from garuda_intel.types.entity.type import EntityType
from garuda_intel.database.engine import SQLAlchemyStore
from garuda_intel.extractor.llm import LLMIntelExtractor

# Initialize components
store = SQLAlchemyStore("sqlite:///crawler.db")
llm_extractor = LLMIntelExtractor()
crawler = EntityAwareCrawler(store, llm_extractor)

# Example 1: Discovery Mode - Find seed URLs for unknown entity
profile = EntityProfile(
    name="Acme Corporation",
    entity_type=EntityType.COMPANY,
    location_hint="San Francisco, CA"
)

result = crawler.crawl_for_entity(profile, mode=CrawlMode.DISCOVERY)
print("Discovery queries:", result["queries"])
# Output: ["Acme Corporation official website", "Acme Corporation company information", ...]

# Example 2: Targeting Mode - Fill data gaps in known entity
entity_id = "existing-entity-uuid"
gaps = crawler.analyze_entity_gaps(entity_id)
print(f"Completeness: {gaps['completeness']*100:.1f}%")
print(f"Missing fields: {gaps['missing_fields']}")

result = crawler.crawl_for_entity(profile, mode=CrawlMode.TARGETING, entity_id=entity_id)
print("Targeted queries:", result["queries"])
# Output: ["Acme Corporation leadership team", "Acme Corporation headquarters address", ...]

# Example 3: Expansion Mode - Find related entities
profile = EntityProfile(
    name="Acme Corporation",
    entity_type=EntityType.COMPANY,
    aliases=["Acme Inc", "Acme Ltd"]
)

result = crawler.crawl_for_entity(profile, mode=CrawlMode.EXPANSION)
print("Expansion queries:", result["queries"])
# Output: ["Acme Corporation partners collaborations", "Acme Corporation acquisitions", ...]


# ============================================================
# Task 2: Entity Deduplication
# ============================================================

# Example 1: Find similar entities
similar = store.find_similar_entities(
    name="Microsoft Corporation",
    threshold=0.8,
    kind="company",
    embedder=llm_extractor
)
print(f"Found {len(similar)} similar entities")

# Example 2: Merge duplicate entities
success = store.merge_entities(
    source_id="duplicate-entity-uuid",
    target_id="canonical-entity-uuid"
)
if success:
    print("Entities merged successfully")

# Example 3: Resolve entity by aliases
entity_id = store.resolve_entity_aliases(
    name="Microsoft Corporation",
    aliases=["Microsoft", "MSFT", "Microsoft Corp"],
    kind="company"
)
if entity_id:
    print(f"Found entity: {entity_id}")

# Example 4: Traverse entity relationships
relations = store.get_entity_relations(
    entity_id="some-entity-uuid",
    direction="both",  # "outgoing", "incoming", or "both"
    max_depth=2
)
print(f"Entity: {relations['name']}")
print(f"Outgoing relations: {len(relations['outgoing'])}")
print(f"Incoming relations: {len(relations['incoming'])}")

# Example 5: Automatic deduplication
merged_map = store.deduplicate_entities(
    threshold=0.85,
    embedder=llm_extractor
)
print(f"Merged {len(merged_map)} duplicate entities")
for source_id, target_id in merged_map.items():
    print(f"  {source_id} -> {target_id}")


# ============================================================
# Task 3: Entity Profile with Gaps Tracking
# ============================================================

from datetime import datetime

# Create entity profile with completeness tracking
profile = EntityProfile(
    name="Acme Corporation",
    entity_type=EntityType.COMPANY,
    aliases=["Acme Inc"],
    location_hint="San Francisco",
    official_domains=["acme.com"],
    data_gaps=["financials", "products", "leadership"],
    completeness_score=0.45,
    last_enrichment=datetime.utcnow()
)

# Update after enrichment
if profile.completeness_score < 0.7:
    print(f"Entity needs enrichment: {profile.completeness_score:.1%} complete")
    print(f"Missing: {', '.join(profile.data_gaps)}")
    
    # Run targeted crawl
    result = crawler.crawl_for_entity(profile, mode=CrawlMode.TARGETING)
    
    # After crawling, update profile
    profile.completeness_score = 0.75
    profile.data_gaps = ["financials"]
    profile.last_enrichment = datetime.utcnow()

print(f"Updated completeness: {profile.completeness_score:.1%}")
