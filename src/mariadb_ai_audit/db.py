from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import mariadb

from mariadb_ai_audit.config import MariaDBConfig


class DatabaseError(RuntimeError):
    pass


def connect(cfg: MariaDBConfig) -> mariadb.Connection:
    """Create a new MariaDB connection.

    Uses SSL and verifies server certificate. If cfg.database is provided,
    connects with that database selected.
    """
    try:
        kwargs = dict(
            host=cfg.host,
            port=cfg.port,
            user=cfg.user,
            password=cfg.password,
            ssl=True,
            ssl_verify_cert=True,
        )

        if cfg.database:
            kwargs["database"] = cfg.database

        return mariadb.connect(**kwargs)
    except mariadb.Error as exc:
        raise DatabaseError(str(exc)) from exc


@contextmanager
def connection(cfg: MariaDBConfig) -> Iterator[mariadb.Connection]:
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
