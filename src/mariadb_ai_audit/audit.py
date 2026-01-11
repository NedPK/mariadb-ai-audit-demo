from __future__ import annotations

import os
from typing import Optional, Protocol

import pymysql
from pymysql import MySQLError


class ChunkHitLike(Protocol):
    chunk_id: int
    document_id: int
    chunk_index: int
    score: float


class AuditError(RuntimeError):
    pass


def retrieval_audit_enabled() -> bool:
    value = os.getenv("MARIADB_AI_AUDIT_SEARCHES")
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def log_retrieval_request(
    *,
    conn: pymysql.Connection,
    user_id: Optional[str],
    feature: Optional[str],
    source: Optional[str],
    query: str,
    k: int,
    embedding_model: str,
    query_embedding_vec_text: str,
    candidates: list[ChunkHitLike],
) -> int:
    if query.strip() == "":
        raise AuditError("Query must not be empty")
    if k <= 0:
        raise AuditError("k must be > 0")
    if embedding_model.strip() == "":
        raise AuditError("embedding_model must not be empty")
    if query_embedding_vec_text.strip() == "":
        raise AuditError("query_embedding_vec_text must not be empty")

    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO retrieval_requests (user_id, feature, source, query, k, embedding_model, query_embedding, candidates_returned) "
                "VALUES (%s, %s, %s, %s, %s, %s, VEC_FromText(%s), %s)",
                (
                    user_id,
                    feature,
                    source,
                    query,
                    k,
                    embedding_model,
                    query_embedding_vec_text,
                    len(candidates),
                ),
            )
            request_id = int(cur.lastrowid)

            if candidates:
                rows: list[tuple[int, int, int, float, int, int]] = []
                rows_with_content: list[tuple[int, int, int, float, int, int, str]] = []
                for rank, hit in enumerate(candidates, start=1):
                    rows_with_content.append(
                        (
                            request_id,
                            rank,
                            int(hit.chunk_id),
                            float(hit.score),
                            int(hit.document_id),
                            int(hit.chunk_index),
                            str(getattr(hit, "content", "")),
                        )
                    )

                cur.executemany(
                    "INSERT INTO retrieval_candidates (request_id, rank, chunk_id, score, document_id, chunk_index, content) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    rows_with_content,
                )

            conn.commit()
            return request_id
        finally:
            cur.close()
    except MySQLError as exc:
        raise AuditError(str(exc)) from exc


def log_retrieval_exposure(
    *,
    conn: pymysql.Connection,
    request_id: int,
    kind: str,
    content: str,
    chunks: list[ChunkHitLike],
) -> int:
    if request_id <= 0:
        raise AuditError("request_id must be > 0")
    if kind.strip() == "":
        raise AuditError("kind must not be empty")
    if content.strip() == "":
        raise AuditError("content must not be empty")

    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO retrieval_exposures (request_id, kind, content, chunks_exposed) VALUES (%s, %s, %s, %s)",
                (request_id, kind, content, len(chunks)),
            )
            exposure_id = int(cur.lastrowid)

            if chunks:
                rows: list[tuple[int, int, int, int, float, int, int, str]] = []
                for rank, hit in enumerate(chunks, start=1):
                    rows.append(
                        (
                            exposure_id,
                            request_id,
                            rank,
                            int(hit.chunk_id),
                            float(hit.score),
                            int(hit.document_id),
                            int(hit.chunk_index),
                            str(getattr(hit, "content", "")),
                        )
                    )

                cur.executemany(
                    "INSERT INTO retrieval_exposure_chunks (exposure_id, request_id, rank, chunk_id, score, document_id, chunk_index, content) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    rows,
                )

            conn.commit()
            return exposure_id
        finally:
            cur.close()
    except MySQLError as exc:
        raise AuditError(str(exc)) from exc
