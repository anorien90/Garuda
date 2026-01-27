"""Active browser recording mode."""

import sys
import time
import queue
import logging
from ..recorder.app import start_server_thread
from ..recorder.ingest import RecorderIngestor
from ..browser.active import RecordingBrowser, get_env_chrome_args, get_browser_start_url, get_session_id

logger = logging.getLogger(__name__)


def print_active_mode_instructions(session_id):
    msg = f"""
    ===============================================
    🟢 ACTIVE MODE (session: {session_id})
    -----------------------------------------------
    1. A Chrome browser window will open.
    2. Use the floating "Mark Recorder" panel to:
        - [Mark Page]: Save a snapshot of current page
            (shortcut: Shift+P)
        - [Element Select]: Click any text/element to save
            (shortcut: Shift+E)
        - [Image Select]: Click an image to save
            (shortcut: Shift+I)
        - You can drag the panel with its header.

    3. Status messages and session-id shown at bottom.
    4. All marks are saved into your database: inspection, search, and extractions are possible!

    [Tips]
    - Start URL for browser can be set via .env BROWSER_START_URL
    - To enable more Chrome features, set BROWSER_EXTRA_CHROME_ARGS in .env

    To exit: close the browser window or press [CTRL+C] in this terminal.
    ===============================================
    """
    print(msg)


def run_active_session(store):
    mark_queue = start_server_thread()
    ingestor = RecorderIngestor(store)
    session_id = get_session_id()
    print_active_mode_instructions(session_id)
    print(">> Launching Browser. Close the window to finish.")
    extra_chrome_args = get_env_chrome_args()
    start_url = get_browser_start_url()
    with RecordingBrowser(start_url=start_url, extra_chrome_args=extra_chrome_args, session_id=session_id) as browser:
        time.sleep(2)
        try:
            while browser.is_alive():
                try:
                    data = mark_queue.get(timeout=0.5)
                    if "session_id" not in data:
                        data["session_id"] = session_id
                    ingestor.ingest_marked_page(data)
                    logger.info(f">> Persisted: {data.get('url', '')[:50]}...")
                except queue.Empty:
                    continue
                except KeyboardInterrupt:
                    break
        finally:
            browser.close()
    print(">> Browser closed. Draining final items...")
    while not mark_queue.empty():
        d = mark_queue.get_nowait()
        if "session_id" not in d:
            d["session_id"] = session_id
        ingestor.ingest_marked_page(d)
    print(">> Session Complete.")
    sys.exit(0)
