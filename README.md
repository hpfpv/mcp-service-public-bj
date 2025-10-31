# MCP Service Public BJ

An MCP (Model Context Protocol) server that provides AI assistants with access to Benin's public service information from [service-public.bj](https://service-public.bj).

## What it does

This server enables AI assistants to help citizens find information about Beninese government services, procedures, and requirements. It provides:

- **Service search**: Find government services by keywords
- **Category browsing**: Explore services by thematic areas
- **Detailed procedures**: Get step-by-step instructions, required documents, and contact information
- **Real-time data**: Live scraping ensures information stays current

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
# Build
docker build -t mcp-service-public-bj .

# Run stdio mode
docker run --rm -i mcp-service-public-bj

# Run HTTP mode
docker run --rm -p 8000:8000 mcp-service-public-bj serve-http --host 0.0.0.0
```

## Available Tools

| Tool | Purpose | Example |
|------|---------|---------|
| `list_categories` | Browse service categories | Get all thematic areas |
| `search_services` | Find services by keywords | Search "carte identité" |
| `get_service_details` | Get complete procedure info | Full passport renewal guide |
| `get_scraper_status` | Check system health | Cache stats, provider status |

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
```

## Documentation

- **[Developer Guide](docs/developer-guide.md)** - Technical details, architecture, testing
- **[Release Guide](docs/release-guide.md)** - Deployment and release process

## License

MIT License - see [LICENSE](LICENSE) file.