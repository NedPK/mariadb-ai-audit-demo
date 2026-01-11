from __future__ import annotations

from typing import Any

import pytest

from mariadb_ai_audit.config import MariaDBConfig
from mariadb_ai_audit.db import healthcheck


class _Cursor:
    def __init__(self) -> None:
        self.executed: list[str] = []

    def execute(self, sql: str) -> None:
        self.executed.append(sql)

    def fetchone(self) -> tuple[int]:
        return (1,)

    def close(self) -> None:
        return None


class _Conn:
    def __init__(self) -> None:
        self.closed = False
        self.cur = _Cursor()

    def cursor(self) -> _Cursor:
        return self.cur

    def close(self) -> None:
        self.closed = True


def test_healthcheck_executes_select_1(monkeypatch: pytest.MonkeyPatch) -> None:
    import mariadb_ai_audit.db as db

    conn = _Conn()

    def _connect(*args: Any, **kwargs: Any) -> _Conn:
        return conn

    monkeypatch.setattr(db.mariadb, "connect", _connect)

    cfg = MariaDBConfig(host="h", port=3306, user="u", password="p", database="d")
    healthcheck(cfg)

    assert conn.cur.executed == ["SELECT 1"]
    assert conn.closed is True
