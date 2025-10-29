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
git clone https://github.com/<your-org>/mcp-service-public-bj.git
cd mcp-service-public-bj
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .[dev]

# run tests
pytest
```

### Docker image

```bash
docker build -t mcp-service-public-bj:latest .
docker run --rm -it \
  -v $(pwd)/data/registry:/app/data/registry \
  -p 8000:8000 \
  mcp-service-public-bj:latest
```

The container executes `mcp-service-public-bj serve-http --host 0.0.0.0 --port 8000`, exposing the streamable HTTP transport on `http://localhost:8000`. Mount `data/registry` to persist registry snapshots between runs.

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

### Claude Desktop (macOS / Windows)
Follow the [official Claude documentation](https://modelcontextprotocol.io/docs/develop/connect-local-servers#claude-desktop) and register the server over stdio:

1. Install the project (`pip install -e .`).
2. Edit the configuration file (see [Claude Desktop docs](https://modelcontextprotocol.io/docs/develop/connect-local-servers#claude-desktop)):
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%/Claude/claude_desktop_config.json`
3. Add (or update) an entry following Claude’s expected shape:
   ```json
   {
     "mcpServers": {
       "service-public-bj": {
         "command": "/Users/<you>/mcp-service-public-bj/.venv/bin/python",
         "args": [
           "-m",
           "server.main",
           "--transport",
           "stdio"
         ],
         "env": {
           "PYTHONPATH": "/Users/<you>/mcp-service-public-bj/src"
         },
         "workingDirectory": "/Users/<you>/mcp-service-public-bj"
       }
     }
   }
   ```
   Adjust paths for your environment (the entry mirrors the filesystem example in Claude’s documentation). `env` is optional but helps when the project isn’t installed system-wide.
4. Restart Claude Desktop and toggle the server in **Settings → MCP Servers**.

> Claude Desktop only supports stdio transports today. Use the HTTP bridge workflow below if you need to expose the server to additional clients.

### Visual Studio Code (Copilot Chat)
VS Code uses the configuration described in the [official Copilot/MCP guidance](https://code.visualstudio.com/docs/copilot/customization/mcp-servers). Add this block to `.vscode/settings.json`:

```json
{
  "mcp.servers": {
    "service-public-bj": {
      "command": "/Users/<you>/mcp-service-public-bj/.venv/bin/python",
      "args": [
        "-m",
        "server.main",
        "--transport",
        "stdio"
      ],
      "transport": "stdio",
      "cwd": "/Users/<you>/mcp-service-public-bj"
    }
  }
}
```

Reload VS Code and enable the server inside Copilot Chat.

### Using the Docker image with stdio clients
If you prefer to run the server in a container while still exposing stdio to Claude Desktop or VS Code, override the default command (which starts the HTTP transport) so the container launches `serve` instead. Example Claude configuration:

```json
{
  "mcpServers": {
    "service-public-bj": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--volume",
        "/Users/<you>/mcp-service-public-bj/data/registry:/app/data/registry",
        "mcp-service-public-bj:latest",
        "mcp-service-public-bj",
        "serve"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

For VS Code, place the equivalent entry in `.vscode/settings.json`:

```json
{
  "mcp.servers": {
    "service-public-bj": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--volume",
        "/Users/<you>/mcp-service-public-bj/data/registry:/app/data/registry",
        "mcp-service-public-bj:latest",
        "mcp-service-public-bj",
        "serve"
      ],
      "transport": "stdio"
    }
  }
}
```

Adjust the volume path for your host; it ensures registry snapshots persist between runs. When running on Windows, replace the POSIX-style path with the appropriate Windows path (for example `C:/Users/<you>/mcp-service-public-bj/data/registry`).

### Any client via HTTP bridge (Claude web, shared deployments, etc.)
When you run the streamable HTTP transport, connect clients using a bridge as recommended in the [MCP integration guide](https://modelcontextprotocol.io/docs/develop/connect-local-servers#using-the-model-context-protocol-cli):

1. Start the HTTP server:
   - Local: `mcp-service-public-bj serve-http --host 0.0.0.0 --port 8000`
   - Docker: `docker run -p 8000:8000 mcp-service-public-bj:latest`
2. Launch an MCP bridge that proxies HTTP requests to your client’s preferred protocol. Using the official CLI:
   ```bash
   npx @modelcontextprotocol/cli http http://localhost:8000/mcp --port 3333
   ```
   Adjust flags to match your environment (see CLI docs for TLS/auth options). Add `--json` if the server is running with `--json-response`.
3. Configure your client (Claude web, custom agent, etc.) to talk to the bridge endpoint on `http://localhost:3333`.

## Command Line Usage

```bash
# launch the MCP server (stdio)
mcp-service-public-bj serve

# launch the streamable HTTP server (multi-client)
mcp-service-public-bj serve-http --host 0.0.0.0 --port 8000

# refresh data and prefetch a query
mcp-service-public-bj scrape --query "carte" --limit 25

# refresh a specific service record
mcp-service-public-bj scrape --service-id PS00409

# display cache metrics
mcp-service-public-bj status --live
```

Equivalent Makefile targets: `make serve`, `make serve-http ARGS="--host 0.0.0.0 --port 8000"`, `make scrape ARGS="--query carte"`, `make status ARGS="--live"`.

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

## Development

- Style: `black`, `ruff`, `mypy` (strict). Use `make lint`, `make mypy`, `make test`.
- Tests use stubs instead of live HTTP calls.
- Adding a provider: implement `BaseProvider`, register in `server/providers/__init__.py`, add tests.

## Release Notes

- **0.1.0** – initial MCP release (CLI, pagination, detail caching, Docker image).

## Additional Docs

- `.specs/mcp-service-public-bj/requirements.md`
- `.specs/mcp-service-public-bj/design.md`
- `.specs/mcp-service-public-bj/tasks.md`

## License

MIT License (see `LICENSE`).
