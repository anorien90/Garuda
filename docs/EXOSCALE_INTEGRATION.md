# Exoscale Remote Ollama Integration

This module provides seamless integration with Exoscale cloud to run Ollama instances remotely, with automatic lifecycle management, idle shutdown, and secure access.

## Overview

The Exoscale adapter allows Garuda Intel to:
- **Automatically provision** Ollama instances on Exoscale cloud
- **Secure access** via nginx reverse proxy with API key authentication
- **Auto-shutdown** after idle period to save costs
- **Transparent proxying** - works seamlessly with existing code
- **Full lifecycle management** - create, start, stop, destroy instances

## Architecture

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│                 │ HTTPS   │                  │ nginx   │                 │
│ Garuda Intel    ├────────>│ Exoscale         ├────────>│ Ollama          │
│ (Local)         │  API    │ Instance         │ proxy   │ (Docker)        │
│                 │  Key    │ :11435           │ :11434  │                 │
└─────────────────┘         └──────────────────┘         └─────────────────┘
```

### Security

- Exoscale API uses HMAC-SHA256 signed requests
- Security group restricts inbound traffic to port 11435 only
- Nginx reverse proxy validates `X-Ollama-Key` header before forwarding
- Random API key generated automatically if not provided

### Instance Setup (Cloud-Init)

The instance is provisioned with:
1. Docker CE installation
2. Ollama container running on localhost:11434
3. Nginx reverse proxy on 0.0.0.0:11435 with API key validation
4. Configured Ollama model pre-pulled

## Configuration

### Environment Variables

```bash
# Required
EXOSCALE_API_KEY=EXO...                    # Exoscale API key
EXOSCALE_API_SECRET=...                     # Exoscale API secret

# Optional (with defaults)
EXOSCALE_ZONE=ch-gva-2                      # Zone: ch-gva-2, de-fra-1, at-vie-1, etc.
EXOSCALE_INSTANCE_TYPE=standard.medium      # Instance type (or gpu2.medium for GPU)
EXOSCALE_TEMPLATE="Linux Ubuntu 22.04 LTS 64-bit"
EXOSCALE_DISK_SIZE=50                       # Root disk size in GB
EXOSCALE_OLLAMA_KEY=...                     # API key for proxy (auto-generated if not set)
EXOSCALE_IDLE_TIMEOUT=1800                  # Idle timeout in seconds (30 min)
```

### Instance Types

Common instance types:
- `standard.medium` - 2 vCPU, 4 GB RAM (CPU-only, cost-effective)
- `standard.large` - 4 vCPU, 8 GB RAM
- `gpu2.medium` - 2 vCPU, 16 GB RAM, NVIDIA GPU (for larger models)
- `gpu2.large` - 4 vCPU, 32 GB RAM, NVIDIA GPU

### Zones

Available zones:
- `ch-gva-2` - Geneva, Switzerland (default)
- `de-fra-1` - Frankfurt, Germany
- `at-vie-1` - Vienna, Austria
- `de-muc-1` - Munich, Germany
- `bg-sof-1` - Sofia, Bulgaria

## Usage

### Web App Integration

The Exoscale adapter is automatically initialized when you start the Garuda webapp if the API credentials are set:

```bash
export EXOSCALE_API_KEY=EXO...
export EXOSCALE_API_SECRET=...
python -m garuda_intel.webapp.app
```

The webapp will:
1. Initialize the Exoscale adapter
2. Find or create an Ollama instance
3. Start the idle monitor
4. Update `settings.ollama_url` to point to the remote instance
5. Shutdown the instance when the webapp exits

### CLI Tool

The `garuda-exoscale` CLI provides manual control:

```bash
# Show instance status
garuda-exoscale status

# Start or create instance
garuda-exoscale start

# Stop/destroy instance
garuda-exoscale stop

# Show detailed instance information
garuda-exoscale logs
```

### Programmatic Usage

```python
from garuda_intel.exoscale import ExoscaleOllamaAdapter

adapter = ExoscaleOllamaAdapter(
    api_key="EXO...",
    api_secret="...",
    zone="ch-gva-2",
    instance_type="standard.medium",
    ollama_model="granite3.1-dense:8b",
    idle_timeout=1800,
)

# Ensure instance is running
ollama_url = adapter.ensure_instance()
print(f"Ollama URL: {ollama_url}")

# Start idle monitoring
adapter.start_idle_monitor()

# Make requests (adapter records activity)
result = adapter.proxy_request({
    "model": "granite3.1-dense:8b",
    "prompt": "Hello world",
    "stream": False,
})

# Cleanup on exit
adapter.shutdown()
```

## Idle Monitoring & Auto-Shutdown

The adapter includes built-in idle monitoring to save costs:

1. **Activity Tracking**: Every request to Ollama records a timestamp
2. **Background Thread**: Checks idle time every 60 seconds
3. **Auto-Shutdown**: If idle > `idle_timeout`, destroys the instance
4. **Thread-Safe**: Uses locks for concurrent request handling

To disable auto-shutdown, set a very high timeout:
```bash
export EXOSCALE_IDLE_TIMEOUT=86400  # 24 hours
```

## Docker Integration

The Exoscale environment variables are included in `docker-compose.yml`:

```yaml
environment:
  - EXOSCALE_API_KEY=${EXOSCALE_API_KEY:-}
  - EXOSCALE_API_SECRET=${EXOSCALE_API_SECRET:-}
  - EXOSCALE_ZONE=${EXOSCALE_ZONE:-ch-gva-2}
  - EXOSCALE_INSTANCE_TYPE=${EXOSCALE_INSTANCE_TYPE:-standard.medium}
  - EXOSCALE_IDLE_TIMEOUT=${EXOSCALE_IDLE_TIMEOUT:-1800}
```

Create a `.env` file with your credentials:

```bash
EXOSCALE_API_KEY=EXO...
EXOSCALE_API_SECRET=...
```

Then start with Docker Compose:

```bash
docker-compose up -d
```

## Cost Optimization

Tips for minimizing costs:

1. **Use CPU instances** for smaller models (standard.medium)
2. **Shorter idle timeout** for development (e.g., 600 = 10 min)
3. **Longer idle timeout** for production (e.g., 3600 = 1 hour)
4. **Manual shutdown** when not in use via CLI
5. **Monitor usage** through Exoscale console

Approximate costs (as of 2024):
- standard.medium: ~$0.05/hour
- gpu2.medium: ~$0.70/hour

## Troubleshooting

### Instance fails to start

Check logs:
```bash
garuda-exoscale logs
```

Common issues:
- Template not available in zone (check available templates in Exoscale console)
- Instance type not available (try standard.medium)
- Security group creation failed (check permissions)

### Connection refused

The cloud-init script takes ~60 seconds to complete. The adapter waits, but if you connect manually, allow time for setup.

Check instance is running:
```bash
garuda-exoscale status
```

### API authentication errors

Ensure credentials are correct:
```bash
# Test with CLI
EXOSCALE_API_KEY=EXO... EXOSCALE_API_SECRET=... garuda-exoscale status
```

### Model not available

The default model is `granite3.1-dense:8b`. For other models:
```bash
export GARUDA_OLLAMA_MODEL=llama2:7b
```

## API Reference

### ExoscaleOllamaAdapter

#### Constructor

```python
ExoscaleOllamaAdapter(
    api_key: str,
    api_secret: str,
    zone: str = "ch-gva-2",
    instance_type: str = "standard.medium",
    template_name: str = "Linux Ubuntu 22.04 LTS 64-bit",
    disk_size: int = 50,
    ollama_model: str = "granite3.1-dense:8b",
    ollama_key: Optional[str] = None,
    idle_timeout: int = 1800,
)
```

#### Methods

- `ensure_instance() -> Optional[str]` - Ensure instance is running, return Ollama URL
- `create_instance() -> Optional[str]` - Create new instance, return Ollama URL
- `destroy_instance() -> bool` - Destroy instance
- `get_instance_status() -> Optional[str]` - Get instance state
- `get_ollama_url() -> Optional[str]` - Get Ollama API URL
- `record_activity()` - Record activity timestamp
- `start_idle_monitor()` - Start idle monitoring thread
- `stop_idle_monitor()` - Stop idle monitoring thread
- `proxy_request(payload: Dict) -> Optional[Dict]` - Proxy request to Ollama
- `shutdown()` - Cleanup and destroy instance

## Security Considerations

1. **API Credentials**: Store in environment variables or secure vault, never commit to git
2. **Ollama API Key**: Auto-generated and stored in adapter instance
3. **Security Group**: Restricts inbound to port 11435 only
4. **HTTPS**: Exoscale API uses HTTPS with HMAC-SHA256 signatures
5. **Network Exposure**: Instance has public IP - ensure strong API key

## Limitations

- Exoscale API v2 only (not compatible with v1)
- Linux templates only (Ubuntu 22.04 tested)
- No support for instance scaling (single instance per adapter)
- Cloud-init errors not visible in adapter (check Exoscale console)

## Contributing

To extend the adapter:

1. **Add instance features**: Modify cloud-init script in `_generate_cloud_init()`
2. **Support more clouds**: Create similar adapters for AWS, GCP, Azure
3. **Enhanced monitoring**: Add CloudWatch/metrics integration
4. **Instance pools**: Support multiple instances with load balancing

## License

Same as Garuda Intel project (GPL v3+).
