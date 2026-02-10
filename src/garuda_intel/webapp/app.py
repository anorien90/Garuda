"""Garuda Intel Webapp - Main Application Entry Point."""

import os
import signal
import sys
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS
from functools import wraps
import logging

# Configure root logger with proper format BEFORE any other imports
# This ensures all module-level loggers pick up the configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

from ..database.engine import SQLAlchemyStore
from ..database.relationship_manager import RelationshipManager
from ..vector.engine import QdrantVectorStore
from ..extractor.llm import LLMIntelExtractor
from ..config import Settings
from ..discover.crawl_modes import EntityAwareCrawler
from ..discover.crawl_learner import CrawlLearner
from ..services.entity_gap_analyzer import EntityGapAnalyzer
from ..services.adaptive_crawler import AdaptiveCrawlerService
from ..services.media_processor import MediaProcessor
from ..services.task_queue import TaskQueueService
from .services.event_system import init_event_logging
from .utils.shutdown import ShutdownManager

# Import route blueprints
from .routes import static, recorder, search, crawling, entities, relationships
from .routes import entity_gaps, entity_deduplication, entity_relations, media
from .routes import graph_search, relationship_confidence, schema, agent
from .routes import tasks as tasks_routes
from .routes import local_data as local_data_routes

settings = Settings.from_env()

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app, resources={r"/api/*": {"origins": settings.cors_origins}})

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

print(f"Starting Garuda Intel Webapp with DB: {settings.db_url}")
print(f"Qdrant Vector Store: {settings.qdrant_url} Collection: {settings.qdrant_collection}")
print(f"Ollama LLM: {settings.ollama_url} Model: {settings.ollama_model}")
print(f"Embedding Model: {settings.embedding_model}")

# Initialize core components
store = SQLAlchemyStore(settings.db_url)
llm = LLMIntelExtractor(
    ollama_url=settings.ollama_url,
    model=settings.ollama_model,
    embedding_model=settings.embedding_model,
)

vector_store = None
if settings.vector_enabled:
    try:
        logger.info(f"Initializing Qdrant vector store at {settings.qdrant_url}")
        vector_store = QdrantVectorStore(
            url=settings.qdrant_url, collection=settings.qdrant_collection
        )
        logger.info(f"✓ Vector store initialized successfully")
    except Exception as e:
        logger.error(f"✗ Qdrant unavailable - embeddings will NOT be generated: {e}")
        vector_store = None
else:
    logger.warning(f"✗ Vector store disabled (vector_enabled=False) - embeddings will NOT be generated")

# Initialize new components for enhanced features
relationship_manager = RelationshipManager(store, llm)
entity_crawler = EntityAwareCrawler(store, llm)
crawl_learner = CrawlLearner(store)
gap_analyzer = EntityGapAnalyzer(store)
adaptive_crawler = AdaptiveCrawlerService(store, llm, crawl_learner, vector_store)
media_processor = MediaProcessor(
    llm, 
    enable_processing=settings.media_processing_enabled,
    image_method=settings.media_image_method,
    video_method=settings.media_video_method,
    audio_method=settings.media_audio_method,
)

# Initialize media extractor for crawling integration
from ..services.media_extractor import MediaExtractor
media_extractor = MediaExtractor(
    store, 
    media_processor, 
    auto_process=settings.media_crawling_enabled and settings.media_processing_enabled
)

# Initialize event logging
init_event_logging()

# Initialize persistent task queue
task_queue = TaskQueueService(store)


def _register_task_handlers(tq, agent_svc, store, gap_analyzer, adaptive_crawler):
    """Register task handlers for the queue worker."""

    def _handle_agent_reflect(task_id, params):
        tq.update_progress(task_id, 0.1, "Starting reflect & refine")
        result = agent_svc.reflect_and_refine(
            target_entities=params.get("target_entities"),
            dry_run=params.get("dry_run", True),
        )
        tq.update_progress(task_id, 1.0, "Reflect & refine complete")
        return result

    def _handle_agent_explore(task_id, params):
        tq.update_progress(task_id, 0.1, "Starting explore & prioritize")
        result = agent_svc.explore_and_prioritize(
            root_entities=params.get("root_entities", []),
            max_depth=int(params.get("max_depth", 3)),
            top_n=int(params.get("top_n", 20)),
        )
        tq.update_progress(task_id, 1.0, "Explore complete")
        return result

    def _handle_agent_autonomous(task_id, params):
        tq.update_progress(task_id, 0.1, "Starting autonomous discovery")
        result = agent_svc.autonomous_discover(
            max_entities=int(params.get("max_entities", 10)),
            priority_threshold=float(params.get("priority_threshold", 0.3)),
            max_depth=int(params.get("max_depth", 3)),
            auto_crawl=params.get("auto_crawl", False),
            max_pages=int(params.get("max_pages", 25)),
        )
        tq.update_progress(task_id, 1.0, "Autonomous discovery complete")
        return result

    def _handle_agent_reflect_relate(task_id, params):
        tq.update_progress(task_id, 0.1, "Starting reflect & relate")
        result = agent_svc.reflect_relate(
            target_entities=params.get("target_entities"),
            max_depth=int(params.get("max_depth", 2)),
            top_n=int(params.get("top_n", 20)),
        )
        tq.update_progress(task_id, 1.0, "Reflect & relate complete")
        return result

    def _handle_agent_investigate(task_id, params):
        tq.update_progress(task_id, 0.1, "Starting investigate crawl")
        result = agent_svc.investigate_crawl(
            investigation_tasks=params.get("investigation_tasks"),
            max_entities=int(params.get("max_entities", 10)),
            max_pages=int(params.get("max_pages", 25)),
            max_depth=int(params.get("max_depth", 3)),
            priority_threshold=float(params.get("priority_threshold", 0.3)),
        )
        tq.update_progress(task_id, 1.0, "Investigate crawl complete")
        return result

    def _handle_agent_combined(task_id, params):
        tq.update_progress(task_id, 0.1, "Starting combined autonomous")
        result = agent_svc.combined_autonomous(
            target_entities=params.get("target_entities"),
            max_entities=int(params.get("max_entities", 10)),
            max_pages=int(params.get("max_pages", 25)),
            max_depth=int(params.get("max_depth", 3)),
            priority_threshold=float(params.get("priority_threshold", 0.3)),
        )
        tq.update_progress(task_id, 1.0, "Combined autonomous complete")
        return result

    def _handle_agent_chat(task_id, params):
        import asyncio
        tq.update_progress(task_id, 0.1, "Processing chat query")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                agent_svc.chat_async(
                    question=params.get("question", ""),
                    entity=params.get("entity"),
                )
            )
        finally:
            loop.close()
        tq.update_progress(task_id, 1.0, "Chat complete")
        return result

    def _handle_chat(task_id, params):
        """Handle general chat tasks (same as agent chat for now)."""
        import asyncio
        tq.update_progress(task_id, 0.1, "Processing chat query")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                agent_svc.chat_async(
                    question=params.get("question", ""),
                    entity=params.get("entity"),
                )
            )
        finally:
            loop.close()
        tq.update_progress(task_id, 1.0, "Chat complete")
        return result

    def _handle_crawl(task_id, params):
        """Handle crawl tasks (standard, intelligent, or unified)."""
        from ...search import run_crawl_api
        from ...database.models import Entity
        
        mode = params.get("mode", "standard")
        tq.update_progress(task_id, 0.1, f"Starting {mode} crawl")
        
        if mode == "intelligent":
            plan = gap_analyzer.generate_crawl_plan(
                params.get("entity_name", ""), params.get("entity_type")
            )
            tq.update_progress(task_id, 0.3, "Crawl plan generated, executing crawl")
            results = adaptive_crawler.intelligent_crawl(
                entity_name=params.get("entity_name", ""),
                entity_type=params.get("entity_type"),
                max_pages=int(params.get("max_pages", 50)),
                max_depth=int(params.get("max_depth", 2)),
            )
            tq.update_progress(task_id, 1.0, "Intelligent crawl complete")
            return {"plan": plan, "results": results, "mode": "intelligent"}
        elif mode == "unified":
            entity_name = params.get("entity", "")
            entity_type = params.get("type")
            use_intelligent = params.get("use_intelligent", False)
            if not use_intelligent:
                with store.Session() as session:
                    existing = session.query(Entity).filter(
                        Entity.name.ilike(f"%{entity_name}%")
                    ).first()
                    if existing:
                        use_intelligent = True
            if use_intelligent:
                plan = gap_analyzer.generate_crawl_plan(entity_name, entity_type)
                tq.update_progress(task_id, 0.3, "Crawl plan generated, executing intelligent crawl")
                results = adaptive_crawler.intelligent_crawl(
                    entity_name=entity_name,
                    entity_type=entity_type,
                    max_pages=int(params.get("max_pages", 50)),
                    max_depth=int(params.get("max_depth", 2)),
                )
                tq.update_progress(task_id, 1.0, "Unified intelligent crawl complete")
                return {"mode": "intelligent", "plan": plan, "results": results}
            else:
                tq.update_progress(task_id, 0.3, "Running standard crawl")
                result = run_crawl_api(params)
                tq.update_progress(task_id, 1.0, "Standard crawl complete")
                return {"mode": "standard", "results": result}
        else:
            tq.update_progress(task_id, 0.3, "Running standard crawl")
            result = run_crawl_api(params)
            tq.update_progress(task_id, 1.0, "Crawl complete")
            return result

    # Pre-compiled URL pattern for extracting links from local file content
    import re as _re_mod
    _URL_PATTERN = _re_mod.compile(
        r'https?://[^\s<>"\')\],;]+', _re_mod.IGNORECASE
    )

    def _handle_local_ingest(task_id, params):
        """Handle local file ingestion tasks (insert or update).

        Extracts content from the file, persists it as Page + PageContent,
        extracts URLs found in the text as Link records, and stores complete
        file metadata (hash, stored path) for change tracking.
        """
        from ..sources.local_file_adapter import LocalFileAdapter
        import hashlib as _hashlib
        
        file_path = params.get("file_path", "")
        event = params.get("event", "unknown")
        stored_path = params.get("stored_path", file_path)
        
        tq.update_progress(task_id, 0.1, f"Processing local file: {os.path.basename(file_path)}")
        
        adapter = LocalFileAdapter({"max_file_size_mb": getattr(settings, 'local_data_max_file_size_mb', 100)})
        document = adapter.process_file(file_path)
        
        if not document:
            return {"error": "Failed to extract content from file", "file_path": file_path}
        
        tq.update_progress(task_id, 0.3, "Content extracted, storing results")
        
        # Calculate file hash for change tracking
        file_hash = None
        try:
            hasher = _hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    hasher.update(chunk)
            file_hash = hasher.hexdigest()
        except (IOError, OSError) as e:
            logger.warning(f"Failed to compute file hash for {file_path}: {e}")
        
        # Store or update the extracted content in the database
        import uuid as _uuid
        from datetime import datetime as _dt
        from ..database.models import Page, PageContent
        
        def _build_metadata_json():
            meta = {
                "source": "local_file",
                "event": event,
                "file_type": document.metadata.get("file_type", ""),
                "file_size_mb": document.metadata.get("file_size_mb", 0),
                "file_size_bytes": document.metadata.get("file_size_bytes", 0),
                "confidence": document.confidence,
                "original_filename": params.get("original_filename", document.title),
                "stored_path": stored_path,
                "absolute_path": document.metadata.get("absolute_path", file_path),
            }
            if file_hash:
                meta["file_hash"] = file_hash
            if document.metadata.get("mime_type"):
                meta["mime_type"] = document.metadata["mime_type"]
            return meta
        
        with store.Session() as session:
            # Check if this file was already ingested (upsert logic)
            existing_page = session.query(Page).filter(
                Page.url == document.url
            ).first()
            
            if existing_page:
                # Update existing page and content
                page_id = existing_page.id
                existing_page.title = document.title
                existing_page.last_status = "processed"
                existing_page.last_fetch_at = _dt.utcnow()
                existing_page.text_length = len(document.content) if document.content else 0
                existing_page.score = document.confidence
                
                existing_content = session.query(PageContent).filter(
                    PageContent.page_id == page_id
                ).first()
                
                if existing_content:
                    existing_content.text = document.content[:50000] if document.content else ""
                    existing_content.metadata_json = _build_metadata_json()
                    existing_content.fetch_ts = _dt.utcnow()
                else:
                    page_content = PageContent(
                        id=_uuid.uuid4(),
                        entry_type="page_content",
                        page_id=page_id,
                        page_url=document.url,
                        text=document.content[:50000] if document.content else "",
                        metadata_json=_build_metadata_json(),
                        fetch_ts=_dt.utcnow(),
                    )
                    session.add(page_content)
                
                session.commit()
                upsert_action = "updated"
                logger.info(f"Updated existing local file record: {document.url}")
            else:
                # Insert new page and content
                page_id = _uuid.uuid4()
                page = Page(
                    id=page_id,
                    entry_type="page",
                    url=document.url,
                    title=document.title,
                    page_type="local_file",
                    last_status="processed",
                    last_fetch_at=_dt.utcnow(),
                    text_length=len(document.content) if document.content else 0,
                    score=document.confidence,
                )
                session.add(page)
                session.flush()
                
                page_content = PageContent(
                    id=_uuid.uuid4(),
                    entry_type="page_content",
                    page_id=page_id,
                    page_url=document.url,
                    text=document.content[:50000] if document.content else "",
                    metadata_json=_build_metadata_json(),
                    fetch_ts=_dt.utcnow(),
                )
                session.add(page_content)
                session.commit()
                upsert_action = "inserted"
                logger.info(f"Inserted new local file record: {document.url}")
        
        tq.update_progress(task_id, 0.6, "Page stored, extracting links")
        
        # Extract URLs from content and store as Link records
        extracted_links = []
        if document.content:
            seen_urls = set()
            for match in _URL_PATTERN.finditer(document.content):
                url = match.group(0).rstrip('.')
                if url not in seen_urls:
                    seen_urls.add(url)
                    extracted_links.append({
                        "href": url,
                        "text": "",
                        "score": 0.5,
                        "reason": "extracted_from_local_file",
                        "depth": 0,
                    })
        
        if extracted_links:
            try:
                store.save_links(document.url, extracted_links)
                logger.info(
                    f"Saved {len(extracted_links)} links from local file: {document.title}"
                )
            except Exception as e:
                logger.warning(f"Failed to save links from local file: {e}")
        
        tq.update_progress(task_id, 1.0, "Local file ingestion complete")
        
        return {
            "page_id": str(page_id),
            "file_path": file_path,
            "stored_path": stored_path,
            "title": document.title,
            "content_length": len(document.content),
            "confidence": document.confidence,
            "source_type": document.source_type.value,
            "event": event,
            "action": upsert_action,
            "links_extracted": len(extracted_links),
            "file_hash": file_hash,
        }

    tq.register_handler(TaskQueueService.TASK_AGENT_REFLECT, _handle_agent_reflect)
    tq.register_handler(TaskQueueService.TASK_AGENT_EXPLORE, _handle_agent_explore)
    tq.register_handler(TaskQueueService.TASK_AGENT_AUTONOMOUS, _handle_agent_autonomous)
    tq.register_handler(TaskQueueService.TASK_AGENT_REFLECT_RELATE, _handle_agent_reflect_relate)
    tq.register_handler(TaskQueueService.TASK_AGENT_INVESTIGATE, _handle_agent_investigate)
    tq.register_handler(TaskQueueService.TASK_AGENT_COMBINED, _handle_agent_combined)
    tq.register_handler(TaskQueueService.TASK_AGENT_CHAT, _handle_agent_chat)
    tq.register_handler(TaskQueueService.TASK_CHAT, _handle_chat)
    tq.register_handler(TaskQueueService.TASK_CRAWL, _handle_crawl)
    tq.register_handler(TaskQueueService.TASK_LOCAL_INGEST, _handle_local_ingest)


# Auth helper
def api_key_required(fn):
    """Decorator to require API key for protected endpoints."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not settings.api_key:
            return fn(*args, **kwargs)
        key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if key != settings.api_key:
            return jsonify({"error": "unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper


# Register blueprints
app.register_blueprint(
    static.init_routes(api_key_required, settings, store, llm, vector_store)
)

app.register_blueprint(
    recorder.init_routes(api_key_required, store)
)

app.register_blueprint(
    search.init_routes(api_key_required, settings, store, llm, vector_store)
)

app.register_blueprint(
    crawling.init_routes(
        api_key_required, settings, store, llm, 
        entity_crawler, crawl_learner, gap_analyzer, adaptive_crawler
    )
)

app.register_blueprint(
    entities.init_routes(
        api_key_required, settings, store, llm, vector_store,
        entity_crawler, gap_analyzer, adaptive_crawler
    )
)

# Register new extracted entity route modules
app.register_blueprint(
    entity_gaps.init_gaps_routes(api_key_required, gap_analyzer, adaptive_crawler)
)

app.register_blueprint(
    entity_deduplication.init_deduplication_routes(api_key_required, store)
)

app.register_blueprint(
    entity_relations.init_relations_routes(api_key_required, store)
)

app.register_blueprint(
    relationships.init_routes(api_key_required, relationship_manager)
)

app.register_blueprint(
    media.init_media_routes(api_key_required, store, llm, media_processor)
)

# Register new graph search and relationship confidence routes
app.register_blueprint(
    graph_search.init_graph_routes(api_key_required, store, llm)
)

app.register_blueprint(
    relationship_confidence.init_relationship_confidence_routes(api_key_required, store)
)

app.register_blueprint(
    schema.init_schema_routes(api_key_required, store)
)

# Register agent routes for intelligent exploration and refinement
app.register_blueprint(
    agent.init_agent_routes(api_key_required, settings, store, llm, vector_store)
)

# Register task queue routes and handlers
app.register_blueprint(
    tasks_routes.init_task_routes(api_key_required, task_queue)
)

# Initialize directory watcher if configured
_directory_watcher = None
if settings.local_data_watch_enabled and settings.local_data_watch_dir:
    try:
        from ..services.directory_watcher import DirectoryWatcherService
        _directory_watcher = DirectoryWatcherService(
            watch_dir=settings.local_data_watch_dir,
            task_queue=task_queue,
            poll_interval=settings.local_data_watch_interval,
            recursive=settings.local_data_watch_recursive,
        )
        logger.info(f"Directory watcher configured for: {settings.local_data_watch_dir}")
    except Exception as e:
        logger.error(f"Failed to initialize directory watcher: {e}")

# Register local data routes
app.register_blueprint(
    local_data_routes.init_local_data_routes(
        api_key_required, settings, task_queue, _directory_watcher
    )
)

# Lazy-register task handlers: we need the same AgentService instance used by agent routes.
# Import it fresh and create one to register handlers.
from ..services.agent_service import AgentService as _AgentService
_agent_for_queue = _AgentService(
    store=store,
    llm=llm,
    vector_store=vector_store,
    entity_merge_threshold=getattr(settings, 'agent_entity_merge_threshold', 0.85),
    max_exploration_depth=getattr(settings, 'agent_max_exploration_depth', 3),
    priority_unknown_weight=getattr(settings, 'agent_priority_unknown_weight', 0.7),
    priority_relation_weight=getattr(settings, 'agent_priority_relation_weight', 0.3),
)
_register_task_handlers(task_queue, _agent_for_queue, store, gap_analyzer, adaptive_crawler)

# Start the task queue worker
task_queue.start_worker()

# Start directory watcher if configured
if _directory_watcher:
    _directory_watcher.start()
    logger.info("Directory watcher started")
    # Scan existing files so any files already in the watch directory are picked up
    try:
        scan_result = _directory_watcher.scan_existing()
        logger.info(
            f"Initial directory scan: queued={scan_result['queued']} "
            f"skipped={scan_result['skipped']}"
        )
    except Exception as e:
        logger.error(f"Failed initial directory scan: {e}")


def main():
    """Run the Flask application."""
    shutdown_manager = ShutdownManager()
    app.config['shutdown_manager'] = shutdown_manager
    
    def signal_handler(signum, frame):
        """Handle shutdown signals gracefully.
        
        Args:
            signum: Signal number (not used directly but required by signal handler interface)
            frame: Current stack frame (not used directly but required by signal handler interface)
        """
        shutdown_manager.request_shutdown()
        task_queue.stop_worker()
        if _directory_watcher:
            _directory_watcher.stop()
    
    # Only register signal handlers in production mode
    # In debug mode, Flask's reloader interferes with signal handling
    if not settings.debug:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        logger.info("Graceful shutdown handlers registered (production mode)")
    else:
        logger.info("Running in debug mode - signal handlers disabled")
    
    app.run(host="0.0.0.0", port=8080, debug=settings.debug)


if __name__ == "__main__":
    main()
