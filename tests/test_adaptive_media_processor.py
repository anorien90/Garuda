"""
Unit tests for adaptive media processing.

Tests the AdaptiveMediaProcessor class and processing method selection.
"""

import pytest

from garuda_intel.services.adaptive_media_processor import (
    AdaptiveMediaProcessor,
    MediaCharacteristics,
    MediaType,
    ProcessingMethod,
    ProcessingDecision,
    detect_media_characteristics
)


class TestMediaCharacteristics:
    """Test MediaCharacteristics dataclass."""
    
    def test_characteristics_creation(self):
        """Test creating media characteristics."""
        chars = MediaCharacteristics(
            media_type=MediaType.IMAGE,
            width=1920,
            height=1080,
            url="https://example.com/image.jpg"
        )
        
        assert chars.media_type == MediaType.IMAGE
        assert chars.width == 1920
        assert chars.height == 1080
        assert chars.url == "https://example.com/image.jpg"


class TestDetectMediaCharacteristics:
    """Test helper function for creating characteristics."""
    
    def test_detect_from_basic_info(self):
        """Test detecting characteristics from basic info."""
        chars = detect_media_characteristics(
            media_url="https://example.com/photo.jpg",
            media_type="image",
            width=800,
            height=600
        )
        
        assert chars.media_type == MediaType.IMAGE
        assert chars.width == 800
        assert chars.height == 600
        assert chars.url == "https://example.com/photo.jpg"
    
    def test_detect_with_additional_kwargs(self):
        """Test detection with additional properties."""
        chars = detect_media_characteristics(
            media_url="https://example.com/video.mp4",
            media_type="video",
            duration=120.5,
            has_audio=True,
            has_clear_speech=True
        )
        
        assert chars.media_type == MediaType.VIDEO
        assert chars.duration == 120.5
        assert chars.has_audio is True
        assert chars.has_clear_speech is True


class TestAdaptiveMediaProcessor:
    """Test AdaptiveMediaProcessor class."""
    
    @pytest.fixture
    def processor(self):
        """Create a processor instance."""
        return AdaptiveMediaProcessor(
            prefer_speed=False,
            prefer_quality=True,
            gpu_available=False
        )
    
    @pytest.fixture
    def speed_processor(self):
        """Create a speed-preferring processor."""
        return AdaptiveMediaProcessor(
            prefer_speed=True,
            prefer_quality=False
        )
    
    def test_initialization(self, processor):
        """Test processor initialization."""
        assert processor.prefer_quality is True
        assert processor.prefer_speed is False
        assert processor.gpu_available is False
    
    def test_select_method_for_printed_text(self, processor):
        """Test selection for printed text image."""
        chars = MediaCharacteristics(
            media_type=MediaType.IMAGE,
            is_printed_text=True,
            url="https://example.com/screenshot.png"
        )
        
        decision = processor.select_processing_method(chars)
        
        assert decision.method == ProcessingMethod.TESSERACT_OCR
        assert decision.confidence >= 0.9
        assert "printed" in decision.reasoning.lower()
    
    def test_select_method_for_handwritten_text(self, processor):
        """Test selection for handwritten text."""
        chars = MediaCharacteristics(
            media_type=MediaType.IMAGE,
            is_handwritten=True
        )
        
        decision = processor.select_processing_method(chars)
        
        assert decision.method == ProcessingMethod.AI_IMAGE2TEXT
        assert decision.confidence >= 0.9
        assert "handwritten" in decision.reasoning.lower()
    
    def test_select_method_for_small_image(self, processor):
        """Test selection for small image."""
        chars = MediaCharacteristics(
            media_type=MediaType.IMAGE,
            width=300,
            height=300  # 90k pixels, < 200k threshold
        )
        
        decision = processor.select_processing_method(chars)
        
        assert decision.method == ProcessingMethod.AI_IMAGE2TEXT
        assert "small" in decision.reasoning.lower() or "low resolution" in decision.reasoning.lower()
    
    def test_select_method_for_screenshot(self, processor):
        """Test selection for screenshot."""
        chars = MediaCharacteristics(
            media_type=MediaType.IMAGE,
            url="https://example.com/screenshot_2024.png"
        )
        
        decision = processor.select_processing_method(chars)
        
        assert decision.method == ProcessingMethod.TESSERACT_OCR
        assert "screenshot" in decision.reasoning.lower()
    
    def test_select_method_for_diagram(self, processor):
        """Test selection for diagram/chart."""
        chars = MediaCharacteristics(
            media_type=MediaType.IMAGE,
            url="https://example.com/diagram_flow.png"
        )
        
        decision = processor.select_processing_method(chars)
        
        assert decision.method == ProcessingMethod.AI_IMAGE2TEXT
        assert "diagram" in decision.reasoning.lower() or "chart" in decision.reasoning.lower()
    
    def test_select_method_quality_preference(self, processor):
        """Test that quality preference influences selection."""
        chars = MediaCharacteristics(
            media_type=MediaType.IMAGE
        )
        
        decision = processor.select_processing_method(chars)
        
        # Quality-preferring should choose AI
        assert decision.method == ProcessingMethod.AI_IMAGE2TEXT
    
    def test_select_method_speed_preference(self, speed_processor):
        """Test that speed preference influences selection."""
        chars = MediaCharacteristics(
            media_type=MediaType.IMAGE
        )
        
        decision = speed_processor.select_processing_method(chars)
        
        # Speed-preferring should choose Tesseract
        assert decision.method == ProcessingMethod.TESSERACT_OCR
    
    def test_select_video_with_clear_speech(self, processor):
        """Test video selection with clear speech."""
        chars = MediaCharacteristics(
            media_type=MediaType.VIDEO,
            has_clear_speech=True
        )
        
        decision = processor.select_processing_method(chars)
        
        assert decision.method == ProcessingMethod.AUDIO_TRANSCRIPTION
        assert decision.confidence >= 0.9
        assert "clear speech" in decision.reasoning.lower()
    
    def test_select_video_no_audio(self, processor):
        """Test video selection without audio."""
        chars = MediaCharacteristics(
            media_type=MediaType.VIDEO,
            has_audio=False
        )
        
        decision = processor.select_processing_method(chars)
        
        assert decision.method == ProcessingMethod.AI_VIDEO2TEXT
        assert "no audio" in decision.reasoning.lower()
    
    def test_select_short_video(self, processor):
        """Test selection for short video."""
        chars = MediaCharacteristics(
            media_type=MediaType.VIDEO,
            duration=90  # 1.5 minutes
        )
        
        decision = processor.select_processing_method(chars)
        
        assert decision.method == ProcessingMethod.AI_VIDEO2TEXT
        assert "short" in decision.reasoning.lower()
    
    def test_select_long_video(self, processor):
        """Test selection for long video."""
        chars = MediaCharacteristics(
            media_type=MediaType.VIDEO,
            duration=900  # 15 minutes
        )
        
        decision = processor.select_processing_method(chars)
        
        assert decision.method == ProcessingMethod.AUDIO_TRANSCRIPTION
        assert "long" in decision.reasoning.lower()
    
    def test_select_audio(self, processor):
        """Test selection for audio."""
        chars = MediaCharacteristics(
            media_type=MediaType.AUDIO
        )
        
        decision = processor.select_processing_method(chars)
        
        assert decision.method == ProcessingMethod.AUDIO_TRANSCRIPTION
        assert decision.confidence == 1.0
    
    def test_select_pdf(self, processor):
        """Test selection for PDF."""
        chars = MediaCharacteristics(
            media_type=MediaType.PDF
        )
        
        decision = processor.select_processing_method(chars)
        
        assert decision.method == ProcessingMethod.PDF_EXTRACT
        assert decision.confidence == 1.0
    
    def test_decision_includes_cost_estimates(self, processor):
        """Test that decisions include cost and time estimates."""
        chars = MediaCharacteristics(
            media_type=MediaType.IMAGE,
            is_printed_text=True
        )
        
        decision = processor.select_processing_method(chars)
        
        assert decision.estimated_cost in ["low", "medium", "high"]
        assert decision.estimated_time in ["fast", "medium", "slow"]
    
    def test_get_method_for_config(self, processor):
        """Test converting decision to config string."""
        decision = ProcessingDecision(
            method=ProcessingMethod.TESSERACT_OCR,
            confidence=0.9,
            reasoning="Test",
            estimated_cost="low",
            estimated_time="fast"
        )
        
        method_str = processor.get_method_for_config(decision)
        assert method_str == "tesseract"
        
        decision2 = ProcessingDecision(
            method=ProcessingMethod.AI_IMAGE2TEXT,
            confidence=0.9,
            reasoning="Test",
            estimated_cost="medium",
            estimated_time="medium"
        )
        
        method_str2 = processor.get_method_for_config(decision2)
        assert method_str2 == "image2text"
    
    def test_estimate_processing_resources(self, processor):
        """Test estimating processing resources."""
        decision = ProcessingDecision(
            method=ProcessingMethod.AI_VIDEO2TEXT,
            confidence=0.8,
            reasoning="Test reasoning",
            estimated_cost="high",
            estimated_time="slow"
        )
        
        resources = processor.estimate_processing_resources(decision)
        
        assert resources["method"] == "video2text"
        assert resources["estimated_cost_units"] == 20
        assert resources["estimated_time_seconds"] == 15
        assert resources["confidence"] == 0.8
        assert resources["reasoning"] == "Test reasoning"
    
    def test_unsupported_media_type_raises_error(self, processor):
        """Test that unsupported media type raises error."""
        chars = MediaCharacteristics(
            media_type="unsupported"  # This won't work with enum, but test the concept
        )
        
        # Since we're using enums, this would fail at creation time
        # Test would need adjustment based on actual error handling
