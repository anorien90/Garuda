# Ollama Exoscale Proxy

A standalone Docker container that acts as a local Ollama instance but proxies all requests to a remote Ollama instance running on Exoscale cloud infrastructure.

## Features

- **Local Ollama API**: Exposes port 11434 and implements the full Ollama HTTP API
- **Remote Execution**: Under the hood, manages a remote Ollama instance on Exoscale
- **Auto-scaling**: Automatically starts the Exoscale instance when requests come in
- **Idle Shutdown**: Stops the remote instance after a configurable period of inactivity to save costs
- **python-exoscale SDK**: Uses the official Exoscale Python library for better compatibility
- **Full API Support**: Supports all Ollama endpoints including streaming responses

## Quick Start

### Using Docker Compose (Recommended)

The easiest way to use the Ollama Exoscale proxy is through the main Garuda docker-compose.yml with the `exoscale` profile:

```bash
# Set your Exoscale credentials
export EXOSCALE_API_KEY="your_api_key"
export EXOSCALE_API_SECRET="your_api_secret"

# Start with exoscale profile
docker-compose --profile exoscale up -d ollama-exoscale

# Use it with Garuda (point GARUDA_OLLAMA_URL to the proxy)
export GARUDA_OLLAMA_URL="http://garuda-ollama-exoscale:11434/api/generate"
docker-compose up garuda
```

### Standalone Docker

```bash
# Build the image
cd ollama-exoscale
docker build -t ollama-exoscale .

# Run the container
docker run -d \
  -p 11434:11434 \
  -e EXOSCALE_API_KEY="your_api_key" \
  -e EXOSCALE_API_SECRET="your_api_secret" \
  -e EXOSCALE_ZONE="at-vie-2" \
  -e EXOSCALE_INSTANCE_TYPE="a5000.small" \
  -e OLLAMA_MODEL="granite3.1-dense:8b" \
  -e EXOSCALE_IDLE_TIMEOUT="1800" \
  --name ollama-exoscale \
  ollama-exoscale
```

## Configuration

All configuration is done via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `EXOSCALE_API_KEY` | Exoscale API key (required) | - |
| `EXOSCALE_API_SECRET` | Exoscale API secret (required) | - |
| `EXOSCALE_ZONE` | Exoscale zone (e.g., `at-vie-2`, `ch-gva-2`) | `at-vie-2` |
| `EXOSCALE_INSTANCE_TYPE` | Instance type (e.g., `a5000.small`, `standard.medium`) | `a5000.small` |
| `EXOSCALE_TEMPLATE` | OS template name | `Linux Ubuntu 22.04 LTS 64-bit` |
| `EXOSCALE_DISK_SIZE` | Root disk size in GB | `50` |
| `EXOSCALE_IDLE_TIMEOUT` | Seconds of inactivity before auto-stop | `1800` (30 min) |
| `OLLAMA_MODEL` | Ollama model to pull on startup | `granite3.1-dense:8b` |

## API Endpoints

The proxy implements all Ollama API endpoints:

### Generation
- `POST /api/generate` - Generate completion (supports streaming)
- `POST /api/chat` - Chat completion (supports streaming)

### Embeddings
- `POST /api/embeddings` - Generate embeddings
- `POST /api/embed` - Generate embeddings (new format)

### Model Management
- `GET /api/tags` - List models
- `POST /api/show` - Show model info
- `POST /api/pull` - Pull a model (streaming)
- `POST /api/push` - Push a model (streaming)
- `POST /api/create` - Create a model from Modelfile (streaming)
- `DELETE /api/delete` - Delete a model
- `POST /api/copy` - Copy a model
- `GET /api/ps` - List running models

### System
- `GET /api/version` - Get Ollama version
- `GET /` - Health check
- `HEAD /` - Health check
- `GET /status` - Exoscale instance status (custom endpoint)

## How It Works

1. **Startup**: The container starts and initializes the Exoscale adapter
2. **First Request**: When the first API request arrives:
   - The adapter checks for an existing Exoscale instance
   - If found and stopped/halted, it starts the instance
   - If not found, it creates a new instance with cloud-init script
   - The cloud-init script installs Docker and runs the Ollama container
3. **Request Proxying**: All requests are transparently forwarded to the remote Ollama instance
4. **Activity Tracking**: Each request records activity for idle monitoring
5. **Idle Shutdown**: After `EXOSCALE_IDLE_TIMEOUT` seconds of inactivity, the remote instance is stopped (not destroyed) to preserve quota

## Monitoring

Check the status of the remote instance:

```bash
curl http://localhost:11434/status
```

Response example:
```json
{
  "service": "ollama-exoscale",
  "instance_status": "running",
  "remote_url": "http://185.19.30.45:11434",
  "zone": "at-vie-2",
  "instance_type": "a5000.small",
  "ollama_model": "granite3.1-dense:8b",
  "idle_timeout": 1800
}
```

## Cost Optimization

The proxy is designed to minimize cloud costs:

- **Idle Shutdown**: Automatically stops (halts) the instance after inactivity, preserving it for quick restart
- **On-Demand Creation**: Only creates instances when needed
- **Instance Reuse**: Finds and reuses existing stopped/halted instances before creating new ones
- **Quota Preservation**: Instances are stopped instead of destroyed to avoid quota limitations on instance creation

With default settings (30 minute idle timeout), you only pay for the time the instance is actually processing requests plus the idle period.

## Security

- The remote instance is protected by an Exoscale security group that allows inbound traffic only on port 11434
- The instance is created in your Exoscale account, not shared with others
- All traffic between the proxy and remote instance is over HTTP (use VPN or configure HTTPS for production)

## Troubleshooting

### Container won't start

Check that you've set the required environment variables:
```bash
docker logs ollama-exoscale
```

### Instance takes too long to start

The first startup takes 1-2 minutes for cloud-init to complete:
- Installing Docker
- Pulling the Ollama container
- Pulling the configured model

Subsequent starts are faster (30-60 seconds) as the instance is stopped (not destroyed) when idle.

### Requests timeout

Check the instance status:
```bash
curl http://localhost:11434/status
```

If the instance is `stopped`, it will be started automatically on the next request.

## Development

### Running Tests

```bash
# Install dependencies
pip install -r requirements.txt
pip install pytest pytest-mock

# Run tests
cd /path/to/Garuda
python -m pytest tests/test_ollama_exoscale.py -v
```

### Local Development

```bash
# Install dependencies
cd ollama-exoscale
pip install -r requirements.txt

# Set environment variables
export EXOSCALE_API_KEY="your_key"
export EXOSCALE_API_SECRET="your_secret"

# Run with Flask dev server
python app.py

# Or run with Gunicorn (production)
gunicorn --bind 0.0.0.0:11434 --workers 2 --timeout 600 app:app
```

## Architecture

```
┌─────────────────┐
│  Client/Garuda  │
└────────┬────────┘
         │ HTTP requests to localhost:11434
         ▼
┌─────────────────────────────────────┐
│  Ollama Exoscale Proxy (Container)  │
│  ┌──────────────────────────────┐   │
│  │  Flask App (app.py)          │   │
│  │  - Ollama API endpoints      │   │
│  │  - Request proxying          │   │
│  └──────────┬───────────────────┘   │
│             │                        │
│  ┌──────────▼───────────────────┐   │
│  │  Exoscale Adapter            │   │
│  │  - Instance lifecycle        │   │
│  │  - Idle monitoring           │   │
│  │  - python-exoscale SDK       │   │
│  └──────────┬───────────────────┘   │
└─────────────┼───────────────────────┘
              │ Exoscale API
              ▼
┌─────────────────────────────────────┐
│  Exoscale Cloud                     │
│  ┌───────────────────────────────┐  │
│  │  Compute Instance             │  │
│  │  ┌─────────────────────────┐  │  │
│  │  │ Docker Container        │  │  │
│  │  │ - ollama/ollama:latest  │  │  │
│  │  │ - Port 11434            │  │  │
│  │  └─────────────────────────┘  │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

## Differences from Embedded Exoscale Adapter

The original Garuda had an embedded Exoscale adapter in `src/garuda_intel/exoscale/adapter.py` that:
- Used raw HTTP requests with HMAC authentication
- Was initialized directly in the Garuda webapp
- Included nginx reverse proxy with API key authentication

This standalone component:
- Uses the official `python-exoscale` SDK
- Runs as a separate Docker container
- Exposes the Ollama API directly (no nginx proxy layer)
- Can be used by any application, not just Garuda

The embedded adapter is still available for use with the `garuda-exoscale` CLI tool.

## License

Same as the main Garuda project.
