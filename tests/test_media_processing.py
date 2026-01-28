"""Basic tests for media processing functionality."""

import pytest
import tempfile
import os
from pathlib import Path


def test_media_downloader():
    """Test MediaDownloader basic functionality."""
    from garuda_intel.services.media_downloader import MediaDownloader
    
    # Create temporary cache directory
    with tempfile.TemporaryDirectory() as tmpdir:
        downloader = MediaDownloader(cache_dir=tmpdir)
        
        # Test with a simple URL (GitHub's logo)
        test_url = "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png"
        
        file_path, metadata = downloader.download(test_url)
        
        if file_path:
            assert Path(file_path).exists()
            assert metadata is not None
            assert metadata.get("mime_type") is not None
            print(f"✓ Download successful: {metadata}")
        else:
            print(f"⚠ Download failed (network issue or rate limit): {metadata}")


def test_media_processor_initialization():
    """Test MediaProcessor initialization with different methods."""
    from garuda_intel.services.media_processor import MediaProcessor
    
    # Test with default methods
    processor = MediaProcessor(llm_extractor=None, enable_processing=True)
    
    assert processor.enabled == True
    assert processor.image_method == "tesseract"
    assert processor.video_method == "speech"
    assert processor.audio_method == "speech"
    print(f"✓ MediaProcessor initialized with default methods")
    print(f"  OCR available: {processor.ocr_available}")
    print(f"  Speech available: {processor.speech_available}")
    print(f"  Video available: {processor.video_available}")
    
    # Test with custom methods
    processor2 = MediaProcessor(
        llm_extractor=None, 
        enable_processing=True,
        image_method="image2text",
        video_method="video2text",
        audio_method="speech"
    )
    
    assert processor2.image_method == "image2text"
    assert processor2.video_method == "video2text"
    print(f"✓ MediaProcessor initialized with custom methods")


def test_media_processor_image_processing():
    """Test image processing with OCR (if pytesseract available)."""
    from garuda_intel.services.media_processor import MediaProcessor
    
    processor = MediaProcessor(llm_extractor=None, enable_processing=True)
    
    if not processor.ocr_available:
        print("⚠ Skipping OCR test - pytesseract not available")
        return
    
    # Create a simple test image with text
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = Path(tmpdir) / "test.png"
            
            # Create a simple image with text
            img = Image.new('RGB', (200, 100), color='white')
            draw = ImageDraw.Draw(img)
            draw.text((10, 40), "Hello World", fill='black')
            img.save(img_path)
            
            # Process the image with tesseract
            result = processor.process_image(str(img_path), "test://url", method="tesseract")
            
            assert result is not None
            assert result.get("metadata_json", {}).get("method") == "tesseract"
            print(f"✓ Image processing (Tesseract) result: {result}")
            
            if result.get("extracted_text"):
                print(f"  Extracted text: {result['extracted_text'][:100]}")
    except ImportError:
        print("⚠ Skipping image test - PIL not available")


def test_media_processor_audio_extraction():
    """Test audio extraction from video."""
    from garuda_intel.services.media_processor import MediaProcessor
    
    processor = MediaProcessor(llm_extractor=None, enable_processing=True)
    
    if not processor.video_available:
        print("⚠ Skipping audio extraction test - moviepy not available")
        return
    
    # Note: This would need a real video file to test properly
    # For now, just verify the method exists
    assert hasattr(processor, 'extract_audio_from_video')
    print(f"✓ Audio extraction method available")


def test_media_processor_video_processing():
    """Test video processing methods."""
    from garuda_intel.services.media_processor import MediaProcessor
    
    processor = MediaProcessor(
        llm_extractor=None, 
        enable_processing=True,
        video_method="speech"
    )
    
    # Verify processing method is set
    assert processor.video_method == "speech"
    print(f"✓ Video processing method configured: {processor.video_method}")
    
    # Test extract_audio_only parameter exists in process_video
    import inspect
    sig = inspect.signature(processor.process_video)
    assert 'extract_audio_only' in sig.parameters
    print(f"✓ Video processing supports audio extraction option")


def test_media_extractor():
    """Test MediaExtractor initialization."""
    from garuda_intel.services.media_extractor import MediaExtractor
    from garuda_intel.services.media_processor import MediaProcessor
    from garuda_intel.database.engine import SQLAlchemyStore
    
    # Create in-memory database
    store = SQLAlchemyStore("sqlite:///:memory:")
    processor = MediaProcessor(llm_extractor=None, enable_processing=False)
    
    extractor = MediaExtractor(store, processor, auto_process=False)
    
    assert extractor is not None
    print("✓ MediaExtractor initialized")


if __name__ == "__main__":
    print("\n=== Testing Media Processing Components ===\n")
    
    test_media_downloader()
    print()
    
    test_media_processor_initialization()
    print()
    
    test_media_processor_image_processing()
    print()
    
    test_media_processor_audio_extraction()
    print()
    
    test_media_processor_video_processing()
    print()
    
    test_media_extractor()
    print()
    
    print("\n=== All tests completed ===\n")
