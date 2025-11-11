# MCP Service Public BJ

An MCP (Model Context Protocol) server that provides AI assistants with access to Benin's public service information from [service-public.bj](https://service-public.bj).

## What it does

This server enables AI assistants to help citizens find information about Beninese government services, procedures, and requirements. It provides:

- **Service search**: Find government and finance services by keywords
- **Category browsing**: Explore services by thematic areas across enabled providers
- **Detailed procedures**: Get step-by-step instructions, required documents, and contact information
- **Real-time data**: Live scraping ensures information stays current
- **Smart provider routing**: Queries are routed automatically using provider coverage tags, then priority and fallback logic

## Quick Start

### Prerequisites
- Python 3.10+
- Virtual environment (recommended)

### Installation

```bash
# Clone and setup
git clone https://github.com/hpfpv/mcp-service-public-bj.git
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

## Available Tools

| Tool | Purpose | Example |
|------|---------|---------|
| `list_providers` | Discover available providers, coverage tags, priority and supported tools | Inspect routing candidates |
| `list_categories` | Browse service categories | Get all thematic areas |
| `search_services` | Find services by keywords (auto-routing between providers) | Search "autorisation change" |
| `get_service_details` | Get complete procedure info | Full passport renewal guide |
| `get_scraper_status` | Check per-provider health and registry counters | Cache stats, provider status |

## License

MIT License - see [LICENSE](LICENSE) file.