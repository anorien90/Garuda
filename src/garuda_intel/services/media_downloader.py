"""Media file downloader with retry logic and caching."""

import os
import hashlib
import logging
import requests
from typing import Optional, Tuple
from pathlib import Path
import mimetypes
import tempfile

logger = logging.getLogger(__name__)


class MediaDownloader:
    """Download and cache media files from URLs."""

    def __init__(self, cache_dir: Optional[str] = None, max_file_size: int = 100 * 1024 * 1024):
        """Initialize media downloader.
        
        Args:
            cache_dir: Directory to cache downloaded files (default: temp directory)
            max_file_size: Maximum file size to download in bytes (default: 100MB)
        """
        if cache_dir:
            self.cache_dir = Path(cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.cache_dir = Path(tempfile.gettempdir()) / "garuda_media_cache"
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_file_size = max_file_size
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; Garuda/1.0; +https://github.com/anorien90/Garuda)'
        })

    def _get_cache_path(self, url: str, file_extension: Optional[str] = None) -> Path:
        """Generate cache file path for a URL.
        
        Args:
            url: Media URL
            file_extension: Optional file extension to use
            
        Returns:
            Path to cache file
        """
        # Generate hash of URL for filename
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        
        if file_extension:
            if not file_extension.startswith('.'):
                file_extension = f'.{file_extension}'
            filename = f"{url_hash}{file_extension}"
        else:
            filename = url_hash
        
        return self.cache_dir / filename

    def download(self, url: str, timeout: int = 30, max_retries: int = 3) -> Tuple[Optional[str], Optional[dict]]:
        """Download media file from URL with retry logic.
        
        Args:
            url: URL of media file
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            
        Returns:
            Tuple of (local_file_path, metadata_dict) or (None, None) on failure
        """
        for attempt in range(max_retries):
            try:
                # Send HEAD request first to check file size and type
                head_response = self.session.head(url, timeout=timeout, allow_redirects=True)
                head_response.raise_for_status()
                
                # Get content type and size
                content_type = head_response.headers.get('Content-Type', '')
                content_length = head_response.headers.get('Content-Length')
                
                # Check file size
                if content_length and int(content_length) > self.max_file_size:
                    logger.warning(f"File too large: {url} ({content_length} bytes)")
                    return None, {"error": "File too large"}
                
                # Determine file extension from content type
                ext = mimetypes.guess_extension(content_type.split(';')[0])
                cache_path = self._get_cache_path(url, ext)
                
                # Check if already cached
                if cache_path.exists():
                    logger.info(f"Using cached file for {url}")
                    return str(cache_path), {
                        "cached": True,
                        "mime_type": content_type,
                        "file_size": cache_path.stat().st_size
                    }
                
                # Download file
                logger.info(f"Downloading {url} (attempt {attempt + 1}/{max_retries})")
                response = self.session.get(url, timeout=timeout, stream=True)
                response.raise_for_status()
                
                # Write to cache file
                downloaded_size = 0
                with open(cache_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            
                            # Check size limit while downloading
                            if downloaded_size > self.max_file_size:
                                logger.warning(f"Download exceeded max size: {url}")
                                cache_path.unlink()  # Delete partial file
                                return None, {"error": "File too large"}
                
                metadata = {
                    "cached": False,
                    "mime_type": content_type,
                    "file_size": downloaded_size
                }
                
                logger.info(f"Successfully downloaded {url} to {cache_path}")
                return str(cache_path), metadata
                
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout downloading {url} (attempt {attempt + 1}/{max_retries})")
                if attempt == max_retries - 1:
                    return None, {"error": "Download timeout"}
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Error downloading {url}: {e}")
                if attempt == max_retries - 1:
                    return None, {"error": str(e)}
                    
            except Exception as e:
                logger.error(f"Unexpected error downloading {url}: {e}")
                return None, {"error": str(e)}
        
        return None, {"error": "Max retries exceeded"}

    def cleanup_cache(self, max_age_days: int = 7):
        """Remove old files from cache.
        
        Args:
            max_age_days: Maximum age of cached files in days
        """
        import time
        current_time = time.time()
        max_age_seconds = max_age_days * 24 * 60 * 60
        
        removed_count = 0
        for cache_file in self.cache_dir.iterdir():
            if cache_file.is_file():
                file_age = current_time - cache_file.stat().st_mtime
                if file_age > max_age_seconds:
                    cache_file.unlink()
                    removed_count += 1
        
        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} old cache files")

    def clear_cache(self):
        """Clear all cached files."""
        import shutil
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Cache cleared")
