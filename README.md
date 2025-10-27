# MCP Service Public BJ

Live-scraping MCP server exposing data from [service-public.bj](https://service-public.bj/public/) so agents can answer questions about Beninese public services.

## Project Status
This repository is under active development. Phase 0 establishes the project skeleton, tooling, and initial dependencies. Later phases will implement live scraping, MCP tooling, and optional continuous crawling.

## Getting Started
```bash
# create and activate a virtual environment of your choice
python -m venv .venv
source .venv/bin/activate

# install package with development dependencies
pip install --upgrade pip
pip install -e ".[dev]"

# install pre-commit hooks
pre-commit install
```

## Development Tooling
- **Formatting & linting:** `black`, `ruff`
- **Static typing:** `mypy`
- **Testing:** `pytest`, `pytest-asyncio`

Configuration for these tools lives in `pyproject.toml`. Run them via your preferred task runner or directly:

```bash
ruff check src tests
black src tests
pytest

# run the default pre-commit suite manually
pre-commit run --all-files
```

## Command Line Helpers
Install the project in editable mode (or install the wheel), then use the CLI entry point:

```bash
# serve the MCP server over stdio
mcp-service-public-bj serve

# refresh cached data for all providers
mcp-service-public-bj scrape

# run a search while refreshing the cache
mcp-service-public-bj scrape --query "carte d'identité" --limit 25

# display cached statistics; add --live to fetch status from the remote site
mcp-service-public-bj status
```

The same commands are available via the `Makefile` (e.g. `make serve`, `make scrape ARGS="--query carte"`).

Environment variables can be provided through a shell export or by copying `.env.example`.

## Docker Image

Build and run the containerised MCP server:

```bash
docker build -t mcp-service-public-bj:latest .
docker run --rm -it mcp-service-public-bj:latest

# persist registry snapshots locally
docker run --rm -it \
  -v $(pwd)/data/registry:/app/data/registry \
  mcp-service-public-bj:latest
```

Use `-e` flags to override configuration (e.g. `-e MCP_SP_CACHE_DIR=/app/data/registry`).

## Adding Additional Providers
- Create a new provider class inheriting from `server.providers.BaseProvider`.
- Implement live scraping logic and register it via `server.registry.RegistryState` (categories, services, selector profiles).
- Update configuration (`MCP_ENABLED_PROVIDERS`) to include the new provider id.
- Ensure new providers expose health metrics through `get_status` and supply tests mirroring those in `tests/test_service_public_provider.py`.

## Roadmap
Project planning documents live in `.specs/mcp-service-public-bj/`. Refer to `requirements.md`, `design.md`, and `tasks.md` for detailed scope and implementation phases.
