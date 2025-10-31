"""Data models for categories and services."""

from __future__ import annotations

from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, Field


class Category(BaseModel):
    """Represents a category or thematic grouping of services."""

    id: str
    name: str
    url: AnyHttpUrl
    provider_id: str = Field(default="service-public-bj")
    description: str | None = None
    parent_id: str | None = None
    order: int | None = None


class DocumentLink(BaseModel):
    """Represents a downloadable document or related resource."""

    title: str
    url: AnyHttpUrl | None = None
    document_type: str | None = None


class Step(BaseModel):
    """Represents an individual procedure step."""

    title: str
    content: str


class Requirement(BaseModel):
    """Represents a requirement or prerequisite for the service."""

    title: str
    content: str | None = None


class ContactPoint(BaseModel):
    """Represents a contact channel or office."""

    label: str
    value: str | None = None


class ServiceSummary(BaseModel):
    """Lightweight result used in listings and search."""

    id: str
    title: str
    url: AnyHttpUrl
    provider_id: str = Field(default="service-public-bj")
    category_ids: list[str] = Field(default_factory=list)
    excerpt: str | None = None
    score: float | None = Field(
        default=None,
        description="Optional relevance score supplied by search implementation.",
    )


class ServiceDetails(ServiceSummary):
    """Full service information for detail views."""

    summary: str | None = None
    last_updated: datetime | None = None
    steps: list[Step] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    documents: list[DocumentLink] = Field(default_factory=list)
    costs: list[str] = Field(default_factory=list)
    processing_time: str | None = None
    contacts: list[ContactPoint] = Field(default_factory=list)
    external_links: list[DocumentLink] = Field(default_factory=list)
