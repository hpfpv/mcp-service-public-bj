# MCP Service Public BJ Server

MCP (Model Context Protocol) server exposing curated data from [service-public.bj](https://service-public.bj/) so AI assistants can answer questions about Beninese public services.

## Description

The server is written in Python and offers four capabilities:

- **list_categories** – browse the portal taxonomy.
- **search_services** – search the public catalogue (pagination metadata included).
- **get_service_details** – retrieve complete procedure data (summary, steps, documents, contacts).
- **get_scraper_status** – inspect cache freshness and provider health metrics.

Behind the scenes, the provider retrieves JSON payloads from `https://service-public.bj/api/portal/publicservices/...`, normalises them, and persists the latest snapshot to `data/registry/registry.json` for fast follow-up queries.

By default, `search_services` fetches the full result set and disables pagination (`next_offset = null`). Provide `limit`/`offset` parameters when you want explicit paging behaviour.

Two serving modes are available:

- **stdio** — original single-client mode, ideal for desktop integrations.
- **Streamable HTTP** — multi-client mode exposed over `/mcp`, recommended for Docker/Kubernetes or shared deployments. It supports streaming responses by default, with an optional JSON mode.

## Serving Modes

### Stdio (single client)

```bash
mcp-service-public-bj serve
```

This mode keeps parity with earlier releases and is the easiest way to plug the server into MCP clients that spawn a subprocess (Claude Desktop, VS Code, etc.). Only one client can be connected at a time.

### Streamable HTTP (multi-client)

```bash
mcp-service-public-bj serve-http --host 0.0.0.0 --port 8000
```

The streamable HTTP transport exposes:

- `POST /mcp` – primary endpoint for JSON-RPC requests with server-driven streaming.
- `GET /mcp` – establishes an event stream for incremental responses (optional).
- `DELETE /mcp` – terminates the session if needed.
- `GET /healthz` – liveness probe with registry metadata.

Run this mode when the server must be shared across users or deployed in a container. Multiple clients can connect concurrently, and the process keeps a single provider/cache runtime in memory. Use the `--json-response` flag if you prefer standard JSON replies instead of streaming.

## Installation

### From source (development setup)

```bash
git clone https://github.com/hpfpv/mcp-service-public-bj.git
cd mcp-service-public-bj
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .[dev]

# run tests
pytest
```

### Docker image (Recommanded)

```bash
docker build -t mcp-service-public-bj:latest .
docker run -i mcp-service-public-bj:latest serve-http
```

The image uses `python3 -m server.main` as its entrypoint; provide the desired sub-command (`serve`, `serve-http`, `scrape`) as extra arguments. Defaults to `serve` for stdio. Add `-v $(pwd)/data/registry:/app/data/registry` if you want registry snapshots to persist between runs.

## Configuration

Environment variables (see `.env.example`):

| Variable | Description | Default |
|----------|-------------|---------|
| `MCP_SP_BASE_URL` | Base portal URL | `https://service-public.bj/` |
| `MCP_SP_CACHE_DIR` | Directory for registry snapshots | `data/registry` |
| `MCP_SP_CONCURRENCY` | Maximum concurrent fetches | `2` |
| `MCP_SP_TIMEOUT` | HTTP timeout (seconds) | `30` |
| `MCP_SP_CACHE_TTL` | TTL for the in-memory cache | `300` |
| `MCP_ENABLED_PROVIDERS` | Provider ids (comma separated) | `service-public-bj` |

## MCP Client Integration

### Summary
- **Claude Desktop** supports stdio only; you can run the server from a local virtualenv or via Docker.
- **Visual Studio Code** supports stdio (local or Docker) and direct HTTP connections to a running `serve-http` instance.
- For Docker-based, add `--volume /path/to/registry:/app/data/registry` if you need persistent registry snapshots.

### Claude Desktop (stdio)
Edit the configuration file (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`, Windows: `%APPDATA%/Claude/claude_desktop_config.json`) to include the variant you want to use:

#### Local dev environment

```json
{
  "mcpServers": {
    "service-public-bj-local": {
      "command": "/Users/<you>/mcp-service-public-bj/.venv/bin/python",
      "args": ["-m", "server.main"]
    }
  }
}
```

#### Docker
```json
{
  "mcpServers": {
    "service-public-bj-docker": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "mcp-service-public-bj:latest"]
    }
  }
}
```

Restart Claude Desktop and enable the desired server(s) under **Settings → Developers → MCP Servers**.

### Visual Studio Code (stdio & HTTP)
Edit the configuration file (macOS: `~/Library/Application Support/Code/User/mcp.json`, Windows: `%APPDATA%/Code/User/mcp.json`) to include the variant you want to use:

#### Local dev environment
```json
{
  "servers": {
    "service-public-local-stdio": {
      "type": "stdio",
      "command": "/Users/<you>/mcp-service-public-bj/.venv/bin/python",
      "args": ["-m", "server.main"]
    }
  },
  "inputs": []
}
```

#### Docker
```json
{
  "servers": {
    "service-public-docker-stdio": {
      "type": "stdio",
      "command": "docker",
      "args": ["run", "--rm", "-i", "mcp-service-public-bj:latest"]
    },
    "mcp-service-public-bj-http": {
      "type": "http",
      "url": "http://localhost:8000/mcp"
    }
  },
  "inputs": []
}
```

#### HTTP
To add the MCP server as an HTTP endpoint on VSCode, run the Docker container using the `serve-httpsub-command`:

```bash
docker build -t mcp-service-public-bj:latest .
docker run -i mcp-service-public-bj:latest serve-http
```
Then update the `mcp.json` file as follow:

```json
{
  "servers": {
    "mcp-service-public-bj-http": {
      "type": "http",
      "url": "http://localhost:8000/mcp"
    }
  },
  "inputs": []
}
```

## Command Line Usage

```bash
# launch the MCP server (stdio)
mcp-service-public-bj serve

# launch the streamable HTTP server
mcp-service-public-bj serve-http --host 0.0.0.0 --port 8000

# refresh data and prefetch a query
mcp-service-public-bj scrape --query "passeport" --limit 25

# refresh a specific service record
mcp-service-public-bj scrape --service-id PS00409

# display cache metrics
mcp-service-public-bj status --live
```

Equivalent Makefile targets: `make serve`, `make serve-http ARGS="--host 0.0.0.0 --port 8000"`, `make scrape ARGS="--query passeport"`, `make status ARGS="--live"`.

## Tools Overview

| Tool | Input | Output |
|------|-------|--------|
| `list_categories` | `parent_id` (optional), `refresh` | Array of categories (id, name, URL) |
| `search_services` | `query`, `limit`, `offset`, `category_id`, `refresh` | Matching services with pagination metadata (default returns all matches) |
| `get_service_details` | `service_id`, `refresh` | Full service details (summary, steps, documents, contacts) |
| `get_scraper_status` | `provider_id` (optional) | Cache/provider diagnostics |

## Troubleshooting

- No results → check network access and run `scrape --refresh`.
- Stale data → call `get_service_details` with `refresh=true` or use `scrape --service-id`.
- Snapshots not persisted in Docker → mount a volume on `/app/data/registry`.
- SSL errors → configure `REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE`.

## Release Notes

- **0.1.0** – initial MCP release (CLI, pagination, detail caching, Docker image).


## License

MIT License (see `LICENSE`).
