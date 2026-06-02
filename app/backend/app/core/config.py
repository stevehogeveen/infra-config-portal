from __future__ import annotations

import os
from dataclasses import dataclass


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "infra-config-portal")
    environment: str = os.getenv("ENVIRONMENT", "local")
    provider_mode: str = os.getenv("PROVIDER_MODE", "mock")
    media_inventory_dirs: tuple[str, ...] = tuple(
        _split_csv(os.getenv("MEDIA_INVENTORY_DIRS", ""))
    )
    database_url: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///./.local/infra_config_portal.db",
    )
    cors_origins: tuple[str, ...] = tuple(
        _split_csv(os.getenv("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"))
    )


settings = Settings()
