"""Application configuration utilities."""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

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
    finances_base_url: AnyHttpUrl = Field(
        default="https://finances.bj/",
        alias="FINANCES_BASE_URL",
        description="Base URL for finances.bj WordPress API.",
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
    enabled_providers: list[str] = Field(
        default_factory=lambda: ["service-public-bj", "finances-bj"],
        alias="ENABLED_PROVIDERS",
        description="Comma-separated list of provider identifiers to enable.",
    )
    provider_priorities: dict[str, int] = Field(
        default_factory=dict,
        alias="PROVIDER_PRIORITIES",
        description="Comma-separated mapping of provider priorities (e.g. service-public-bj:100,finances-bj:80).",
    )

    model_config = SettingsConfigDict(
        env_prefix="MCP_",
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("enabled_providers", mode="before")
    @classmethod
    def _split_providers(cls, value: Sequence[str] | str | None) -> list[str]:
        if value is None:
            return ["service-public-bj", "finances-bj"]
        if isinstance(value, str):
            candidates = [item.strip() for item in value.split(",")]
            return [item for item in candidates if item]
        return list(value)

    @field_validator("provider_priorities", mode="before")
    @classmethod
    def _parse_priorities(cls, value: dict[str, int] | str | None) -> dict[str, int]:
        if value is None or value == "":
            return {}
        if isinstance(value, dict):
            return value
        priorities: dict[str, int] = {}
        for item in value.split(","):
            item = item.strip()
            if not item:
                continue
            if ":" not in item:
                continue
            provider_id, _, priority_str = item.partition(":")
            provider_id = provider_id.strip()
            priority_str = priority_str.strip()
            if not provider_id or not priority_str:
                continue
            try:
                priorities[provider_id] = int(priority_str)
            except ValueError:
                continue
        return priorities


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached instance of application settings."""

    settings = Settings()
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    return settings
