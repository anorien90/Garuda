"""
Directory Watcher Service.

Monitors a directory for file changes and automatically queues them
for processing through the extraction pipeline. Uses polling to detect
new, modified, and deleted files without external dependencies.
"""

import hashlib
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from ..sources.local_file_adapter import LocalFileAdapter

logger = logging.getLogger(__name__)


class DirectoryWatcherService:
    """
    Directory monitoring service with automatic file ingestion.
    
    Monitors a directory for file changes using a polling approach and
    automatically queues supported files for processing via the task queue.
    Tracks file states to detect new, modified, and deleted files.
    
    Features:
    - Polling-based monitoring (no external dependencies)
    - Recursive directory scanning
    - File state tracking (mtime, size, hash)
    - Change detection (new, modified, deleted)
    - Debouncing to avoid partial writes
    - Extension filtering via LocalFileAdapter
    - Thread-safe state management
    """
    
    # Debounce settings
    DEBOUNCE_WAIT_SECONDS = 1.0
    DEBOUNCE_SIZE_CHECK_INTERVAL = 0.2
    
    # Task type constant (should match TaskQueueService.TASK_LOCAL_INGEST)
    TASK_LOCAL_INGEST = "local_ingest"
    
    def __init__(
        self,
        watch_dir: str,
        task_queue: 'TaskQueueService',
        poll_interval: float = 5.0,
        recursive: bool = True,
    ):
        """
        Initialize the directory watcher service.
        
        Args:
            watch_dir: Directory path to monitor
            task_queue: TaskQueueService instance for queueing tasks
            poll_interval: Seconds between directory scans
            recursive: If True, scan subdirectories recursively
        """
        self.watch_dir = os.path.abspath(watch_dir)
        self.task_queue = task_queue
        self.poll_interval = poll_interval
        self.recursive = recursive
        
        # Internal state
        self._file_states: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._shutdown_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._last_scan_time: Optional[float] = None
        self._running = False
        
        # Get supported extensions from LocalFileAdapter
        self._supported_extensions = set(LocalFileAdapter.get_supported_extensions())
        
        # Validate watch directory
        if not os.path.isdir(self.watch_dir):
            raise ValueError(f"Watch directory does not exist: {self.watch_dir}")
        
        logger.info(
            f"DirectoryWatcher initialized: dir={self.watch_dir} "
            f"poll={poll_interval}s recursive={recursive}"
        )
    
    def start(self):
        """Start the directory monitoring thread."""
        if self._worker_thread and self._worker_thread.is_alive():
            logger.warning("Directory watcher already running")
            return
        
        self._shutdown_event.clear()
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._poll_loop,
            name="directory-watcher",
            daemon=True,
        )
        self._worker_thread.start()
        logger.info(f"Directory watcher started monitoring: {self.watch_dir}")
    
    def stop(self):
        """Stop the directory monitoring thread gracefully."""
        if not self._running:
            logger.warning("Directory watcher not running")
            return
        
        self._shutdown_event.set()
        self._running = False
        
        if self._worker_thread:
            self._worker_thread.join(timeout=10.0)
            if self._worker_thread.is_alive():
                logger.warning("Directory watcher thread did not stop cleanly")
            else:
                logger.info("Directory watcher stopped")
    
    def scan_existing(self) -> Dict[str, int]:
        """
        Perform initial scan and queue all existing files.
        
        This method scans the directory once and queues all supported files
        that are found. Useful for initial ingestion when starting the watcher.
        
        Returns:
            Dict with counts: {"queued": int, "skipped": int}
        """
        logger.info(f"Scanning existing files in: {self.watch_dir}")
        
        queued = 0
        skipped = 0
        
        try:
            # Collect all supported files
            files_to_process = []
            
            if self.recursive:
                for root, dirs, files in os.walk(self.watch_dir):
                    for filename in files:
                        filepath = os.path.join(root, filename)
                        if self._is_supported_file(filepath):
                            files_to_process.append(filepath)
            else:
                for filename in os.listdir(self.watch_dir):
                    filepath = os.path.join(self.watch_dir, filename)
                    if os.path.isfile(filepath) and self._is_supported_file(filepath):
                        files_to_process.append(filepath)
            
            # Process each file
            for filepath in files_to_process:
                try:
                    # Get file state
                    state = self._get_file_state(filepath)
                    if state:
                        # Add to tracking
                        with self._lock:
                            self._file_states[filepath] = state
                        
                        # Queue for processing
                        self._queue_file(filepath, "new")
                        queued += 1
                    else:
                        skipped += 1
                except Exception as e:
                    logger.warning(f"Failed to queue file {filepath}: {e}")
                    skipped += 1
            
            logger.info(
                f"Scan complete: queued={queued} skipped={skipped} "
                f"total={queued + skipped}"
            )
            
        except Exception as e:
            logger.error(f"Error during initial scan: {e}", exc_info=True)
        
        return {"queued": queued, "skipped": skipped}
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current watcher status.
        
        Returns:
            Status dict with running state, config, and statistics
        """
        with self._lock:
            tracked_count = len(self._file_states)
            last_scan = self._last_scan_time
        
        return {
            "running": self._running,
            "watch_dir": self.watch_dir,
            "recursive": self.recursive,
            "poll_interval": self.poll_interval,
            "tracked_files": tracked_count,
            "last_scan_time": last_scan,
            "supported_extensions": sorted(list(self._supported_extensions)),
        }
    
    # =========================================================================
    # INTERNAL METHODS
    # =========================================================================
    
    def _poll_loop(self):
        """Main polling loop that scans directory periodically."""
        logger.info("Directory watcher poll loop started")
        
        try:
            while not self._shutdown_event.is_set():
                try:
                    # Scan directory for changes
                    changes = self._scan_directory()
                    
                    # Update last scan time
                    with self._lock:
                        self._last_scan_time = time.time()
                    
                    # Process changes
                    if changes:
                        logger.info(f"Detected {len(changes)} file changes")
                        for filepath, event in changes:
                            try:
                                self._queue_file(filepath, event)
                            except Exception as e:
                                logger.error(
                                    f"Failed to queue {filepath}: {e}",
                                    exc_info=True
                                )
                    
                    # Wait for next poll interval
                    self._shutdown_event.wait(self.poll_interval)
                    
                except Exception as e:
                    logger.error(f"Error in poll loop: {e}", exc_info=True)
                    self._shutdown_event.wait(self.poll_interval)
        
        finally:
            logger.info("Directory watcher poll loop exiting")
    
    def _scan_directory(self) -> List[Tuple[str, str]]:
        """
        Scan directory and detect changes.
        
        Returns:
            List of (filepath, event) tuples where event is "new" or "modified"
        """
        changes = []
        current_files = set()
        
        try:
            # Collect all files in directory
            if self.recursive:
                for root, dirs, files in os.walk(self.watch_dir):
                    for filename in files:
                        filepath = os.path.join(root, filename)
                        if self._is_supported_file(filepath):
                            current_files.add(filepath)
            else:
                for filename in os.listdir(self.watch_dir):
                    filepath = os.path.join(self.watch_dir, filename)
                    if os.path.isfile(filepath) and self._is_supported_file(filepath):
                        current_files.add(filepath)
            
            with self._lock:
                tracked_files = set(self._file_states.keys())
            
            # Detect new files
            new_files = current_files - tracked_files
            for filepath in new_files:
                if self._debounce_file(filepath):
                    state = self._get_file_state(filepath)
                    if state:
                        with self._lock:
                            self._file_states[filepath] = state
                        changes.append((filepath, "new"))
            
            # Detect modified files
            for filepath in current_files & tracked_files:
                current_state = self._get_file_state(filepath)
                if not current_state:
                    continue
                
                with self._lock:
                    old_state = self._file_states.get(filepath)
                
                if old_state and self._has_changed(old_state, current_state):
                    if self._debounce_file(filepath):
                        # Re-get state after debounce
                        final_state = self._get_file_state(filepath)
                        if final_state:
                            with self._lock:
                                self._file_states[filepath] = final_state
                            changes.append((filepath, "modified"))
            
            # Detect deleted files (remove from tracking)
            deleted_files = tracked_files - current_files
            if deleted_files:
                with self._lock:
                    for filepath in deleted_files:
                        self._file_states.pop(filepath, None)
                logger.debug(f"Removed {len(deleted_files)} deleted files from tracking")
        
        except Exception as e:
            logger.error(f"Error scanning directory: {e}", exc_info=True)
        
        return changes
    
    def _is_supported_file(self, filepath: str) -> bool:
        """
        Check if file has a supported extension.
        
        Args:
            filepath: Path to file
            
        Returns:
            True if file extension is supported
        """
        if not os.path.isfile(filepath):
            return False
        
        _, ext = os.path.splitext(filepath)
        ext = ext.lower()
        return ext in self._supported_extensions
    
    def _get_file_state(self, filepath: str) -> Optional[Dict[str, Any]]:
        """
        Get current state of a file.
        
        Args:
            filepath: Path to file
            
        Returns:
            State dict with mtime, size, and hash, or None if error
        """
        try:
            stat = os.stat(filepath)
            
            # Calculate file hash (for change detection)
            file_hash = self._calculate_file_hash(filepath)
            
            return {
                "mtime": stat.st_mtime,
                "size": stat.st_size,
                "hash": file_hash,
            }
        except Exception as e:
            logger.warning(f"Failed to get state for {filepath}: {e}")
            return None
    
    def _calculate_file_hash(self, filepath: str) -> str:
        """
        Calculate SHA256 hash of file content.
        
        Args:
            filepath: Path to file
            
        Returns:
            Hex digest of file hash
        """
        try:
            hasher = hashlib.sha256()
            with open(filepath, 'rb') as f:
                # Read in chunks to handle large files
                for chunk in iter(lambda: f.read(8192), b''):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logger.warning(f"Failed to hash {filepath}: {e}")
            # Return a fallback based on mtime/size
            stat = os.stat(filepath)
            fallback = f"{stat.st_mtime}-{stat.st_size}"
            return hashlib.sha256(fallback.encode()).hexdigest()
    
    def _has_changed(self, old_state: Dict[str, Any], new_state: Dict[str, Any]) -> bool:
        """
        Check if file has changed by comparing states.
        
        Args:
            old_state: Previous file state
            new_state: Current file state
            
        Returns:
            True if file has changed
        """
        # Compare mtime and size first (fast)
        if old_state["mtime"] != new_state["mtime"]:
            return True
        if old_state["size"] != new_state["size"]:
            return True
        
        # If mtime/size match, compare hashes (slower but accurate)
        return old_state["hash"] != new_state["hash"]
    
    def _debounce_file(self, filepath: str) -> bool:
        """
        Debounce file changes to avoid partial writes.
        
        Waits until file size is stable before returning True.
        
        Args:
            filepath: Path to file
            
        Returns:
            True if file is stable, False if still being written
        """
        try:
            # Get initial size
            initial_size = os.path.getsize(filepath)
            
            # Wait debounce period (interruptible by shutdown)
            self._shutdown_event.wait(self.DEBOUNCE_WAIT_SECONDS)
            
            # Check if shutdown was requested during wait
            if self._shutdown_event.is_set():
                return False
            
            # Check if file still exists
            if not os.path.isfile(filepath):
                return False
            
            # Get final size
            final_size = os.path.getsize(filepath)
            
            # Return True only if size is stable
            is_stable = initial_size == final_size
            if not is_stable:
                logger.debug(
                    f"File {filepath} still being written "
                    f"(size changed: {initial_size} -> {final_size})"
                )
            
            return is_stable
            
        except Exception as e:
            logger.warning(f"Debounce check failed for {filepath}: {e}")
            return False
    
    def _queue_file(self, filepath: str, event: str):
        """
        Queue a file for processing via task queue.
        
        Args:
            filepath: Path to file
            event: Event type ("new" or "modified")
        """
        try:
            task_id = self.task_queue.submit(
                task_type=self.TASK_LOCAL_INGEST,
                params={
                    "file_path": filepath,
                    "event": event,
                },
                priority=0,
            )
            logger.info(
                f"Queued file for processing: {filepath} "
                f"(event={event}, task_id={task_id})"
            )
        except Exception as e:
            logger.error(
                f"Failed to queue file {filepath}: {e}",
                exc_info=True
            )
