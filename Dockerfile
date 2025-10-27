FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md .
COPY src src
COPY tests tests
COPY data data

RUN pip install --upgrade pip \
    && pip install .

CMD ["mcp-service-public-bj", "serve"]
