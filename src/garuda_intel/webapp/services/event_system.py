"""Event system for logging and streaming application events."""

import logging
import json
import queue
import threading
from datetime import datetime, timezone
from collections import deque
from typing import Generator


_EVENT_BUFFER_LIMIT = 1000
_event_buffer = deque(maxlen=_EVENT_BUFFER_LIMIT)
_event_listeners: list[queue.Queue] = []
_event_lock = threading.Lock()

logger = logging.getLogger(__name__)


def _now_iso():
    """Get current time in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _publish_event(evt: dict):
    """Push an event to the in-memory buffer and live listeners."""
    with _event_lock:
        _event_buffer.append(evt)
        dead = []
        for q in _event_listeners:
            try:
                q.put_nowait(evt)
            except Exception:
                dead.append(q)
        for q in dead:
            if q in _event_listeners:
                _event_listeners.remove(q)


def emit_event(step: str, message: str, level: str = "info", payload=None, session_id=None):
    """Primary emitter used across the app when logging explicit steps."""
    evt = {
        "ts": _now_iso(),
        "level": level,
        "step": step,
        "message": message,
        "payload": payload or {},
        "session_id": session_id,
    }
    _publish_event(evt)
    logger.log(getattr(logging, level.upper(), logging.INFO), f"[{step}] {message}")


class EventQueueHandler(logging.Handler):
    """Logging handler that mirrors all log records into the UI event stream."""

    def emit(self, record: logging.LogRecord):
        try:
            evt = {
                "ts": _now_iso(),
                "level": record.levelname.lower(),
                "step": getattr(record, "step", record.name),
                "message": self.format(record),
                "payload": getattr(record, "payload", {}) or {},
                "session_id": getattr(record, "session_id", None),
            }
            _publish_event(evt)
        except Exception:
            pass


def init_event_logging():
    """Attach the event queue handler to the root logger so all modules funnel into UI logs."""
    handler = EventQueueHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(message)s"))

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    if root_logger.level > logging.INFO:
        root_logger.setLevel(logging.INFO)

    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def _event_stream() -> Generator:
    """Server-Sent Events stream generator."""
    q: queue.Queue = queue.Queue()
    with _event_lock:
        _event_listeners.append(q)
    try:
        while True:
            evt = q.get()
            yield f"data: {json.dumps(evt)}\n\n"
    except GeneratorExit:
        with _event_lock:
            if q in _event_listeners:
                _event_listeners.remove(q)


def get_event_buffer():
    """Get the current event buffer."""
    return _event_buffer
