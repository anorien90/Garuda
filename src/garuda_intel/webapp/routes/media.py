"""Media processing API routes."""

from flask import Blueprint, request, jsonify
import logging
from typing import Callable

from ...services.media_processor import MediaProcessor

logger = logging.getLogger(__name__)


def init_media_routes(
    api_key_required: Callable, 
    store, 
    llm,
    media_processor: MediaProcessor
) -> Blueprint:
    """Initialize media processing routes.
    
    Args:
        api_key_required: Auth decorator
        store: Database store
        llm: LLM extractor
        media_processor: Media processing service
    
    Returns:
        Flask Blueprint with media routes
    """
    bp = Blueprint("media", __name__, url_prefix="/api/media")

    @bp.route("/stats", methods=["GET"])
    @api_key_required
    def get_media_stats():
        """Get media processing statistics."""
        try:
            with store.get_session() as session:
                from ...database.models import MediaItem
                
                total = session.query(MediaItem).count()
                processed = session.query(MediaItem).filter(MediaItem.processed == True).count()
                errors = session.query(MediaItem).filter(MediaItem.processing_error.isnot(None)).count()
                pending = total - processed
                
                return jsonify({
                    "total": total,
                    "processed": processed,
                    "pending": pending,
                    "errors": errors
                })
        except Exception as e:
            logger.error(f"Error getting media stats: {e}")
            return jsonify({"error": str(e)}), 500

    @bp.route("/items", methods=["GET"])
    @api_key_required
    def list_media_items():
        """List media items with optional filtering."""
        try:
            media_type = request.args.get("type")
            processed = request.args.get("processed")
            limit = int(request.args.get("limit", 50))
            offset = int(request.args.get("offset", 0))
            
            with store.get_session() as session:
                from ...database.models import MediaItem
                
                query = session.query(MediaItem)
                
                if media_type:
                    query = query.filter(MediaItem.media_type == media_type)
                
                if processed == "true":
                    query = query.filter(MediaItem.processed.is_(True))
                elif processed == "false":
                    query = query.filter(MediaItem.processed.is_(False))
                elif processed == "error":
                    query = query.filter(MediaItem.processing_error.isnot(None))
                
                total = query.count()
                items = query.order_by(MediaItem.created_at.desc()).limit(limit).offset(offset).all()
                
                return jsonify({
                    "total": total,
                    "items": [
                        {
                            "id": str(item.id),
                            "url": item.url,
                            "media_type": item.media_type,
                            "processed": item.processed,
                            "extracted_text": item.extracted_text[:200] if item.extracted_text else None,
                            "processing_error": item.processing_error,
                            "processed_at": item.processed_at.isoformat() if item.processed_at else None,
                            "created_at": item.created_at.isoformat() if item.created_at else None,
                        }
                        for item in items
                    ]
                })
        except Exception as e:
            logger.error(f"Error listing media items: {e}")
            return jsonify({"error": str(e)}), 500

    @bp.route("/process", methods=["POST"])
    @api_key_required
    def process_media():
        """Process a media item manually."""
        try:
            data = request.json
            url = data.get("url")
            media_type = data.get("media_type", "image")
            page_url = data.get("page_url")
            auto_process = data.get("auto_process", True)
            
            if not url:
                return jsonify({"error": "url is required"}), 400
            
            # Validate media_type
            if media_type not in ["image", "video", "audio"]:
                return jsonify({"error": f"Invalid media_type: {media_type}. Must be one of: image, video, audio"}), 400
            
            # Basic URL validation
            if not url.startswith(("http://", "https://")):
                return jsonify({"error": "Invalid URL format. Must start with http:// or https://"}), 400
            
            # Process the media and create item in database
            with store.get_session() as session:
                from ...database.models import MediaItem, Page
                import uuid
                
                # Find page if page_url provided
                page_id = None
                if page_url:
                    page = session.query(Page).filter(Page.url == page_url).first()
                    if page:
                        page_id = page.id
                
                # Check if media item already exists
                existing = session.query(MediaItem).filter(MediaItem.url == url).first()
                if existing:
                    # If already exists and processed, return existing
                    if existing.processed:
                        return jsonify({
                            "message": "Media item already exists and is processed",
                            "id": str(existing.id),
                            "processed": existing.processed,
                            "extracted_text": existing.extracted_text[:200] if existing.extracted_text else None
                        })
                    # If exists but not processed, we'll try to process it
                    media_item = existing
                else:
                    # Create new media item
                    media_item = MediaItem(
                        id=uuid.uuid4(),
                        url=url,
                        media_type=media_type,
                        source_page_id=page_id,
                        processed=False
                    )
                    session.add(media_item)
                    session.flush()
                
                # Process the media if auto_process is enabled
                if auto_process and media_processor.enabled:
                    logger.info(f"Processing media from URL: {url}")
                    processing_result = media_processor.process_from_url(url, media_type)
                    
                    # Update media item with processing results
                    media_item.processed = processing_result.get("processed", False)
                    media_item.processed_at = processing_result.get("processed_at")
                    media_item.extracted_text = processing_result.get("extracted_text")
                    media_item.text_embedding = processing_result.get("text_embedding")
                    media_item.processing_error = processing_result.get("processing_error")
                    media_item.file_size = processing_result.get("file_size")
                    media_item.mime_type = processing_result.get("mime_type")
                    media_item.width = processing_result.get("width")
                    media_item.height = processing_result.get("height")
                    media_item.duration = processing_result.get("duration")
                    
                    if processing_result.get("metadata_json"):
                        media_item.metadata_json = processing_result["metadata_json"]
                    
                    session.commit()
                    
                    return jsonify({
                        "message": "Media item processed successfully",
                        "id": str(media_item.id),
                        "processed": media_item.processed,
                        "extracted_text": media_item.extracted_text[:200] if media_item.extracted_text else None,
                        "has_embedding": bool(media_item.text_embedding),
                        "processing_error": media_item.processing_error
                    })
                else:
                    # Just create the item without processing
                    session.commit()
                    return jsonify({
                        "message": "Media item created. Set auto_process=true to process immediately.",
                        "id": str(media_item.id),
                        "status": "pending"
                    })
                
        except Exception as e:
            logger.error(f"Error processing media: {e}")
            return jsonify({"error": str(e)}), 500

    @bp.route("/settings", methods=["GET", "POST"])
    @api_key_required
    def media_settings():
        """Get or update media processing settings."""
        if request.method == "GET":
            return jsonify({
                "media_crawling_enabled": True,  # Would be from config
                "auto_process": True,
                "generate_embeddings": True,
                "supported_types": ["image", "video", "audio"]
            })
        else:
            # Update settings (would save to config)
            data = request.json
            return jsonify({
                "message": "Settings updated",
                "settings": data
            })

    @bp.route("/process-pending", methods=["POST"])
    @api_key_required
    def process_pending():
        """Process pending media items in batch."""
        try:
            limit = int(request.args.get("limit", 10))
            
            with store.get_session() as session:
                from ...database.models import MediaItem
                
                # Get pending media items
                pending_items = session.query(MediaItem).filter(
                    MediaItem.processed == False,
                    MediaItem.processing_error.is_(None)
                ).limit(limit).all()
                
                processed_count = 0
                failed_count = 0
                results = []
                
                for item in pending_items:
                    logger.info(f"Processing pending media item: {item.url}")
                    processing_result = media_processor.process_from_url(item.url, item.media_type)
                    
                    # Update item with results
                    item.processed = processing_result.get("processed", False)
                    item.processed_at = processing_result.get("processed_at")
                    item.extracted_text = processing_result.get("extracted_text")
                    item.text_embedding = processing_result.get("text_embedding")
                    item.processing_error = processing_result.get("processing_error")
                    item.file_size = processing_result.get("file_size")
                    item.mime_type = processing_result.get("mime_type")
                    item.width = processing_result.get("width")
                    item.height = processing_result.get("height")
                    item.duration = processing_result.get("duration")
                    
                    if processing_result.get("metadata_json"):
                        item.metadata_json = processing_result["metadata_json"]
                    
                    if item.processed and not item.processing_error:
                        processed_count += 1
                    else:
                        failed_count += 1
                    
                    results.append({
                        "id": str(item.id),
                        "url": item.url,
                        "processed": item.processed,
                        "error": item.processing_error
                    })
                
                session.commit()
                
                return jsonify({
                    "message": f"Processed {processed_count} items, {failed_count} failed",
                    "processed": processed_count,
                    "failed": failed_count,
                    "results": results
                })
                
        except Exception as e:
            logger.error(f"Error processing pending media: {e}")
            return jsonify({"error": str(e)}), 500

    return bp
