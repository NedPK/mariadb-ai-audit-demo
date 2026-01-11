from __future__ import annotations

from contextlib import contextmanager
import ssl
from typing import Iterator

import pymysql
from pymysql import MySQLError

from mariadb_ai_audit.config import MariaDBConfig


class DatabaseError(RuntimeError):
    pass


def connect(cfg: MariaDBConfig) -> pymysql.Connection:
    """Create a new MariaDB connection.

    Uses SSL and verifies server certificate. If cfg.database is provided,
    connects with that database selected.
    """
    try:
        ssl_ctx = ssl.create_default_context()
        kwargs = dict(
            host=cfg.host,
            port=cfg.port,
            user=cfg.user,
            password=cfg.password,
            ssl=ssl_ctx,
        )

        if cfg.database:
            kwargs["database"] = cfg.database

        return pymysql.connect(**kwargs)
    except MySQLError as exc:
        raise DatabaseError(str(exc)) from exc


@contextmanager
def connection(cfg: MariaDBConfig) -> Iterator[pymysql.Connection]:
    """Context manager that opens and reliably closes a MariaDB connection."""
    conn = connect(cfg)
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass


def healthcheck(cfg: MariaDBConfig) -> None:
    """Verify DB connectivity by executing a trivial SELECT 1."""
    with connection(cfg) as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
