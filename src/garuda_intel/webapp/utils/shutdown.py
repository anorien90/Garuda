"""Graceful shutdown manager for Flask application."""

import logging
import threading


class ShutdownManager:
    """Manages graceful shutdown of the application."""
    
    def __init__(self):
        self._shutdown_event = threading.Event()
        self._logger = logging.getLogger(__name__)
    
    def request_shutdown(self):
        """Request graceful shutdown."""
        if not self._shutdown_event.is_set():
            self._logger.info("Shutdown requested - allowing current requests to finish")
            self._shutdown_event.set()
    
    def is_shutting_down(self):
        """Check if shutdown has been requested."""
        return self._shutdown_event.is_set()
