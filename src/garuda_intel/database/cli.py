"""
Database CLI for Garuda Intel.

Provides command-line interface for database operations including:
- Entity management (CRUD)
- Dynamic field management
- Relationship queries
- Schema introspection
"""

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func

from .engine import SQLAlchemyStore
from .models import (
    Entity,
    Relationship,
    Page,
    Intelligence,
    DynamicFieldDefinition,
    EntityFieldValue,
    FieldDiscoveryLog,
)


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger(__name__)


def get_store(db_url: str) -> SQLAlchemyStore:
    """Create database store from URL."""
    return SQLAlchemyStore(url=db_url)


# ============================================================================
# Entity Commands
# ============================================================================

def cmd_entity_list(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    """List entities in the database."""
    with store.Session() as session:
        stmt = select(Entity)
        
        if args.kind:
            stmt = stmt.where(Entity.kind == args.kind)
        if args.name:
            stmt = stmt.where(Entity.name.ilike(f"%{args.name}%"))
        
        stmt = stmt.order_by(Entity.created_at.desc()).limit(args.limit)
        
        entities = session.execute(stmt).scalars().all()
        
        if args.format == "json":
            print(json.dumps([
                {
                    "id": str(e.id),
                    "name": e.name,
                    "kind": e.kind,
                    "data": e.data,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in entities
            ], indent=2))
        else:
            print(f"\n{'ID':<40} {'Name':<30} {'Kind':<15} {'Created':<20}")
            print("-" * 105)
            for e in entities:
                created = e.created_at.strftime("%Y-%m-%d %H:%M") if e.created_at else "N/A"
                print(f"{str(e.id):<40} {e.name[:28]:<30} {(e.kind or 'N/A'):<15} {created:<20}")
        
        print(f"\nTotal: {len(entities)} entities")


def cmd_entity_get(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    """Get detailed information about an entity."""
    with store.Session() as session:
        entity = session.execute(
            select(Entity).where(Entity.id == args.entity_id)
        ).scalar_one_or_none()
        
        if not entity:
            print(f"Entity not found: {args.entity_id}")
            sys.exit(1)
        
        result = {
            "id": str(entity.id),
            "name": entity.name,
            "kind": entity.kind,
            "data": entity.data,
            "metadata_json": entity.metadata_json,
            "last_seen": entity.last_seen.isoformat() if entity.last_seen else None,
            "created_at": entity.created_at.isoformat() if entity.created_at else None,
            "updated_at": entity.updated_at.isoformat() if entity.updated_at else None,
        }
        
        # Get dynamic field values if any
        field_values = session.execute(
            select(EntityFieldValue)
            .where(EntityFieldValue.entity_id == entity.id)
            .where(EntityFieldValue.is_current == True)  # noqa: E712
        ).scalars().all()
        
        if field_values:
            result["dynamic_fields"] = [fv.to_dict() for fv in field_values]
        
        # Get relationships
        out_rels = session.execute(
            select(Relationship).where(Relationship.source_id == entity.id)
        ).scalars().all()
        
        in_rels = session.execute(
            select(Relationship).where(Relationship.target_id == entity.id)
        ).scalars().all()
        
        if out_rels or in_rels:
            result["relationships"] = {
                "outgoing": [
                    {
                        "target_id": str(r.target_id),
                        "type": r.relation_type,
                    }
                    for r in out_rels
                ],
                "incoming": [
                    {
                        "source_id": str(r.source_id),
                        "type": r.relation_type,
                    }
                    for r in in_rels
                ],
            }
        
        print(json.dumps(result, indent=2))


def cmd_entity_create(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    """Create a new entity."""
    data = json.loads(args.data) if args.data else None
    
    with store.Session() as session:
        entity = Entity(
            id=uuid.uuid4(),
            name=args.name,
            kind=args.kind,
            data=data,
            last_seen=datetime.now(timezone.utc),
        )
        session.add(entity)
        session.commit()
        
        print(f"Created entity: {entity.id}")
        print(json.dumps({
            "id": str(entity.id),
            "name": entity.name,
            "kind": entity.kind,
            "data": entity.data,
        }, indent=2))


def cmd_entity_update(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    """Update an existing entity."""
    with store.Session() as session:
        entity = session.execute(
            select(Entity).where(Entity.id == args.entity_id)
        ).scalar_one_or_none()
        
        if not entity:
            print(f"Entity not found: {args.entity_id}")
            sys.exit(1)
        
        if args.name:
            entity.name = args.name
        if args.kind:
            entity.kind = args.kind
        if args.data:
            entity.data = json.loads(args.data)
        
        entity.last_seen = datetime.now(timezone.utc)
        session.commit()
        
        print(f"Updated entity: {entity.id}")


def cmd_entity_delete(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    """Delete an entity."""
    with store.Session() as session:
        entity = session.execute(
            select(Entity).where(Entity.id == args.entity_id)
        ).scalar_one_or_none()
        
        if not entity:
            print(f"Entity not found: {args.entity_id}")
            sys.exit(1)
        
        if not args.force:
            confirm = input(f"Delete entity '{entity.name}'? [y/N]: ")
            if confirm.lower() != "y":
                print("Cancelled.")
                return
        
        session.delete(entity)
        session.commit()
        print(f"Deleted entity: {args.entity_id}")


# ============================================================================
# Dynamic Field Commands
# ============================================================================

def cmd_field_list(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    """List dynamic field definitions."""
    with store.Session() as session:
        stmt = select(DynamicFieldDefinition)
        
        if args.entity_type:
            stmt = stmt.where(DynamicFieldDefinition.entity_type == args.entity_type)
        if args.importance:
            stmt = stmt.where(DynamicFieldDefinition.importance == args.importance)
        if args.active_only:
            stmt = stmt.where(DynamicFieldDefinition.is_active == True)  # noqa: E712
        
        stmt = stmt.order_by(
            DynamicFieldDefinition.discovery_count.desc()
        ).limit(args.limit)
        
        fields = session.execute(stmt).scalars().all()
        
        if args.format == "json":
            print(json.dumps([f.to_dict() for f in fields], indent=2))
        else:
            print(f"\n{'Field Name':<25} {'Entity Type':<15} {'Importance':<15} {'Count':<8} {'Success':<8}")
            print("-" * 80)
            for f in fields:
                print(f"{f.field_name[:23]:<25} {(f.entity_type or 'any')[:13]:<15} "
                      f"{f.importance:<15} {f.discovery_count:<8} {f.success_rate:.1%}")
        
        print(f"\nTotal: {len(fields)} field definitions")


def cmd_field_create(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    """Create a new dynamic field definition."""
    schema = json.loads(args.schema) if args.schema else None
    
    with store.Session() as session:
        field = DynamicFieldDefinition(
            id=uuid.uuid4(),
            field_name=args.field_name,
            display_name=args.display_name,
            description=args.description,
            entity_type=args.entity_type,
            field_type=args.field_type,
            importance=args.importance,
            schema_json=schema,
            source=args.source or "user",
            is_active=True,
            last_seen_at=datetime.now(timezone.utc),
        )
        session.add(field)
        session.commit()
        
        print(f"Created field definition: {field.id}")
        print(json.dumps(field.to_dict(), indent=2))


def cmd_field_discover(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    """Discover fields from sample text using LLM."""
    from ..extractor.schema_discovery import DynamicSchemaDiscoverer, FieldImportance
    from ..types.entity import EntityProfile, EntityType
    
    discoverer = DynamicSchemaDiscoverer(
        ollama_url=args.ollama_url,
        model=args.model,
        cache_schemas=False,  # Don't use in-memory cache for CLI
    )
    
    # Read sample text
    if args.text:
        sample_text = args.text
    elif args.file:
        with open(args.file, "r") as f:
            sample_text = f.read()
    else:
        print("Reading from stdin (Ctrl+D to finish)...")
        sample_text = sys.stdin.read()
    
    # Create entity profile
    try:
        entity_type = EntityType(args.entity_type)
    except ValueError:
        entity_type = EntityType.COMPANY
    
    profile = EntityProfile(
        name=args.entity_name or "Unknown",
        entity_type=entity_type,
    )
    
    # Discover fields
    print(f"Discovering fields for {profile.name} ({entity_type.value})...")
    fields = discoverer.discover_fields(profile, sample_text, max_fields=args.max_fields)
    
    if not fields:
        print("No fields discovered.")
        return
    
    # Save to database if requested
    if args.save:
        with store.Session() as session:
            saved_count = 0
            for f in fields:
                # Check if field already exists
                existing = session.execute(
                    select(DynamicFieldDefinition)
                    .where(DynamicFieldDefinition.field_name == f.field_name)
                    .where(DynamicFieldDefinition.entity_type == args.entity_type)
                ).scalar_one_or_none()
                
                if existing:
                    # Update existing
                    existing.discovery_count += 1
                    existing.last_seen_at = datetime.now(timezone.utc)
                    if f.importance == FieldImportance.CRITICAL:
                        existing.importance = "critical"
                else:
                    # Create new
                    new_field = DynamicFieldDefinition(
                        id=uuid.uuid4(),
                        field_name=f.field_name,
                        description=f.description,
                        entity_type=args.entity_type,
                        field_type="text",
                        importance=f.importance.value,
                        example_values={"examples": [f.example]} if f.example else None,
                        source="llm",
                        is_active=True,
                        last_seen_at=datetime.now(timezone.utc),
                    )
                    session.add(new_field)
                    saved_count += 1
            
            session.commit()
            print(f"Saved {saved_count} new field definitions")
    
    # Output results
    if args.format == "json":
        print(json.dumps([f.to_dict() for f in fields], indent=2))
    else:
        print(f"\nDiscovered {len(fields)} fields:")
        print(f"\n{'Field Name':<25} {'Importance':<15} {'Description':<50}")
        print("-" * 90)
        for f in fields:
            print(f"{f.field_name:<25} {f.importance.value:<15} {f.description[:48]}")


def cmd_field_set_value(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    """Set a field value for an entity."""
    with store.Session() as session:
        # Verify entity exists
        entity = session.execute(
            select(Entity).where(Entity.id == args.entity_id)
        ).scalar_one_or_none()
        
        if not entity:
            print(f"Entity not found: {args.entity_id}")
            sys.exit(1)
        
        # Get field definition if exists
        field_def = session.execute(
            select(DynamicFieldDefinition)
            .where(DynamicFieldDefinition.field_name == args.field_name)
        ).scalar_one_or_none()
        
        # Mark old values as not current
        old_values = session.execute(
            select(EntityFieldValue)
            .where(EntityFieldValue.entity_id == entity.id)
            .where(EntityFieldValue.field_name == args.field_name)
            .where(EntityFieldValue.is_current == True)  # noqa: E712
        ).scalars().all()
        
        for old in old_values:
            old.is_current = False
        
        # Parse value based on type
        value_text = None
        value_number = None
        value_json = None
        
        if args.value_type == "number":
            value_number = float(args.value)
        elif args.value_type == "json":
            value_json = json.loads(args.value)
        else:
            value_text = args.value
        
        # Create new field value
        field_value = EntityFieldValue(
            id=uuid.uuid4(),
            entity_id=entity.id,
            field_definition_id=field_def.id if field_def else None,
            field_name=args.field_name,
            value_text=value_text,
            value_number=value_number,
            value_json=value_json,
            confidence=args.confidence,
            extraction_method="user",
            source_url=args.source_url,
            is_current=True,
        )
        session.add(field_value)
        session.commit()
        
        print(f"Set {args.field_name}={args.value} for entity {entity.name}")
        print(json.dumps(field_value.to_dict(), indent=2))


def cmd_field_get_values(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    """Get field values for an entity."""
    with store.Session() as session:
        stmt = select(EntityFieldValue).where(
            EntityFieldValue.entity_id == args.entity_id
        )
        
        if args.current_only:
            stmt = stmt.where(EntityFieldValue.is_current == True)  # noqa: E712
        if args.field_name:
            stmt = stmt.where(EntityFieldValue.field_name == args.field_name)
        
        values = session.execute(stmt).scalars().all()
        
        if args.format == "json":
            print(json.dumps([v.to_dict() for v in values], indent=2))
        else:
            print(f"\n{'Field Name':<25} {'Value':<40} {'Confidence':<12} {'Current':<8}")
            print("-" * 90)
            for v in values:
                val = str(v.get_value())[:38]
                print(f"{v.field_name:<25} {val:<40} {v.confidence:.2f}       {'Yes' if v.is_current else 'No'}")


# ============================================================================
# Stats and Inspection Commands
# ============================================================================

def cmd_stats(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    """Show database statistics."""
    with store.Session() as session:
        stats = {}
        
        # Count entities
        stats["entities"] = session.execute(
            select(func.count(Entity.id))
        ).scalar() or 0
        
        # Count by kind
        kind_counts = session.execute(
            select(Entity.kind, func.count(Entity.id))
            .group_by(Entity.kind)
        ).all()
        stats["entities_by_kind"] = {k or "unknown": c for k, c in kind_counts}
        
        # Count relationships
        stats["relationships"] = session.execute(
            select(func.count(Relationship.id))
        ).scalar() or 0
        
        # Count pages
        stats["pages"] = session.execute(
            select(func.count(Page.id))
        ).scalar() or 0
        
        # Count intelligence
        stats["intelligence"] = session.execute(
            select(func.count(Intelligence.id))
        ).scalar() or 0
        
        # Count dynamic fields
        stats["field_definitions"] = session.execute(
            select(func.count(DynamicFieldDefinition.id))
        ).scalar() or 0
        
        stats["field_values"] = session.execute(
            select(func.count(EntityFieldValue.id))
        ).scalar() or 0
        
        stats["discovery_logs"] = session.execute(
            select(func.count(FieldDiscoveryLog.id))
        ).scalar() or 0
        
        if args.format == "json":
            print(json.dumps(stats, indent=2))
        else:
            print("\n=== Garuda Intel Database Statistics ===\n")
            print(f"  Entities:          {stats['entities']:>10}")
            for kind, count in stats["entities_by_kind"].items():
                print(f"    - {kind}:          {count:>10}")
            print(f"  Relationships:     {stats['relationships']:>10}")
            print(f"  Pages:             {stats['pages']:>10}")
            print(f"  Intelligence:      {stats['intelligence']:>10}")
            print(f"\n  Field Definitions: {stats['field_definitions']:>10}")
            print(f"  Field Values:      {stats['field_values']:>10}")
            print(f"  Discovery Logs:    {stats['discovery_logs']:>10}")


def cmd_init_db(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    """Initialize/migrate database tables."""
    from .models import Base
    
    print(f"Initializing database: {args.db_url}")
    Base.metadata.create_all(store.engine)
    print("Database tables created/updated successfully.")


# ============================================================================
# Main CLI Parser
# ============================================================================

def create_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="garuda-db",
        description="Garuda Intel Database CLI - Manage entities, fields, and relationships",
    )
    parser.add_argument(
        "--db-url",
        default="sqlite:///crawler.db",
        help="Database URL (default: sqlite:///crawler.db)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # ==================== Entity Commands ====================
    
    # entity list
    entity_list = subparsers.add_parser("entity-list", help="List entities")
    entity_list.add_argument("--kind", help="Filter by entity kind")
    entity_list.add_argument("--name", help="Filter by name (partial match)")
    entity_list.add_argument("--limit", type=int, default=50, help="Maximum results")
    entity_list.add_argument("--format", choices=["table", "json"], default="table")
    
    # entity get
    entity_get = subparsers.add_parser("entity-get", help="Get entity details")
    entity_get.add_argument("entity_id", type=uuid.UUID, help="Entity UUID")
    
    # entity create
    entity_create = subparsers.add_parser("entity-create", help="Create entity")
    entity_create.add_argument("name", help="Entity name")
    entity_create.add_argument("--kind", default="unknown", help="Entity kind (company, person, etc.)")
    entity_create.add_argument("--data", help="JSON data payload")
    
    # entity update
    entity_update = subparsers.add_parser("entity-update", help="Update entity")
    entity_update.add_argument("entity_id", type=uuid.UUID, help="Entity UUID")
    entity_update.add_argument("--name", help="New name")
    entity_update.add_argument("--kind", help="New kind")
    entity_update.add_argument("--data", help="New JSON data")
    
    # entity delete
    entity_delete = subparsers.add_parser("entity-delete", help="Delete entity")
    entity_delete.add_argument("entity_id", type=uuid.UUID, help="Entity UUID")
    entity_delete.add_argument("-f", "--force", action="store_true", help="Skip confirmation")
    
    # ==================== Field Commands ====================
    
    # field list
    field_list = subparsers.add_parser("field-list", help="List field definitions")
    field_list.add_argument("--entity-type", help="Filter by entity type")
    field_list.add_argument("--importance", choices=["critical", "important", "supplementary"])
    field_list.add_argument("--active-only", action="store_true", help="Only active fields")
    field_list.add_argument("--limit", type=int, default=100, help="Maximum results")
    field_list.add_argument("--format", choices=["table", "json"], default="table")
    
    # field create
    field_create = subparsers.add_parser("field-create", help="Create field definition")
    field_create.add_argument("field_name", help="Field name (snake_case)")
    field_create.add_argument("--display-name", help="Human-readable name")
    field_create.add_argument("--description", help="Field description")
    field_create.add_argument("--entity-type", help="Entity type this applies to")
    field_create.add_argument("--field-type", default="text", 
                              choices=["text", "number", "date", "list", "object"])
    field_create.add_argument("--importance", default="supplementary",
                              choices=["critical", "important", "supplementary"])
    field_create.add_argument("--schema", help="JSON schema for complex fields")
    field_create.add_argument("--source", help="Source of this definition")
    
    # field discover
    field_discover = subparsers.add_parser("field-discover", help="Discover fields using LLM")
    field_discover.add_argument("--entity-name", help="Entity name for context")
    field_discover.add_argument("--entity-type", default="company", help="Entity type")
    field_discover.add_argument("--text", help="Sample text to analyze")
    field_discover.add_argument("--file", help="File containing sample text")
    field_discover.add_argument("--save", action="store_true", help="Save discovered fields to DB")
    field_discover.add_argument("--max-fields", type=int, default=15, help="Max fields to discover")
    field_discover.add_argument("--ollama-url", default="http://localhost:11434/api/generate")
    field_discover.add_argument("--model", default="granite3.1-dense:8b")
    field_discover.add_argument("--format", choices=["table", "json"], default="table")
    
    # field set-value
    field_set = subparsers.add_parser("field-set", help="Set field value for entity")
    field_set.add_argument("entity_id", type=uuid.UUID, help="Entity UUID")
    field_set.add_argument("field_name", help="Field name")
    field_set.add_argument("value", help="Field value")
    field_set.add_argument("--value-type", choices=["text", "number", "json"], default="text")
    field_set.add_argument("--confidence", type=float, default=1.0, help="Confidence score")
    field_set.add_argument("--source-url", help="Source URL for this value")
    
    # field get-values
    field_get = subparsers.add_parser("field-get", help="Get field values for entity")
    field_get.add_argument("entity_id", type=uuid.UUID, help="Entity UUID")
    field_get.add_argument("--field-name", help="Specific field name")
    field_get.add_argument("--current-only", action="store_true", default=True, 
                          help="Only current values")
    field_get.add_argument("--format", choices=["table", "json"], default="table")
    
    # ==================== Graph Search Commands ====================
    
    # graph search
    graph_search = subparsers.add_parser("graph-search", help="Search entities with hybrid SQL + semantic")
    graph_search.add_argument("query", help="Search query")
    graph_search.add_argument("--kind", help="Entity kind filter")
    graph_search.add_argument("--threshold", type=float, default=0.7, help="Semantic similarity threshold")
    graph_search.add_argument("--limit", type=int, default=20, help="Maximum results")
    graph_search.add_argument("--format", choices=["table", "json"], default="table")
    
    # graph traverse
    graph_traverse = subparsers.add_parser("graph-traverse", help="Traverse entity relationships")
    graph_traverse.add_argument("entity_id", type=uuid.UUID, help="Starting entity UUID")
    graph_traverse.add_argument("--depth", type=int, default=2, help="Maximum traversal depth")
    graph_traverse.add_argument("--top-n", type=int, default=10, help="Top N entities per depth")
    graph_traverse.add_argument("--relation-types", nargs="+", help="Filter by relation types")
    graph_traverse.add_argument("--format", choices=["table", "json"], default="json")
    
    # graph path
    graph_path = subparsers.add_parser("graph-path", help="Find path between two entities")
    graph_path.add_argument("source_id", type=uuid.UUID, help="Source entity UUID")
    graph_path.add_argument("target_id", type=uuid.UUID, help="Target entity UUID")
    graph_path.add_argument("--max-depth", type=int, default=5, help="Maximum path length")
    graph_path.add_argument("--format", choices=["table", "json"], default="table")
    
    # ==================== Deduplication Commands ====================
    
    # dedupe find
    dedupe_find = subparsers.add_parser("dedupe-find", help="Find duplicate entities")
    dedupe_find.add_argument("name", help="Entity name to find duplicates for")
    dedupe_find.add_argument("--kind", help="Entity kind filter")
    dedupe_find.add_argument("--threshold", type=float, default=0.85, help="Similarity threshold")
    dedupe_find.add_argument("--format", choices=["table", "json"], default="table")
    
    # dedupe scan
    dedupe_scan = subparsers.add_parser("dedupe-scan", help="Scan for duplicate entities")
    dedupe_scan.add_argument("--kind", help="Entity kind filter")
    dedupe_scan.add_argument("--threshold", type=float, default=0.9, help="Similarity threshold")
    dedupe_scan.add_argument("--merge", action="store_true", help="Actually merge duplicates (dangerous!)")
    dedupe_scan.add_argument("--format", choices=["table", "json"], default="table")
    
    # dedupe merge
    dedupe_merge = subparsers.add_parser("dedupe-merge", help="Merge two entities")
    dedupe_merge.add_argument("source_id", type=uuid.UUID, help="Source entity UUID (to be deleted)")
    dedupe_merge.add_argument("target_id", type=uuid.UUID, help="Target entity UUID (to keep)")
    dedupe_merge.add_argument("-f", "--force", action="store_true", help="Skip confirmation")
    
    # ==================== Relationship Commands ====================
    
    # rel record
    rel_record = subparsers.add_parser("rel-record", help="Record a relationship (boosts confidence if exists)")
    rel_record.add_argument("source_id", type=uuid.UUID, help="Source entity UUID")
    rel_record.add_argument("target_id", type=uuid.UUID, help="Target entity UUID")
    rel_record.add_argument("relation_type", help="Relationship type")
    rel_record.add_argument("--source-url", help="Source URL where relationship was found")
    
    # rel high-confidence
    rel_high = subparsers.add_parser("rel-high-confidence", help="List high-confidence relationships")
    rel_high.add_argument("--min-confidence", type=float, default=0.7, help="Minimum confidence")
    rel_high.add_argument("--min-occurrences", type=int, default=2, help="Minimum occurrences")
    rel_high.add_argument("--limit", type=int, default=50, help="Maximum results")
    rel_high.add_argument("--format", choices=["table", "json"], default="table")
    
    # ==================== Utility Commands ====================
    
    # stats
    stats = subparsers.add_parser("stats", help="Show database statistics")
    stats.add_argument("--format", choices=["table", "json"], default="table")
    
    # init
    subparsers.add_parser("init", help="Initialize database tables")
    
    # ==================== Multi-Database Commands ====================
    
    subparsers.add_parser("db-list", help="List all registered databases")
    
    db_create = subparsers.add_parser("db-create", help="Create a new database")
    db_create.add_argument("name", help="Database name")
    db_create.add_argument("--description", default="", help="Database description")
    db_create.add_argument("--activate", action="store_true", help="Switch to the new database")
    
    db_switch = subparsers.add_parser("db-switch", help="Switch active database")
    db_switch.add_argument("name", help="Database name to switch to")
    
    db_delete = subparsers.add_parser("db-delete", help="Delete a database")
    db_delete.add_argument("name", help="Database name to delete")
    db_delete.add_argument("--delete-files", action="store_true", help="Also delete db file and Qdrant collection")
    
    db_merge = subparsers.add_parser("db-merge", help="Merge source database into target")
    db_merge.add_argument("source", help="Source database name")
    db_merge.add_argument("target", help="Target database name")
    
    db_search = subparsers.add_parser("db-search", help="Global search across all databases")
    db_search.add_argument("query", help="Search query")
    db_search.add_argument("--limit", type=int, default=10, help="Results per database")
    
    return parser


# ============================================================================
# Graph Search Commands
# ============================================================================

def cmd_graph_search(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    """Search entities using hybrid SQL + semantic search."""
    from ..extractor.entity_merger import GraphSearchEngine
    
    engine = GraphSearchEngine(store.Session)
    results = engine.search_entities(
        query=args.query,
        kind=args.kind,
        semantic_threshold=args.threshold,
        limit=args.limit,
    )
    
    if args.format == "json":
        print(json.dumps(results, indent=2))
    else:
        print(f"\n{'Name':<40} {'Kind':<15} {'Match':<12} {'Score':<8}")
        print("-" * 80)
        for r in results:
            e = r["entity"]
            print(f"{e['name'][:38]:<40} {(e['kind'] or 'N/A'):<15} {r['match_type']:<12} {r['score']:.2f}")
        print(f"\nTotal: {len(results)} entities")


def cmd_graph_traverse(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    """Traverse entity relationships from starting entity."""
    from ..extractor.entity_merger import GraphSearchEngine
    
    engine = GraphSearchEngine(store.Session)
    result = engine.traverse_graph(
        entity_ids=[str(args.entity_id)],
        max_depth=args.depth,
        top_n_per_depth=args.top_n,
        relation_types=args.relation_types,
    )
    
    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        print("\n=== Root Entities ===")
        for e in result["root_entities"]:
            print(f"  {e['name']} ({e['kind']})")
        
        for depth, data in result["depths"].items():
            print(f"\n=== Depth {depth} ({data['entity_count']} entities) ===")
            for item in data["entities"]:
                e = item["entity"]
                rel = item["relation_type"]
                direction = item["direction"]
                print(f"  {e['name']} ({e['kind']}) [{rel}, {direction}]")


def cmd_graph_path(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    """Find path between two entities."""
    from ..extractor.entity_merger import GraphSearchEngine
    
    engine = GraphSearchEngine(store.Session)
    path = engine.find_path(
        source_id=str(args.source_id),
        target_id=str(args.target_id),
        max_depth=args.max_depth,
    )
    
    if path is None:
        print("No path found between entities.")
        sys.exit(1)
    
    if args.format == "json":
        print(json.dumps(path, indent=2))
    else:
        print("\nPath found:")
        for i, step in enumerate(path):
            e = step["entity"]
            rel = step.get("relationship")
            
            if rel:
                print(f"  {i+1}. {e['name']} ({e['kind']}) -- [{rel['type']}] -->")
            else:
                print(f"  {i+1}. {e['name']} ({e['kind']})")


# ============================================================================
# Deduplication Commands
# ============================================================================

def cmd_dedupe_find(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    """Find duplicate entities for a given name."""
    from ..extractor.entity_merger import SemanticEntityDeduplicator
    
    deduplicator = SemanticEntityDeduplicator(store.Session)
    results = deduplicator.find_semantic_duplicates(
        name=args.name,
        kind=args.kind,
        threshold=args.threshold,
    )
    
    if args.format == "json":
        print(json.dumps(results, indent=2))
    else:
        print(f"\n{'Name':<40} {'Kind':<15} {'Match':<12} {'Similarity':<10}")
        print("-" * 80)
        for r in results:
            e = r["entity"]
            print(f"{e['name'][:38]:<40} {(e['kind'] or 'N/A'):<15} {r['match_type']:<12} {r['similarity']:.2f}")
        print(f"\nTotal: {len(results)} potential duplicates")


def cmd_dedupe_scan(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    """Scan database for duplicate entities."""
    from ..extractor.entity_merger import SemanticEntityDeduplicator
    
    deduplicator = SemanticEntityDeduplicator(store.Session)
    report = deduplicator.deduplicate_entities(
        dry_run=not args.merge,
        threshold=args.threshold,
        kind=args.kind,
    )
    
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(f"\n=== Duplicate Scan Report ===")
        print(f"Duplicate groups found: {len(report['duplicates_found'])}")
        
        for i, group in enumerate(report["duplicates_found"][:10]):
            print(f"\n  Group {i+1}: {group['canonical']['name']}")
            for dup in group["duplicates"]:
                print(f"    - {dup['entity']['name']} (similarity: {dup['similarity']:.2f})")
        
        if report["merged"]:
            print(f"\nMerged: {len(report['merged'])} entities")
        
        if report["errors"]:
            print(f"\nErrors: {len(report['errors'])}")


def cmd_dedupe_merge(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    """Merge two entities."""
    from ..extractor.entity_merger import SemanticEntityDeduplicator
    
    deduplicator = SemanticEntityDeduplicator(store.Session)
    
    # Get entity names for confirmation
    with store.Session() as session:
        source = session.execute(
            select(Entity).where(Entity.id == args.source_id)
        ).scalar_one_or_none()
        target = session.execute(
            select(Entity).where(Entity.id == args.target_id)
        ).scalar_one_or_none()
        
        if not source:
            print(f"Source entity not found: {args.source_id}")
            sys.exit(1)
        if not target:
            print(f"Target entity not found: {args.target_id}")
            sys.exit(1)
        
        source_name = source.name
        target_name = target.name
        
        if not args.force:
            confirm = input(f"Merge '{source_name}' into '{target_name}'? [y/N]: ")
            if confirm.lower() != "y":
                print("Cancelled.")
                return
    
    # Perform merge using public API
    success = deduplicator.merge_entities(str(args.source_id), str(args.target_id))
    
    if success:
        print(f"Successfully merged '{source_name}' into '{target_name}'")
    else:
        print("Merge failed.")
        sys.exit(1)


# ============================================================================
# Relationship Commands
# ============================================================================

def cmd_rel_record(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    """Record a relationship, boosting confidence if it already exists."""
    from ..extractor.entity_merger import RelationshipConfidenceManager
    
    manager = RelationshipConfidenceManager(store.Session)
    result = manager.record_relationship(
        source_id=str(args.source_id),
        target_id=str(args.target_id),
        relation_type=args.relation_type,
        source_url=args.source_url,
    )
    
    status = "Created new" if result["is_new"] else "Updated existing"
    print(f"{status} relationship: {args.relation_type}")
    print(f"  Confidence: {result['confidence']:.2f}")
    print(f"  Occurrences: {result['occurrence_count']}")


def cmd_rel_high_confidence(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    """List high-confidence relationships."""
    from ..extractor.entity_merger import RelationshipConfidenceManager
    
    manager = RelationshipConfidenceManager(store.Session)
    results = manager.get_high_confidence_relationships(
        min_confidence=args.min_confidence,
        min_occurrences=args.min_occurrences,
        limit=args.limit,
    )
    
    if args.format == "json":
        print(json.dumps(results, indent=2))
    else:
        print(f"\n{'Type':<25} {'Confidence':<12} {'Occurrences':<12} {'Sources':<10}")
        print("-" * 65)
        for r in results:
            sources = len(r.get("sources", []))
            print(f"{r['relation_type'][:23]:<25} {r['confidence']:.2f}        {r['occurrence_count']:<12} {sources}")
        print(f"\nTotal: {len(results)} high-confidence relationships")


# ============================================================================
# Multi-Database Commands
# ============================================================================

def _get_db_manager(args):
    """Create a DatabaseManager from CLI args."""
    import os
    from ..services.database_manager import DatabaseManager
    data_dir = os.path.dirname(args.db_url.replace("sqlite:///", "")) or "/app/data"
    qdrant_url = os.environ.get("GARUDA_QDRANT_URL") or os.environ.get("QDRANT_URL")
    return DatabaseManager(data_dir=data_dir, qdrant_url=qdrant_url)


def cmd_db_list(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    mgr = _get_db_manager(args)
    dbs = mgr.list_databases()
    print(f"\n{'Name':<20} {'Active':<8} {'Collection':<25} {'Description'}")
    print("-" * 80)
    for db in dbs:
        active = "✓" if db.get("is_active") else ""
        print(f"{db['name']:<20} {active:<8} {db.get('qdrant_collection', ''):<25} {db.get('description', '')}")
    print(f"\nTotal: {len(dbs)} databases")


def cmd_db_create(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    mgr = _get_db_manager(args)
    info = mgr.create_database(args.name, description=args.description, set_active=args.activate)
    print(f"Created database: {info['name']}")
    print(f"  Path: {info['db_path']}")
    print(f"  Qdrant collection: {info['qdrant_collection']}")
    if args.activate:
        print("  (set as active)")


def cmd_db_switch(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    mgr = _get_db_manager(args)
    _, collection = mgr.switch_database(args.name)
    print(f"Switched to database: {args.name} (collection: {collection})")


def cmd_db_delete(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    mgr = _get_db_manager(args)
    mgr.delete_database(args.name, delete_files=args.delete_files)
    print(f"Deleted database: {args.name}")


def cmd_db_merge(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    mgr = _get_db_manager(args)
    stats = mgr.merge_databases(args.source, args.target)
    print(f"Merge {args.source} → {args.target} complete:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


def cmd_db_search(store: SQLAlchemyStore, args: argparse.Namespace) -> None:
    mgr = _get_db_manager(args)
    results = mgr.global_search(args.query, limit_per_db=args.limit)
    if not results:
        print("No results found.")
        return
    for db_name, hits in results.items():
        print(f"\n📂 {db_name}:")
        for hit in hits:
            if hit["type"] == "entity":
                print(f"  [entity] {hit['name']} ({hit.get('kind', '')})")
            else:
                print(f"  [intel]  {hit.get('entity_name', '?')} ({hit.get('entity_type', '')}) conf={hit.get('confidence', 0):.2f}")


def main() -> None:
    """Main entry point for the database CLI."""
    parser = create_parser()
    args = parser.parse_args()
    
    logger = setup_logging(args.verbose)
    
    # Create store
    store = get_store(args.db_url)
    
    # Dispatch to command handler
    commands = {
        "entity-list": cmd_entity_list,
        "entity-get": cmd_entity_get,
        "entity-create": cmd_entity_create,
        "entity-update": cmd_entity_update,
        "entity-delete": cmd_entity_delete,
        "field-list": cmd_field_list,
        "field-create": cmd_field_create,
        "field-discover": cmd_field_discover,
        "field-set": cmd_field_set_value,
        "field-get": cmd_field_get_values,
        "graph-search": cmd_graph_search,
        "graph-traverse": cmd_graph_traverse,
        "graph-path": cmd_graph_path,
        "dedupe-find": cmd_dedupe_find,
        "dedupe-scan": cmd_dedupe_scan,
        "dedupe-merge": cmd_dedupe_merge,
        "rel-record": cmd_rel_record,
        "rel-high-confidence": cmd_rel_high_confidence,
        "stats": cmd_stats,
        "init": cmd_init_db,
        "db-list": cmd_db_list,
        "db-create": cmd_db_create,
        "db-switch": cmd_db_switch,
        "db-delete": cmd_db_delete,
        "db-merge": cmd_db_merge,
        "db-search": cmd_db_search,
    }
    
    handler = commands.get(args.command)
    if handler:
        try:
            handler(store, args)
        except Exception as e:
            logger.error(f"Command failed: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
