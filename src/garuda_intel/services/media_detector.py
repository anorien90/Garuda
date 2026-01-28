"""
Automatic media detection and scoring for intelligent processing decisions.
"""

import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse


@dataclass
class MediaItem:
    """Represents a media item found on a page."""
    url: str
    media_type: str  # 'image', 'video', 'audio', 'pdf'
    source_url: str  # Page URL where media was found
    score: float = 0.0  # Information potential score
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class MediaDetector:
    """
    Automatically detects processable media on web pages.
    Scores media by information potential to prioritize processing.
    """
    
    def __init__(
        self,
        min_image_score: float = 0.3,
        min_video_duration: int = 30,
        max_file_size_mb: int = 50,
    ):
        """
        Initialize media detector.
        
        Args:
            min_image_score: Minimum score for image to be processed
            min_video_duration: Minimum video duration in seconds
            max_file_size_mb: Maximum file size to process (MB)
        """
        self.logger = logging.getLogger(__name__)
        self.min_image_score = min_image_score
        self.min_video_duration = min_video_duration
        self.max_file_size_mb = max_file_size_mb
        
        # Domains likely to have valuable media
        self.whitelist_domains = [
            'slideshare', 'youtube', 'vimeo', 'medium', 'substack',
            'linkedin', 'twitter', 'github', 'wikipedia',
        ]
        
        # Image extensions that may contain text
        self.text_image_extensions = [
            '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'
        ]
        
        # Video/audio extensions
        self.video_extensions = ['.mp4', '.webm', '.mov', '.avi', '.mkv']
        self.audio_extensions = ['.mp3', '.wav', '.m4a', '.ogg', '.flac']
        self.document_extensions = ['.pdf']

    def detect_media_on_page(self, html: str, url: str) -> List[MediaItem]:
        """
        Detect all processable media on a page.
        
        Args:
            html: HTML content of the page
            url: Page URL
            
        Returns:
            List of MediaItem objects, sorted by score (highest first)
        """
        if not html:
            return []
        
        media_items = []
        
        # Detect images
        media_items.extend(self._detect_images(html, url))
        
        # Detect videos
        media_items.extend(self._detect_videos(html, url))
        
        # Detect audio
        media_items.extend(self._detect_audio(html, url))
        
        # Detect PDFs
        media_items.extend(self._detect_pdfs(html, url))
        
        # Score all media items
        for item in media_items:
            item.score = self._score_media(item, url)
        
        # Filter and sort
        media_items = [m for m in media_items if self.should_process(m)]
        media_items.sort(key=lambda x: x.score, reverse=True)
        
        if media_items:
            self.logger.info(
                f"Detected {len(media_items)} processable media items on {url}"
            )
        
        return media_items

    def _detect_images(self, html: str, url: str) -> List[MediaItem]:
        """Detect images in HTML."""
        items = []
        
        # Find img tags
        img_pattern = r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>'
        for match in re.finditer(img_pattern, html, re.IGNORECASE):
            img_url = match.group(1)
            full_url = urljoin(url, img_url)
            
            # Extract metadata from img tag
            img_tag = match.group(0)
            metadata = {}
            
            # Get alt text
            alt_match = re.search(r'alt=["\']([^"\']+)["\']', img_tag)
            if alt_match:
                metadata['alt'] = alt_match.group(1)
            
            # Get dimensions
            width_match = re.search(r'width=["\']?(\d+)', img_tag)
            height_match = re.search(r'height=["\']?(\d+)', img_tag)
            if width_match:
                metadata['width'] = int(width_match.group(1))
            if height_match:
                metadata['height'] = int(height_match.group(1))
            
            items.append(MediaItem(
                url=full_url,
                media_type='image',
                source_url=url,
                metadata=metadata
            ))
        
        return items

    def _detect_videos(self, html: str, url: str) -> List[MediaItem]:
        """Detect videos in HTML."""
        items = []
        
        # Find video tags
        video_pattern = r'<video[^>]+src=["\']([^"\']+)["\'][^>]*>'
        for match in re.finditer(video_pattern, html, re.IGNORECASE):
            video_url = match.group(1)
            full_url = urljoin(url, video_url)
            
            items.append(MediaItem(
                url=full_url,
                media_type='video',
                source_url=url
            ))
        
        # Find source tags within video
        source_pattern = r'<source[^>]+src=["\']([^"\']+)["\'][^>]*type=["\']video'
        for match in re.finditer(source_pattern, html, re.IGNORECASE):
            video_url = match.group(1)
            full_url = urljoin(url, video_url)
            
            items.append(MediaItem(
                url=full_url,
                media_type='video',
                source_url=url
            ))
        
        # Detect YouTube embeds
        youtube_pattern = r'youtube\.com/embed/([a-zA-Z0-9_-]+)'
        for match in re.finditer(youtube_pattern, html):
            video_id = match.group(1)
            items.append(MediaItem(
                url=f"https://www.youtube.com/watch?v={video_id}",
                media_type='video',
                source_url=url,
                metadata={'platform': 'youtube', 'video_id': video_id}
            ))
        
        return items

    def _detect_audio(self, html: str, url: str) -> List[MediaItem]:
        """Detect audio files in HTML."""
        items = []
        
        # Find audio tags
        audio_pattern = r'<audio[^>]+src=["\']([^"\']+)["\'][^>]*>'
        for match in re.finditer(audio_pattern, html, re.IGNORECASE):
            audio_url = match.group(1)
            full_url = urljoin(url, audio_url)
            
            items.append(MediaItem(
                url=full_url,
                media_type='audio',
                source_url=url
            ))
        
        return items

    def _detect_pdfs(self, html: str, url: str) -> List[MediaItem]:
        """Detect PDF links in HTML."""
        items = []
        
        # Find links to PDFs
        pdf_pattern = r'<a[^>]+href=["\']([^"\']+\.pdf)["\'][^>]*>'
        for match in re.finditer(pdf_pattern, html, re.IGNORECASE):
            pdf_url = match.group(1)
            full_url = urljoin(url, pdf_url)
            
            items.append(MediaItem(
                url=full_url,
                media_type='pdf',
                source_url=url
            ))
        
        return items

    def _score_media(self, media: MediaItem, page_url: str) -> float:
        """
        Score media item by information potential.
        
        Args:
            media: MediaItem to score
            page_url: URL of the page containing the media
            
        Returns:
            Score from 0.0 to 1.0
        """
        score = 0.0
        
        # Domain whitelist bonus
        parsed_url = urlparse(page_url)
        if any(domain in parsed_url.netloc for domain in self.whitelist_domains):
            score += 0.3
        
        # Score by media type
        if media.media_type == 'image':
            score += self._score_image(media)
        elif media.media_type == 'video':
            score += 0.6  # Videos often have valuable content
        elif media.media_type == 'audio':
            score += 0.5  # Audio may have valuable speech
        elif media.media_type == 'pdf':
            score += 0.7  # PDFs often have structured information
        
        # Cap at 1.0
        return min(score, 1.0)

    def _score_image(self, media: MediaItem) -> float:
        """Score image by likelihood of containing valuable text."""
        score = 0.0
        
        metadata = media.metadata or {}
        
        # Check size (larger images more likely to have readable text)
        width = metadata.get('width', 0)
        height = metadata.get('height', 0)
        
        if width > 200 and height > 200:
            score += 0.3
        elif width > 100 and height > 100:
            score += 0.1
        
        # Check alt text (indicates meaningful image)
        if metadata.get('alt'):
            alt_text = metadata['alt'].lower()
            # Screenshots, diagrams, charts likely have text
            if any(keyword in alt_text for keyword in ['screenshot', 'diagram', 'chart', 'infographic', 'slide']):
                score += 0.3
            else:
                score += 0.1
        
        # Check URL for indicators
        url_lower = media.url.lower()
        if any(keyword in url_lower for keyword in ['screenshot', 'diagram', 'chart', 'slide', 'infographic']):
            score += 0.2
        
        # Avoid decorative images
        if any(keyword in url_lower for keyword in ['icon', 'logo', 'button', 'avatar', 'thumbnail']):
            score -= 0.3
        
        return max(score, 0.0)

    def should_process(self, media: MediaItem) -> bool:
        """
        Determine if media should be processed.
        
        Args:
            media: MediaItem to evaluate
            
        Returns:
            True if media should be processed
        """
        # Check score threshold
        if media.score < self.min_image_score:
            return False
        
        # Check file extension
        url_lower = media.url.lower()
        
        # Skip common non-processable formats
        if any(ext in url_lower for ext in ['.css', '.js', '.woff', '.ttf', '.eot']):
            return False
        
        # Accept if score is high enough
        if media.score >= self.min_image_score:
            return True
        
        return False

    def get_processing_priority(self, media_items: List[MediaItem]) -> List[MediaItem]:
        """
        Sort media items by processing priority.
        
        Args:
            media_items: List of MediaItem objects
            
        Returns:
            Sorted list (highest priority first)
        """
        # Already sorted by score in detect_media_on_page
        return media_items

    def estimate_processing_cost(self, media_items: List[MediaItem]) -> Dict[str, Any]:
        """
        Estimate processing cost for media items.
        
        Args:
            media_items: List of MediaItem objects
            
        Returns:
            Dictionary with cost estimates
        """
        cost = {
            'total_items': len(media_items),
            'images': sum(1 for m in media_items if m.media_type == 'image'),
            'videos': sum(1 for m in media_items if m.media_type == 'video'),
            'audio': sum(1 for m in media_items if m.media_type == 'audio'),
            'pdfs': sum(1 for m in media_items if m.media_type == 'pdf'),
            'estimated_time_seconds': 0,
        }
        
        # Rough time estimates
        cost['estimated_time_seconds'] += cost['images'] * 2  # 2 sec per image
        cost['estimated_time_seconds'] += cost['videos'] * 30  # 30 sec per video
        cost['estimated_time_seconds'] += cost['audio'] * 15  # 15 sec per audio
        cost['estimated_time_seconds'] += cost['pdfs'] * 10  # 10 sec per PDF
        
        return cost
