"""
Agent CLI for Garuda Intel.

Provides command-line interface for agent operations including:
- Reflect & Refine mode (entity merging, data quality)
- Explore & Prioritize mode (entity graph exploration)
- Multidimensional search
"""

import argparse
import json
import logging
import sys
from datetime import datetime

from ..config import Settings
from ..database.engine import SQLAlchemyStore
from ..extractor.llm import LLMIntelExtractor
from ..services.agent_service import AgentService


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger(__name__)


def get_services(settings: Settings):
    """Initialize required services."""
    store = SQLAlchemyStore(url=settings.db_url)
    llm = LLMIntelExtractor(
        ollama_url=settings.ollama_url,
        model=settings.ollama_model,
        embedding_model=settings.embedding_model,
        summarize_timeout=settings.llm_summarize_timeout,
        extract_timeout=settings.llm_extract_timeout,
        reflect_timeout=settings.llm_reflect_timeout,
        summarize_retries=settings.llm_summarize_retries,
    )
    
    vector_store = None
    if settings.vector_enabled:
        try:
            from ..vector.engine import QdrantVectorStore
            vector_store = QdrantVectorStore(
                url=settings.qdrant_url,
                collection=settings.qdrant_collection
            )
        except Exception as e:
            logging.warning(f"Vector store unavailable: {e}")
    
    agent = AgentService(
        store=store,
        llm=llm,
        vector_store=vector_store,
        entity_merge_threshold=settings.agent_entity_merge_threshold,
        max_exploration_depth=settings.agent_max_exploration_depth,
        priority_unknown_weight=settings.agent_priority_unknown_weight,
        priority_relation_weight=settings.agent_priority_relation_weight,
    )
    
    return store, llm, vector_store, agent


# ============================================================================
# Reflect Commands
# ============================================================================

def cmd_reflect(settings: Settings, args: argparse.Namespace) -> None:
    """Run reflect & refine mode."""
    logger = setup_logging(args.verbose)
    logger.info("Starting reflect & refine mode...")
    
    _, _, _, agent = get_services(settings)
    
    target_entities = None
    if args.entities:
        target_entities = [e.strip() for e in args.entities.split(",")]
        logger.info(f"Targeting entities: {target_entities}")
    
    report = agent.reflect_and_refine(
        target_entities=target_entities,
        dry_run=args.dry_run,
    )
    
    if args.format == "json":
        print(json.dumps(report, indent=2, default=str))
    else:
        print("\n" + "=" * 60)
        print("REFLECT & REFINE REPORT")
        print("=" * 60)
        
        stats = report.get("statistics", {})
        print(f"\nEntities: {stats.get('entities_before', 0)} -> {stats.get('entities_after', 0)}")
        print(f"Merges performed: {stats.get('merges_performed', 0)}")
        print(f"Quality issues: {stats.get('quality_issues_found', 0)}")
        
        duplicates = report.get("duplicates_found", [])
        if duplicates:
            print(f"\n--- Duplicate Groups ({len(duplicates)}) ---")
            for group in duplicates[:10]:
                print(f"\n  Group: {group.get('normalized_name')}")
                for e in group.get("entities", []):
                    print(f"    - {e.get('name')} (kind={e.get('kind')}, relations={e.get('relation_count')})")
        
        issues = report.get("data_quality_issues", [])
        if issues:
            print(f"\n--- Data Quality Issues ({len(issues)}) ---")
            for issue in issues[:10]:
                print(f"\n  Entity: {issue.get('entity_name')}")
                for i in issue.get("issues", []):
                    print(f"    - {i}")
        
        if args.dry_run:
            print("\n[DRY RUN - No changes made]")
        
        print("\n" + "=" * 60)


# ============================================================================
# Explore Commands
# ============================================================================

def cmd_explore(settings: Settings, args: argparse.Namespace) -> None:
    """Run explore & prioritize mode."""
    logger = setup_logging(args.verbose)
    logger.info("Starting explore & prioritize mode...")
    
    _, _, _, agent = get_services(settings)
    
    root_entities = [e.strip() for e in args.entities.split(",")]
    logger.info(f"Root entities: {root_entities}")
    
    report = agent.explore_and_prioritize(
        root_entities=root_entities,
        max_depth=args.depth,
        top_n=args.top_n,
    )
    
    if args.format == "json":
        print(json.dumps(report, indent=2, default=str))
    else:
        print("\n" + "=" * 60)
        print("EXPLORE & PRIORITIZE REPORT")
        print("=" * 60)
        
        stats = report.get("statistics", {})
        print(f"\nUnique entities found: {stats.get('unique_entities', 0)}")
        print(f"Max depth reached: {stats.get('max_depth_reached', 0)}")
        print(f"Relations traversed: {stats.get('relations_traversed', 0)}")
        
        prioritized = report.get("prioritized_entities", [])
        if prioritized:
            print(f"\n--- Top Priority Entities ({len(prioritized)}) ---")
            print(f"\n{'Name':<30} {'Kind':<15} {'Depth':<6} {'Relations':<10} {'Priority':<8}")
            print("-" * 75)
            for e in prioritized:
                print(
                    f"{e.get('name', '')[:28]:<30} "
                    f"{(e.get('kind') or 'N/A'):<15} "
                    f"{e.get('depth_from_root', 0):<6} "
                    f"{e.get('relation_count', 0):<10} "
                    f"{e.get('priority_score', 0):.3f}"
                )
        
        if report.get("error"):
            print(f"\nError: {report['error']}")
        
        print("\n" + "=" * 60)


# ============================================================================
# Search Commands
# ============================================================================

def cmd_search(settings: Settings, args: argparse.Namespace) -> None:
    """Run multidimensional search."""
    logger = setup_logging(args.verbose)
    logger.info(f"Searching: {args.query}")
    
    _, _, _, agent = get_services(settings)
    
    result = agent.multidimensional_search(
        query=args.query,
        top_k=args.top_k,
        include_graph=not args.no_graph,
        graph_depth=args.graph_depth,
    )
    
    if args.format == "json":
        print(json.dumps(result, indent=2, default=str))
    else:
        print("\n" + "=" * 60)
        print("MULTIDIMENSIONAL SEARCH RESULTS")
        print("=" * 60)
        
        stats = result.get("statistics", {})
        print(f"\nQuery: {result.get('query')}")
        print(f"Embedding hits: {stats.get('embedding_hits', 0)}")
        print(f"Graph hits: {stats.get('graph_hits', 0)}")
        print(f"Unique results: {stats.get('unique_results', 0)}")
        
        combined = result.get("combined_results", [])
        if combined:
            print(f"\n--- Combined Results ({len(combined)}) ---")
            for i, r in enumerate(combined[:10], 1):
                print(f"\n{i}. {r.get('entity', r.get('url', 'Unknown'))}")
                print(f"   Source: {r.get('source', 'N/A')} | Score: {r.get('combined_score', r.get('score', 0)):.3f}")
                if r.get("text"):
                    print(f"   Text: {r['text'][:100]}...")
        
        if result.get("error"):
            print(f"\nError: {result['error']}")
        
        print("\n" + "=" * 60)


# ============================================================================
# Chat Commands
# ============================================================================

def cmd_chat(settings: Settings, args: argparse.Namespace) -> None:
    """Run agent chat."""
    import asyncio
    
    logger = setup_logging(args.verbose)
    logger.info("Chat: deep RAG search (embedding + graph + SQL)")
    
    _, _, _, agent = get_services(settings)
    
    # Run async chat
    async def run_chat():
        return await agent.chat_async(
            question=args.question,
            entity=args.entity,
        )
    
    response = asyncio.run(run_chat())
    
    if args.format == "json":
        print(json.dumps(response, indent=2, default=str))
    else:
        print("\n" + "=" * 60)
        print("AGENT CHAT (DEEP RAG)")
        print("=" * 60)
        
        print(f"\nQuestion: {response.get('question')}")
        if response.get("entity"):
            print(f"Entity: {response['entity']}")
        
        print(f"\n--- Answer ---")
        print(response.get("answer", "No answer generated"))
        
        context = response.get("context", [])
        if context:
            print(f"\n--- Context ({len(context)} items) ---")
            for i, c in enumerate(context[:5], 1):
                print(f"\n{i}. {c.get('name', c.get('entity', c.get('url', 'Unknown')))}")
                if c.get("text"):
                    print(f"   {c['text'][:100]}...")
        
        if response.get("error"):
            print(f"\nError: {response['error']}")
        
        print("\n" + "=" * 60)


# ============================================================================
# Autonomous Commands
# ============================================================================

def cmd_autonomous(settings: Settings, args: argparse.Namespace) -> None:
    """Run autonomous discovery mode."""
    logger = setup_logging(args.verbose)
    
    action = getattr(args, 'action', 'discover')
    logger.info(f"Starting autonomous mode: {action}...")

    _, _, _, agent = get_services(settings)

    # Dispatch based on action
    if action == "reflect-relate":
        report = agent.reflect_relate(
            target_entities=args.target_entities if hasattr(args, 'target_entities') else None,
            max_depth=args.depth,
            top_n=args.top_n if hasattr(args, 'top_n') else 20,
        )
    elif action == "investigate-crawl":
        report = agent.investigate_crawl(
            investigation_tasks=None,  # Auto-generate
            max_entities=args.max_entities,
            max_pages=args.max_pages,
            max_depth=args.depth,
            priority_threshold=args.priority_threshold,
        )
    elif action == "combined":
        report = agent.combined_autonomous(
            target_entities=args.target_entities if hasattr(args, 'target_entities') else None,
            max_entities=args.max_entities,
            max_pages=args.max_pages,
            max_depth=args.depth,
            priority_threshold=args.priority_threshold,
        )
    else:  # "discover"
        report = agent.autonomous_discover(
            max_entities=args.max_entities,
            priority_threshold=args.priority_threshold,
            max_depth=args.depth,
            auto_crawl=args.auto_crawl,
            max_pages=args.max_pages,
        )

    if args.format == "json":
        print(json.dumps(report, indent=2, default=str))
    else:
        print("\n" + "=" * 60)
        print(f"AUTONOMOUS MODE REPORT: {action.upper()}")
        print("=" * 60)

        stats = report.get("statistics", {})
        
        # Print mode-specific statistics
        if action == "reflect-relate":
            print(f"\nEntities analyzed: {stats.get('entities_analyzed', 0)}")
            print(f"Potential relations found: {stats.get('potential_relations_found', 0)}")
            print(f"Investigation tasks created: {stats.get('investigation_tasks_created', 0)}")
            
            potential_relations = report.get("potential_relations", [])
            if potential_relations:
                print(f"\n--- Potential Relations ({len(potential_relations)}) ---")
                for pr in potential_relations[:10]:
                    print(f"\n  {pr.get('entity_a')} ↔ {pr.get('entity_b')}")
                    print(f"    Confidence: {pr.get('confidence', 0):.2f} | {pr.get('reason', 'N/A')}")
            
            investigation_tasks = report.get("investigation_tasks", [])
            if investigation_tasks:
                print(f"\n--- Investigation Tasks ({len(investigation_tasks)}) ---")
                for task in investigation_tasks[:10]:
                    print(f"\n  [{task.get('task_type', 'N/A')}] {task.get('entity_name', 'Unknown')}")
                    if task.get('related_to'):
                        print(f"    Related to: {task.get('related_to')}")
                    print(f"    Reason: {task.get('reason', 'N/A')}")
                    print(f"    Priority: {task.get('priority', 0):.2f}")
        
        elif action == "investigate-crawl":
            print(f"\nTasks received: {stats.get('tasks_received', 0)}")
            print(f"Tasks processed: {stats.get('tasks_processed', 0)}")
            print(f"Crawl plans generated: {stats.get('crawl_plans_generated', 0)}")
            print(f"Crawls executed: {stats.get('crawls_executed', 0)}")
            print(f"Pages discovered: {stats.get('pages_discovered', 0)}")
            
            crawl_plans = report.get("crawl_plans", [])
            if crawl_plans:
                print(f"\n--- Crawl Plans ({len(crawl_plans)}) ---")
                for plan in crawl_plans[:10]:
                    print(f"\n  {plan.get('entity_name', 'Unknown')}")
                    print(f"    Mode: {plan.get('mode', '-')} | Strategy: {plan.get('strategy', '-')}")
            
            crawl_results = report.get("crawl_results", [])
            if crawl_results:
                print(f"\n--- Crawl Results ({len(crawl_results)}) ---")
                for result in crawl_results[:10]:
                    entity_name = result.get('entity_name', 'Unknown')
                    if 'error' in result:
                        print(f"\n  ✗ {entity_name}: {result.get('error', 'Unknown error')}")
                    else:
                        crawl_result = result.get('result', {})
                        pages = crawl_result.get('pages_crawled', 0)
                        print(f"\n  ✓ {entity_name}: {pages} pages crawled")
        
        elif action == "combined":
            print(f"\nTotal entities analyzed: {stats.get('total_entities_analyzed', 0)}")
            print(f"Total crawls executed: {stats.get('total_crawls_executed', 0)}")
            print(f"Total pages discovered: {stats.get('total_pages_discovered', 0)}")
            
            reflect_report = report.get("reflect_relate_report", {})
            investigate_report = report.get("investigate_crawl_report", {})
            
            print("\n--- Phase 1: Reflect & Relate ---")
            rr_stats = reflect_report.get("statistics", {})
            print(f"  Entities analyzed: {rr_stats.get('entities_analyzed', 0)}")
            print(f"  Potential relations: {rr_stats.get('potential_relations_found', 0)}")
            print(f"  Investigation tasks: {rr_stats.get('investigation_tasks_created', 0)}")
            
            print("\n--- Phase 2: Investigate Crawl ---")
            ic_stats = investigate_report.get("statistics", {})
            print(f"  Tasks processed: {ic_stats.get('tasks_processed', 0)}")
            print(f"  Crawls executed: {ic_stats.get('crawls_executed', 0)}")
            print(f"  Pages discovered: {ic_stats.get('pages_discovered', 0)}")
        
        else:  # "discover"
            print(f"\nEntities analyzed: {stats.get('entities_analyzed', 0)}")
            print(f"Dead ends found: {stats.get('dead_ends_found', 0)}")
            print(f"Knowledge gaps found: {stats.get('gaps_found', 0)}")
            print(f"Crawl plans generated: {stats.get('crawl_plans_generated', 0)}")
            print(f"Crawls executed: {stats.get('crawls_executed', 0)}")

            dead_ends = report.get("dead_ends", [])
            if dead_ends:
                print(f"\n--- Dead-End Entities ({len(dead_ends)}) ---")
                print(f"\n{'Name':<30} {'Kind':<15} {'Out':<5} {'In':<5} {'Dead End':<10}")
                print("-" * 65)
                for de in dead_ends[:15]:
                    print(
                        f"{(de.get('name') or '')[:28]:<30} "
                        f"{(de.get('kind') or 'N/A'):<15} "
                        f"{de.get('outgoing_relations', 0):<5} "
                        f"{de.get('incoming_relations', 0):<5} "
                        f"{'Yes' if de.get('is_dead_end') else 'No':<10}"
                    )

            gaps = report.get("knowledge_gaps", [])
            if gaps:
                print(f"\n--- Knowledge Gaps ({len(gaps)}) ---")
                for gap in gaps[:10]:
                    print(f"\n  {gap.get('entity_name', 'Unknown')} (gap score: {gap.get('gap_score', 0)})")
                    print(f"    Intel: {gap.get('intelligence_count', 0)} | Missing: {', '.join(gap.get('missing_fields', []))}")

            plans = report.get("crawl_plans", [])
            if plans:
                print(f"\n--- Crawl Plans ({len(plans)}) ---")
                for plan in plans[:10]:
                    print(f"\n  {plan.get('entity_name', 'Unknown')} (priority: {plan.get('priority_score', 0):.3f})")
                    print(f"    Mode: {plan.get('mode', '-')} | Strategy: {plan.get('strategy', '-')}")

        if report.get("message"):
            print(f"\n{report['message']}")
        if report.get("error"):
            print(f"\nError: {report['error']}")

        print("\n" + "=" * 60)


# ============================================================================
# Interactive Mode
# ============================================================================

def cmd_interactive(settings: Settings, args: argparse.Namespace) -> None:
    """Run interactive agent chat session."""
    import asyncio
    
    logger = setup_logging(args.verbose)
    
    _, _, _, agent = get_services(settings)
    
    print("\n" + "=" * 60)
    print("GARUDA AGENT - DEEP RAG INTERACTIVE MODE")
    print("=" * 60)
    print("\nDeep RAG search (embedding + graph + SQL) is always active.")
    print("\nCommands:")
    print("  /entity <name>                  - Set entity context")
    print("  /help                           - Show help")
    print("  /quit or /exit                  - Exit")
    print("-" * 60)
    
    current_entity = None
    
    async def process_question(question: str) -> dict:
        return await agent.chat_async(
            question=question,
            entity=current_entity,
        )
    
    while True:
        try:
            user_input = input("\nYou: ").strip()
            
            if not user_input:
                continue
            
            # Handle commands
            if user_input.startswith("/"):
                parts = user_input.split(maxsplit=1)
                cmd = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else ""
                
                if cmd in ["/quit", "/exit", "/q"]:
                    print("\nGoodbye!")
                    break
                elif cmd == "/entity":
                    current_entity = arg if arg else None
                    print(f"Entity context: {current_entity or 'None'}")
                elif cmd == "/help":
                    print("\nDeep RAG search (embedding + graph + SQL) is always active.")
                    print("\nCommands:")
                    print("  /entity <name>                  - Set entity context")
                    print("  /quit or /exit                  - Exit")
                    print(f"\nCurrent entity: {current_entity or 'None'}")
                else:
                    print(f"Unknown command: {cmd}")
                continue
            
            # Process question
            print("\nAgent: ", end="", flush=True)
            
            response = asyncio.run(process_question(user_input))
            
            answer = response.get("answer", "I couldn't generate an answer.")
            print(answer)
            
            # Show context summary if available
            context = response.get("context", [])
            if context:
                print(f"\n  ({len(context)} context items found)")
            
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except EOFError:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}")


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point for agent CLI."""
    parser = argparse.ArgumentParser(
        description="Garuda Intel Agent CLI - Intelligent data exploration and refinement"
    )
    
    parser.add_argument(
        "--db-url",
        default=None,
        help="Database URL (overrides GARUDA_DB_URL env var)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "-f", "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Reflect command
    reflect_parser = subparsers.add_parser(
        "reflect",
        help="Reflect & refine mode: merge entities, validate data quality"
    )
    reflect_parser.add_argument(
        "-e", "--entities",
        help="Comma-separated list of entity names to focus on"
    )
    reflect_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report without making changes"
    )
    
    # Explore command
    explore_parser = subparsers.add_parser(
        "explore",
        help="Explore & prioritize mode: analyze entity graph"
    )
    explore_parser.add_argument(
        "entities",
        help="Comma-separated list of root entity names"
    )
    explore_parser.add_argument(
        "-d", "--depth",
        type=int,
        default=3,
        help="Maximum exploration depth (default: 3)"
    )
    explore_parser.add_argument(
        "-n", "--top-n",
        type=int,
        default=20,
        help="Number of top-priority entities to return (default: 20)"
    )
    
    # Search command
    search_parser = subparsers.add_parser(
        "search",
        help="Multidimensional RAG search"
    )
    search_parser.add_argument(
        "query",
        help="Search query"
    )
    search_parser.add_argument(
        "-k", "--top-k",
        type=int,
        default=10,
        help="Number of results (default: 10)"
    )
    search_parser.add_argument(
        "--no-graph",
        action="store_true",
        help="Disable graph traversal"
    )
    search_parser.add_argument(
        "--graph-depth",
        type=int,
        default=2,
        help="Graph traversal depth (default: 2)"
    )
    
    # Chat command
    chat_parser = subparsers.add_parser(
        "chat",
        help="Single question chat"
    )
    chat_parser.add_argument(
        "question",
        help="Question to ask"
    )
    chat_parser.add_argument(
        "-e", "--entity",
        help="Entity context"
    )
    
    # Interactive command
    interactive_parser = subparsers.add_parser(
        "interactive",
        help="Interactive chat session"
    )
    
    # Autonomous command
    autonomous_parser = subparsers.add_parser(
        "autonomous",
        help="Autonomous discovery: find dead-ends, gaps, and generate crawl plans"
    )
    autonomous_parser.add_argument(
        "-a", "--action",
        choices=["discover", "reflect-relate", "investigate-crawl", "combined"],
        default="discover",
        help="Autonomous action mode (default: discover)"
    )
    autonomous_parser.add_argument(
        "-n", "--max-entities",
        type=int,
        default=10,
        help="Max entities to process (default: 10)"
    )
    autonomous_parser.add_argument(
        "-t", "--priority-threshold",
        type=float,
        default=0.3,
        help="Minimum priority score (default: 0.3)"
    )
    autonomous_parser.add_argument(
        "-d", "--depth",
        type=int,
        default=3,
        help="Max exploration depth (default: 3)"
    )
    autonomous_parser.add_argument(
        "--auto-crawl",
        action="store_true",
        help="Automatically trigger crawls for discovered entities"
    )
    autonomous_parser.add_argument(
        "--max-pages",
        type=int,
        default=25,
        help="Max pages per crawl (default: 25)"
    )
    autonomous_parser.add_argument(
        "--target-entities",
        nargs="+",
        help="Target entity names to focus on (for reflect-relate and combined modes)"
    )
    autonomous_parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="Maximum potential relations to suggest (for reflect-relate mode, default: 20)"
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    # Load settings
    settings = Settings.from_env()
    if args.db_url:
        settings.db_url = args.db_url
    
    # Pass format and verbose to commands
    args.format = getattr(args, 'format', 'text')
    args.verbose = getattr(args, 'verbose', False)
    
    # Route to command handler
    if args.command == "reflect":
        cmd_reflect(settings, args)
    elif args.command == "explore":
        cmd_explore(settings, args)
    elif args.command == "search":
        cmd_search(settings, args)
    elif args.command == "chat":
        cmd_chat(settings, args)
    elif args.command == "interactive":
        cmd_interactive(settings, args)
    elif args.command == "autonomous":
        cmd_autonomous(settings, args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
