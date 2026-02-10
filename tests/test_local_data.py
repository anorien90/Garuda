"""Tests for LocalFileAdapter and DirectoryWatcherService."""

import os
import re
import time
import tempfile
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from garuda_intel.sources.base_adapter import (
    SourceAdapter,
    Document,
    SourceType,
    FetchError,
    NormalizationError,
)
from garuda_intel.sources.local_file_adapter import LocalFileAdapter
from garuda_intel.services.directory_watcher import DirectoryWatcherService


# ============================================================================
# LocalFileAdapter Tests
# ============================================================================

class TestLocalFileAdapterInit:
    """Tests for LocalFileAdapter initialization."""

    def test_default_config(self):
        """Test adapter creation with default config."""
        adapter = LocalFileAdapter()
        assert adapter.max_file_size == 100 * 1024 * 1024
        assert len(adapter.supported_extensions) > 0

    def test_custom_config(self):
        """Test adapter creation with custom config."""
        adapter = LocalFileAdapter({"max_file_size_mb": 50})
        assert adapter.max_file_size == 50 * 1024 * 1024

    def test_custom_extensions(self):
        """Test adapter with custom supported extensions."""
        adapter = LocalFileAdapter({"supported_extensions": [".txt", ".pdf"]})
        assert adapter.supported_extensions == [".txt", ".pdf"]

    def test_get_supported_extensions_classmethod(self):
        """Test class method returns all extensions."""
        exts = LocalFileAdapter.get_supported_extensions()
        assert ".pdf" in exts
        assert ".txt" in exts
        assert ".md" in exts
        assert ".png" in exts
        assert ".mp4" in exts


class TestLocalFileAdapterTextFiles:
    """Tests for text file processing."""

    def test_process_text_file(self, tmp_path):
        """Test processing a plain text file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, this is a test document with enough content to be valid.")

        adapter = LocalFileAdapter()
        doc = adapter.process_file(str(test_file))

        assert doc is not None
        assert doc.content == "Hello, this is a test document with enough content to be valid."
        assert doc.title == "test.txt"
        assert doc.confidence >= 0.9
        assert doc.source_type == SourceType.STRUCTURED_DATA

    def test_process_markdown_file(self, tmp_path):
        """Test processing a markdown file."""
        test_file = tmp_path / "readme.md"
        test_file.write_text("# Title\n\nThis is a markdown document for testing.")

        adapter = LocalFileAdapter()
        doc = adapter.process_file(str(test_file))

        assert doc is not None
        assert "# Title" in doc.content
        assert doc.title == "readme.md"

    def test_process_json_file(self, tmp_path):
        """Test processing a JSON file."""
        test_file = tmp_path / "data.json"
        test_file.write_text('{"name": "test", "value": 42}')

        adapter = LocalFileAdapter()
        doc = adapter.process_file(str(test_file))

        assert doc is not None
        assert "test" in doc.content
        assert doc.metadata["file_type"] == ".json"

    def test_process_csv_file(self, tmp_path):
        """Test processing a CSV file."""
        test_file = tmp_path / "data.csv"
        test_file.write_text("name,age,city\nAlice,30,NYC\nBob,25,LA")

        adapter = LocalFileAdapter()
        doc = adapter.process_file(str(test_file))

        assert doc is not None
        assert "Alice" in doc.content
        assert "Bob" in doc.content

    def test_process_yaml_file(self, tmp_path):
        """Test processing a YAML file."""
        test_file = tmp_path / "config.yaml"
        test_file.write_text("key: value\nlist:\n  - item1\n  - item2")

        adapter = LocalFileAdapter()
        doc = adapter.process_file(str(test_file))

        assert doc is not None
        assert "key: value" in doc.content


class TestLocalFileAdapterValidation:
    """Tests for file validation."""

    def test_unsupported_extension(self, tmp_path):
        """Test rejection of unsupported file types."""
        test_file = tmp_path / "test.xyz"
        test_file.write_text("content")

        adapter = LocalFileAdapter()
        with pytest.raises(FetchError, match="Unsupported file type"):
            adapter.process_file(str(test_file))

    def test_nonexistent_file(self):
        """Test handling of missing files."""
        adapter = LocalFileAdapter()
        with pytest.raises(FetchError, match="Invalid file path"):
            adapter.process_file("/nonexistent/path/file.txt")

    def test_path_traversal_blocked(self, tmp_path):
        """Test that path traversal is blocked."""
        adapter = LocalFileAdapter()
        with pytest.raises(FetchError, match="Invalid file path"):
            adapter.process_file("../../etc/passwd")

    def test_file_size_limit(self, tmp_path):
        """Test file size validation."""
        test_file = tmp_path / "large.txt"
        # Create a file slightly over 1MB limit
        test_file.write_text("x" * (2 * 1024 * 1024))

        adapter = LocalFileAdapter({"max_file_size_mb": 1})
        with pytest.raises(FetchError, match="too large"):
            adapter.process_file(str(test_file))


class TestLocalFileAdapterFetch:
    """Tests for the fetch method."""

    def test_fetch_returns_documents(self, tmp_path):
        """Test fetch returns list of documents."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("This is test content for the fetch method.")

        adapter = LocalFileAdapter()
        docs = adapter.fetch(str(test_file))

        assert len(docs) == 1
        assert isinstance(docs[0], Document)
        assert docs[0].content == "This is test content for the fetch method."

    def test_fetch_caches_result(self, tmp_path):
        """Test fetch uses cache on second call."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Cached content here.")

        adapter = LocalFileAdapter()
        docs1 = adapter.fetch(str(test_file))
        docs2 = adapter.fetch(str(test_file))

        assert docs1[0] is docs2[0]  # Same cached object

    def test_fetch_nonexistent_raises(self):
        """Test fetch raises FetchError for missing files."""
        adapter = LocalFileAdapter()
        with pytest.raises(FetchError):
            adapter.fetch("/nonexistent/file.txt")


class TestLocalFileAdapterNormalize:
    """Tests for the normalize method."""

    def test_normalize_creates_document(self):
        """Test normalization creates proper Document."""
        adapter = LocalFileAdapter()
        doc = adapter.normalize({
            "path": "/test/file.txt",
            "content": "Test content for normalization testing.",
            "file_type": ".txt",
            "metadata": {"file_type": ".txt", "file_size_bytes": 100},
        })

        assert isinstance(doc, Document)
        assert doc.content == "Test content for normalization testing."
        assert doc.title == "file.txt"
        assert doc.confidence >= 0.9

    def test_normalize_pdf_source_type(self):
        """Test PDF files get PDF source type."""
        adapter = LocalFileAdapter()
        doc = adapter.normalize({
            "path": "/test/report.pdf",
            "content": "PDF text content for testing the adapter.",
            "file_type": ".pdf",
            "metadata": {"file_type": ".pdf"},
        })

        assert doc.source_type == SourceType.PDF

    def test_normalize_image_source_type(self):
        """Test image files get LOCAL_FILE source type."""
        adapter = LocalFileAdapter()
        doc = adapter.normalize({
            "path": "/test/photo.png",
            "content": "OCR text from image.",
            "file_type": ".png",
            "metadata": {"file_type": ".png"},
        })

        assert doc.source_type == SourceType.LOCAL_FILE


class TestLocalFileAdapterMetadata:
    """Tests for metadata extraction."""

    def test_metadata_includes_file_info(self, tmp_path):
        """Test metadata contains file information."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content for metadata extraction testing here.")

        adapter = LocalFileAdapter()
        doc = adapter.process_file(str(test_file))

        assert "file_type" in doc.metadata
        assert doc.metadata["file_type"] == ".txt"
        assert "file_size_bytes" in doc.metadata
        assert "file_size_mb" in doc.metadata
        assert "created_time" in doc.metadata
        assert "modified_time" in doc.metadata
        assert "absolute_path" in doc.metadata

    def test_metadata_includes_mime_type(self, tmp_path):
        """Test metadata includes MIME type."""
        test_file = tmp_path / "test.html"
        test_file.write_text("<html><body>Test HTML content here.</body></html>")

        adapter = LocalFileAdapter()
        doc = adapter.process_file(str(test_file))

        assert "mime_type" in doc.metadata
        assert "html" in doc.metadata["mime_type"]


class TestLocalFileAdapterQuality:
    """Tests for content quality assessment."""

    def test_text_file_high_confidence(self, tmp_path):
        """Test text files get high confidence."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("This is a proper text document with enough content.")

        adapter = LocalFileAdapter()
        doc = adapter.process_file(str(test_file))
        assert doc.confidence >= 0.9

    def test_short_content_low_confidence(self):
        """Test short content gets low confidence."""
        adapter = LocalFileAdapter()
        score = adapter._assess_content_quality("abc", ".txt")
        assert score == 0.3


class TestLocalFileAdapterID:
    """Tests for document ID generation."""

    def test_same_path_same_id(self, tmp_path):
        """Test same file path produces same ID."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Content for ID testing.")

        adapter = LocalFileAdapter()
        doc1 = adapter.process_file(str(test_file))
        adapter.clear_cache()  # Force reprocess
        doc2 = adapter.process_file(str(test_file))

        assert doc1.id == doc2.id

    def test_different_path_different_id(self, tmp_path):
        """Test different paths produce different IDs."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("Content for file one.")
        file2.write_text("Content for file two.")

        adapter = LocalFileAdapter()
        doc1 = adapter.process_file(str(file1))
        doc2 = adapter.process_file(str(file2))

        assert doc1.id != doc2.id


# ============================================================================
# DirectoryWatcherService Tests
# ============================================================================

class TestDirectoryWatcherInit:
    """Tests for DirectoryWatcherService initialization."""

    def test_init_valid_directory(self, tmp_path):
        """Test initialization with valid directory."""
        mock_tq = Mock()
        watcher = DirectoryWatcherService(
            watch_dir=str(tmp_path),
            task_queue=mock_tq,
        )

        assert watcher.watch_dir == str(tmp_path)
        assert watcher.poll_interval == 5.0
        assert watcher.recursive is True

    def test_init_custom_config(self, tmp_path):
        """Test initialization with custom config."""
        mock_tq = Mock()
        watcher = DirectoryWatcherService(
            watch_dir=str(tmp_path),
            task_queue=mock_tq,
            poll_interval=10.0,
            recursive=False,
        )

        assert watcher.poll_interval == 10.0
        assert watcher.recursive is False

    def test_init_nonexistent_directory(self):
        """Test initialization with non-existent directory that cannot be created raises."""
        mock_tq = Mock()
        with pytest.raises(ValueError, match="cannot be created"):
            DirectoryWatcherService(
                watch_dir="/nonexistent/path",
                task_queue=mock_tq,
            )


class TestDirectoryWatcherScanExisting:
    """Tests for scan_existing method."""

    def test_scan_empty_directory(self, tmp_path):
        """Test scanning empty directory."""
        mock_tq = Mock()
        mock_tq.submit = Mock(return_value="task-123")
        watcher = DirectoryWatcherService(
            watch_dir=str(tmp_path),
            task_queue=mock_tq,
        )

        result = watcher.scan_existing()
        assert result["queued"] == 0
        assert result["skipped"] == 0

    def test_scan_directory_with_files(self, tmp_path):
        """Test scanning directory with supported files."""
        # Create test files
        (tmp_path / "doc.txt").write_text("Hello world!")
        (tmp_path / "data.json").write_text('{"key": "value"}')
        (tmp_path / "notes.md").write_text("# Notes")

        mock_tq = Mock()
        mock_tq.submit = Mock(return_value="task-123")
        watcher = DirectoryWatcherService(
            watch_dir=str(tmp_path),
            task_queue=mock_tq,
        )

        result = watcher.scan_existing()
        assert result["queued"] == 3
        assert mock_tq.submit.call_count == 3

    def test_scan_skips_unsupported_files(self, tmp_path):
        """Test scanning skips unsupported file types."""
        (tmp_path / "doc.txt").write_text("Hello world!")
        (tmp_path / "binary.exe").write_bytes(b"\x00\x01\x02")
        (tmp_path / "data.abc").write_text("Unknown type")

        mock_tq = Mock()
        mock_tq.submit = Mock(return_value="task-123")
        watcher = DirectoryWatcherService(
            watch_dir=str(tmp_path),
            task_queue=mock_tq,
        )

        result = watcher.scan_existing()
        assert result["queued"] == 1  # Only .txt is supported

    def test_scan_recursive(self, tmp_path):
        """Test recursive scanning."""
        # Create nested structure
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "root.txt").write_text("Root file content")
        (subdir / "nested.txt").write_text("Nested file content")

        mock_tq = Mock()
        mock_tq.submit = Mock(return_value="task-123")
        watcher = DirectoryWatcherService(
            watch_dir=str(tmp_path),
            task_queue=mock_tq,
            recursive=True,
        )

        result = watcher.scan_existing()
        assert result["queued"] == 2

    def test_scan_non_recursive(self, tmp_path):
        """Test non-recursive scanning."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "root.txt").write_text("Root file content")
        (subdir / "nested.txt").write_text("Nested file content")

        mock_tq = Mock()
        mock_tq.submit = Mock(return_value="task-123")
        watcher = DirectoryWatcherService(
            watch_dir=str(tmp_path),
            task_queue=mock_tq,
            recursive=False,
        )

        result = watcher.scan_existing()
        assert result["queued"] == 1  # Only root file


class TestDirectoryWatcherStatus:
    """Tests for get_status method."""

    def test_status_not_running(self, tmp_path):
        """Test status when watcher is not running."""
        mock_tq = Mock()
        watcher = DirectoryWatcherService(
            watch_dir=str(tmp_path),
            task_queue=mock_tq,
        )

        status = watcher.get_status()
        assert status["running"] is False
        assert status["watch_dir"] == str(tmp_path)
        assert status["tracked_files"] == 0
        assert status["last_scan_time"] is None

    def test_status_after_scan(self, tmp_path):
        """Test status after scanning directory."""
        (tmp_path / "test.txt").write_text("Test content")

        mock_tq = Mock()
        mock_tq.submit = Mock(return_value="task-123")
        watcher = DirectoryWatcherService(
            watch_dir=str(tmp_path),
            task_queue=mock_tq,
        )

        watcher.scan_existing()
        status = watcher.get_status()
        assert status["tracked_files"] == 1


class TestDirectoryWatcherChangeDetection:
    """Tests for change detection."""

    def test_detect_new_file(self, tmp_path):
        """Test detection of new files."""
        mock_tq = Mock()
        mock_tq.submit = Mock(return_value="task-123")
        watcher = DirectoryWatcherService(
            watch_dir=str(tmp_path),
            task_queue=mock_tq,
            poll_interval=0.1,
        )

        # Initial scan (no files)
        watcher.scan_existing()

        # Add a file
        (tmp_path / "new_file.txt").write_text("New file content")

        # Scan for changes
        changes = watcher._scan_directory()

        # Should detect the new file
        assert len(changes) == 1
        assert changes[0][1] == "new"

    def test_detect_modified_file(self, tmp_path):
        """Test detection of modified files."""
        test_file = tmp_path / "modify_me.txt"
        test_file.write_text("Original content")

        mock_tq = Mock()
        mock_tq.submit = Mock(return_value="task-123")
        watcher = DirectoryWatcherService(
            watch_dir=str(tmp_path),
            task_queue=mock_tq,
            poll_interval=0.1,
        )

        # Initial scan
        watcher.scan_existing()

        # Modify the file (change content to ensure hash changes)
        time.sleep(0.1)
        test_file.write_text("Modified content with different hash value!")

        # Scan for changes
        changes = watcher._scan_directory()

        # Should detect the modification
        assert len(changes) == 1
        assert changes[0][1] == "modified"

    def test_detect_deleted_file(self, tmp_path):
        """Test that deleted files are removed from tracking."""
        test_file = tmp_path / "delete_me.txt"
        test_file.write_text("Will be deleted")

        mock_tq = Mock()
        mock_tq.submit = Mock(return_value="task-123")
        watcher = DirectoryWatcherService(
            watch_dir=str(tmp_path),
            task_queue=mock_tq,
            poll_interval=0.1,
        )

        # Initial scan
        watcher.scan_existing()
        assert watcher.get_status()["tracked_files"] == 1

        # Delete the file
        test_file.unlink()

        # Scan for changes
        watcher._scan_directory()

        # Should be removed from tracking
        assert watcher.get_status()["tracked_files"] == 0


class TestDirectoryWatcherFiltering:
    """Tests for file extension filtering."""

    def test_is_supported_file(self, tmp_path):
        """Test supported file detection."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("content")

        mock_tq = Mock()
        watcher = DirectoryWatcherService(
            watch_dir=str(tmp_path),
            task_queue=mock_tq,
        )

        assert watcher._is_supported_file(str(txt_file)) is True

    def test_is_not_supported_file(self, tmp_path):
        """Test unsupported file detection."""
        exe_file = tmp_path / "test.exe"
        exe_file.write_bytes(b"\x00")

        mock_tq = Mock()
        watcher = DirectoryWatcherService(
            watch_dir=str(tmp_path),
            task_queue=mock_tq,
        )

        assert watcher._is_supported_file(str(exe_file)) is False


class TestDirectoryWatcherTaskQueueing:
    """Tests for task queue integration."""

    def test_queued_task_params(self, tmp_path):
        """Test that queued tasks have correct parameters."""
        (tmp_path / "test.txt").write_text("Test content")

        mock_tq = Mock()
        mock_tq.submit = Mock(return_value="task-123")
        watcher = DirectoryWatcherService(
            watch_dir=str(tmp_path),
            task_queue=mock_tq,
        )

        watcher.scan_existing()

        # Verify task submission parameters
        mock_tq.submit.assert_called_once()
        call_kwargs = mock_tq.submit.call_args
        assert call_kwargs.kwargs["task_type"] == "local_ingest"
        assert "file_path" in call_kwargs.kwargs["params"]
        assert call_kwargs.kwargs["params"]["event"] == "new"


class TestDirectoryWatcherFilePersistence:
    """Tests for file persistence to storage directory."""

    def test_persist_file_copies_to_storage(self, tmp_path):
        """Test that watched files are copied to the storage directory."""
        watch_dir = tmp_path / "watch"
        storage_dir = tmp_path / "uploads"
        watch_dir.mkdir()

        test_file = watch_dir / "report.txt"
        test_file.write_text("Important report content")

        mock_tq = Mock()
        mock_tq.submit = Mock(return_value="task-123")
        watcher = DirectoryWatcherService(
            watch_dir=str(watch_dir),
            task_queue=mock_tq,
            storage_dir=str(storage_dir),
        )

        stored = watcher._persist_file(str(test_file))
        assert os.path.isfile(stored)
        assert str(storage_dir) in stored
        with open(stored) as f:
            assert f.read() == "Important report content"

    def test_persist_file_handles_duplicates(self, tmp_path):
        """Test duplicate filenames in storage get a counter suffix."""
        watch_dir = tmp_path / "watch"
        storage_dir = tmp_path / "uploads"
        watch_dir.mkdir()
        storage_dir.mkdir()

        # Create existing file in storage
        (storage_dir / "data.txt").write_text("old")

        test_file = watch_dir / "data.txt"
        test_file.write_text("new content")

        mock_tq = Mock()
        watcher = DirectoryWatcherService(
            watch_dir=str(watch_dir),
            task_queue=mock_tq,
            storage_dir=str(storage_dir),
        )

        stored = watcher._persist_file(str(test_file))
        assert os.path.isfile(stored)
        assert "data_1.txt" in stored

    def test_scan_existing_persists_files(self, tmp_path):
        """Test scan_existing copies files to storage and queues stored path."""
        watch_dir = tmp_path / "watch"
        storage_dir = tmp_path / "uploads"
        watch_dir.mkdir()

        (watch_dir / "doc.txt").write_text("Document content")

        mock_tq = Mock()
        mock_tq.submit = Mock(return_value="task-123")
        watcher = DirectoryWatcherService(
            watch_dir=str(watch_dir),
            task_queue=mock_tq,
            storage_dir=str(storage_dir),
        )

        result = watcher.scan_existing()
        assert result["queued"] == 1

        # The task should be submitted with the stored path
        call_kwargs = mock_tq.submit.call_args
        params = call_kwargs.kwargs["params"]
        assert "stored_path" in params
        assert str(storage_dir) in params["stored_path"]
        assert os.path.isfile(params["stored_path"])

    def test_storage_dir_defaults_to_sibling_uploads(self, tmp_path):
        """Test storage directory defaults to a sibling 'uploads' directory."""
        watch_dir = tmp_path / "watch"
        watch_dir.mkdir()

        mock_tq = Mock()
        watcher = DirectoryWatcherService(
            watch_dir=str(watch_dir),
            task_queue=mock_tq,
        )

        assert watcher.storage_dir == os.path.join(str(tmp_path), "uploads")

    def test_status_includes_storage_dir(self, tmp_path):
        """Test status includes storage_dir field."""
        mock_tq = Mock()
        watcher = DirectoryWatcherService(
            watch_dir=str(tmp_path),
            task_queue=mock_tq,
        )

        status = watcher.get_status()
        assert "storage_dir" in status


class TestDirectoryWatcherStartStop:
    """Tests for start/stop lifecycle."""

    def test_start_creates_thread(self, tmp_path):
        """Test that start creates a monitoring thread."""
        mock_tq = Mock()
        watcher = DirectoryWatcherService(
            watch_dir=str(tmp_path),
            task_queue=mock_tq,
            poll_interval=0.1,
        )

        watcher.start()
        assert watcher._running is True
        assert watcher._worker_thread is not None
        assert watcher._worker_thread.is_alive()

        watcher.stop()
        assert watcher._running is False

    def test_stop_without_start(self, tmp_path):
        """Test stop when not running."""
        mock_tq = Mock()
        watcher = DirectoryWatcherService(
            watch_dir=str(tmp_path),
            task_queue=mock_tq,
        )

        # Should not raise
        watcher.stop()


# ============================================================================
# Integration: TASK_LOCAL_INGEST constant
# ============================================================================

class TestTaskQueueLocalIngest:
    """Tests for TASK_LOCAL_INGEST in TaskQueueService."""

    def test_task_local_ingest_constant_exists(self):
        """Test that TASK_LOCAL_INGEST constant is defined."""
        from garuda_intel.services.task_queue import TaskQueueService
        assert hasattr(TaskQueueService, 'TASK_LOCAL_INGEST')
        assert TaskQueueService.TASK_LOCAL_INGEST == "local_ingest"

    def test_local_ingest_category_is_io(self):
        """Test that local_ingest is categorized as IO task."""
        from garuda_intel.services.task_queue import TaskQueueService
        # Create minimal mock store
        mock_store = Mock()
        mock_store.Session = Mock(return_value=MagicMock())
        
        with patch.object(TaskQueueService, '_recover_stale_tasks'):
            tq = TaskQueueService(mock_store)
            assert tq._task_categories.get("local_ingest") == "io"


# ============================================================================
# SourceType enum test
# ============================================================================

class TestSourceTypeEnum:
    """Tests for SourceType enum changes."""

    def test_local_file_source_type_exists(self):
        """Test LOCAL_FILE source type is available."""
        assert hasattr(SourceType, 'LOCAL_FILE')
        assert SourceType.LOCAL_FILE.value == "local_file"


# ============================================================================
# Link extraction from local file content
# ============================================================================

class TestLocalFileLinkExtraction:
    """Tests for URL extraction from local file content."""

    def test_extract_urls_from_text(self):
        """Test that URLs are extracted from text content."""
        content = (
            "Visit https://example.com for details. "
            "Also see http://test.org/page?q=1 and "
            "https://another.site/path/to/resource.html for more."
        )
        url_pattern = re.compile(r'https?://[^\s<>"\')\],;]+', re.IGNORECASE)
        seen = set()
        links = []
        for m in url_pattern.finditer(content):
            url = m.group(0).rstrip('.')
            if url not in seen:
                seen.add(url)
                links.append({"href": url})

        assert len(links) == 3
        hrefs = [l["href"] for l in links]
        assert "https://example.com" in hrefs
        assert "http://test.org/page?q=1" in hrefs
        assert "https://another.site/path/to/resource.html" in hrefs

    def test_no_duplicate_urls(self):
        """Test that duplicate URLs are deduplicated."""
        content = (
            "https://example.com is mentioned here. "
            "And https://example.com is mentioned again."
        )
        url_pattern = re.compile(r'https?://[^\s<>"\')\],;]+', re.IGNORECASE)
        seen = set()
        links = []
        for m in url_pattern.finditer(content):
            url = m.group(0).rstrip('.')
            if url not in seen:
                seen.add(url)
                links.append({"href": url})

        assert len(links) == 1

    def test_no_urls_in_content(self):
        """Test content with no URLs produces empty links."""
        content = "This is plain text with no URLs at all."
        url_pattern = re.compile(r'https?://[^\s<>"\')\],;]+', re.IGNORECASE)
        links = list(url_pattern.finditer(content))
        assert len(links) == 0


class TestDirectoryWatcherPreservesSubdirs:
    """Tests for subdirectory structure preservation in storage."""

    def test_persist_preserves_subdirectory(self, tmp_path):
        """Test that subdirectory structure from watch dir is preserved in storage."""
        watch_dir = tmp_path / "watch"
        storage_dir = tmp_path / "storage"
        sub = watch_dir / "subdir"
        sub.mkdir(parents=True)

        test_file = sub / "nested.txt"
        test_file.write_text("nested content")

        mock_tq = Mock()
        watcher = DirectoryWatcherService(
            watch_dir=str(watch_dir),
            task_queue=mock_tq,
            storage_dir=str(storage_dir),
        )

        stored = watcher._persist_file(str(test_file))
        assert "subdir" in stored
        assert os.path.isfile(stored)
        with open(stored) as f:
            assert f.read() == "nested content"
