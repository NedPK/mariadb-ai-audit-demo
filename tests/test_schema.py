from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mariadb_ai_audit.config import MariaDBConfig
from mariadb_ai_audit.schema import (
    DEFAULT_DATABASE,
    SchemaError,
    _split_sql,
    apply_schema,
)


class _Cursor:
    def __init__(self) -> None:
        self.executed: list[str] = []

    def execute(self, sql: str) -> None:
        self.executed.append(sql)

    def close(self) -> None:
        return None


class _Conn:
    def __init__(self) -> None:
        self.closed = False
        self.committed = False
        self.cur = _Cursor()

    def cursor(self) -> _Cursor:
        return self.cur

    def close(self) -> None:
        self.closed = True

    def commit(self) -> None:
        self.committed = True


def test_split_sql() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS t1 (id INT);

    CREATE TABLE IF NOT EXISTS t2 (id INT);
    """
    stmts = _split_sql(sql)
    assert stmts == [
        "CREATE TABLE IF NOT EXISTS t1 (id INT)",
        "CREATE TABLE IF NOT EXISTS t2 (id INT)",
    ]


def test_apply_schema_rejects_invalid_database_name(tmp_path: Path) -> None:
    schema_file = tmp_path / "schema.sql"
    schema_file.write_text(
        "CREATE TABLE IF NOT EXISTS t1 (id INT);\n", encoding="utf-8"
    )

    cfg = MariaDBConfig(
        host="h", port=3306, user="u", password="p", database="bad-name"
    )
    with pytest.raises(SchemaError):
        apply_schema(cfg, schema_path=schema_file)


def test_apply_schema_executes_all_statements(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import mariadb_ai_audit.schema as schema

    schema_file = tmp_path / "schema.sql"
    schema_file.write_text(
        "CREATE TABLE IF NOT EXISTS t1 (id INT);\nCREATE TABLE IF NOT EXISTS t2 (id INT);\n",
        encoding="utf-8",
    )

    conn = _Conn()

    class _Ctx:
        def __enter__(self) -> _Conn:
            return conn

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            conn.close()

    def _connection(_cfg: MariaDBConfig):
        return _Ctx()

    monkeypatch.setattr(schema, "connection", _connection)

    cfg = MariaDBConfig(host="h", port=3306, user="u", password="p", database=None)
    apply_schema(cfg, schema_path=schema_file)

    assert conn.cur.executed == [
        f"CREATE DATABASE IF NOT EXISTS {DEFAULT_DATABASE}",
        "CREATE TABLE IF NOT EXISTS t1 (id INT)",
        "CREATE TABLE IF NOT EXISTS t2 (id INT)",
    ]
    assert conn.committed is True
    assert conn.closed is True
