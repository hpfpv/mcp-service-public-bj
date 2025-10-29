"""Application configuration utilities."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Sequence

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_cache_dir() -> Path:
    module_root = Path(__file__).resolve().parents[2]
    if (module_root / "pyproject.toml").exists():
        return module_root / "data" / "registry"
    return Path.home() / ".cache" / "mcp-service-public-bj"


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    base_url: AnyHttpUrl = Field(
        default="https://service-public.bj/",
        alias="SP_BASE_URL",
        description="Default base URL for the primary service-public BJ website.",
    )
    cache_dir: Path = Field(
        default_factory=_default_cache_dir,
        alias="SP_CACHE_DIR",
        description="Directory used for lightweight cache or registry persistence.",
    )
    concurrency: int = Field(
        default=2,
        alias="SP_CONCURRENCY",
        ge=1,
        description="Maximum number of concurrent live fetches per provider.",
    )
    timeout_seconds: float = Field(
        default=30.0,
        alias="SP_TIMEOUT",
        gt=0,
        description="HTTP timeout in seconds for live fetch calls.",
    )
    cache_ttl_seconds: int = Field(
        default=300,
        alias="SP_CACHE_TTL",
        ge=0,
        description="Global cache TTL (seconds) for live responses.",
    )
    user_agent: str = Field(
        default="MCP-Service-Public-BJ/0.1",
        alias="SP_USER_AGENT",
        description="User-Agent header presented to remote servers.",
    )
    enabled_providers: List[str] = Field(
        default_factory=lambda: ["service-public-bj"],
        alias="ENABLED_PROVIDERS",
        description="Comma-separated list of provider identifiers to enable.",
    )

    model_config = SettingsConfigDict(
        env_prefix="MCP_",
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("enabled_providers", mode="before")
    @classmethod
    def _split_providers(cls, value: Sequence[str] | str | None) -> List[str]:
        if value is None:
            return ["service-public-bj"]
        if isinstance(value, str):
            candidates = [item.strip() for item in value.split(",")]
            return [item for item in candidates if item]
        return list(value)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached instance of application settings."""

    settings = Settings()
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    return settings
