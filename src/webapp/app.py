from flask import Flask, request, jsonify, render_template
from ..database.engine import SQLAlchemyStore
from ..vector.engine import QdrantVectorStore
from ..extractor.llm import LLMIntelExtractor

app = Flask(__name__, template_folder="templates", static_folder="static")
store = SQLAlchemyStore("sqlite:///crawler.db")

@app.get("/")
def home():
    return render_template("index.html")

@app.get("/api/intel")
def api_intel():
    q = request.args.get("q", "")
    entity = request.args.get("entity")
    min_conf = float(request.args.get("min_conf", 0))
    limit = int(request.args.get("limit", 50))
    rows = store.search_intelligence_data(q) if q else store.get_intelligence(entity_name=entity, min_confidence=min_conf, limit=limit)
    return jsonify(rows)

@app.get("/api/pages")
def api_pages():
    return jsonify(store.get_all_pages())

@app.get("/api/page")
def api_page():
    url = request.args.get("url")
    if not url: return jsonify({"error": "url required"}), 400
    return jsonify({
        "url": url,
        "content": store.get_page_content(url),
        "page": store.get_page(url),
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
