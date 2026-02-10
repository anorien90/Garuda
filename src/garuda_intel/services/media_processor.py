"""Media Processing Service for Images, Video, and Audio.

This module provides functionality to extract text from media files
and convert them into embeddings for integration into the knowledge graph.
"""

from typing import Optional, Dict, Any
import logging
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .media_downloader import MediaDownloader
from .adaptive_media_processor import (
    AdaptiveMediaProcessor,
    MediaCharacteristics,
    MediaType,
    detect_media_characteristics
)

logger = logging.getLogger(__name__)

# Configuration for keyword extraction
DEFAULT_KEYWORD_COUNT = "5-10"
KEYWORD_EXTRACTION_PROMPT_TEMPLATE = (
    "Extract {count} descriptive keywords from this image description. "
    "Return ONLY a comma-separated list of keywords, nothing else.\n\n"
    "Description: {description}"
)


class MediaProcessor:
    """Process media items (images, video, audio) to extract text and embeddings."""

    def __init__(
        self, 
        llm_extractor=None, 
        enable_processing: bool = True, 
        cache_dir: Optional[str] = None,
        image_method: str = "tesseract",
        video_method: str = "speech",
        audio_method: str = "speech",
        use_adaptive_processing: bool = False,
    ):
        """Initialize media processor.
        
        Args:
            llm_extractor: LLM extractor for generating embeddings and Image2Text
            enable_processing: Whether media processing is enabled (optional feature)
            cache_dir: Directory for caching downloaded media files
            image_method: Method for image processing - "tesseract" (OCR) or "image2text" (AI model)
            video_method: Method for video processing - "speech" (audio transcription) or "video2text" (AI model)
            audio_method: Method for audio processing - "speech" (speech recognition)
            use_adaptive_processing: Whether to use adaptive method selection (Phase 2 feature)
        """
        self.llm = llm_extractor
        self.enabled = enable_processing
        self.downloader = MediaDownloader(cache_dir=cache_dir)
        self.image_method = image_method
        self.video_method = video_method
        self.audio_method = audio_method
        self.use_adaptive_processing = use_adaptive_processing
        
        # Initialize adaptive processor if enabled
        if use_adaptive_processing:
            self.adaptive_processor = AdaptiveMediaProcessor(
                prefer_speed=False,
                prefer_quality=True,
                gpu_available=False
            )
        else:
            self.adaptive_processor = None
        
        # Try to import optional dependencies
        self.ocr_available = False
        self.speech_available = False
        self.video_available = False
        self.image2text_available = False
        
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
        
        try:
            from moviepy.editor import VideoFileClip
            self.video_available = True
            logger.info("moviepy available for video processing")
        except ImportError:
            logger.info("moviepy not available - video processing disabled")
        
        # Check if LLM supports Image2Text
        if llm_extractor and hasattr(llm_extractor, 'image_to_text'):
            self.image2text_available = True
            logger.info("Image2Text (LLM) available for image processing")

    def process_image(self, image_path: str, url: str, method: Optional[str] = None, width: Optional[int] = None, height: Optional[int] = None) -> Dict[str, Any]:
        """Extract text from image using OCR or Image2Text model.
        
        Args:
            image_path: Local path to image file
            url: Original URL of the image
            method: Processing method - "tesseract", "image2text", "comprehensive", or None (use default/adaptive)
            width: Image width in pixels (for adaptive processing)
            height: Image height in pixels (for adaptive processing)
            
        Returns:
            Dict with extracted_text, metadata, and processing status
        """
        if not self.enabled:
            return {
                "extracted_text": None,
                "processed": False,
                "processing_error": "Image processing disabled"
            }
        
        # Use adaptive processing if enabled and no specific method requested
        if self.use_adaptive_processing and self.adaptive_processor and method is None:
            characteristics = detect_media_characteristics(
                media_url=url,
                media_type="image",
                width=width,
                height=height
            )
            decision = self.adaptive_processor.select_processing_method(characteristics)
            method = self.adaptive_processor.get_method_for_config(decision)
            logger.info(f"Adaptive processing selected: {method} - {decision.reasoning}")
        else:
            # Use specified method or default
            method = method or self.image_method
        
        # Check if comprehensive processing should be used
        # Comprehensive mode is used when both OCR and AI are available and
        # no specific single method was explicitly requested
        can_use_comprehensive = self.ocr_available and self.image2text_available
        if method == "comprehensive" or (can_use_comprehensive and method in (None, self.image_method)):
            return self._process_image_comprehensive(image_path, url)
        elif method == "image2text" and self.image2text_available:
            return self._process_image_with_ai(image_path, url)
        elif method == "tesseract" and self.ocr_available:
            return self._process_image_with_tesseract(image_path, url)
        else:
            # Fallback: try comprehensive first, then individual methods
            if can_use_comprehensive:
                return self._process_image_comprehensive(image_path, url)
            elif self.ocr_available:
                return self._process_image_with_tesseract(image_path, url)
            elif self.image2text_available:
                return self._process_image_with_ai(image_path, url)
            else:
                return {
                    "extracted_text": None,
                    "processed": False,
                    "processing_error": f"No image processing method available (requested: {method})"
                }
    
    def _process_image_with_tesseract(self, image_path: str, url: str) -> Dict[str, Any]:
        """Extract text from image using Tesseract OCR.
        
        Args:
            image_path: Local path to image file
            url: Original URL of the image
            
        Returns:
            Dict with extracted_text, metadata, and processing status
        """
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
                "method": "tesseract",
            }
            
            # Perform OCR
            text = pytesseract.image_to_string(img)
            
            return {
                "extracted_text": text.strip() if text else None,
                "width": width,
                "height": height,
                "metadata_json": metadata,
                "processed": True,
                "processed_at": datetime.now(timezone.utc),
            }
            
        except Exception as e:
            logger.error(f"Error processing image with Tesseract {url}: {e}")
            return {
                "extracted_text": None,
                "processed": False,
                "processing_error": str(e),
            }
    
    def _process_image_with_ai(self, image_path: str, url: str) -> Dict[str, Any]:
        """Extract text from image using AI Image2Text model.
        
        Args:
            image_path: Local path to image file
            url: Original URL of the image
            
        Returns:
            Dict with extracted_text, metadata, and processing status
        """
        try:
            from PIL import Image
            
            img = Image.open(image_path)
            
            # Extract metadata
            width, height = img.size
            metadata = {
                "format": img.format,
                "mode": img.mode,
                "width": width,
                "height": height,
                "method": "image2text",
            }
            
            # Use LLM's Image2Text capability
            text = None
            if self.llm and hasattr(self.llm, 'image_to_text'):
                text = self.llm.image_to_text(image_path)
            
            return {
                "extracted_text": text.strip() if text else None,
                "width": width,
                "height": height,
                "metadata_json": metadata,
                "processed": True,
                "processed_at": datetime.now(timezone.utc),
            }
            
        except Exception as e:
            logger.error(f"Error processing image with AI {url}: {e}")
            return {
                "extracted_text": None,
                "processed": False,
                "processing_error": str(e),
            }

    def _process_image_comprehensive(self, image_path: str, url: str) -> Dict[str, Any]:
        """Extract text, description, and keywords from image using all available methods.
        
        Combines OCR text extraction with AI-based description and keyword generation
        for maximum content extraction from images.
        
        Args:
            image_path: Local path to image file
            url: Original URL of the image
            
        Returns:
            Dict with extracted_text, description, keywords, metadata, and processing status
        """
        try:
            from PIL import Image
            
            img = Image.open(image_path)
            width, height = img.size
            metadata = {
                "format": img.format,
                "mode": img.mode,
                "width": width,
                "height": height,
                "method": "comprehensive",
            }
            
            text_parts = []
            description = None
            keywords = []
            
            # Step 1: OCR text extraction
            if self.ocr_available:
                try:
                    import pytesseract
                    ocr_text = pytesseract.image_to_string(img)
                    if ocr_text and ocr_text.strip():
                        text_parts.append(f"OCR Text:\n{ocr_text.strip()}")
                        metadata["ocr_text"] = ocr_text.strip()
                except Exception as e:
                    logger.warning(f"OCR failed for {url}: {e}")
            
            # Step 2: AI description
            if self.image2text_available and self.llm:
                try:
                    if hasattr(self.llm, 'image_to_text'):
                        ai_text = self.llm.image_to_text(image_path)
                        if ai_text and ai_text.strip():
                            description = ai_text.strip()
                            text_parts.append(f"Description:\n{description}")
                            metadata["description"] = description
                except Exception as e:
                    logger.warning(f"Image2Text failed for {url}: {e}")
            
            # Step 3: Keyword extraction via LLM
            if self.llm and description:
                try:
                    if hasattr(self.llm, 'extract_keywords_from_image'):
                        kw = self.llm.extract_keywords_from_image(image_path, description)
                        if kw and isinstance(kw, list):
                            keywords = kw
                    elif hasattr(self.llm, 'generate') or hasattr(self.llm, 'chat'):
                        # Fallback: Use public LLM interface to extract keywords from the description
                        kw_prompt = KEYWORD_EXTRACTION_PROMPT_TEMPLATE.format(
                            count=DEFAULT_KEYWORD_COUNT,
                            description=description
                        )
                        kw_response = None
                        if hasattr(self.llm, 'generate'):
                            kw_response = self.llm.generate(kw_prompt)
                        elif hasattr(self.llm, 'chat'):
                            kw_response = self.llm.chat(kw_prompt)
                        
                        if kw_response and isinstance(kw_response, str):
                            keywords = [k.strip() for k in kw_response.split(",") if k.strip()]
                        elif kw_response:
                            logger.warning(f"Unexpected keyword response type for {url}: {type(kw_response)}")
                    else:
                        logger.warning(f"LLM does not support keyword extraction methods for {url}")
                    
                    if keywords:
                        text_parts.append(f"Keywords: {', '.join(keywords)}")
                        metadata["keywords"] = keywords
                except Exception as e:
                    logger.warning(f"Keyword extraction failed for {url}: {e}")
            
            combined_text = "\n\n".join(text_parts) if text_parts else None
            
            return {
                "extracted_text": combined_text,
                "description": description,
                "keywords": keywords,
                "width": width,
                "height": height,
                "metadata_json": metadata,
                "processed": True,
                "processed_at": datetime.now(timezone.utc),
            }
            
        except Exception as e:
            logger.error(f"Error in comprehensive image processing {url}: {e}")
            return {
                "extracted_text": None,
                "processed": False,
                "processing_error": str(e),
            }

    def extract_audio_from_video(self, video_path: str, output_path: Optional[str] = None) -> Optional[str]:
        """Extract audio track from video file.
        
        Args:
            video_path: Local path to video file
            output_path: Optional path for output audio file (WAV format)
            
        Returns:
            Path to extracted audio file, or None on failure
        """
        if not self.video_available:
            logger.error("Video processing not available - cannot extract audio")
            return None
        
        try:
            from moviepy.editor import VideoFileClip
            
            video = VideoFileClip(video_path)
            
            try:
                audio = video.audio
                
                if audio is None:
                    logger.warning(f"No audio track found in video: {video_path}")
                    return None
                
                # Create output path if not specified
                if not output_path:
                    # Use mkstemp for secure temp file creation
                    fd, output_path = tempfile.mkstemp(suffix='.wav')
                    os.close(fd)  # Close the file descriptor, we just need the path
                
                # Extract audio
                audio.write_audiofile(output_path, verbose=False, logger=None)
                
                logger.info(f"Extracted audio from {video_path} to {output_path}")
                return output_path
            finally:
                # Always close video resource
                video.close()
                
        except Exception as e:
            logger.error(f"Failed to extract audio from video {video_path}: {e}")
            return None

    def process_video(self, video_path: str, url: str, method: Optional[str] = None, extract_audio_only: bool = False) -> Dict[str, Any]:
        """Extract text from video (audio track or using Video2Text).
        
        Args:
            video_path: Local path to video file
            url: Original URL of the video
            method: Processing method - "speech" (audio transcription) or "video2text" (AI model)
            extract_audio_only: If True, only extract audio without transcription
            
        Returns:
            Dict with extracted_text, metadata, and processing status
        """
        if not self.enabled:
            return {
                "extracted_text": None,
                "processed": False,
                "processing_error": "Video processing disabled"
            }
        
        if not self.video_available:
            return {
                "extracted_text": None,
                "processed": False,
                "processing_error": "Video processing dependencies not available (moviepy)"
            }
        
        try:
            from moviepy.editor import VideoFileClip
            
            # Extract video metadata
            video = VideoFileClip(video_path)
            
            try:
                duration = video.duration
                width, height = video.size
                fps = video.fps
                
                metadata = {
                    "duration": duration,
                    "width": width,
                    "height": height,
                    "fps": fps,
                }
                
                # If extract_audio_only is True, just extract audio and return
                if extract_audio_only:
                    temp_audio_path = self.extract_audio_from_video(video_path)
                    
                    if temp_audio_path:
                        return {
                            "extracted_text": None,
                            "audio_path": temp_audio_path,
                            "processed": True,
                            "processing_note": "Audio extracted successfully",
                            "metadata_json": metadata,
                            "duration": duration,
                            "width": width,
                            "height": height,
                        }
                    else:
                        return {
                            "extracted_text": None,
                            "processed": False,
                            "processing_error": "Failed to extract audio",
                            "metadata_json": metadata,
                            "duration": duration,
                            "width": width,
                            "height": height,
                        }
                
                # Use specified method or default
                method = method or self.video_method
                
                # Process based on method
                if method == "video2text" and self.llm and hasattr(self.llm, 'video_to_text'):
                    result = self._process_video_with_ai(video_path, url, metadata, duration, width, height)
                elif method == "speech" and self.speech_available:
                    result = self._process_video_with_speech(video_path, url, metadata, duration, width, height)
                else:
                    # Fallback to speech recognition if available
                    if self.speech_available:
                        result = self._process_video_with_speech(video_path, url, metadata, duration, width, height)
                    else:
                        result = {
                            "extracted_text": None,
                            "processed": False,
                            "processing_error": f"No video processing method available (requested: {method})",
                            "metadata_json": metadata,
                            "duration": duration,
                            "width": width,
                            "height": height,
                        }
                
                return result
                
            finally:
                # Always close video resource
                video.close()
                    
        except Exception as e:
            logger.error(f"Error processing video {url}: {e}")
            return {
                "extracted_text": None,
                "processed": False,
                "processing_error": str(e),
            }
    
    def _process_video_with_speech(self, video_path: str, url: str, metadata: Dict, duration: float, width: int, height: int) -> Dict[str, Any]:
        """Process video by extracting and transcribing audio track.
        
        Args:
            video_path: Local path to video file
            url: Original URL of the video
            metadata: Video metadata dict
            duration: Video duration in seconds
            width: Video width
            height: Video height
            
        Returns:
            Dict with processing results
        """
        import speech_recognition as sr
        
        metadata["method"] = "speech"
        
        # Extract audio from video
        temp_audio_path = self.extract_audio_from_video(video_path)
        
        if not temp_audio_path:
            return {
                "extracted_text": None,
                "processed": True,
                "processing_error": "No audio track found in video",
                "metadata_json": metadata,
                "duration": duration,
                "width": width,
                "height": height,
            }
        
        try:
            # Use speech recognition on the audio
            recognizer = sr.Recognizer()
            with sr.AudioFile(temp_audio_path) as source:
                audio_data = recognizer.record(source)
            
            # Perform speech recognition
            try:
                text = recognizer.recognize_google(audio_data)
                return {
                    "extracted_text": text,
                    "processed": True,
                    "processed_at": datetime.now(timezone.utc),
                    "metadata_json": metadata,
                    "duration": duration,
                    "width": width,
                    "height": height,
                }
            except sr.UnknownValueError:
                return {
                    "extracted_text": None,
                    "processed": True,
                    "processing_error": "Could not understand audio",
                    "metadata_json": metadata,
                    "duration": duration,
                    "width": width,
                    "height": height,
                }
            except sr.RequestError as e:
                return {
                    "extracted_text": None,
                    "processed": False,
                    "processing_error": f"Speech recognition API error: {e}",
                    "metadata_json": metadata,
                    "duration": duration,
                    "width": width,
                    "height": height,
                }
        finally:
            # Clean up temporary audio file
            if temp_audio_path and os.path.exists(temp_audio_path):
                os.unlink(temp_audio_path)
    
    def _process_video_with_ai(self, video_path: str, url: str, metadata: Dict, duration: float, width: int, height: int) -> Dict[str, Any]:
        """Process video using AI Video2Text model.
        
        Args:
            video_path: Local path to video file
            url: Original URL of the video
            metadata: Video metadata dict
            duration: Video duration in seconds
            width: Video width
            height: Video height
            
        Returns:
            Dict with processing results
        """
        metadata["method"] = "video2text"
        
        try:
            # Use LLM's Video2Text capability
            text = None
            if self.llm and hasattr(self.llm, 'video_to_text'):
                text = self.llm.video_to_text(video_path)
            
            return {
                "extracted_text": text,
                "processed": True,
                "processed_at": datetime.now(timezone.utc),
                "metadata_json": metadata,
                "duration": duration,
                "width": width,
                "height": height,
            }
        except Exception as e:
            logger.error(f"Error processing video with AI {url}: {e}")
            return {
                "extracted_text": None,
                "processed": False,
                "processing_error": str(e),
                "metadata_json": metadata,
                "duration": duration,
                "width": width,
                "height": height,
            }

    def process_audio(self, audio_path: str, url: str, method: Optional[str] = None) -> Dict[str, Any]:
        """Extract text from audio using speech recognition.
        
        Note: Only supports WAV audio files. Other formats need conversion first.
        Uses Google's speech recognition API which has rate limits.
        
        Args:
            audio_path: Local path to audio file (WAV format)
            url: Original URL of the audio
            method: Processing method - "speech" (speech recognition)
            
        Returns:
            Dict with extracted_text, metadata, and processing status
        """
        if not self.enabled:
            return {
                "extracted_text": None,
                "processed": False,
                "processing_error": "Audio processing disabled"
            }
        
        # Use specified method or default
        method = method or self.audio_method
        
        if method == "speech" and self.speech_available:
            return self._process_audio_with_speech(audio_path, url)
        else:
            return {
                "extracted_text": None,
                "processed": False,
                "processing_error": f"Speech recognition not available (requested: {method})"
            }
    
    def _process_audio_with_speech(self, audio_path: str, url: str) -> Dict[str, Any]:
        """Extract text from audio using speech recognition.
        
        Args:
            audio_path: Local path to audio file (WAV format)
            url: Original URL of the audio
            
        Returns:
            Dict with extracted_text, metadata, and processing status
        """
        try:
            import speech_recognition as sr
            
            recognizer = sr.Recognizer()
            
            metadata = {
                "method": "speech",
            }
            
            # Load audio file
            with sr.AudioFile(audio_path) as source:
                audio_data = recognizer.record(source)
                
            # Perform speech recognition
            try:
                text = recognizer.recognize_google(audio_data)
                return {
                    "extracted_text": text,
                    "processed": True,
                    "processed_at": datetime.now(timezone.utc),
                    "metadata_json": metadata,
                }
            except sr.UnknownValueError:
                return {
                    "extracted_text": None,
                    "processed": True,
                    "processing_error": "Could not understand audio",
                    "metadata_json": metadata,
                }
            except sr.RequestError as e:
                return {
                    "extracted_text": None,
                    "processed": False,
                    "processing_error": f"API error: {e}",
                    "metadata_json": metadata,
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

    def process_from_url(self, url: str, media_type: str) -> Dict[str, Any]:
        """Download and process media from URL.
        
        Args:
            url: URL of media file
            media_type: Type of media (image, video, audio)
            
        Returns:
            Dict with processing results including download metadata
        """
        if not self.enabled:
            return {
                "extracted_text": None,
                "processed": False,
                "processing_error": "Media processing disabled"
            }
        
        # Download the file
        logger.info(f"Downloading {media_type} from {url}")
        file_path, download_metadata = self.downloader.download(url)
        
        if not file_path:
            error_msg = download_metadata.get("error", "Download failed") if download_metadata else "Download failed"
            return {
                "extracted_text": None,
                "processed": False,
                "processing_error": f"Download failed: {error_msg}"
            }
        
        # Process the downloaded file
        try:
            result = self.process_media_item(media_type, file_path, url)
            
            # Add download metadata to result
            if download_metadata:
                result["file_size"] = download_metadata.get("file_size")
                result["mime_type"] = download_metadata.get("mime_type")
            
            return result
        except Exception as e:
            logger.error(f"Error processing media from {url}: {e}")
            return {
                "extracted_text": None,
                "processed": False,
                "processing_error": str(e)
            }
