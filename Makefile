PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
VENV ?= .venv
ACTIVATE = . $(VENV)/bin/activate

.PHONY: install dev-install lint format test serve serve-http scrape status docker-build

install:
	$(PIP) install --upgrade pip
	$(PIP) install .

dev-install:
	$(PIP) install --upgrade pip
	$(PIP) install -e .[dev]

lint:
	$(ACTIVATE) && ruff check src tests

format:
	$(ACTIVATE) && black src tests

mypy:
	$(ACTIVATE) && mypy src

test:
	$(ACTIVATE) && pytest

serve:
	$(ACTIVATE) && mcp-service-public-bj serve

serve-http:
	$(ACTIVATE) && mcp-service-public-bj serve-http $(ARGS)

scrape:
	$(ACTIVATE) && mcp-service-public-bj scrape $(ARGS)

status:
	$(ACTIVATE) && mcp-service-public-bj status $(ARGS)

docker-build:
	docker build -t mcp-service-public-bj:latest .
