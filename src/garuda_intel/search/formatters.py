"""Formatting and output functions for search results."""

import json
from datetime import datetime


def list_pages(store):
    try:
        pages = store.get_all_pages()
        def serial(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError("Type not serializable")
        data = [p.to_dict() for p in pages]
        print(json.dumps(data, default=serial, indent=2))
    except AttributeError as e:
        print(f"Error: The store implementation is missing a method: {e}")


def fetch_text(store, url: str):
    pc = store.get_page_content_by_url(url)
    if pc and pc.get("text"):
        print(pc["text"])
        return True
    return False
