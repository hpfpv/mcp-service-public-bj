# Developer Guide

## Architecture Overview

The MCP Service Public BJ server is built with a hybrid architecture that combines live scraping with intelligent caching:

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   MCP Client    │───▶│   MCP Server     │───▶│  Live Fetcher   │
│ (Claude/VS Code)│    │   (Tools API)    │    │   (HTTP + AI)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
                       ┌──────────────────┐    ┌─────────────────┐
                       │ Registry Cache   │    │ service-public  │
                       │ (JSON Storage)   │    │      .bj        │
                       └──────────────────┘    └─────────────────┘
```

### Core Components

#### 1. MCP Server (`src/server/main.py`)
- **Framework**: Built on `mcp>=1.19.0` Python package
- **Transports**: Supports both stdio and HTTP (streamable)
- **Tools**: Exposes 5 main tools via JSON-RPC
- **Concurrency**: Async event loop with configurable limits

#### 2. Provider System (`src/server/providers/`)
- **Base Provider**: Abstract interface for data sources
- **Service Public BJ Provider**: Implements live API scraping
- **Registry Pattern**: Pluggable architecture for multiple sources

#### 3. Live Fetch Engine (`src/server/live_fetch.py`)
- **HTTP Client**: `httpx` with HTTP/2 support
- **Rate Limiting**: Configurable concurrency per provider
- **Caching**: TTL-based with automatic invalidation
- **Error Handling**: Retry logic with exponential backoff

#### 4. Data Models (`src/server/models.py`)
- **Pydantic Models**: Type-safe data structures
- **JSON Serialization**: MCP-compatible output formats
- **Validation**: Input sanitization and error handling

#### 5. Search & Registry (`src/server/search.py`, `registry.py`)
- **In-Memory Index**: Fast fuzzy search with `rapidfuzz`
- **Persistent Storage**: JSON-based registry snapshots
- **Category Management**: Hierarchical service organization

## Technical Stack

### Dependencies
```toml
# Core MCP and async
mcp>=1.19.0
httpx[http2]>=0.26.0
pydantic>=2.6.0

# Web scraping
scrapy>=2.11.1
parsel>=1.9.1

# Performance & reliability
tenacity>=8.2.3
aiocache>=0.12.2
orjson>=3.9.15
rapidfuzz>=3.14.0

# HTTP server
starlette>=0.37.2
uvicorn>=0.27.1
sse-starlette>=1.6.1

# Observability
structlog>=23.2.0
prometheus-client>=0.20.0
```

### Python Requirements
- **Version**: Python 3.10+
- **Type Checking**: Full mypy strict mode
- **Code Style**: Black + Ruff linting
- **Testing**: pytest with asyncio support

## Development Setup

### 1. Environment Setup
```bash
# Clone repository
git clone <repository-url>
cd mcp-service-public-bj

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install development dependencies
make dev-install
# or: pip install -e .[dev]
```

### 2. Configuration
```bash
# Copy environment template
cp .env.example .env

# Edit configuration
vim .env
```

Key environment variables:
- `MCP_SP_BASE_URL`: Target website (default: https://service-public.bj/)
- `MCP_SP_CACHE_DIR`: Registry storage location
- `MCP_SP_CONCURRENCY`: Max concurrent requests (default: 2)
- `MCP_SP_TIMEOUT`: HTTP timeout in seconds (default: 30)
- `MCP_SP_CACHE_TTL`: Cache lifetime in seconds (default: 300)

### 3. Development Commands
```bash
# Code quality
make lint          # Run ruff linter
make format        # Format with black
make mypy          # Type checking

# Testing
make test          # Run pytest suite
pytest tests/test_specific.py -v  # Run specific tests

# Local development
make serve         # Start stdio server
make serve-http    # Start HTTP server
make scrape ARGS="--query test"  # Test scraping
make status        # Check system status
```

## Project Structure

```
mcp-service-public-bj/
├── src/server/                     # Core MCP server
│   ├── providers/                  # Data source adapters
│   ├── main.py                     # Server entrypoint
│   ├── cli.py                      # Command interface
│   ├── tools.py                    # MCP tool handlers
│   └── config.py                   # Settings
├── tests/                          # Test suite
├── docs/                           # Documentation
│   ├── developer-guide.md
│   └── release-guide.md
├── data/registry/                  # Cache storage
├── pyproject.toml                  # Dependencies & config
├── Dockerfile                      # Container build
├── Makefile                        # Dev commands
└── README.md                       # Quick start
```

## API Reference

### MCP Tools

#### `list_categories`
```json
{
  "tool": "list_categories",
  "arguments": {
    "provider_id": "service-public-bj",  // optional
    "parent_id": null,                   // optional
    "refresh": false                     // optional
  }
}
```

#### `search_services`
```json
{
  "tool": "search_services", 
  "arguments": {
    "query": "passeport",               // required
    "category_id": null,                // optional
    "limit": 10,                        // optional
    "offset": 0,                        // optional
    "refresh": false                    // optional
  }
}
```

#### `get_service_details`
```json
{
  "tool": "get_service_details",
  "arguments": {
    "service_id": "PS00328",            // required
    "refresh": false                    // optional
  }
}
```

### HTTP Endpoints (when using serve-http)

- `GET /healthz` - Health check
- `GET /metrics` - Prometheus metrics
- `POST /mcp` - MCP JSON-RPC endpoint
- `GET /mcp` - MCP Server-Sent Events (SSE)

## Testing

### Test Categories

1. **Unit Tests**: Pure Python modules (search index, registry, tools) with isolated logic
2. **Integration Tests**: Provider + live fetch plumbing using mocked HTTP 
3. **Transport End-to-End Tests**: Full stdio and HTTP runtime exercises (`tests/test_stdio_e2e.py`, `tests/test_http_e2e.py`)
4. **Resilience & Chaos Tests**: Network failures, malformed data, cache failover, concurrency stress (`tests/test_resilience.py`)
5. **Performance Benchmarks**: Optional timing assertions behind the `performance` marker
6. **Contract Tests**: MCP protocol compliance and schema validation of tool payloads

### Running Tests
```bash
# All tests
pytest

# With coverage
pytest --cov=src --cov-report=html

# Specific test categories
pytest tests/test_registry.py -v
pytest tests/test_service_public_provider.py -k "test_search"
```

### Test Configuration
```python
# pytest.ini equivalent in pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
addopts = ["--color=yes", "--maxfail=1", "--strict-markers"]
testpaths = ["tests"]
```

## Observability

### Logging
- **Framework**: `structlog` for structured logging
- **Levels**: DEBUG, INFO, WARNING, ERROR
- **Format**: JSON in production, human-readable in development

### Metrics (Prometheus)
Available at `GET /metrics`:

- `mcp_tool_invocations_total{tool, status}` - Tool usage counters
- `mcp_tool_duration_seconds{tool}` - Tool execution time
- `mcp_http_requests_total{method, path, status}` - HTTP request metrics
- `mcp_live_fetch_duration_seconds{provider}` - Scraping performance

### Health Monitoring
```bash
# Check system status
curl http://localhost:8000/healthz

# Get detailed provider status
mcp-service-public-bj status --live
```

## Integration Patterns

### MCP Client Integration

The server supports both **stdio** (single client) and **HTTP** (multi-client) transports, with local Python or Docker deployment options.

#### Claude Desktop

**Local Python (stdio)**
```json
{
  "mcpServers": {
    "service-public-bj-local": {
      "command": "/path/to/.venv/bin/python",
      "args": ["-m", "server.main"]
    }
  }
}
```

**Docker (stdio)**
```json
{
  "mcpServers": {
    "service-public-bj-docker": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "mcp-service-public-bj:latest"
      ]
    }
  }
}
```

#### VS Code MCP Extension

**Local Python (stdio)**
```json
{
  "servers": {
    "service-public-local-stdio": {
      "type": "stdio",
      "command": "/path/to/.venv/bin/python",
      "args": ["-m", "server.main"]
    }
  }
}
```

**Docker (stdio)**
```json
{
  "servers": {
    "service-public-docker-stdio": {
      "type": "stdio",
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "mcp-service-public-bj:latest"
      ]
    }
  }
}
```

**HTTP (shared server)**
```json
{
  "servers": {
    "mcp-service-public-bj-http": {
      "type": "http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

*Note: For HTTP mode, start server separately:*
```bash
# Local
mcp-service-public-bj serve-http --host 0.0.0.0 --port 8000

# Docker
docker run -p 8000:8000 mcp-service-public-bj serve-http --host 0.0.0.0
```

### Transport Comparison

| Transport | Use Case | Pros | Cons |
|-----------|----------|------|------|
| **stdio** | Single client (Claude, VS Code) | Simple setup, no network | One client only |
| **HTTP** | Multiple clients, web apps | Multi-client, REST API | Requires server management |

### Deployment Comparison

| Method | Use Case | Pros | Cons |
|--------|----------|------|------|
| **Local Python** | Development, personal use | Fast startup, easy debugging | Requires Python setup |
| **Docker** | Production, isolation | Consistent environment | Slower startup, image size |

#### Custom HTTP Client
```python
import httpx

async def call_mcp_tool():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "search_services",
                    "arguments": {"query": "passeport"}
                }
            }
        )
        return response.json()
```

### Docker Integration

#### Development
```bash
# Build image
docker build -t mcp-service-public-bj .

# Run with volume for persistence
docker run --rm -i \
  -v $(pwd)/data:/app/data \
  mcp-service-public-bj
```

#### Production
```bash
# HTTP server with custom config
docker run -d \
  --name mcp-service-public-bj \
  -p 8000:8000 \
  -e MCP_SP_CACHE_TTL=600 \
  -e MCP_SP_CONCURRENCY=4 \
  -v /opt/mcp-data:/app/data \
  mcp-service-public-bj:latest \
  serve-http --host 0.0.0.0
```

### TLS deployment (reverse proxy)

The container does not ship with TLS termination. In production, place an HTTPS reverse proxy (nginx, Traefik, Caddy, Kong, etc.) in front of the HTTP transport.

1. **Bind MCP to localhost/internal network** – run `serve-http --host 127.0.0.1 --port 8000` (or use an internal Docker network) so the HTTP port is not exposed publicly.
2. **Terminate TLS at the proxy** – the proxy handles certificates (Let’s Encrypt, internal CA). Forward traffic to the MCP container, preserving the `/mcp`, `/metrics`, and `/healthz` paths.

Example nginx configuration:

```nginx
server {
    listen 443 ssl;
    ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;

    location /mcp/ {
        proxy_pass http://127.0.0.1:8000/mcp/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_buffering off;  # keep SSE streaming responsive
    }

    location /metrics {
        allow 10.0.0.0/8;
        deny all;
        proxy_pass http://127.0.0.1:8000/metrics;
    }

    location /healthz {
        proxy_pass http://127.0.0.1:8000/healthz;
    }
}

server {
    listen 80;
    return 301 https://$host$request_uri;
}
```

If you prefer Kong or Traefik, create a route that forwards `/mcp` traffic to the service running on the internal MCP port and attach TLS / auth plugins there. Document any authentication, rate limiting, or mTLS requirements in your infrastructure repository.

## Performance Tuning

### Concurrency Settings
```bash
# Environment variables
MCP_SP_CONCURRENCY=4        # Max concurrent requests per provider
MCP_SP_TIMEOUT=45           # HTTP timeout (seconds)
MCP_SP_CACHE_TTL=600        # Cache lifetime (seconds)
```

### Memory Management
- Registry data is kept in memory for fast access
- Automatic cleanup of expired cache entries
- Configurable cache size limits (future enhancement)

### Network Optimization
- HTTP/2 support via `httpx`
- Connection pooling and keep-alive
- Gzip compression for responses
- Retry logic with exponential backoff

## Troubleshooting

### Common Issues

#### 1. No Results Returned
```bash
# Check network connectivity
mcp-service-public-bj scrape --query "test" --limit 1

# Force refresh
mcp-service-public-bj scrape --query "test" --refresh
```

#### 2. Stale Data
```bash
# Clear cache and refresh
rm -rf data/registry/registry.json
mcp-service-public-bj scrape --query "passeport"
```

#### 3. SSL/TLS Errors
```bash
# Set certificate bundle
export REQUESTS_CA_BUNDLE=/path/to/ca-bundle.crt
export SSL_CERT_FILE=/path/to/ca-bundle.crt
```

#### 4. Docker Volume Issues
```bash
# Ensure proper permissions
docker run --rm -v $(pwd)/data:/app/data \
  --user $(id -u):$(id -g) \
  mcp-service-public-bj
```

### Debug Mode
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
mcp-service-public-bj serve

# Or via CLI
mcp-service-public-bj serve --log-level DEBUG
```

### Performance Monitoring
```bash
# Check metrics
curl http://localhost:8000/metrics

# Monitor logs
tail -f logs/mcp-service-public-bj.log | jq .
```

## Contributing

### Code Style
- **Formatting**: Black with 100-character line length
- **Linting**: Ruff with strict rules
- **Type Hints**: Full mypy coverage required
- **Docstrings**: Google-style documentation

### Pre-commit Hooks
```bash
# Install pre-commit
pip install pre-commit
pre-commit install

# Run manually
pre-commit run --all-files
```

### Pull Request Process
1. Fork repository and create feature branch
2. Add tests for new functionality
3. Ensure all tests pass and code is formatted
4. Update documentation if needed
5. Submit PR with clear description

### Release Process
See [Release Guide](release-guide.md) for detailed deployment instructions.
