"""Media extraction service for crawled pages."""

import logging
from typing import List, Dict, Optional
from urllib.parse import urljoin
import uuid

logger = logging.getLogger(__name__)


class MediaExtractor:
    """Extract and create media items from crawled pages."""

    def __init__(self, store, media_processor, auto_process: bool = True):
        """Initialize media extractor.
        
        Args:
            store: Database store
            media_processor: MediaProcessor instance
            auto_process: Whether to automatically process extracted media
        """
        self.store = store
        self.media_processor = media_processor
        self.auto_process = auto_process

    def extract_media_from_page(self, page_id: uuid.UUID, page_url: str, html: str) -> Dict[str, int]:
        """Extract media items from a page's HTML and store them.
        
        Args:
            page_id: UUID of the page
            page_url: URL of the page (for resolving relative URLs)
            html: HTML content of the page
            
        Returns:
            Dict with counts of extracted media by type
        """
        from bs4 import BeautifulSoup
        from ..database.models import MediaItem
        
        soup = BeautifulSoup(html, "html.parser")
        stats = {"images": 0, "videos": 0, "audio": 0}
        
        with self.store.get_session() as session:
            # Extract images
            for img in soup.find_all("img"):
                src = img.get("src")
                if src and not src.startswith("data:"):
                    # Resolve relative URL
                    absolute_url = urljoin(page_url, src)
                    
                    # Check if media item already exists
                    existing = session.query(MediaItem).filter(MediaItem.url == absolute_url).first()
                    if existing:
                        # Update page association if not set
                        if not existing.source_page_id:
                            existing.source_page_id = page_id
                        continue
                    
                    # Create new media item
                    media_item = MediaItem(
                        id=uuid.uuid4(),
                        url=absolute_url,
                        media_type="image",
                        source_page_id=page_id,
                        processed=False
                    )
                    session.add(media_item)
                    stats["images"] += 1
                    
                    # Process immediately if auto_process enabled
                    if self.auto_process:
                        self._process_media_item(media_item)
            
            # Extract videos (HTML5 video tags and common embed patterns)
            for video in soup.find_all("video"):
                for source in video.find_all("source"):
                    src = source.get("src")
                    if src:
                        absolute_url = urljoin(page_url, src)
                        
                        existing = session.query(MediaItem).filter(MediaItem.url == absolute_url).first()
                        if existing:
                            if not existing.source_page_id:
                                existing.source_page_id = page_id
                            continue
                        
                        media_item = MediaItem(
                            id=uuid.uuid4(),
                            url=absolute_url,
                            media_type="video",
                            source_page_id=page_id,
                            processed=False
                        )
                        session.add(media_item)
                        stats["videos"] += 1
                        
                        if self.auto_process:
                            self._process_media_item(media_item)
            
            # Extract audio (HTML5 audio tags)
            for audio in soup.find_all("audio"):
                for source in audio.find_all("source"):
                    src = source.get("src")
                    if src:
                        absolute_url = urljoin(page_url, src)
                        
                        existing = session.query(MediaItem).filter(MediaItem.url == absolute_url).first()
                        if existing:
                            if not existing.source_page_id:
                                existing.source_page_id = page_id
                            continue
                        
                        media_item = MediaItem(
                            id=uuid.uuid4(),
                            url=absolute_url,
                            media_type="audio",
                            source_page_id=page_id,
                            processed=False
                        )
                        session.add(media_item)
                        stats["audio"] += 1
                        
                        if self.auto_process:
                            self._process_media_item(media_item)
            
            session.commit()
        
        logger.info(f"Extracted {stats['images']} images, {stats['videos']} videos, {stats['audio']} audio from {page_url}")
        return stats

    def _process_media_item(self, media_item: "MediaItem"):
        """Process a media item (download and extract text).
        
        Args:
            media_item: MediaItem database object
        """
        try:
            logger.info(f"Processing media: {media_item.url}")
            result = self.media_processor.process_from_url(media_item.url, media_item.media_type)
            
            # Update media item with results
            media_item.processed = result.get("processed", False)
            media_item.processed_at = result.get("processed_at")
            media_item.extracted_text = result.get("extracted_text")
            media_item.text_embedding = result.get("text_embedding")
            media_item.processing_error = result.get("processing_error")
            media_item.file_size = result.get("file_size")
            media_item.mime_type = result.get("mime_type")
            media_item.width = result.get("width")
            media_item.height = result.get("height")
            media_item.duration = result.get("duration")
            
            if result.get("metadata_json"):
                media_item.metadata_json = result["metadata_json"]
                
        except Exception as e:
            logger.error(f"Error processing media item {media_item.url}: {e}")
            media_item.processing_error = str(e)
            media_item.processed = False
