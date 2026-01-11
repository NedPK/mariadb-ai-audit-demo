from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MariaDBConfig:
    host: str
    port: int
    user: str
    password: str
    database: Optional[str]


class ConfigError(ValueError):
    pass


def _require_env(name: str) -> str:
    """Read a required environment variable.

    Raises ConfigError if the variable is missing or empty.
    """
    value = os.getenv(name)
    if value is None or value == "":
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _env_or_default(name: str, default: str) -> str:
    """Read an environment variable or return a default when missing/empty."""
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _optional_env(name: str) -> Optional[str]:
    """Read an optional environment variable.

    Returns None when missing or empty.
    """
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value if value != "" else None


def load_mariadb_config() -> MariaDBConfig:
    """Load MariaDB connection settings from environment variables.

    Required:
    - MARIADB_USER
    - MARIADB_PASSWORD

    Optional:
    - MARIADB_HOST (defaults to localhost)
    - MARIADB_PORT (defaults to 3306)
    - MARIADB_DATABASE (optional; required for init-db)
    """
    host = _env_or_default("MARIADB_HOST", "localhost")
    port_raw = _env_or_default("MARIADB_PORT", "3306")
    user = _require_env("MARIADB_USER")
    password = _require_env("MARIADB_PASSWORD")
    database = _optional_env("MARIADB_DATABASE")

    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ConfigError("MARIADB_PORT must be an integer") from exc

    return MariaDBConfig(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )
