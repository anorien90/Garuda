"""Main entry point for Garuda Intel search CLI.

This module provides the main() function that serves as the entry point
for the command-line interface. The actual functionality has been refactored
into the search/ subpackage.
"""

import sys
import os
import logging

# Handle both module import and direct script execution
if __name__ == "__main__" and __package__ is None:
    # Add parent directory to path for direct script execution
    parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    from garuda_intel.search.utils import try_load_dotenv
    from garuda_intel.search.cli import parse_args
    from garuda_intel.search.handlers import handle_intel, handle_run, interactive_chat
    from garuda_intel.search import (
        EntityProfile,
        EntityType,
        IntelligentExplorer,
        perform_rag_search,
        collect_candidates_simple,
        run_crawl_api,
    )
else:
    from .search.utils import try_load_dotenv
    from .search.cli import parse_args
    from .search.handlers import handle_intel, handle_run, interactive_chat
    from .search import (
        EntityProfile,
        EntityType,
        IntelligentExplorer,
        perform_rag_search,
        collect_candidates_simple,
        run_crawl_api,
    )

# Initialize environment
try_load_dotenv()


def main():
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.command == "chat":
        interactive_chat(args)

    if args.command == "intel":
        handle_intel(args)

    elif args.command == "run":
        handle_run(args)


if __name__ == "__main__":
    main()


# Export all public functions for backward compatibility
__all__ = [
    "main",
    "EntityProfile",
    "EntityType",
    "IntelligentExplorer",
    "perform_rag_search",
    "collect_candidates_simple",
    "run_crawl_api",
]
