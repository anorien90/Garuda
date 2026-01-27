"""Garuda Intel Webapp - Main Application Entry Point."""

from flask import Flask, request, jsonify
from flask_cors import CORS
from functools import wraps
import logging

from ..database.engine import SQLAlchemyStore
from ..database.relationship_manager import RelationshipManager
from ..vector.engine import QdrantVectorStore
from ..extractor.llm import LLMIntelExtractor
from ..config import Settings
from ..discover.crawl_modes import EntityAwareCrawler
from ..discover.crawl_learner import CrawlLearner
from ..services.entity_gap_analyzer import EntityGapAnalyzer
from ..services.adaptive_crawler import AdaptiveCrawlerService
from .services.event_system import init_event_logging

# Import route blueprints
from .routes import static, recorder, search, crawling, entities, relationships


settings = Settings.from_env()

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app, resources={r"/api/*": {"origins": settings.cors_origins}})

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

print(f"Starting Garuda Intel Webapp with DB: {settings.db_url}")
print(f"Qdrant Vector Store: {settings.qdrant_url} Collection: {settings.qdrant_collection}")
print(f"Ollama LLM: {settings.ollama_url} Model: {settings.ollama_model}")
print(f"Embedding Model: {settings.embedding_model}")

# Initialize core components
store = SQLAlchemyStore(settings.db_url)
llm = LLMIntelExtractor(
    ollama_url=settings.ollama_url,
    model=settings.ollama_model,
    embedding_model=settings.embedding_model,
)

vector_store = None
if settings.vector_enabled:
    try:
        vector_store = QdrantVectorStore(
            url=settings.qdrant_url, collection=settings.qdrant_collection
        )
    except Exception as e:
        logger.warning(f"Qdrant unavailable: {e}")
        vector_store = None

# Initialize new components for enhanced features
relationship_manager = RelationshipManager(store, llm)
entity_crawler = EntityAwareCrawler(store, llm)
crawl_learner = CrawlLearner(store)
gap_analyzer = EntityGapAnalyzer(store)
adaptive_crawler = AdaptiveCrawlerService(store, llm, crawl_learner)

# Initialize event logging
init_event_logging()


# Auth helper
def api_key_required(fn):
    """Decorator to require API key for protected endpoints."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not settings.api_key:
            return fn(*args, **kwargs)
        key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if key != settings.api_key:
            return jsonify({"error": "unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper


# Register blueprints
app.register_blueprint(
    static.init_routes(api_key_required, settings, store, llm, vector_store)
)

app.register_blueprint(
    recorder.init_routes(api_key_required, store)
)

app.register_blueprint(
    search.init_routes(api_key_required, settings, store, llm, vector_store)
)

app.register_blueprint(
    crawling.init_routes(
        api_key_required, settings, store, llm, 
        entity_crawler, crawl_learner, gap_analyzer, adaptive_crawler
    )
)

app.register_blueprint(
    entities.init_routes(
        api_key_required, settings, store, llm, vector_store,
        entity_crawler, gap_analyzer, adaptive_crawler
    )
)

app.register_blueprint(
    relationships.init_routes(api_key_required, relationship_manager)
)


def main():
    """Run the Flask application."""
    app.run(host="0.0.0.0", port=8080, debug=settings.debug)


if __name__ == "__main__":
    main()
