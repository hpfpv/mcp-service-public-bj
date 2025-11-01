"""JSON Schema definitions for MCP tools."""

from __future__ import annotations

CATEGORY_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "url": {"type": "string", "format": "uri"},
        "provider_id": {"type": "string"},
        "description": {"type": ["string", "null"]},
        "parent_id": {"type": ["string", "null"]},
        "order": {"type": ["integer", "null"]},
    },
    "required": ["id", "name", "url", "provider_id"],
    "additionalProperties": False,
}

DOCUMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "url": {"type": ["string", "null"], "format": "uri"},
        "document_type": {"type": ["string", "null"]},
    },
    "required": ["title"],
    "additionalProperties": False,
}

STEP_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "content": {"type": "string"},
    },
    "required": ["title", "content"],
    "additionalProperties": False,
}

REQUIREMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "content": {"type": ["string", "null"]},
    },
    "required": ["title"],
    "additionalProperties": False,
}

CONTACT_POINT_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string"},
        "value": {"type": ["string", "null"]},
    },
    "required": ["label"],
    "additionalProperties": False,
}

PROVIDER_DESCRIPTOR_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "description": {"type": "string"},
        "priority": {"type": "integer"},
        "coverage_tags": {
            "type": "array",
            "items": {"type": "string"},
        },
        "supported_tools": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["id", "name", "description", "priority"],
    "additionalProperties": False,
}

SERVICE_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "title": {"type": "string"},
        "url": {"type": "string", "format": "uri"},
        "provider_id": {"type": "string"},
        "category_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
        "excerpt": {"type": ["string", "null"]},
        "score": {"type": ["number", "null"]},
    },
    "required": ["id", "title", "url", "provider_id", "category_ids"],
    "additionalProperties": False,
}

SERVICE_DETAILS_SCHEMA = {
    "type": "object",
    "properties": {
        **SERVICE_SUMMARY_SCHEMA["properties"],
        "summary": {"type": ["string", "null"]},
        "last_updated": {"type": ["string", "null"], "format": "date-time"},
        "steps": {"type": "array", "items": STEP_SCHEMA},
        "requirements": {"type": "array", "items": REQUIREMENT_SCHEMA},
        "documents": {"type": "array", "items": DOCUMENT_SCHEMA},
        "costs": {"type": "array", "items": {"type": "string"}},
        "processing_time": {"type": ["string", "null"]},
        "contacts": {"type": "array", "items": CONTACT_POINT_SCHEMA},
        "external_links": {"type": "array", "items": DOCUMENT_SCHEMA},
    },
    "required": SERVICE_SUMMARY_SCHEMA["required"],
    "additionalProperties": False,
}

WARNINGS_SCHEMA = {
    "type": "array",
    "items": {"type": "string"},
}

LIST_CATEGORIES_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "provider_id": {"type": "string"},
        "parent_id": {"type": "string"},
        "refresh": {"type": "boolean"},
    },
    "additionalProperties": False,
}

LIST_CATEGORIES_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "provider_id": {"type": "string"},
        "source": {"type": "string"},
        "categories": {
            "type": "array",
            "items": CATEGORY_SCHEMA,
        },
        "warnings": WARNINGS_SCHEMA,
    },
    "required": ["provider_id", "source", "categories"],
    "additionalProperties": False,
}

LIST_PROVIDERS_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
}

LIST_PROVIDERS_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "providers": {
            "type": "array",
            "items": PROVIDER_DESCRIPTOR_SCHEMA,
        }
    },
    "required": ["providers"],
    "additionalProperties": False,
}

SEARCH_SERVICES_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "provider_id": {"type": "string"},
        "query": {"type": "string"},
        "category_id": {"type": "string"},
        "limit": {"type": "integer", "minimum": 1},
        "offset": {"type": "integer", "minimum": 0},
        "refresh": {"type": "boolean"},
    },
    "required": ["query"],
    "additionalProperties": False,
}

SEARCH_SERVICES_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "provider_id": {"type": "string"},
        "source": {"type": "string"},
        "results": {
            "type": "array",
            "items": SERVICE_SUMMARY_SCHEMA,
        },
        "limit": {"type": "integer"},
        "offset": {"type": "integer"},
        "total_results": {"type": "integer"},
        "next_offset": {"type": ["integer", "null"]},
        "warnings": WARNINGS_SCHEMA,
    },
    "required": ["provider_id", "source", "results", "limit", "offset", "total_results"],
    "additionalProperties": False,
}

GET_SERVICE_DETAILS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "provider_id": {"type": "string"},
        "service_id": {"type": "string"},
        "refresh": {"type": "boolean"},
    },
    "required": ["service_id"],
    "additionalProperties": False,
}

GET_SERVICE_DETAILS_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "provider_id": {"type": "string"},
        "source": {"type": "string"},
        "service": SERVICE_DETAILS_SCHEMA,
    },
    "required": ["provider_id", "source", "service"],
    "additionalProperties": False,
}

VALIDATE_SERVICE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "provider_id": {"type": "string"},
        "source": {"type": "string"},
        "service": SERVICE_DETAILS_SCHEMA,
        "validated": {"type": "boolean"},
    },
    "required": ["provider_id", "source", "service", "validated"],
    "additionalProperties": False,
}

SCRAPER_STATUS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "provider_id": {"type": "string"},
    },
    "additionalProperties": False,
}

SCRAPER_STATUS_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "provider_id": {"type": "string"},
        "status": {"type": "object"},
        "registry": {
            "type": "object",
            "properties": {
                "categories_indexed": {"type": "integer"},
                "services_indexed": {"type": "integer"},
            },
            "required": ["categories_indexed", "services_indexed"],
            "additionalProperties": False,
        },
        "descriptor": PROVIDER_DESCRIPTOR_SCHEMA,
    },
    "required": ["provider_id", "status", "registry", "descriptor"],
    "additionalProperties": False,
}

SCRAPER_STATUS_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "providers": {
            "type": "array",
            "items": SCRAPER_STATUS_ITEM_SCHEMA,
        }
    },
    "required": ["providers"],
    "additionalProperties": False,
}
