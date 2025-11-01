# MCP Service Public BJ

An MCP (Model Context Protocol) server that provides AI assistants with access to Benin's public service information from [service-public.bj](https://service-public.bj).

## What it does

This server enables AI assistants to help citizens find information about Beninese government services, procedures, and requirements. It provides:

- **Service search**: Find government and finance services by keywords
- **Category browsing**: Explore services by thematic areas across enabled providers
- **Detailed procedures**: Get step-by-step instructions, required documents, and contact information
- **Real-time data**: Live scraping ensures information stays current
- **Smart provider routing**: Queries are routed automatically using provider coverage tags, then priority and fallback logic

## Example Usage

Here's how an AI assistant can help users find information about Beninese public services:

![MCP Service Public BJ Example 1](images/mcp-example-1.png)
![MCP Service Public BJ Example 2](images/mcp-example-2.png)

*Example: AI assistant helping a user find information about passport renewal procedures using the MCP server*

## Quick Start

### Prerequisites
- Python 3.10+
- Virtual environment (recommended)

### Installation

```bash
# Clone and setup
git clone <repository-url>
cd mcp-service-public-bj
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install
pip install -e .
```

### Basic Usage

```bash
# Start MCP server (stdio mode)
mcp-service-public-bj serve

# Start HTTP server
mcp-service-public-bj serve-http --host 0.0.0.0 --port 8000

# Test with a search
mcp-service-public-bj scrape --query "passeport" --limit 5
```

## Integration with MCP clients

### Claude Desktop
Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "service-public-bj": {
      "command": "/path/to/your/.venv/bin/python",
      "args": ["-m", "server.main"]
    }
  }
}
```

### VS Code with MCP
Add to `~/Library/Application Support/Code/User/mcp.json`:

```json
{
  "servers": {
    "service-public-bj": {
      "type": "stdio",
      "command": "/path/to/your/.venv/bin/python",
      "args": ["-m", "server.main"]
    }
  }
}
```

### Docker
```bash
# Pull from GitHub Container Registry
docker pull ghcr.io/hpfpv/mcp-service-public-bj:latest

# Run HTTP mode (default)
docker run --rm -p 8000:8000 ghcr.io/hpfpv/mcp-service-public-bj:latest

# Run stdio mode
docker run --rm -i ghcr.io/hpfpv/mcp-service-public-bj:latest serve
```

## Available Tools

| Tool | Purpose | Example |
|------|---------|---------|
| `list_providers` | Discover available providers, coverage tags, priority and supported tools | Inspect routing candidates |
| `list_categories` | Browse service categories | Get all thematic areas |
| `search_services` | Find services by keywords (auto-routing between providers) | Search "autorisation change" |
| `get_service_details` | Get complete procedure info | Full passport renewal guide |
| `get_scraper_status` | Check per-provider health and registry counters | Cache stats, provider status |

When a tool call omits `provider_id`, the server automatically routes the request using provider coverage tags (fuzzy match between query and tags). Providers whose tags best match the query are attempted first; ties fall back to priority ordering. If a provider fails or returns no results, the server transparently falls back to the next candidate and reports the attempted providers in the `warnings` field. Clients can preload routing hints via `list_providers` and send `provider_id` explicitly to pin a source.

## Configuration

Copy `.env.example` to `.env` and customize:

```bash
# Base URL (default: https://service-public.bj/)
MCP_SP_BASE_URL=https://service-public.bj/

# Cache directory
MCP_SP_CACHE_DIR=/path/to/cache

# Performance tuning
MCP_SP_CONCURRENCY=2
MCP_SP_TIMEOUT=30
MCP_SP_CACHE_TTL=300

# Enable providers (comma-separated)
MCP_ENABLED_PROVIDERS=service-public-bj,finances-bj

# Override finances.bj base URL if required
MCP_FINANCES_BASE_URL=https://finances.bj/

# Optional priority overrides (higher = earlier fallback)
# MCP_PROVIDER_PRIORITIES=service-public-bj:100,finances-bj:80
```

## Documentation

- **[Developer Guide](docs/developer-guide.md)** - Technical details, architecture, testing
- **[Release Guide](docs/release-guide.md)** - Deployment and release process
- Operational runbooks (cache rotation, provider onboarding) are covered in the Developer Guide

## License

MIT License - see [LICENSE](LICENSE) file.
