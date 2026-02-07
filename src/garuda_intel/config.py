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
    
    # Chat pipeline settings
    chat_max_search_cycles: int = 3  # Maximum number of search/crawl cycles in chat
    chat_max_pages: int = 5  # Maximum pages to crawl per chat search cycle
    chat_use_selenium: bool = False  # Use Selenium for chat crawling
    chat_rag_quality_threshold: float = 0.7  # Minimum RAG similarity score threshold
    chat_min_high_quality_hits: int = 2  # Minimum high-quality RAG hits before considering sufficient
    chat_extract_related_entities: bool = True  # Extract related entities during chat crawl
    
    # LLM timeout settings (in seconds) - default 15 minutes for long operations
    llm_summarize_timeout: int = 900  # 15 minutes
    llm_extract_timeout: int = 900  # 15 minutes
    llm_reflect_timeout: int = 300  # 5 minutes
    llm_summarize_retries: int = 3
    
    # Agent mode settings
    agent_enabled: bool = True
    agent_max_exploration_depth: int = 3  # Maximum relation depth for exploration
    agent_entity_merge_threshold: float = 0.85  # Similarity threshold for entity merging
    agent_priority_unknown_weight: float = 0.7  # Weight for prioritizing unknown entities
    agent_priority_relation_weight: float = 0.3  # Weight for relation count in priority

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
            # Chat pipeline settings
            chat_max_search_cycles=int(os.environ.get("GARUDA_CHAT_MAX_SEARCH_CYCLES", "3")),
            chat_max_pages=int(os.environ.get("GARUDA_CHAT_MAX_PAGES", "5")),
            chat_use_selenium=_as_bool(os.environ.get("GARUDA_CHAT_USE_SELENIUM"), False),
            chat_rag_quality_threshold=float(os.environ.get("GARUDA_CHAT_RAG_QUALITY_THRESHOLD", "0.7")),
            chat_min_high_quality_hits=int(os.environ.get("GARUDA_CHAT_MIN_HIGH_QUALITY_HITS", "2")),
            chat_extract_related_entities=_as_bool(os.environ.get("GARUDA_CHAT_EXTRACT_RELATED_ENTITIES"), True),
            # LLM timeout settings
            llm_summarize_timeout=int(os.environ.get("GARUDA_LLM_SUMMARIZE_TIMEOUT", "900")),
            llm_extract_timeout=int(os.environ.get("GARUDA_LLM_EXTRACT_TIMEOUT", "900")),
            llm_reflect_timeout=int(os.environ.get("GARUDA_LLM_REFLECT_TIMEOUT", "300")),
            llm_summarize_retries=int(os.environ.get("GARUDA_LLM_SUMMARIZE_RETRIES", "3")),
            # Agent mode settings
            agent_enabled=_as_bool(os.environ.get("GARUDA_AGENT_ENABLED"), True),
            agent_max_exploration_depth=int(os.environ.get("GARUDA_AGENT_MAX_EXPLORATION_DEPTH", "3")),
            agent_entity_merge_threshold=float(os.environ.get("GARUDA_AGENT_ENTITY_MERGE_THRESHOLD", "0.85")),
            agent_priority_unknown_weight=float(os.environ.get("GARUDA_AGENT_PRIORITY_UNKNOWN_WEIGHT", "0.7")),
            agent_priority_relation_weight=float(os.environ.get("GARUDA_AGENT_PRIORITY_RELATION_WEIGHT", "0.3")),
        )

    @property
    def vector_enabled(self) -> bool:
        return bool(self.qdrant_url)
