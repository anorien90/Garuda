"""Ollama Exoscale Proxy - Flask application that proxies Ollama API to Exoscale.

This Flask application implements the full Ollama HTTP API and transparently
proxies all requests to a remote Ollama instance running on Exoscale cloud.

Features:
- Exposes all Ollama API endpoints
- Automatically starts/stops Exoscale instance on demand
- Supports streaming responses for chat and generate endpoints
- Records activity for idle monitoring
- Provides status endpoint for monitoring
"""

import atexit
import logging
import signal
import sys
from typing import Iterator, Optional

import requests
from flask import Flask, Response, jsonify, request, stream_with_context

from exoscale_adapter import ExoscaleOllamaAdapter, ExoscaleAuthError


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Initialize Exoscale adapter
adapter: Optional[ExoscaleOllamaAdapter] = None

try:
    logger.info("Initializing Exoscale Ollama adapter")
    adapter = ExoscaleOllamaAdapter()
    logger.info("✓ Exoscale adapter initialized")
except ExoscaleAuthError as e:
    logger.error(f"✗ Failed to initialize Exoscale adapter: {e}")
    logger.error("Please set EXOSCALE_API_KEY and EXOSCALE_API_SECRET environment variables")
    sys.exit(1)
except Exception as e:
    logger.error(f"✗ Unexpected error initializing Exoscale adapter: {e}")
    sys.exit(1)


def ensure_remote_instance() -> Optional[str]:
    """Ensure remote Ollama instance is running and return base URL.
    
    Returns:
        Base URL (http://ip:port) or None on error
    """
    if not adapter:
        logger.error("Adapter not initialized")
        return None
    
    return adapter.ensure_instance()


def proxy_request(
    endpoint: str,
    method: str = "GET",
    json_data: Optional[dict] = None,
    stream: bool = False
):
    """Proxy a request to the remote Ollama instance.
    
    Args:
        endpoint: API endpoint path (e.g., '/api/generate')
        method: HTTP method (GET, POST, DELETE)
        json_data: JSON request body for POST requests
        stream: Whether to stream the response
        
    Returns:
        Flask Response object or tuple (json, status_code)
    """
    # Record activity
    if adapter:
        adapter.record_activity()
    
    # Ensure instance is running
    base_url = ensure_remote_instance()
    if not base_url:
        return jsonify({"error": "Failed to start remote Ollama instance"}), 503
    
    # Build full URL
    url = f"{base_url}{endpoint}"
    
    try:
        if method == "GET":
            resp = requests.get(url, timeout=300, stream=stream)
        elif method == "POST":
            resp = requests.post(url, json=json_data, timeout=300, stream=stream)
        elif method == "DELETE":
            resp = requests.delete(url, json=json_data, timeout=300)
        else:
            return jsonify({"error": f"Unsupported method: {method}"}), 400
        
        # Handle streaming responses
        if stream and resp.ok:
            def generate() -> Iterator[bytes]:
                """Stream response chunks."""
                try:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            yield chunk
                except Exception as e:
                    logger.error(f"Error streaming response: {e}")
            
            return Response(
                stream_with_context(generate()),
                status=resp.status_code,
                headers=dict(resp.headers),
                content_type=resp.headers.get('Content-Type', 'application/json')
            )
        
        # Handle non-streaming responses
        if resp.ok:
            # Return JSON if content type is JSON
            content_type = resp.headers.get('Content-Type', '')
            if 'application/json' in content_type:
                return jsonify(resp.json()), resp.status_code
            else:
                return Response(resp.content, status=resp.status_code, headers=dict(resp.headers))
        else:
            return jsonify({"error": resp.text}), resp.status_code
    
    except requests.exceptions.Timeout:
        return jsonify({"error": "Request to remote Ollama timed out"}), 504
    except requests.exceptions.RequestException as e:
        logger.error(f"Proxy request failed: {e}")
        return jsonify({"error": f"Proxy request failed: {str(e)}"}), 502


# Health check endpoints
@app.route("/", methods=["GET", "HEAD"])
def health_check():
    """Health check endpoint - mimics Ollama's root endpoint."""
    if request.method == "HEAD":
        return Response(status=200)
    return "Ollama is running"


@app.route("/status", methods=["GET"])
def status():
    """Status endpoint showing Exoscale instance information."""
    if not adapter:
        return jsonify({"error": "Adapter not initialized"}), 503
    
    status_info = {
        "service": "ollama-exoscale",
        "instance_status": adapter.get_instance_status(),
        "remote_url": adapter.get_remote_url(),
        "zone": adapter.zone_name,
        "instance_type": adapter.instance_type,
        "ollama_model": adapter.ollama_model,
        "idle_timeout": adapter.idle_timeout,
    }
    
    return jsonify(status_info)


# Ollama API endpoints - Generation
@app.route("/api/generate", methods=["POST"])
def generate():
    """Generate completion endpoint - supports streaming."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    
    # Check if streaming is requested
    is_stream = data.get("stream", False)
    
    return proxy_request("/api/generate", method="POST", json_data=data, stream=is_stream)


@app.route("/api/chat", methods=["POST"])
def chat():
    """Chat completion endpoint - supports streaming."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    
    # Check if streaming is requested
    is_stream = data.get("stream", False)
    
    return proxy_request("/api/chat", method="POST", json_data=data, stream=is_stream)


# Ollama API endpoints - Embeddings
@app.route("/api/embeddings", methods=["POST"])
def embeddings():
    """Generate embeddings endpoint."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    
    return proxy_request("/api/embeddings", method="POST", json_data=data)


@app.route("/api/embed", methods=["POST"])
def embed():
    """Generate embeddings endpoint (new format)."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    
    return proxy_request("/api/embed", method="POST", json_data=data)


# Ollama API endpoints - Model management
@app.route("/api/tags", methods=["GET"])
def list_models():
    """List available models."""
    return proxy_request("/api/tags", method="GET")


@app.route("/api/show", methods=["POST"])
def show_model():
    """Show model information."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    
    return proxy_request("/api/show", method="POST", json_data=data)


@app.route("/api/pull", methods=["POST"])
def pull_model():
    """Pull a model - supports streaming."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    
    # Model pulling typically streams progress
    is_stream = data.get("stream", True)
    
    return proxy_request("/api/pull", method="POST", json_data=data, stream=is_stream)


@app.route("/api/push", methods=["POST"])
def push_model():
    """Push a model - supports streaming."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    
    # Model pushing typically streams progress
    is_stream = data.get("stream", True)
    
    return proxy_request("/api/push", method="POST", json_data=data, stream=is_stream)


@app.route("/api/create", methods=["POST"])
def create_model():
    """Create a model from Modelfile."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    
    # Model creation typically streams progress
    is_stream = data.get("stream", True)
    
    return proxy_request("/api/create", method="POST", json_data=data, stream=is_stream)


@app.route("/api/delete", methods=["DELETE"])
def delete_model():
    """Delete a model."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    
    return proxy_request("/api/delete", method="DELETE", json_data=data)


@app.route("/api/copy", methods=["POST"])
def copy_model():
    """Copy a model."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    
    return proxy_request("/api/copy", method="POST", json_data=data)


@app.route("/api/ps", methods=["GET"])
def list_running():
    """List running models."""
    return proxy_request("/api/ps", method="GET")


@app.route("/api/version", methods=["GET"])
def version():
    """Get Ollama version."""
    return proxy_request("/api/version", method="GET")


# Shutdown handling
def shutdown_handler(signum=None, frame=None):
    """Handle graceful shutdown.
    
    Args:
        signum: Signal number (for signal handlers)
        frame: Current stack frame (for signal handlers)
    """
    logger.info("Received shutdown signal, cleaning up...")
    if adapter:
        adapter.shutdown()
    logger.info("Shutdown complete")


def _atexit_shutdown():
    """Atexit handler for cleanup."""
    logger.info("Atexit cleanup...")
    if adapter:
        adapter.shutdown()


# Register shutdown handlers
signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)
atexit.register(_atexit_shutdown)


if __name__ == "__main__":
    # Start idle monitor
    if adapter:
        adapter.start_idle_monitor()
    
    logger.info("Starting Ollama Exoscale proxy server on port 11434")
    app.run(host="0.0.0.0", port=11434, debug=False)
