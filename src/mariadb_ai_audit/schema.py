from __future__ import annotations

from pathlib import Path
import re

from mariadb_ai_audit.config import MariaDBConfig
from mariadb_ai_audit.db import connection


class SchemaError(RuntimeError):
    pass


DEFAULT_DATABASE = "mariadb_ai_audit"


def _default_schema_path() -> Path:
    """Return the default path to sql/schema.sql."""
    return Path(__file__).resolve().parents[2] / "sql" / "schema.sql"


def _split_sql(sql: str) -> list[str]:
    """Split a SQL file into individual statements.

    This is a simple splitter intended for the demo schema, where each statement
    ends with a semicolon.
    """
    statements: list[str] = []
    buff: list[str] = []

    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        buff.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(buff).strip()
            if stmt.endswith(";"):
                stmt = stmt[:-1].strip()
            if stmt:
                statements.append(stmt)
            buff = []

    tail = "\n".join(buff).strip()
    if tail:
        statements.append(tail)

    return statements


def apply_schema(cfg: MariaDBConfig, *, schema_path: Path | None = None) -> None:
    """Apply the demo schema to the configured database.

    If cfg.database is not set, a default database name is used.

    Statements are executed sequentially and committed.
    """
    target_db = cfg.database or DEFAULT_DATABASE
    if not re.fullmatch(r"[A-Za-z0-9_]+", target_db):
        raise SchemaError("Invalid database name")

    path = schema_path or _default_schema_path()
    sql = path.read_text(encoding="utf-8")
    statements = _split_sql(sql)

    if not statements:
        raise SchemaError("Schema file contains no statements")

    cfg_no_db = MariaDBConfig(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        database=None,
    )

    with connection(cfg_no_db) as conn:
        cur = conn.cursor()
        cur.execute(f"CREATE DATABASE IF NOT EXISTS {target_db}")
        cur.close()
        conn.commit()

    cfg_with_db = MariaDBConfig(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        database=target_db,
    )

    with connection(cfg_with_db) as conn:
        cur = conn.cursor()
        for stmt in statements:
            cur.execute(stmt)
        cur.close()
        conn.commit()
