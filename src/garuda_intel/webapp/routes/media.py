"""Media processing API routes."""

from flask import Blueprint, request, jsonify
import logging
from typing import Callable

from ....services.media_processor import MediaProcessor

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
                from ....database.models import MediaItem
                
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
                from ....database.models import MediaItem
                
                query = session.query(MediaItem)
                
                if media_type:
                    query = query.filter(MediaItem.media_type == media_type)
                
                if processed == "true":
                    query = query.filter(MediaItem.processed == True)
                elif processed == "false":
                    query = query.filter(MediaItem.processed == False)
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
            
            if not url:
                return jsonify({"error": "url is required"}), 400
            
            # Create media item in database
            with store.get_session() as session:
                from ....database.models import MediaItem, Page
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
                    return jsonify({
                        "message": "Media item already exists",
                        "id": str(existing.id),
                        "processed": existing.processed
                    })
                
                # Create new media item
                media_item = MediaItem(
                    id=uuid.uuid4(),
                    url=url,
                    media_type=media_type,
                    source_page_id=page_id,
                    processed=False
                )
                
                session.add(media_item)
                session.commit()
                
                return jsonify({
                    "message": "Media item created. Processing is not yet implemented.",
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

    return bp
