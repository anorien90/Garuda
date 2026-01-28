# Media Processing Feature - Implementation Summary

## Overview

This implementation adds comprehensive media processing capabilities to Garuda, including:
- **Image OCR** using pytesseract
- **Audio Speech-to-Text** using SpeechRecognition
- **Video processing** with audio extraction and transcription using moviepy
- **Automatic embedding generation** from extracted text
- **Integration with the knowledge graph**

## Components Implemented

### 1. MediaDownloader (`src/garuda_intel/services/media_downloader.py`)
- Downloads media files from URLs with retry logic
- Caches downloaded files to avoid redundant downloads
- Supports file size limits and timeout handling
- Automatic MIME type detection
- Cache cleanup functionality

### 2. MediaProcessor (`src/garuda_intel/services/media_processor.py`)
- Processes images using OCR (pytesseract + PIL)
- Processes audio files using speech recognition (SpeechRecognition)
- Processes video files by extracting audio and applying STT (moviepy + SpeechRecognition)
- Generates embeddings from extracted text via LLM
- Graceful fallback when optional dependencies are not available
- `process_from_url()` method combines download and processing

### 3. MediaExtractor (`src/garuda_intel/services/media_extractor.py`)
- Extracts media items (images, videos, audio) from HTML during crawling
- Creates MediaItem database entries
- Optionally auto-processes media immediately
- Integrates with the page crawling workflow

### 4. API Routes (`src/garuda_intel/webapp/routes/media.py`)
- `GET /api/media/stats` - Get processing statistics
- `GET /api/media/items` - List media items with filtering
- `POST /api/media/process` - Manually process a media URL
- `POST /api/media/process-pending` - Batch process pending items
- `GET|POST /api/media/settings` - Manage settings

### 5. UI Integration (`src/garuda_intel/webapp/templates/components/media.html`)
- Media processing dashboard with statistics
- Browse and filter media items
- Manual media processing form
- Batch processing button
- Real-time status updates

### 6. Crawler Integration
- Added `media_extractor` parameter to `IntelligentExplorer`
- Automatic media extraction after page save
- Initialized in webapp with configurable settings

## Database Schema

The `MediaItem` model (already existed) includes:
- URL, media_type (image/video/audio)
- Relationships to Page and Entity
- extracted_text, text_embedding
- Processing status (processed, processing_error, processed_at)
- Metadata (file_size, mime_type, width, height, duration)

## Configuration

Environment variables (`.env`):
```env
GARUDA_MEDIA_PROCESSING=true      # Enable media text extraction
GARUDA_MEDIA_CRAWLING=true        # Auto-extract media from pages
GARUDA_MEDIA_EMBEDDINGS=true      # Generate embeddings from media text
```

## Dependencies

Required packages added to `requirements.txt`:
- `pillow` - Image processing
- `pytesseract` - OCR engine (requires tesseract-ocr system package)
- `SpeechRecognition` - Speech-to-text
- `moviepy` - Video processing
- `pydub` - Audio format conversion

## Usage

### Manual Processing via UI
1. Navigate to the Media tab in the web interface
2. Enter a media URL (image, video, or audio)
3. Select the media type
4. Optionally provide the source page URL
5. Click "Process Media"

### Automatic Processing during Crawling
When `GARUDA_MEDIA_CRAWLING=true`:
- Media is automatically extracted from crawled pages
- MediaItem entries are created in the database
- If `GARUDA_MEDIA_PROCESSING=true`, media is processed immediately
- Extracted text is stored and embeddings are generated

### Batch Processing
Click "Process Pending (10)" button to process up to 10 pending media items at once.

## API Example

```bash
# Process an image
curl -X POST http://localhost:5000/api/media/process \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "url": "https://example.com/image.jpg",
    "media_type": "image",
    "auto_process": true
  }'

# List processed media
curl http://localhost:5000/api/media/items?processed=true \
  -H "X-API-Key: your-api-key"

# Get statistics
curl http://localhost:5000/api/media/stats \
  -H "X-API-Key: your-api-key"
```

## System Requirements

### For Image Processing (OCR)
```bash
# Install tesseract OCR engine
# Ubuntu/Debian:
sudo apt-get install tesseract-ocr

# macOS:
brew install tesseract

# Then install Python package:
pip install pytesseract pillow
```

### For Audio Processing
```bash
pip install SpeechRecognition
# May also need: sudo apt-get install python3-pyaudio
```

### For Video Processing
```bash
pip install moviepy pydub
# May also need: sudo apt-get install ffmpeg
```

## Future Enhancements

### Potential improvements not yet implemented:
1. **Background Job Queue**: Use Celery or RQ for async processing
2. **Media-Entity Linking**: Automatically link media to detected entities
3. **Advanced OCR**: Support for multiple languages, handwriting recognition
4. **Visual Analysis**: Image classification, object detection
5. **Video Keyframes**: Extract and analyze key frames
6. **Subtitle Support**: Parse SRT/VTT caption files
7. **Cloud Storage**: S3/Azure Blob integration for media files
8. **Deduplication**: Detect duplicate media across pages
9. **Audio Language Detection**: Detect and transcribe multiple languages
10. **Progress Tracking**: WebSocket-based real-time progress updates

## Testing

Run the media processing tests:
```bash
cd /home/runner/work/Garuda/Garuda
python tests/test_media_processing.py
```

Note: Full testing requires all optional dependencies to be installed.

## Troubleshooting

### "pytesseract not available"
Install tesseract-ocr system package and pytesseract Python package.

### "speech_recognition not available"
Install: `pip install SpeechRecognition`

### "moviepy not available"
Install: `pip install moviepy` and ensure ffmpeg is installed.

### "Download failed"
- Check network connectivity
- Verify URL is accessible
- Check file size (default limit: 100MB)
- Review logs for rate limiting

### "Processing failed"
- Check processing_error field in MediaItem
- Review application logs
- Verify dependencies are properly installed

## Security Considerations

1. **File Size Limits**: Default 100MB to prevent resource exhaustion
2. **URL Validation**: Only HTTP/HTTPS URLs accepted
3. **Rate Limiting**: Consider adding rate limits for external services
4. **Cache Management**: Implement cache cleanup policies
5. **Content Filtering**: Consider adding content type validation
6. **Sandboxing**: Process media in isolated environment if handling untrusted sources

## Performance Notes

- **OCR**: Can be slow for large images (seconds per image)
- **Speech Recognition**: Limited by Google API rate limits
- **Video Processing**: Resource-intensive, requires ffmpeg
- **Caching**: Significantly improves performance for repeated access
- **Batch Processing**: Processes items sequentially to avoid resource contention

## Conclusion

The media processing feature is now fully implemented and integrated into Garuda. It provides end-to-end functionality for extracting, processing, and searching media content from crawled pages.
