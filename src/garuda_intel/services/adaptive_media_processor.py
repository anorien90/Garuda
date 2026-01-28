"""
Adaptive media processing with intelligent method selection.

Automatically selects the best processing method for each media item
based on content characteristics, performance requirements, and available resources.
"""

import logging
from typing import Optional, Dict, Any
from enum import Enum
from dataclasses import dataclass


class MediaType(str, Enum):
    """Types of media content."""
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    PDF = "pdf"


class ProcessingMethod(str, Enum):
    """Available processing methods for media."""
    TESSERACT_OCR = "tesseract"
    AI_IMAGE2TEXT = "image2text"
    AUDIO_TRANSCRIPTION = "speech"
    AI_VIDEO2TEXT = "video2text"
    PDF_EXTRACT = "pdf_extract"


@dataclass
class MediaCharacteristics:
    """Characteristics of a media item that influence processing method selection."""
    media_type: MediaType
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None  # seconds
    file_size: Optional[int] = None  # bytes
    has_audio: Optional[bool] = None
    has_clear_speech: Optional[bool] = None
    is_printed_text: Optional[bool] = None
    is_handwritten: Optional[bool] = None
    language: Optional[str] = None
    url: Optional[str] = None


@dataclass
class ProcessingDecision:
    """Decision about how to process a media item."""
    method: ProcessingMethod
    confidence: float  # 0.0 to 1.0
    reasoning: str
    estimated_cost: str  # "low", "medium", "high"
    estimated_time: str  # "fast", "medium", "slow"


class AdaptiveMediaProcessor:
    """
    Selects optimal processing method for media based on characteristics.
    
    Balances quality, cost, and speed based on media properties and
    available processing resources.
    """
    
    def __init__(
        self,
        prefer_speed: bool = False,
        prefer_quality: bool = True,
        gpu_available: bool = False
    ):
        """
        Initialize adaptive media processor.
        
        Args:
            prefer_speed: Prioritize speed over quality
            prefer_quality: Prioritize quality over speed (default)
            gpu_available: Whether GPU is available for AI models
        """
        self.prefer_speed = prefer_speed
        self.prefer_quality = prefer_quality
        self.gpu_available = gpu_available
        self.logger = logging.getLogger(__name__)
    
    def select_processing_method(
        self,
        characteristics: MediaCharacteristics
    ) -> ProcessingDecision:
        """
        Select the best processing method for a media item.
        
        Args:
            characteristics: Media characteristics
            
        Returns:
            Processing decision with method and reasoning
        """
        media_type = characteristics.media_type
        
        if media_type == MediaType.IMAGE:
            return self._select_image_method(characteristics)
        elif media_type == MediaType.VIDEO:
            return self._select_video_method(characteristics)
        elif media_type == MediaType.AUDIO:
            return self._select_audio_method(characteristics)
        elif media_type == MediaType.PDF:
            return self._select_pdf_method(characteristics)
        else:
            raise ValueError(f"Unsupported media type: {media_type}")
    
    def _select_image_method(
        self,
        characteristics: MediaCharacteristics
    ) -> ProcessingDecision:
        """
        Select processing method for images.
        
        Strategy:
        - Printed text: Use Tesseract (fast, accurate)
        - Handwritten text: Use AI model (better quality)
        - Complex images: Use AI model (better understanding)
        - Small/low quality: Use AI model (more robust)
        """
        # Check if we know it's handwritten
        if characteristics.is_handwritten:
            return ProcessingDecision(
                method=ProcessingMethod.AI_IMAGE2TEXT,
                confidence=0.9,
                reasoning="Handwritten text detected - AI model handles this better than OCR",
                estimated_cost="medium",
                estimated_time="medium"
            )
        
        # Check if we know it's printed text
        if characteristics.is_printed_text:
            return ProcessingDecision(
                method=ProcessingMethod.TESSERACT_OCR,
                confidence=0.95,
                reasoning="Printed text detected - Tesseract is fast and accurate",
                estimated_cost="low",
                estimated_time="fast"
            )
        
        # Check image size - small images better with AI
        if characteristics.width and characteristics.height:
            pixels = characteristics.width * characteristics.height
            if pixels < 200_000:  # Less than ~450x450
                return ProcessingDecision(
                    method=ProcessingMethod.AI_IMAGE2TEXT,
                    confidence=0.7,
                    reasoning="Small image - AI model more robust for low resolution",
                    estimated_cost="medium",
                    estimated_time="medium"
                )
        
        # Check URL for hints about content type
        if characteristics.url:
            url_lower = characteristics.url.lower()
            
            # Screenshots likely have printed text
            if any(keyword in url_lower for keyword in ['screenshot', 'screen', 'capture']):
                return ProcessingDecision(
                    method=ProcessingMethod.TESSERACT_OCR,
                    confidence=0.8,
                    reasoning="Screenshot detected - likely contains printed text",
                    estimated_cost="low",
                    estimated_time="fast"
                )
            
            # Diagrams, charts, infographics better with AI
            if any(keyword in url_lower for keyword in ['diagram', 'chart', 'infographic', 'graph']):
                return ProcessingDecision(
                    method=ProcessingMethod.AI_IMAGE2TEXT,
                    confidence=0.8,
                    reasoning="Diagram/chart detected - AI model better for complex visuals",
                    estimated_cost="medium",
                    estimated_time="medium"
                )
        
        # Default: Use speed/quality preference
        if self.prefer_speed:
            return ProcessingDecision(
                method=ProcessingMethod.TESSERACT_OCR,
                confidence=0.6,
                reasoning="Speed preferred - using fast OCR",
                estimated_cost="low",
                estimated_time="fast"
            )
        else:
            return ProcessingDecision(
                method=ProcessingMethod.AI_IMAGE2TEXT,
                confidence=0.6,
                reasoning="Quality preferred - using AI model for better understanding",
                estimated_cost="medium",
                estimated_time="medium"
            )
    
    def _select_video_method(
        self,
        characteristics: MediaCharacteristics
    ) -> ProcessingDecision:
        """
        Select processing method for videos.
        
        Strategy:
        - Has clear speech: Extract audio and transcribe (cheaper)
        - Visual-only or poor audio: Use video2text (complete but expensive)
        - Short videos: OK to use video2text
        - Long videos: Prefer audio transcription
        """
        # Check if we know about audio quality
        if characteristics.has_clear_speech:
            return ProcessingDecision(
                method=ProcessingMethod.AUDIO_TRANSCRIPTION,
                confidence=0.9,
                reasoning="Clear speech detected - audio transcription is cheaper and effective",
                estimated_cost="low",
                estimated_time="medium"
            )
        
        # Check if video has no audio
        if characteristics.has_audio is False:
            return ProcessingDecision(
                method=ProcessingMethod.AI_VIDEO2TEXT,
                confidence=0.95,
                reasoning="No audio track - must use visual processing",
                estimated_cost="high",
                estimated_time="slow"
            )
        
        # Check video duration
        if characteristics.duration:
            # Short videos (< 2 min) - OK to use full video processing
            if characteristics.duration < 120:
                return ProcessingDecision(
                    method=ProcessingMethod.AI_VIDEO2TEXT,
                    confidence=0.7,
                    reasoning="Short video - full video processing is acceptable",
                    estimated_cost="medium",
                    estimated_time="medium"
                )
            
            # Long videos (> 10 min) - prefer audio transcription
            elif characteristics.duration > 600:
                return ProcessingDecision(
                    method=ProcessingMethod.AUDIO_TRANSCRIPTION,
                    confidence=0.75,
                    reasoning="Long video - audio transcription more cost-effective",
                    estimated_cost="low",
                    estimated_time="medium"
                )
        
        # Default based on preference
        if self.prefer_speed or not self.prefer_quality:
            return ProcessingDecision(
                method=ProcessingMethod.AUDIO_TRANSCRIPTION,
                confidence=0.6,
                reasoning="Speed/cost preferred - using audio transcription",
                estimated_cost="low",
                estimated_time="medium"
            )
        else:
            return ProcessingDecision(
                method=ProcessingMethod.AI_VIDEO2TEXT,
                confidence=0.6,
                reasoning="Quality preferred - using full video processing",
                estimated_cost="high",
                estimated_time="slow"
            )
    
    def _select_audio_method(
        self,
        characteristics: MediaCharacteristics
    ) -> ProcessingDecision:
        """
        Select processing method for audio.
        
        For audio, we primarily use speech recognition.
        """
        return ProcessingDecision(
            method=ProcessingMethod.AUDIO_TRANSCRIPTION,
            confidence=1.0,
            reasoning="Audio content - using speech recognition",
            estimated_cost="low",
            estimated_time="fast"
        )
    
    def _select_pdf_method(
        self,
        characteristics: MediaCharacteristics
    ) -> ProcessingDecision:
        """
        Select processing method for PDFs.
        
        PDFs typically use text extraction, possibly with OCR for scanned documents.
        """
        return ProcessingDecision(
            method=ProcessingMethod.PDF_EXTRACT,
            confidence=1.0,
            reasoning="PDF document - using text extraction",
            estimated_cost="low",
            estimated_time="fast"
        )
    
    def get_method_for_config(self, decision: ProcessingDecision) -> str:
        """
        Convert processing decision to config-compatible method string.
        
        Args:
            decision: Processing decision
            
        Returns:
            Method string for configuration
        """
        method_map = {
            ProcessingMethod.TESSERACT_OCR: "tesseract",
            ProcessingMethod.AI_IMAGE2TEXT: "image2text",
            ProcessingMethod.AUDIO_TRANSCRIPTION: "speech",
            ProcessingMethod.AI_VIDEO2TEXT: "video2text",
            ProcessingMethod.PDF_EXTRACT: "pdf_extract"
        }
        return method_map.get(decision.method, "tesseract")
    
    def estimate_processing_resources(
        self,
        decision: ProcessingDecision
    ) -> Dict[str, Any]:
        """
        Estimate resource requirements for processing decision.
        
        Args:
            decision: Processing decision
            
        Returns:
            Dictionary with resource estimates
        """
        # Map decision attributes to numeric estimates
        cost_map = {"low": 1, "medium": 5, "high": 20}
        time_map = {"fast": 1, "medium": 5, "slow": 15}
        
        return {
            "method": decision.method.value,
            "estimated_cost_units": cost_map.get(decision.estimated_cost, 5),
            "estimated_time_seconds": time_map.get(decision.estimated_time, 5),
            "confidence": decision.confidence,
            "reasoning": decision.reasoning
        }


def detect_media_characteristics(
    media_url: str,
    media_type: str,
    width: Optional[int] = None,
    height: Optional[int] = None,
    **kwargs
) -> MediaCharacteristics:
    """
    Helper function to create MediaCharacteristics from common inputs.
    
    Args:
        media_url: URL of the media
        media_type: Type of media ("image", "video", "audio", "pdf")
        width: Image/video width in pixels
        height: Image/video height in pixels
        **kwargs: Additional characteristics
        
    Returns:
        MediaCharacteristics object
    """
    try:
        media_type_enum = MediaType(media_type.lower())
    except ValueError:
        media_type_enum = MediaType.IMAGE
    
    return MediaCharacteristics(
        media_type=media_type_enum,
        width=width,
        height=height,
        url=media_url,
        duration=kwargs.get('duration'),
        file_size=kwargs.get('file_size'),
        has_audio=kwargs.get('has_audio'),
        has_clear_speech=kwargs.get('has_clear_speech'),
        is_printed_text=kwargs.get('is_printed_text'),
        is_handwritten=kwargs.get('is_handwritten'),
        language=kwargs.get('language')
    )
