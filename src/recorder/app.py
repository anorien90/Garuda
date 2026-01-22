import logging
import os
import queue
from flask import Flask, request, jsonify, abort
from flask_cors import CORS
from functools import wraps
from .recorder_ingest import RecorderIngestor
from .persistence.sqlalchemy_store import SQLAlchemyStore

app = Flask(__name__)


# Load config
API_KEY = os.environ.get("MARK_SERVER_API_KEY", "changeme")
LISTEN_ADDR = os.environ.get("MARK_SERVER_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("MARK_SERVER_PORT", 8765))
DB_PATH = os.environ.get("MARK_SERVER_DB", "sqlite:///crawler.db")
CORS(app, resources={r"/mark_page": {"origins": "*"}, r"/search*": {"origins": "*"}, r"/view*": {"origins": "*"}})
logger = logging.getLogger("mark_server")
logger.setLevel(logging.INFO)
received_pages = queue.Queue()

store = SQLAlchemyStore(DB_PATH)
ingestor = RecorderIngestor(store)

def api_key_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        key = request.headers.get('X-API-Key')
        print(f"Received API Key: {key}")
        if not key or key != API_KEY:
            abort(401)
        return f(*args, **kwargs)
    return decorated

@app.route('/mark_page', methods=['POST', 'OPTIONS'])
@api_key_required
def mark_page():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    data = request.get_json()
    client_addr = request.remote_addr
    mode = data.get('mode', 'unknown')
    session_id = data.get('session_id', 'unknown')
    url = (data.get('url', '') or '')[:80]
    logger.info(f"[mark_server] ({session_id}) {client_addr} → Received {mode} mark event for {url}")
    received_pages.put(data)
    ingestor.ingest_marked_page(data)
    return jsonify({"status": "received"})

@app.route('/queue_info', methods=['GET'])
def queue_info():
    return jsonify({"length": received_pages.qsize(), "status": "ok"})

@app.route('/healthz', methods=['GET'])
def healthz():
    return jsonify({"status": "ok", "queue_len": received_pages.qsize()})

@app.route('/shutdown', methods=['POST'])
@api_key_required
def shutdown():
    func = request.environ.get('werkzeug.server.shutdown')
    if func:
        func()
        logger.info("Flask server shutdown triggered via /shutdown")
        return jsonify({"status": "shutting down"}), 200
    else:
        return jsonify({"status": "shutdown unavailable"}), 500

# --- NEW: INTEL SEARCH API
@app.route('/search', methods=['GET'])
@api_key_required
def search_intel():
    """?q=keyword[&entity_type][&page_type][&limit]"""
    q = request.args.get("q", "").strip()
    limit = min(int(request.args.get("limit", 20)), 100)
    entity_type = request.args.get("entity_type")
    page_type = request.args.get("page_type")
    if not q:
        return jsonify({"error": "Missing search keyword"}), 400
    results = store.search_intel(q, limit=limit, entity_type=entity_type, page_type=page_type)
    return jsonify({"results": results})

# --- NEW: BASIC VIEW ENDPOINT
@app.route('/view', methods=['GET'])
@api_key_required
def view_page():
    """?url="""
    url = request.args.get("url", "")
    if not url:
        return jsonify({"error": "url required"}), 400
    with store.Session() as session:
        pc = session.get(store.PageContent, url)
        pg = session.get(store.Page, url)
        return jsonify({
            "url": url,
            "metadata": pc.metadata_json if pc else None,
            "html": pc.html if pc else None,
            "text": pc.text if pc else None,
            "page_info": pg.to_dict() if pg else None,
        })

def run_server():
    print(f"Starting mark_server on {LISTEN_ADDR}:{LISTEN_PORT} (API_KEY required)")
    app.run(host=LISTEN_ADDR, port=LISTEN_PORT, debug=False, use_reloader=False)

def start_server_thread():
    import threading
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    return received_pages

if __name__ == "__main__":
    run_server()
