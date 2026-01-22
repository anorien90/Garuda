import logging
from datetime import datetime
from .extractor import ContentExtractor



class RecorderIngestor:
    """Consumes marked pages/elements/images and stores them with context, extraction, session tie-in, dedup."""
    def __init__(self, store):
        self.store = store
        self.logger = logging.getLogger(__name__)
        self.extractor = ContentExtractor()
        self.last_marks = {}  # (url, mode, selector) => ts

    def is_duplicate(self, url, mode, selector, within_secs=30):
        # Don't record if last identical mark within N seconds (avoid spam/repeats)
        key = (url, mode, selector or "")
        now = datetime.now().timestamp()
        mark_ts = self.last_marks.get(key, 0)
        if now - mark_ts < within_secs:
            return True
        self.last_marks[key] = now
        return False

    def ingest_marked_page(self, data):
        mode = data.get("mode")  # "page", "element", "image"
        url = data.get("url")
        html = data.get("html", "")
        raw_ts = data.get("ts")
        ts = datetime.fromtimestamp(raw_ts) if raw_ts else datetime.now()
        selector = data.get("selector")
        element_html = data.get("element_html", "")
        selected = data.get("selected_text", "")
        session_id = data.get("session_id", None)
        client_id = data.get("client_id", None)

        # Deduplication
        if self.is_duplicate(url, mode, selector):
            self.logger.info(f"Skipped duplicate mark ({mode}) for {url} [{selector}]")
            return False

        if mode == "image":
            page_type = "manual_mark_image"
            text_content = f"Image Alt/Source: {selected}"
            content_to_store = element_html
        else:
            page_type = f"manual_mark_{mode}"
            text_content = self.extractor.html_to_text(html if mode == "page" else element_html)
            content_to_store = html if mode == "page" else element_html

        metadata = self.extractor.extract_metadata(content_to_store)

        page_record = {
            "url": url,
            "entity_type": "manual",
            "domain_key": "",
            "depth": 0,
            "score": 150,
            "page_type": page_type,
            "metadata": metadata,
            "text_content": text_content,
            "text_length": len(text_content),
            "html": content_to_store,
            "last_status": "user_marked",
            "last_fetch_at": ts,
            "session_id": session_id or client_id,
            "selector": selector,
        }
        try:
            self.store.save_page(page_record)
            if selector:
                from .models.page_fingerprint import PageFingerprint
                fp = PageFingerprint(
                    page_url=url,
                    selector=selector,
                    purpose=f"manual_{mode}_selection",
                    sample_text=selected[:200]
                )
                self.store.save_fingerprint(fp)
            self.logger.info(f"Successfully recorded {mode} from {url} [session: {session_id}]")
            return True
        except Exception as e:
            self.logger.error(f"Failed to ingest manual mark: {e}")
            return False
