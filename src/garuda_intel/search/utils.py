"""Utility functions for search module."""

import logging
from ..vector.engine import QdrantVectorStore


def try_load_dotenv():
    try:
        import dotenv  # type: ignore
        dotenv.load_dotenv(override=True)
        print("[.env] Loaded environment from .env files.")
    except ImportError:
        pass


def init_vector_store(args) -> QdrantVectorStore | None:
    try:
        return QdrantVectorStore(url=args.qdrant_url, collection=args.qdrant_collection)
    except Exception as e:
        logging.error(f"Failed to init Qdrant vector store: {e}")
        return None


def normalize_db_url(db_url: str, sqlite_path: str) -> str:
    if db_url:
        if "://" not in db_url:
            return f"sqlite:///{db_url}"
        return db_url
    return f"sqlite:///{sqlite_path}"
