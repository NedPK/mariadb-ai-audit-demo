from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from mariadb_ai_audit.config import MariaDBConfig
from mariadb_ai_audit.retrieval import search_chunks


@dataclass
class _Hit:
    chunk_id: int
    document_id: int
    chunk_index: int
    score: float
    content: str


class _Cursor:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.closed = False

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.executed.append((sql, tuple(params or ())))

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows

    def close(self) -> None:
        self.closed = True


class _Conn:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows
        self.closed = False
        self.cursors: list[_Cursor] = []

    def cursor(self) -> _Cursor:
        cur = _Cursor(self._rows)
        self.cursors.append(cur)
        return cur

    def close(self) -> None:
        self.closed = True


class _Embedder:
    model = "m"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        assert texts
        return [[0.1, 0.2]]


def test_search_chunks_does_not_audit_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import mariadb_ai_audit.db as db
    import mariadb_ai_audit.retrieval as retrieval

    monkeypatch.delenv("MARIADB_AI_AUDIT_SEARCHES", raising=False)

    rows = [(1, 10, 0, 0.1, "c")]
    conn = _Conn(rows)

    def _connect(*args: Any, **kwargs: Any) -> _Conn:
        return conn

    monkeypatch.setattr(db.mariadb, "connect", _connect)

    audit_calls: list[dict[str, Any]] = []

    def _log_retrieval_request(**kwargs: Any) -> int:
        audit_calls.append(kwargs)
        return 1

    monkeypatch.setattr(retrieval, "log_retrieval_request", _log_retrieval_request)

    cfg = MariaDBConfig(host="h", port=3306, user="u", password="p", database="d")
    res = search_chunks(cfg=cfg, embedder=_Embedder(), query="q", k=1)

    assert len(res.hits) == 1
    assert audit_calls == []


def test_search_chunks_audits_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import mariadb_ai_audit.db as db
    import mariadb_ai_audit.retrieval as retrieval

    monkeypatch.setenv("MARIADB_AI_AUDIT_SEARCHES", "1")

    rows = [(1, 10, 0, 0.1, "c")]
    conn = _Conn(rows)

    def _connect(*args: Any, **kwargs: Any) -> _Conn:
        return conn

    monkeypatch.setattr(db.mariadb, "connect", _connect)

    audit_calls: list[dict[str, Any]] = []

    def _log_retrieval_request(**kwargs: Any) -> int:
        audit_calls.append(kwargs)
        return 1

    monkeypatch.setattr(retrieval, "log_retrieval_request", _log_retrieval_request)

    cfg = MariaDBConfig(host="h", port=3306, user="u", password="p", database="d")
    res = search_chunks(
        cfg=cfg,
        embedder=_Embedder(),
        query="q",
        k=1,
        source="cli:search-chunks",
    )

    assert len(res.hits) == 1
    assert len(audit_calls) == 1
    assert audit_calls[0]["query"] == "q"
    assert audit_calls[0]["k"] == 1
    assert audit_calls[0]["embedding_model"] == "m"
    assert audit_calls[0]["source"] == "cli:search-chunks"
    assert len(audit_calls[0]["candidates"]) == 1
