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
    ollama_model: str = "phi3:3.8b"
    api_key: Optional[str] = None
    cors_origins: List[str] = None
    debug: bool = False
    
    # Media processing settings (optional feature)
    media_processing_enabled: bool = True
    media_crawling_enabled: bool = True
    media_auto_embeddings: bool = True
    
    # Media processing methods
    # Image: "tesseract" (OCR) or "image2text" (AI model)
    media_image_method: str = "tesseract"
    # Video: "speech" (audio transcription) or "video2text" (AI model)
    media_video_method: str = "speech"
    # Audio: "speech" (speech recognition)
    media_audio_method: str = "speech"
    
    # Caching settings (v2 optimization)
    cache_enabled: bool = True
    embedding_cache_size: int = 10000
    llm_cache_path: str = "/app/data/llm_cache.db"
    llm_cache_ttl_seconds: int = 604800  # 7 days
    
    # Phase 2 v2 optimizations
    # Semantic chunking settings
    use_semantic_chunking: bool = True  # Use topic-aware chunking instead of fixed-size
    
    # Quality validation settings
    enable_quality_validation: bool = True  # Validate and auto-correct extracted intelligence
    min_completeness_score: float = 0.3  # Minimum acceptable completeness score
    
    # Schema discovery settings
    enable_schema_discovery: bool = True  # Use LLM to discover relevant fields dynamically
    cache_discovered_schemas: bool = True  # Cache schemas by entity type
    
    # Adaptive media processing settings
    use_adaptive_media_processing: bool = False  # Automatically select best processing method
    media_prefer_speed: bool = False  # Prioritize speed over quality
    media_prefer_quality: bool = True  # Prioritize quality over speed

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
            media_processing_enabled=_as_bool(os.environ.get("GARUDA_MEDIA_PROCESSING"), True),
            media_crawling_enabled=_as_bool(os.environ.get("GARUDA_MEDIA_CRAWLING"), True),
            media_auto_embeddings=_as_bool(os.environ.get("GARUDA_MEDIA_EMBEDDINGS"), True),
            media_image_method=os.environ.get("GARUDA_MEDIA_IMAGE_METHOD", "tesseract"),
            media_video_method=os.environ.get("GARUDA_MEDIA_VIDEO_METHOD", "speech"),
            media_audio_method=os.environ.get("GARUDA_MEDIA_AUDIO_METHOD", "speech"),
            cache_enabled=_as_bool(os.environ.get("GARUDA_CACHE_ENABLED"), True),
            embedding_cache_size=int(os.environ.get("GARUDA_EMBEDDING_CACHE_SIZE", "10000")),
            llm_cache_path=os.environ.get("GARUDA_LLM_CACHE_PATH", "/app/data/llm_cache.db"),
            llm_cache_ttl_seconds=int(os.environ.get("GARUDA_LLM_CACHE_TTL", "604800")),
            # Phase 2 optimizations
            use_semantic_chunking=_as_bool(os.environ.get("GARUDA_USE_SEMANTIC_CHUNKING"), True),
            enable_quality_validation=_as_bool(os.environ.get("GARUDA_ENABLE_QUALITY_VALIDATION"), True),
            min_completeness_score=float(os.environ.get("GARUDA_MIN_COMPLETENESS_SCORE", "0.3")),
            enable_schema_discovery=_as_bool(os.environ.get("GARUDA_ENABLE_SCHEMA_DISCOVERY"), True),
            cache_discovered_schemas=_as_bool(os.environ.get("GARUDA_CACHE_DISCOVERED_SCHEMAS"), True),
            use_adaptive_media_processing=_as_bool(os.environ.get("GARUDA_USE_ADAPTIVE_MEDIA"), False),
            media_prefer_speed=_as_bool(os.environ.get("GARUDA_MEDIA_PREFER_SPEED"), False),
            media_prefer_quality=_as_bool(os.environ.get("GARUDA_MEDIA_PREFER_QUALITY"), True),
        )

    @property
    def vector_enabled(self) -> bool:
        return bool(self.qdrant_url)
