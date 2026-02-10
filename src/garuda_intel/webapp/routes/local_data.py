"""Local Data API routes for file upload and directory watching."""

import logging
import os
import tempfile
from flask import Blueprint, jsonify, request

from ..services.event_system import emit_event

bp_local_data = Blueprint('local_data', __name__, url_prefix='/api/local-data')
logger = logging.getLogger(__name__)


def init_local_data_routes(api_key_required, settings, task_queue, directory_watcher=None):
    """Initialize local data routes.
    
    Args:
        api_key_required: Auth decorator
        settings: Application settings
        task_queue: TaskQueueService instance
        directory_watcher: Optional DirectoryWatcherService instance
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
