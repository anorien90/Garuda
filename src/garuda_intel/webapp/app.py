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
from .routes import databases as databases_routes

settings = Settings.from_env()

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app, resources={r"/api/*": {"origins": settings.cors_origins}})

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

print(f"Starting Garuda Intel Webapp with DB: {settings.db_url}")
print(f"Qdrant Vector Store: {settings.qdrant_url} Collection: {settings.qdrant_collection}")
print(f"Ollama LLM: {settings.ollama_url} Model: {settings.ollama_model}")
print(f"Embedding Model: {settings.embedding_model}")

# ---------------------------------------------------------------------------
# StoreProxy – transparent wrapper so all closure-captured references
# automatically pick up database switches without touching any route code.
# ---------------------------------------------------------------------------
from .utils.store_proxy import StoreProxy as _StoreProxy

# Initialize core components
_real_store = SQLAlchemyStore(settings.db_url)
store = _StoreProxy(_real_store)

# Multi-database manager
from ..services.database_manager import DatabaseManager as _DatabaseManager
_db_data_dir = os.path.dirname(settings.db_url.replace("sqlite:///", "")) or "/app/data"
db_manager = _DatabaseManager(
    data_dir=_db_data_dir,
    qdrant_url=settings.qdrant_url,
)
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


def _register_task_handlers(tq, agent_svc, store, gap_analyzer, adaptive_crawler,
                            llm_extractor=None, vec_store=None):
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
        from ..search import run_crawl_api
        from ..database.models import Entity
        
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

    def _coerce_scalar(val, default=None):
        """Coerce a list value to its first element (LLM may return lists)."""
        if isinstance(val, list):
            return val[0] if val else default
        return val

    def _handle_local_ingest(task_id, params):
        """Handle local file ingestion tasks with full intel extraction pipeline.

        Pipeline steps:
        1. Extract content from the file via LocalFileAdapter
        2. Persist as Page + PageContent (upsert)
        3. Run LLM intelligence extraction (entities, findings, relationships)
        4. Save entities and relationships to the database
        5. Save intelligence records
        6. Generate and store embeddings in the vector store
        7. Extract URLs found in the text as Link records
        """
        from ..sources.local_file_adapter import LocalFileAdapter
        import hashlib as _hashlib
        
        file_path = params.get("file_path", "")
        event = params.get("event", "unknown")
        stored_path = params.get("stored_path", file_path)
        
        tq.update_progress(task_id, 0.05, f"Processing local file: {os.path.basename(file_path)}")
        
        adapter = LocalFileAdapter({"max_file_size_mb": getattr(settings, 'local_data_max_file_size_mb', 100)})
        document = adapter.process_file(file_path)
        
        if not document:
            return {"error": "Failed to extract content from file", "file_path": file_path}
        
        tq.update_progress(task_id, 0.1, "Content extracted, storing results")
        
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
                    existing_content.text = document.content or ""
                    existing_content.metadata_json = _build_metadata_json()
                    existing_content.fetch_ts = _dt.utcnow()
                else:
                    page_content = PageContent(
                        id=_uuid.uuid4(),
                        entry_type="page_content",
                        page_id=page_id,
                        page_url=document.url,
                        text=document.content or "",
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
                    text=document.content or "",
                    metadata_json=_build_metadata_json(),
                    fetch_ts=_dt.utcnow(),
                )
                session.add(page_content)
                session.commit()
                upsert_action = "inserted"
                logger.info(f"Inserted new local file record: {document.url}")
        
        page_id_str = str(page_id)
        
        # ================================================================
        # INTEL EXTRACTION PIPELINE
        # ================================================================
        text_content = document.content or ""
        extracted_entities = []
        verified_findings = []
        verified_findings_with_scores = []
        finding_to_entities = {}
        entity_id_map = {}
        intel_count = 0
        entities_count = 0
        relationships_count = 0
        summary = ""
        
        if llm_extractor and text_content.strip():
            try:
                from ..types.entity import EntityProfile, EntityType
                profile = EntityProfile(
                    name=document.title or os.path.basename(file_path),
                    entity_type=EntityType.TOPIC,
                )
                
                tq.update_progress(task_id, 0.15, "Running LLM intelligence extraction")
                
                # Step 1: LLM intelligence extraction
                raw_intel = llm_extractor.extract_intelligence(
                    profile=profile,
                    text=text_content,
                    page_type="local_file",
                    url=document.url,
                    existing_intel=None,
                )
                
                if raw_intel:
                    # Normalize to list
                    findings_list = raw_intel if isinstance(raw_intel, list) else [raw_intel]
                    for finding in findings_list:
                        if not isinstance(finding, dict):
                            continue
                        is_verified, conf_score = llm_extractor.reflect_and_verify(profile, finding)
                        if is_verified:
                            verified_findings.append(finding)
                            verified_findings_with_scores.append((finding, conf_score))
                            f_entities = llm_extractor.extract_entities_from_finding(finding)
                            finding_to_entities[id(finding)] = f_entities
                            extracted_entities.extend(f_entities)
                    
                    # Fallback: extract entities even when no findings passed verification
                    if not verified_findings:
                        extracted_entities.extend(
                            llm_extractor.extract_entities_from_finding(raw_intel)
                        )
                
                tq.update_progress(
                    task_id, 0.3,
                    f"Extracted {len(verified_findings)} findings, {len(extracted_entities)} entities",
                )
                
                # Step 2: Infer relationships between extracted entities
                if extracted_entities and hasattr(llm_extractor, 'infer_relationships_from_entities'):
                    _MAX_REL_CTX = 5000
                    inferred_rels = llm_extractor.infer_relationships_from_entities(
                        entities=extracted_entities,
                        context_text=text_content[:_MAX_REL_CTX],
                    )
                    if inferred_rels:
                        logger.info(f"Inferred {len(inferred_rels)} relationships from entity context")
                        if verified_findings:
                            verified_findings[-1].setdefault("relationships", []).extend(inferred_rels)
                        else:
                            inf_finding = {"basic_info": {}, "relationships": inferred_rels}
                            verified_findings.append(inf_finding)
                            verified_findings_with_scores.append((inf_finding, 0.5))
                
                # Step 3: Save extracted entities
                if extracted_entities:
                    for ent in extracted_entities:
                        if "page_id" not in ent:
                            ent["page_id"] = page_id_str
                    entity_id_map = store.save_entities(extracted_entities) or {}
                    entities_count = len(entity_id_map)
                
                tq.update_progress(task_id, 0.4, f"Saved {entities_count} entities")
                
                # Step 4: Save relationships from findings
                entity_name_to_id = {}
                for (ent_name, ent_kind), ent_id in entity_id_map.items():
                    entity_name_to_id[ent_name.lower()] = ent_id
                
                # Auto-create missing entities referenced by relationships
                missing_entities_dict = {}
                for finding, conf_score in verified_findings_with_scores:
                    for rel in (finding.get("relationships") or []):
                        if not isinstance(rel, dict):
                            continue
                        src = _coerce_scalar(rel.get("source"))
                        tgt = _coerce_scalar(rel.get("target"))
                        src_type = _coerce_scalar(rel.get("source_type", "entity"), "entity")
                        tgt_type = _coerce_scalar(rel.get("target_type", "entity"), "entity")
                        if src and not entity_name_to_id.get(src.lower()):
                            key = (src, src_type)
                            if key not in missing_entities_dict:
                                missing_entities_dict[key] = {
                                    "name": src, "kind": src_type,
                                    "data": {"auto_created_from_relationship": True},
                                    "page_id": page_id_str,
                                }
                        if tgt and not entity_name_to_id.get(tgt.lower()):
                            key = (tgt, tgt_type)
                            if key not in missing_entities_dict:
                                missing_entities_dict[key] = {
                                    "name": tgt, "kind": tgt_type,
                                    "data": {"auto_created_from_relationship": True},
                                    "page_id": page_id_str,
                                }
                
                if missing_entities_dict:
                    try:
                        new_map = store.save_entities(list(missing_entities_dict.values())) or {}
                        entity_id_map.update(new_map)
                        for (n, k), eid in new_map.items():
                            entity_name_to_id[n.lower()] = eid
                        entities_count += len(new_map)
                    except Exception as e:
                        logger.warning(f"Failed to create missing entities for relationships: {e}")
                
                # Persist relationships
                for finding, conf_score in verified_findings_with_scores:
                    for rel in (finding.get("relationships") or []):
                        if not isinstance(rel, dict):
                            continue
                        src = _coerce_scalar(rel.get("source"))
                        tgt = _coerce_scalar(rel.get("target"))
                        rel_type = rel.get("relation_type") or "related"
                        desc = rel.get("description", "")
                        if src and tgt:
                            src_id = entity_name_to_id.get(src.lower())
                            tgt_id = entity_name_to_id.get(tgt.lower())
                            if src_id and tgt_id:
                                try:
                                    store.save_relationship(
                                        from_id=src_id, to_id=tgt_id,
                                        relation_type=rel_type,
                                        meta={"description": desc, "confidence": conf_score, "page_id": page_id_str},
                                    )
                                    relationships_count += 1
                                except Exception as e:
                                    logger.debug(f"save_relationship failed: {e}")
                
                tq.update_progress(task_id, 0.5, f"Saved {relationships_count} relationships")
                
                # Step 5: Save intelligence records
                finding_ids = []
                for finding, conf_score in verified_findings_with_scores:
                    try:
                        intel_id = store.save_intelligence(
                            finding=finding,
                            confidence=conf_score,
                            page_id=page_id_str,
                            entity_id=None,
                            entity_name=document.title,
                            entity_type="topic",
                        )
                        if intel_id:
                            # Link intel to extracted sub-entities for provenance
                            f_ents = finding_to_entities.get(id(finding), [])
                            for sub_ent in f_ents:
                                sub_name = sub_ent.get("name")
                                sub_kind = sub_ent.get("kind")
                                if sub_name and sub_kind:
                                    sub_id = entity_id_map.get((sub_name, sub_kind))
                                    if sub_id:
                                        try:
                                            store.save_relationship(
                                                from_id=intel_id, to_id=sub_id,
                                                relation_type="mentions_entity",
                                                meta={"confidence": conf_score, "page_id": page_id_str, "entity_type": sub_kind},
                                            )
                                        except Exception:
                                            pass
                        finding_ids.append((finding, intel_id, None))
                        intel_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to save intelligence record: {e}")
                        finding_ids.append((finding, None, None))
                
                tq.update_progress(task_id, 0.6, f"Saved {intel_count} intelligence records")
                
                # Step 6: Generate and store embeddings
                if vec_store:
                    try:
                        tq.update_progress(task_id, 0.65, "Generating embeddings")
                        summary = llm_extractor.summarize_page(text_content) if text_content else ""
                        entries = llm_extractor.build_embeddings_for_page(
                            url=document.url,
                            metadata=document.metadata,
                            summary=summary,
                            text_content=text_content,
                            findings_with_ids=finding_ids,
                            page_type="local_file",
                            entity_name=profile.name,
                            entity_type=profile.entity_type,
                            page_uuid=page_id_str,
                        )
                        if extracted_entities:
                            entries.extend(
                                llm_extractor.build_embeddings_for_entities(
                                    entities=extracted_entities,
                                    source_url=document.url,
                                    entity_type=profile.entity_type,
                                    entity_id_map=entity_id_map,
                                    page_uuid=page_id_str,
                                )
                            )
                        for entry in entries:
                            vec_store.upsert(
                                point_id=entry["id"],
                                vector=entry["vector"],
                                payload=entry["payload"],
                            )
                        logger.info(f"Stored {len(entries)} embeddings for local file: {document.title}")
                    except Exception as e:
                        logger.warning(f"Failed to generate embeddings for local file: {e}")
            
            except Exception as e:
                logger.error(f"Intel extraction pipeline failed for {file_path}: {e}", exc_info=True)
        elif not llm_extractor:
            logger.warning("LLM extractor not available - skipping intel extraction for local file")
        
        tq.update_progress(task_id, 0.8, "Extracting links from content")
        
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
        
        # Queue web crawl tasks for discovered URLs
        crawl_tasks_queued = 0
        if extracted_links:
            tq.update_progress(task_id, 0.85, f"Queuing crawl tasks for {len(extracted_links)} URLs")
            for link in extracted_links:
                try:
                    link_url = link.get("href", "")
                    if link_url and link_url.startswith(("http://", "https://")):
                        crawl_task_id = tq.submit(
                            task_type=TaskQueueService.TASK_CRAWL,
                            params={
                                "url": link_url,
                                "source": "local_file_extraction",
                                "source_file": document.title,
                                "source_page_id": page_id_str,
                                "depth": 1,
                                "max_pages": 1,
                            },
                            priority=0,
                        )
                        crawl_tasks_queued += 1
                except Exception as e:
                    logger.debug(f"Failed to queue crawl for URL: {e}")
            if crawl_tasks_queued:
                logger.info(f"Queued {crawl_tasks_queued} crawl tasks from local file: {document.title}")
        
        # Process extracted images from PDFs and relate them to the source file
        extracted_images_count = 0
        if document.metadata.get("extracted_image_paths"):
            tq.update_progress(task_id, 0.9, "Processing extracted PDF images")
            from ..database.models import MediaItem
            
            for img_path in document.metadata["extracted_image_paths"]:
                try:
                    if not os.path.isfile(img_path):
                        continue
                    img_url = f"file://{os.path.abspath(img_path)}"
                    
                    # Create MediaItem for the extracted image
                    with store.Session() as session:
                        from sqlalchemy import select as _select
                        existing = session.execute(
                            _select(MediaItem).where(MediaItem.url == img_url)
                        ).scalar_one_or_none()
                        
                        if not existing:
                            media_id = _uuid.uuid4()
                            media_item = MediaItem(
                                id=media_id,
                                entry_type="media_item",
                                url=img_url,
                                media_type="image",
                                source_page_id=page_id,
                                processed=False,
                                metadata_json={
                                    "source_pdf": os.path.basename(file_path),
                                    "source_page_id": page_id_str,
                                    "extracted_from": "pdf",
                                    "local_path": img_path,
                                },
                            )
                            session.add(media_item)
                            session.commit()
                            extracted_images_count += 1
                            
                            # Create relationship: source PDF -> extracted image
                            try:
                                store.save_relationship(
                                    from_id=page_id_str,
                                    to_id=str(media_id),
                                    relation_type="contains_image",
                                    meta={
                                        "source": "pdf_image_extraction",
                                        "image_path": img_path,
                                    },
                                )
                            except Exception:
                                pass
                except Exception as e:
                    logger.debug(f"Failed to process extracted PDF image: {e}")
            
            if extracted_images_count:
                logger.info(f"Created {extracted_images_count} media items from PDF images")
        
        tq.update_progress(task_id, 1.0, "Local file ingestion complete")
        
        return {
            "page_id": page_id_str,
            "file_path": file_path,
            "stored_path": stored_path,
            "title": document.title,
            "content_length": len(document.content),
            "confidence": document.confidence,
            "source_type": document.source_type.value,
            "event": event,
            "action": upsert_action,
            "links_extracted": len(extracted_links),
            "crawl_tasks_queued": crawl_tasks_queued,
            "extracted_images": extracted_images_count,
            "file_hash": file_hash,
            "entities_extracted": entities_count,
            "intel_extracted": intel_count,
            "relationships_created": relationships_count,
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

# Database management: switch callback updates app-level references
def _on_db_switch(new_store, new_collection):
    """Called when the active database changes so all modules use the new store.

    Because *store* is a ``_StoreProxy``, swapping the internal target makes
    every closure that captured ``store`` (in all blueprints) transparently
    start using the new database – no re-registration needed.
    """
    store._swap(new_store)
    if vector_store and new_collection:
        try:
            vector_store.collection = new_collection
            vector_store._ensure_collection()
        except Exception as exc:
            logger.warning("Could not update vector collection: %s", exc)

app.register_blueprint(
    databases_routes.init_database_routes(api_key_required, db_manager, _on_db_switch)
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
        api_key_required, settings, task_queue, _directory_watcher, store
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
_register_task_handlers(task_queue, _agent_for_queue, store, gap_analyzer, adaptive_crawler,
                        llm_extractor=llm, vec_store=vector_store)

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
