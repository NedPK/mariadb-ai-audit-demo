import os

import pytest

from mariadb_ai_audit.config import ConfigError, load_mariadb_config


def test_load_mariadb_config_missing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MARIADB_HOST", raising=False)
    monkeypatch.delenv("MARIADB_PORT", raising=False)
    monkeypatch.delenv("MARIADB_USER", raising=False)
    monkeypatch.delenv("MARIADB_PASSWORD", raising=False)
    monkeypatch.delenv("MARIADB_DATABASE", raising=False)

    with pytest.raises(ConfigError) as exc:
        load_mariadb_config()

    assert "Missing required environment variable: MARIADB_USER" in str(exc.value)


def test_load_mariadb_config_invalid_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARIADB_HOST", "localhost")
    monkeypatch.setenv("MARIADB_PORT", "not_an_int")
    monkeypatch.setenv("MARIADB_USER", "user")
    monkeypatch.setenv("MARIADB_PASSWORD", "pass")
    monkeypatch.setenv("MARIADB_DATABASE", "db")

    with pytest.raises(ConfigError) as exc:
        load_mariadb_config()

    assert "MARIADB_PORT must be an integer" in str(exc.value)


def test_load_mariadb_config_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARIADB_HOST", "localhost")
    monkeypatch.setenv("MARIADB_PORT", "3306")
    monkeypatch.setenv("MARIADB_USER", "user")
    monkeypatch.setenv("MARIADB_PASSWORD", "pass")
    monkeypatch.setenv("MARIADB_DATABASE", "db")

    cfg = load_mariadb_config()

    assert cfg.host == "localhost"
    assert cfg.port == 3306
    assert cfg.user == "user"
    assert cfg.password == "pass"
    assert cfg.database == "db"


def test_load_mariadb_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MARIADB_HOST", raising=False)
    monkeypatch.delenv("MARIADB_PORT", raising=False)
    monkeypatch.setenv("MARIADB_USER", "user")
    monkeypatch.setenv("MARIADB_PASSWORD", "pass")
    monkeypatch.delenv("MARIADB_DATABASE", raising=False)

    cfg = load_mariadb_config()

    assert cfg.host == "localhost"
    assert cfg.port == 3306
    assert cfg.database is None
