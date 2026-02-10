"""Local Data API routes for file upload, directory watching, and file browsing."""

import logging
import os
import tempfile
from flask import Blueprint, jsonify, request, send_file

from ..services.event_system import emit_event

bp_local_data = Blueprint('local_data', __name__, url_prefix='/api/local-data')
logger = logging.getLogger(__name__)


def init_local_data_routes(api_key_required, settings, task_queue, directory_watcher=None, store=None):
    """Initialize local data routes.
    
    Args:
        api_key_required: Auth decorator
        settings: Application settings
        task_queue: TaskQueueService instance
        directory_watcher: Optional DirectoryWatcherService instance
        store: Optional SQLAlchemyStore instance for file browsing
    """

    @bp_local_data.post("/upload")
    @api_key_required
    def api_upload_file():
        """
        Upload a file for processing through the extraction pipeline.
        
        Accepts multipart/form-data with a 'file' field.
        The file is saved to a temporary location and queued for processing.
        
        Returns:
            JSON with task_id and file info
        """
        if 'file' not in request.files:
            return jsonify({"error": "No file provided. Use 'file' field in multipart/form-data."}), 400
        
        uploaded_file = request.files['file']
        
        if not uploaded_file.filename:
            return jsonify({"error": "No filename provided"}), 400
        
        # Validate file extension
        from ...sources.local_file_adapter import LocalFileAdapter
        supported = LocalFileAdapter.get_supported_extensions()
        _, ext = os.path.splitext(uploaded_file.filename)
        ext = ext.lower()
        
        if ext not in supported:
            return jsonify({
                "error": f"Unsupported file type: {ext}",
                "supported_extensions": supported,
            }), 400
        
        # Check file size
        max_size = settings.local_data_max_file_size_mb * 1024 * 1024
        uploaded_file.seek(0, os.SEEK_END)
        file_size = uploaded_file.tell()
        uploaded_file.seek(0)
        
        if file_size > max_size:
            return jsonify({
                "error": f"File too large: {file_size / 1024 / 1024:.1f}MB "
                         f"(max: {settings.local_data_max_file_size_mb}MB)",
            }), 400
        
        # Save to upload directory (always use data dir, watch dir may be read-only)
        db_path = settings.db_url.replace("sqlite:///", "")
        base_dir = os.path.dirname(db_path) if "sqlite" in settings.db_url else "/app/data"
        upload_dir = os.path.join(base_dir, "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        
        # Use secure filename
        safe_filename = _secure_filename(uploaded_file.filename)
        save_path = os.path.join(upload_dir, safe_filename)
        
        # Handle duplicate filenames
        if os.path.exists(save_path):
            base, ext = os.path.splitext(safe_filename)
            counter = 1
            while os.path.exists(save_path):
                safe_filename = f"{base}_{counter}{ext}"
                save_path = os.path.join(upload_dir, safe_filename)
                counter += 1
        
        uploaded_file.save(save_path)
        
        # Submit task for processing
        from ...services.task_queue import TaskQueueService
        task_id = task_queue.submit(
            task_type=TaskQueueService.TASK_LOCAL_INGEST,
            params={
                "file_path": save_path,
                "event": "upload",
                "original_filename": uploaded_file.filename,
                "stored_path": save_path,
            },
            priority=1,  # Uploads get slightly higher priority
        )
        
        emit_event("file_uploaded", f"File uploaded: {uploaded_file.filename}", payload={
            "task_id": task_id,
            "filename": uploaded_file.filename,
            "file_size": file_size,
        })
        
        logger.info(f"File uploaded and queued: {uploaded_file.filename} -> {task_id}")
        
        return jsonify({
            "task_id": task_id,
            "filename": uploaded_file.filename,
            "saved_path": save_path,
            "file_size": file_size,
            "status": "queued",
            "message": f"File '{uploaded_file.filename}' uploaded and queued for processing",
        }), 201

    @bp_local_data.get("/supported-types")
    @api_key_required
    def api_supported_types():
        """Get list of supported file types for upload."""
        from ...sources.local_file_adapter import LocalFileAdapter
        return jsonify({
            "supported_extensions": LocalFileAdapter.get_supported_extensions(),
            "categories": {
                "pdf": LocalFileAdapter.PDF_EXTENSIONS,
                "text": LocalFileAdapter.TEXT_EXTENSIONS,
                "image": LocalFileAdapter.IMAGE_EXTENSIONS,
                "media": LocalFileAdapter.MEDIA_EXTENSIONS,
            },
        })

    @bp_local_data.get("/watcher/status")
    @api_key_required
    def api_watcher_status():
        """Get directory watcher status."""
        if directory_watcher is None:
            return jsonify({
                "enabled": False,
                "message": "Directory watcher not configured. "
                           "Set GARUDA_LOCAL_DATA_WATCH_DIR and "
                           "GARUDA_LOCAL_DATA_WATCH_ENABLED=true to enable.",
            })
        
        return jsonify(directory_watcher.get_status())

    @bp_local_data.post("/watcher/scan")
    @api_key_required
    def api_watcher_scan():
        """Trigger a manual scan of the watched directory."""
        if directory_watcher is None:
            return jsonify({
                "error": "Directory watcher not configured",
            }), 400
        
        result = directory_watcher.scan_existing()
        
        emit_event("directory_scanned", f"Manual scan: {result['queued']} files queued", payload={
            "queued": result["queued"],
            "skipped": result["skipped"],
        })
        
        return jsonify({
            "message": "Directory scan completed",
            **result,
        })

    @bp_local_data.post("/ingest")
    @api_key_required
    def api_ingest_path():
        """
        Ingest a file from a local path.
        
        Request body (JSON):
            file_path: Path to local file to ingest
        """
        body = request.get_json(silent=True) or {}
        file_path = body.get("file_path", "").strip()
        
        if not file_path:
            return jsonify({"error": "file_path is required"}), 400
        
        # Validate file exists and is accessible
        real_path = os.path.realpath(file_path)
        if not os.path.isfile(real_path):
            return jsonify({"error": "Invalid file path"}), 400
        
        # Validate extension
        from ...sources.local_file_adapter import LocalFileAdapter
        _, ext = os.path.splitext(real_path)
        if ext.lower() not in LocalFileAdapter.get_supported_extensions():
            return jsonify({
                "error": f"Unsupported file type: {ext}",
                "supported_extensions": LocalFileAdapter.get_supported_extensions(),
            }), 400
        
        # Copy file to uploads directory for persistence
        db_path = settings.db_url.replace("sqlite:///", "")
        base_dir = os.path.dirname(db_path) if "sqlite" in settings.db_url else "/app/data"
        upload_dir = os.path.join(base_dir, "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        
        import shutil
        safe_name = os.path.basename(real_path)
        stored_path = os.path.join(upload_dir, safe_name)
        if os.path.exists(stored_path):
            base_name, ext_part = os.path.splitext(safe_name)
            counter = 1
            while os.path.exists(stored_path):
                stored_path = os.path.join(upload_dir, f"{base_name}_{counter}{ext_part}")
                counter += 1
        shutil.copy2(real_path, stored_path)
        
        # Submit task
        from ...services.task_queue import TaskQueueService
        task_id = task_queue.submit(
            task_type=TaskQueueService.TASK_LOCAL_INGEST,
            params={
                "file_path": stored_path,
                "event": "manual_ingest",
                "original_filename": os.path.basename(real_path),
                "stored_path": stored_path,
            },
            priority=1,
        )
        
        logger.info(f"File ingestion queued: {real_path} -> {task_id}")
        
        return jsonify({
            "task_id": task_id,
            "file_path": real_path,
            "status": "queued",
            "message": f"File queued for processing",
        }), 201

    # ========================================================================
    # FILE BROWSER & METADATA MANAGEMENT
    # ========================================================================

    @bp_local_data.get("/files")
    @api_key_required
    def api_browse_files():
        """
        Browse uploaded and ingested files stored in the database.
        
        Query params:
            q: Search query (filters by filename, URL, or content)
            page_type: Filter by page type (e.g., 'local_file')
            limit: Max results (default: 50)
            offset: Pagination offset (default: 0)
        
        Returns:
            JSON with list of files and their metadata
        """
        if not store:
            return jsonify({"error": "Database store not available"}), 500
        
        from ...database.models import Page, PageContent
        from sqlalchemy import select, func, or_, desc
        
        q = request.args.get("q", "").strip()
        page_type = request.args.get("page_type", "local_file")
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = int(request.args.get("offset", 0))
        
        try:
            with store.Session() as session:
                stmt = select(Page).where(Page.page_type == page_type)
                
                if q:
                    like = f"%{q.lower()}%"
                    stmt = stmt.where(
                        or_(
                            func.lower(Page.url).ilike(like),
                            func.lower(Page.title).ilike(like),
                        )
                    )
                
                # Count total
                count_stmt = select(func.count()).select_from(
                    stmt.subquery()
                )
                total = session.execute(count_stmt).scalar() or 0
                
                # Fetch paginated results
                stmt = stmt.order_by(desc(Page.last_fetch_at)).offset(offset).limit(limit)
                pages = session.execute(stmt).scalars().all()
                
                files = []
                for page in pages:
                    file_info = page.to_dict()
                    
                    # Get content metadata
                    pc = session.execute(
                        select(PageContent).where(PageContent.page_id == page.id)
                    ).scalar_one_or_none()
                    
                    if pc and pc.metadata_json:
                        meta = pc.metadata_json
                        file_info["original_filename"] = meta.get("original_filename", page.title)
                        file_info["stored_path"] = meta.get("stored_path", "")
                        file_info["file_type"] = meta.get("file_type", "")
                        file_info["file_size_mb"] = meta.get("file_size_mb", 0)
                        file_info["file_size_bytes"] = meta.get("file_size_bytes", 0)
                        file_info["mime_type"] = meta.get("mime_type", "")
                        file_info["file_hash"] = meta.get("file_hash", "")
                        file_info["confidence"] = meta.get("confidence", 0)
                        file_info["extracted_images_count"] = meta.get("extracted_images_count", 0)
                        file_info["content_length"] = len(pc.text) if pc.text else 0
                    else:
                        file_info["original_filename"] = page.title
                        file_info["content_length"] = 0
                    
                    files.append(file_info)
                
                return jsonify({
                    "files": files,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                })
        except Exception as e:
            logger.error(f"Error browsing files: {e}")
            return jsonify({"error": str(e)}), 500

    @bp_local_data.get("/files/<file_id>")
    @api_key_required
    def api_get_file_detail(file_id):
        """
        Get detailed information about a specific file.
        
        Returns file metadata, content preview, extracted entities, 
        relationships, and intelligence records.
        """
        if not store:
            return jsonify({"error": "Database store not available"}), 500
        
        import uuid
        from ...database.models import Page, PageContent, Intelligence, Relationship, MediaItem
        from sqlalchemy import select, or_
        
        try:
            page_uuid = uuid.UUID(file_id)
        except ValueError:
            return jsonify({"error": "Invalid file ID"}), 400
        
        try:
            with store.Session() as session:
                page = session.get(Page, page_uuid)
                if not page:
                    return jsonify({"error": "File not found"}), 404
                
                file_info = page.to_dict()
                
                # Get content
                pc = session.execute(
                    select(PageContent).where(PageContent.page_id == page.id)
                ).scalar_one_or_none()
                
                if pc:
                    file_info["content_preview"] = (pc.text[:2000] + "...") if pc.text and len(pc.text) > 2000 else (pc.text or "")
                    file_info["content_length"] = len(pc.text) if pc.text else 0
                    file_info["metadata"] = pc.metadata_json or {}
                    file_info["extracted_data"] = pc.extracted_json or {}
                
                # Get related intelligence records
                intel_records = session.execute(
                    select(Intelligence).where(Intelligence.page_id == page.id)
                ).scalars().all()
                file_info["intelligence"] = [
                    {
                        "id": str(i.id),
                        "entity_name": i.entity_name,
                        "entity_type": i.entity_type,
                        "confidence": i.confidence,
                        "data": i.data,
                    }
                    for i in intel_records
                ]
                
                # Get related relationships (where this page is referenced)
                relationships_out = session.execute(
                    select(Relationship).where(
                        Relationship.source_id == page.id
                    )
                ).scalars().all()
                relationships_in = session.execute(
                    select(Relationship).where(
                        Relationship.target_id == page.id
                    )
                ).scalars().all()
                
                file_info["relationships"] = [
                    {
                        "id": str(r.id),
                        "source_id": str(r.source_id),
                        "target_id": str(r.target_id),
                        "relation_type": r.relation_type,
                        "direction": "outgoing",
                        "metadata": r.metadata_json,
                    }
                    for r in relationships_out
                ] + [
                    {
                        "id": str(r.id),
                        "source_id": str(r.source_id),
                        "target_id": str(r.target_id),
                        "relation_type": r.relation_type,
                        "direction": "incoming",
                        "metadata": r.metadata_json,
                    }
                    for r in relationships_in
                ]
                
                # Get extracted media items (images from PDFs)
                media_items = session.execute(
                    select(MediaItem).where(MediaItem.source_page_id == page.id)
                ).scalars().all()
                file_info["media_items"] = [
                    {
                        "id": str(m.id),
                        "url": m.url,
                        "media_type": m.media_type,
                        "processed": m.processed,
                        "extracted_text": m.extracted_text[:200] if m.extracted_text else None,
                        "metadata": m.metadata_json,
                    }
                    for m in media_items
                ]
                
                return jsonify(file_info)
        except Exception as e:
            logger.error(f"Error getting file detail: {e}")
            return jsonify({"error": str(e)}), 500

    @bp_local_data.put("/files/<file_id>/metadata")
    @api_key_required
    def api_update_file_metadata(file_id):
        """
        Update metadata for a specific file.
        
        Request body (JSON):
            title: New title for the file
            tags: List of tags
            notes: User notes
            custom_metadata: Dict of custom key-value metadata
        """
        if not store:
            return jsonify({"error": "Database store not available"}), 500
        
        import uuid
        from ...database.models import Page, PageContent
        from sqlalchemy import select
        
        try:
            page_uuid = uuid.UUID(file_id)
        except ValueError:
            return jsonify({"error": "Invalid file ID"}), 400
        
        body = request.get_json(silent=True) or {}
        
        try:
            with store.Session() as session:
                page = session.get(Page, page_uuid)
                if not page:
                    return jsonify({"error": "File not found"}), 404
                
                # Update page title if provided
                if "title" in body:
                    page.title = body["title"]
                
                # Update content metadata
                pc = session.execute(
                    select(PageContent).where(PageContent.page_id == page.id)
                ).scalar_one_or_none()
                
                if pc:
                    meta = pc.metadata_json or {}
                    
                    if "tags" in body:
                        meta["tags"] = body["tags"]
                    if "notes" in body:
                        meta["notes"] = body["notes"]
                    if "custom_metadata" in body:
                        meta["custom_metadata"] = body["custom_metadata"]
                    
                    pc.metadata_json = meta
                
                session.commit()
                
                return jsonify({
                    "success": True,
                    "file_id": file_id,
                    "message": "Metadata updated successfully",
                })
        except Exception as e:
            logger.error(f"Error updating file metadata: {e}")
            return jsonify({"error": str(e)}), 500

    @bp_local_data.post("/files/<file_id>/relations")
    @api_key_required
    def api_add_file_relation(file_id):
        """
        Add a relationship between a file and another entity or file.
        
        Request body (JSON):
            target_id: UUID of the target entity/file
            relation_type: Type of relationship (e.g., 'related_to', 'derived_from')
            description: Optional description of the relationship
        """
        if not store:
            return jsonify({"error": "Database store not available"}), 500
        
        import uuid
        from ...database.models import Page
        
        try:
            page_uuid = uuid.UUID(file_id)
        except ValueError:
            return jsonify({"error": "Invalid file ID"}), 400
        
        body = request.get_json(silent=True) or {}
        target_id = body.get("target_id", "").strip()
        relation_type = body.get("relation_type", "related_to").strip()
        description = body.get("description", "")
        
        if not target_id:
            return jsonify({"error": "target_id is required"}), 400
        
        try:
            uuid.UUID(target_id)
        except ValueError:
            return jsonify({"error": "Invalid target_id"}), 400
        
        try:
            with store.Session() as session:
                page = session.get(Page, page_uuid)
                if not page:
                    return jsonify({"error": "Source file not found"}), 404
            
            rel_id = store.save_relationship(
                from_id=file_id,
                to_id=target_id,
                relation_type=relation_type,
                meta={"description": description, "source": "user_manual"},
            )
            
            return jsonify({
                "success": True,
                "relationship_id": str(rel_id) if rel_id else None,
                "message": "Relationship created",
            }), 201
        except Exception as e:
            logger.error(f"Error adding file relation: {e}")
            return jsonify({"error": str(e)}), 500

    @bp_local_data.get("/files/<file_id>/download")
    @api_key_required
    def api_download_file(file_id):
        """Download the original uploaded file."""
        if not store:
            return jsonify({"error": "Database store not available"}), 500
        
        import uuid
        from ...database.models import Page, PageContent
        from sqlalchemy import select
        
        try:
            page_uuid = uuid.UUID(file_id)
        except ValueError:
            return jsonify({"error": "Invalid file ID"}), 400
        
        try:
            with store.Session() as session:
                page = session.get(Page, page_uuid)
                if not page:
                    return jsonify({"error": "File not found"}), 404
                
                pc = session.execute(
                    select(PageContent).where(PageContent.page_id == page.id)
                ).scalar_one_or_none()
                
                stored_path = None
                if pc and pc.metadata_json:
                    stored_path = pc.metadata_json.get("stored_path")
                
                if not stored_path or not os.path.isfile(stored_path):
                    return jsonify({"error": "File not found on disk"}), 404
                
                return send_file(
                    stored_path,
                    as_attachment=True,
                    download_name=page.title or os.path.basename(stored_path),
                )
        except Exception as e:
            logger.error(f"Error downloading file: {e}")
            return jsonify({"error": str(e)}), 500

    return bp_local_data


def _secure_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and other issues.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename safe for filesystem use
    """
    import re
    
    # Get just the filename, not the path
    filename = os.path.basename(filename)
    
    # Remove any non-alphanumeric characters except dots, dashes, underscores
    filename = re.sub(r'[^\w\-.]', '_', filename)
    
    # Remove leading dots (hidden files)
    filename = filename.lstrip('.')
    
    # Ensure we have a filename
    if not filename:
        filename = "uploaded_file"
    
    return filename
