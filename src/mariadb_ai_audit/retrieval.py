from __future__ import annotations

from dataclasses import dataclass
import os
import sys

import mariadb

from mariadb_ai_audit.audit import log_retrieval_request, retrieval_audit_enabled
from mariadb_ai_audit.config import MariaDBConfig
from mariadb_ai_audit.db import connection
from mariadb_ai_audit.ingest import _vector_literal
from mariadb_ai_audit.openai_embedder import OpenAIEmbedder


class RetrievalError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChunkHit:
    chunk_id: int
    document_id: int
    chunk_index: int
    score: float
    content: str


@dataclass(frozen=True)
class RetrievalResult:
    request_id: int | None
    hits: list[ChunkHit]


def search_chunks(
    *,
    cfg: MariaDBConfig,
    embedder: OpenAIEmbedder,
    query: str,
    k: int = 5,
    user_id: str | None = None,
    feature: str | None = None,
    source: str | None = None,
) -> RetrievalResult:
    if not cfg.database:
        raise RetrievalError("MARIADB_DATABASE must be set to search chunks")

    if query.strip() == "":
        raise RetrievalError("Query must not be empty")

    if k <= 0:
        raise RetrievalError("k must be > 0")

    qvecs = embedder.embed_texts([query])
    if not qvecs or not qvecs[0]:
        raise RetrievalError("Embedding returned empty vector")

    qvec_text = _vector_literal(qvecs[0])

    sql = (
        "SELECT id, document_id, chunk_index, "
        "VEC_DISTANCE_COSINE(embedding, VEC_FromText(?)) AS score, "
        "content "
        "FROM chunks "
        "ORDER BY score ASC "
        "LIMIT ?"
    )

    try:
        with connection(cfg) as conn:
            cur = conn.cursor()
            try:
                cur.execute(sql, (qvec_text, k))
                rows = cur.fetchall()
            finally:
                cur.close()
    except mariadb.Error as exc:
        raise RetrievalError(str(exc)) from exc

    hits: list[ChunkHit] = []
    for row in rows:
        hits.append(
            ChunkHit(
                chunk_id=int(row[0]),
                document_id=int(row[1]),
                chunk_index=int(row[2]),
                score=float(row[3]),
                content=str(row[4]),
            )
        )

    request_id: int | None = None
    if retrieval_audit_enabled():
        try:
            with connection(cfg) as conn:
                request_id = log_retrieval_request(
                    conn=conn,
                    user_id=user_id,
                    feature=feature,
                    source=source,
                    query=query,
                    k=k,
                    embedding_model=embedder.model,
                    query_embedding_vec_text=qvec_text,
                    candidates=hits,
                )
        except Exception as exc:
            if os.getenv("MARIADB_AI_AUDIT_STRICT", "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }:
                raise
            if os.getenv("MARIADB_AI_AUDIT_DEBUG", "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }:
                sys.stderr.write(f"AUDIT ERROR: {exc}\n")

    return RetrievalResult(request_id=request_id, hits=hits)
