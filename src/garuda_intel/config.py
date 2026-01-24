from enum import Enum
from typing import Optional, Dict, Any
import os
from dataclasses import dataclass
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()


def _as_bool(val: Optional[str], default: bool = False) -> bool:
    if val is None:
        return default
    return str(val).lower() in {"1", "true", "yes", "y", "on"}


def _as_list(val: Optional[str]) -> List[str]:
    if not val:
        return []
    return [v.strip() for v in val.split(",") if v.strip()]


@dataclass
class Settings:
    db_url: str = "sqlite:////app/data/crawler.db"
    qdrant_url: Optional[str] = None
    qdrant_collection: str = "pages"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    ollama_url: str = "http://localhost:11434/api/generate"
    ollama_model: str = "granite3.1-dense:8b"
    api_key: Optional[str] = None
    cors_origins: List[str] = None
    debug: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        cors_val = os.environ.get("GARUDA_UI_CORS_ORIGINS", "*")
        cors_origins = ["*"] if cors_val.strip() == "*" else _as_list(cors_val)
        return cls(
            db_url=os.environ.get("GARUDA_DB_URL")
            or "sqlite:////app/data/crawler.db",
            qdrant_url=os.environ.get("GARUDA_QDRANT_URL")
            or os.environ.get("QDRANT_URL"),
            qdrant_collection=os.environ.get("GARUDA_QDRANT_COLLECTION")
            or os.environ.get("QDRANT_COLLECTION", "pages"),
            embedding_model=os.environ.get("GARUDA_EMBED_MODEL")
            or os.environ.get("EMBEDDING_MODEL")
            or "sentence-transformers/all-MiniLM-L6-v2",
            ollama_url=os.environ.get("GARUDA_OLLAMA_URL")
            or os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate"),
            ollama_model=os.environ.get("GARUDA_OLLAMA_MODEL")
            or os.environ.get("OLLAMA_MODEL", "granite3.1-dense:8b"),
            api_key=os.environ.get("GARUDA_UI_API_KEY"),
            cors_origins=cors_origins,
            debug=_as_bool(os.environ.get("GARUDA_UI_DEBUG"), False),
        )

    @property
    def vector_enabled(self) -> bool:
        return bool(self.qdrant_url)
