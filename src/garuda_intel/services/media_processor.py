"""Media Processing Service for Images, Video, and Audio.

This module provides functionality to extract text from media files
and convert them into embeddings for integration into the knowledge graph.
"""

from typing import Optional, Dict, Any
import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)


class MediaProcessor:
    """Process media items (images, video, audio) to extract text and embeddings."""

    def __init__(self, llm_extractor=None, enable_processing: bool = True):
        """Initialize media processor.
        
        Args:
            llm_extractor: LLM extractor for generating embeddings
            enable_processing: Whether media processing is enabled (optional feature)
        """
        self.llm = llm_extractor
        self.enabled = enable_processing
        
        # Try to import optional dependencies
        self.ocr_available = False
        self.speech_available = False
        
        try:
            import pytesseract
            from PIL import Image
            self.ocr_available = True
            logger.info("OCR (pytesseract) available for image processing")
        except ImportError:
            logger.info("pytesseract not available - image OCR disabled")
        
        try:
            import speech_recognition as sr
            self.speech_available = True
            logger.info("speech_recognition available for audio/video processing")
        except ImportError:
            logger.info("speech_recognition not available - audio processing disabled")

    def process_image(self, image_path: str, url: str) -> Dict[str, Any]:
        """Extract text from image using OCR.
        
        Args:
            image_path: Local path to image file
            url: Original URL of the image
            
        Returns:
            Dict with extracted_text, metadata, and processing status
        """
        if not self.enabled or not self.ocr_available:
            return {
                "extracted_text": None,
                "processed": False,
                "processing_error": "OCR not available or disabled"
            }
        
        try:
            import pytesseract
            from PIL import Image
            
            img = Image.open(image_path)
            
            # Extract metadata
            width, height = img.size
            metadata = {
                "format": img.format,
                "mode": img.mode,
                "width": width,
                "height": height,
            }
            
            # Perform OCR
            text = pytesseract.image_to_string(img)
            
            return {
                "extracted_text": text.strip() if text else None,
                "width": width,
                "height": height,
                "metadata_json": metadata,
                "processed": True,
                "processed_at": datetime.utcnow(),
            }
            
        except Exception as e:
            logger.error(f"Error processing image {url}: {e}")
            return {
                "extracted_text": None,
                "processed": False,
                "processing_error": str(e),
            }

    def process_video(self, video_path: str, url: str) -> Dict[str, Any]:
        """Extract text from video (audio track or captions).
        
        Args:
            video_path: Local path to video file
            url: Original URL of the video
            
        Returns:
            Dict with extracted_text, metadata, and processing status
        """
        if not self.enabled:
            return {
                "extracted_text": None,
                "processed": False,
                "processing_error": "Video processing disabled"
            }
        
        try:
            # For now, return a placeholder
            # Full implementation would use moviepy + speech_recognition
            logger.info(f"Video processing for {url} - placeholder implementation")
            
            return {
                "extracted_text": None,
                "processed": False,
                "processing_error": "Video processing not yet implemented",
                "metadata_json": {"note": "Requires moviepy and audio extraction"}
            }
            
        except Exception as e:
            logger.error(f"Error processing video {url}: {e}")
            return {
                "extracted_text": None,
                "processed": False,
                "processing_error": str(e),
            }

    def process_audio(self, audio_path: str, url: str) -> Dict[str, Any]:
        """Extract text from audio using speech recognition.
        
        Note: Only supports WAV audio files. Other formats need conversion first.
        Uses Google's speech recognition API which has rate limits.
        
        Args:
            audio_path: Local path to audio file (WAV format)
            url: Original URL of the audio
            
        Returns:
            Dict with extracted_text, metadata, and processing status
        """
        if not self.enabled or not self.speech_available:
            return {
                "extracted_text": None,
                "processed": False,
                "processing_error": "Speech recognition not available or disabled"
            }
        
        try:
            import speech_recognition as sr
            
            recognizer = sr.Recognizer()
            
            # Load audio file
            with sr.AudioFile(audio_path) as source:
                audio_data = recognizer.record(source)
                
            # Perform speech recognition
            try:
                text = recognizer.recognize_google(audio_data)
                return {
                    "extracted_text": text,
                    "processed": True,
                    "processed_at": datetime.utcnow(),
                }
            except sr.UnknownValueError:
                return {
                    "extracted_text": None,
                    "processed": True,
                    "processing_error": "Could not understand audio",
                }
            except sr.RequestError as e:
                return {
                    "extracted_text": None,
                    "processed": False,
                    "processing_error": f"API error: {e}",
                }
                
        except Exception as e:
            logger.error(f"Error processing audio {url}: {e}")
            return {
                "extracted_text": None,
                "processed": False,
                "processing_error": str(e),
            }

    def generate_embedding(self, text: str) -> Optional[str]:
        """Generate embedding for extracted text.
        
        Args:
            text: Extracted text from media
            
        Returns:
            JSON-encoded embedding vector or None
        """
        if not self.llm or not text or not text.strip():
            return None
        
        try:
            # Check if LLM has embedding functionality
            if not hasattr(self.llm, 'embed_text'):
                logger.warning("LLM does not support embedding generation")
                return None
                
            # Use the LLM's embedding functionality
            embedding = self.llm.embed_text(text)
            if embedding:
                return json.dumps(embedding)
            return None
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None

    def process_media_item(self, media_type: str, file_path: str, url: str) -> Dict[str, Any]:
        """Process a media item based on its type.
        
        Args:
            media_type: Type of media (image, video, audio)
            file_path: Local path to the media file
            url: Original URL of the media
            
        Returns:
            Dict with processing results
        """
        if media_type == "image":
            result = self.process_image(file_path, url)
        elif media_type == "video":
            result = self.process_video(file_path, url)
        elif media_type == "audio":
            result = self.process_audio(file_path, url)
        else:
            return {
                "extracted_text": None,
                "processed": False,
                "processing_error": f"Unknown media type: {media_type}"
            }
        
        # Generate embedding if text was extracted
        if result.get("extracted_text"):
            result["text_embedding"] = self.generate_embedding(result["extracted_text"])
        
        return result
