"""CLI argument parsing functions."""

import argparse
from ..types.entity import EntityType


def add_common_logging(parser: argparse.ArgumentParser):
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")


def add_store_args(parser: argparse.ArgumentParser):
    parser.add_argument("--use-sqlite", action="store_true", help="Use SQLite DB at sqlite-path (default crawler.db)")
    parser.add_argument("--db-url", default="", help="SQLAlchemy DB URL (default sqlite:///crawler.db)")
    parser.add_argument("--sqlite-path", default="crawler.db", help="SQLite file path if db-url not set")


def add_llm_vector_args(parser: argparse.ArgumentParser, include_query_flags: bool = False):
    parser.add_argument("--ollama-url", default="http://localhost:11434/api/generate", help="Ollama endpoint")
    parser.add_argument("--model", default="granite3.1-dense:8b", help="LLM model name")
    parser.add_argument("--embedding-model", default="sentence-transformers/all-MiniLM-L6-v2", help="Embedding model name")
    parser.add_argument("--qdrant-url", default="http://localhost:6333", help="Qdrant URL")
    parser.add_argument("--qdrant-collection", default="pages", help="Qdrant collection name")
    parser.add_argument("--top-k", type=int, default=10, help="Number of search results to return")
    if include_query_flags:
        parser.add_argument("--semantic-search", default="", help="Semantic search query (Qdrant)")
        parser.add_argument("--hybrid-search", default="", help="Hybrid search query (exact + semantic)")
        parser.add_argument(
            "--semantic-kind",
            choices=["any", "page", "page_sentence", "finding", "entity", "page_raw"],
            default="any",
            help="Restrict semantic results to a payload kind",
        )
        parser.add_argument(
            "--entity-name",
            default="",
            help="Filter semantic entity results by exact entity name (case-insensitive)",
        )
        parser.add_argument(
            "--entity-field",
            action="append",
            default=[],
            help="When semantic-kind=entity, return only these fields (repeatable). Example: --entity-field bio",
        )
        parser.add_argument(
            "--hydrate-sql",
            action="store_true",
            help="If set, hydrate sql_intel_id/sql_entity_id from SQLite and include rows in output",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Entity-aware crawler CLI")
    subparsers = parser.add_subparsers(dest="command", required=False)

    run_parser = subparsers.add_parser("run", help="Run the intelligent crawler")
    add_common_logging(run_parser)
    add_store_args(run_parser)
    add_llm_vector_args(run_parser, include_query_flags=True)

    chat_p = subparsers.add_parser("chat")
    chat_p.add_argument("--entity-name", default="General Research")
    chat_p.add_argument("--ollama-url", default="http://localhost:11434/api/generate")
    chat_p.add_argument("--model", default="granite3.1-dense:8b")
    chat_p.add_argument("--sqlite-path", default="crawler.db")
    chat_p.add_argument("--db-url", default="")
    chat_p.add_argument("--qdrant-url", default="http://localhost:6333")
    chat_p.add_argument("--qdrant-collection", default="pages")
    chat_p.add_argument("--max-pages", type=int, default=10)
    chat_p.add_argument("--use-selenium", action="store_true", default=False, help="Enable Selenium (Chrome) fetching")
    chat_p.add_argument("--use-sqlite", action="store_true", help="Use SQLite DB at sqlite-path (default crawler.db)")

    run_parser.add_argument("entity", nargs="?", help="Entity name to search (company/person/topic)")
    run_parser.add_argument("--type", choices=[e.value for e in EntityType], default="company", help="Entity type")
    run_parser.add_argument("--location", default="", help="Location hint (optional)")
    run_parser.add_argument("--max-pages", type=int, default=10, help="Max pages per domain")
    run_parser.add_argument("--total-pages", type=int, default=50, help="Max total pages (default: max_pages*20)")
    run_parser.add_argument("--max-depth", type=int, default=2, help="Max crawl depth")
    run_parser.add_argument("--score-threshold", type=float, default=35.0, help="Scoring threshold for following links")
    run_parser.add_argument("--seed-limit", type=int, default=25, help="Max SERP results per query")
    run_parser.add_argument("--use-selenium", action="store_true", default=False, help="Enable Selenium (Chrome) fetching")
    run_parser.add_argument("--active-mode", action="store_true", help="Interactive browser: record your pageviews")
    run_parser.add_argument("--output", default="", help="Write crawl results JSON to this file")
    run_parser.add_argument("--list-pages", action="store_true", help="List stored page URLs (requires DB)")
    run_parser.add_argument("--fetch-text", default="", help="Fetch stored text_content for URL (requires DB). Refetch if missing.")
    run_parser.add_argument("--refresh", action="store_true", help="Run refresh on stored pages (requires DB)")
    run_parser.add_argument("--refresh-batch", type=int, default=50, help="Batch size for refresh")
    run_parser.add_argument("--seed-url", action="append", default=[], help="Seed URL(s) to start exploration from (bypass SERP)")
    run_parser.add_argument("--seed-query", default="", help="Optional query/context string when using --seed-url")
    run_parser.add_argument("--seed-from-links", action="store_true", help="Seed from stored links table (requires DB)")
    run_parser.add_argument("--seed-from-pages", action="store_true", help="Seed from stored pages table (requires DB)")
    run_parser.add_argument("--seed-domain", action="append", default=[], help="Only use seeds whose domain contains this (repeatable)")
    run_parser.add_argument("--seed-pattern", action="append", default=[], help="Only use seeds whose URL matches this regex (repeatable)")
    run_parser.add_argument("--min-link-score", type=float, default=0.0, help="Only use stored links with score >= this")
    run_parser.add_argument("--seed-limit-db", type=int, default=20, help="Max seeds pulled from DB for continuation")
    run_parser.add_argument("--search-intel", default="", help="Keyword to search within gathered text_content (requires DB)")
    run_parser.add_argument("--search-entity-type", default="", help="Filter search by entity_type")
    run_parser.add_argument("--search-page-type", default="", help="Filter search by page_type")
    run_parser.add_argument("--enable-llm-link-rank", action="store_true", help="Use LLM to rank sublinks before scoring")

    intel_parser = subparsers.add_parser("intel", help="Search and export gathered intelligence")
    add_common_logging(intel_parser)
    add_store_args(intel_parser)
    add_llm_vector_args(intel_parser, include_query_flags=True)

    intel_parser.add_argument("--query", help="Text search across all extracted data")
    intel_parser.add_argument("--entity", help="Filter by entity name")
    intel_parser.add_argument("--min-conf", type=float, default=0.0, help="Min confidence score")
    intel_parser.add_argument("--format", choices=["json", "csv", "table"], default="table")
    intel_parser.add_argument("--export", help="Filename for export (e.g. results.csv)")
    
    return parser.parse_args()
