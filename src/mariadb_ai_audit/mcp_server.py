from __future__ import annotations

from dataclasses import dataclass
import json
import os
import sys
import time

from mcp.server.fastmcp import FastMCP

from mariadb_ai_audit.config import load_mariadb_config
from mariadb_ai_audit.db import connection
from mariadb_ai_audit.audit import log_retrieval_exposure
from mariadb_ai_audit.exposure_policy import (
    ExposurePolicyError,
    build_exposure,
    sanitize_question,
)
from mariadb_ai_audit.openai_embedder import build_openai_embedder
from mariadb_ai_audit.openai_llm import build_openai_chat_client
from mariadb_ai_audit.retrieval import search_chunks


mcp = FastMCP("Semantic Retrieval Audit", json_response=True)


def _debug_enabled() -> bool:
    value = os.getenv("MARIADB_AI_AUDIT_DEBUG")
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _log(msg: str) -> None:
    if not _debug_enabled():
        return
    sys.stderr.write(f"[mcp] {msg}\n")
    sys.stderr.flush()


@dataclass(frozen=True)
class AskAIResult:
    request_id: int | None
    answer: str
    k: int
    chunks: list[dict]


@dataclass(frozen=True)
class AuditRequestRow:
    id: int
    user_id: str | None
    feature: str | None
    source: str | None
    query: str
    k: int
    embedding_model: str
    candidates_returned: int
    created_at: str


@dataclass(frozen=True)
class AuditDetails:
    request: dict
    candidates: list[dict]
    exposures: list[dict]


def _format_context(hits: list, *, max_chars: int = 12000) -> str:
    parts: list[str] = []
    for hit in hits:
        parts.append(
            "\n".join(
                [
                    f"chunk_id={hit.chunk_id}",
                    f"document_id={hit.document_id}",
                    f"chunk_index={hit.chunk_index}",
                    f"score={hit.score}",
                    "content:",
                    hit.content,
                ]
            )
        )

    text = "\n\n---\n\n".join(parts)
    if len(text) > max_chars:
        return text[:max_chars]
    return text


@mcp.tool()
def ask_ai(
    question: str,
    k: int = 5,
    user_id: str | None = None,
    feature: str | None = None,
) -> AskAIResult:
    t0 = time.monotonic()
    _log(
        f"ask_ai start k={k} user_id={user_id} feature={feature} question_len={len(question)}"
    )
    cfg = load_mariadb_config()

    try:
        sanitized_question, question_dlp = sanitize_question(question)
    except ExposurePolicyError as exc:
        raise RuntimeError(str(exc)) from exc

    _log(
        "ask_ai config "
        f"host={cfg.host} port={cfg.port} database={cfg.database} audit_searches={os.getenv('MARIADB_AI_AUDIT_SEARCHES')}"
    )

    embedder = build_openai_embedder()
    _log(f"ask_ai embedding_model={embedder.model}")

    t_search0 = time.monotonic()
    res = search_chunks(
        cfg=cfg,
        embedder=embedder,
        query=sanitized_question,
        k=k,
        user_id=user_id,
        feature=feature,
        source="mcp:ask_ai",
    )
    _log(
        f"ask_ai search_chunks done hits={len(res.hits)} request_id={res.request_id} "
        f"elapsed_ms={(time.monotonic() - t_search0) * 1000:.0f}"
    )
    if not res.hits:
        raise RuntimeError(
            "No chunks found in the database. Ingest documents first (run_cli.py ingest-docs)."
        )

    try:
        exposure = build_exposure(hits=res.hits, question=sanitized_question)
        exposure.policy["question_dlp_hits_total"] = question_dlp.hits_total
        exposure.policy["question_dlp_categories"] = question_dlp.categories
    except ExposurePolicyError as exc:
        if res.request_id is not None:
            policy: dict[str, object] = {
                "blocked": True,
                "block_reason": str(exc),
                "question_len": len(sanitized_question),
                "question_dlp_hits_total": question_dlp.hits_total,
                "question_dlp_categories": question_dlp.categories,
            }
            stats = getattr(exc, "stats", None)
            if stats is not None:
                policy["dlp_hits_total"] = getattr(stats, "hits_total", 0)
                policy["dlp_categories"] = getattr(stats, "categories", {})

            blocked_hit = getattr(exc, "blocked_hit", None)
            if blocked_hit is not None:
                policy["blocked_hit"] = blocked_hit

            try:
                with connection(cfg) as conn:
                    log_retrieval_exposure(
                        conn=conn,
                        request_id=res.request_id,
                        kind="policy_decision",
                        content=json.dumps(policy),
                        chunks=[],
                    )
            except Exception:
                # Best-effort logging; do not mask the original policy block.
                pass

        msg = str(exc)
        stats = getattr(exc, "stats", None)
        if stats is not None and getattr(stats, "categories", None):
            msg = f"{msg} Categories={getattr(stats, 'categories')}"
        raise RuntimeError(msg) from exc

    context = exposure.context
    _log(
        "ask_ai exposure "
        f"exposed_chunks={len(exposure.exposed_hits)} context_chars={len(context)} dlp_hits={exposure.redaction.hits_total}"
    )
    llm = build_openai_chat_client()
    _log(f"ask_ai chat_model={llm.model}")

    t_llm0 = time.monotonic()
    answer = llm.answer_with_context(question=sanitized_question, context=context)
    _log(
        f"ask_ai llm done answer_chars={len(answer)} elapsed_ms={(time.monotonic() - t_llm0) * 1000:.0f}"
    )

    chunks = []
    for hit in exposure.exposed_hits:
        chunks.append(
            {
                "chunk_id": hit.chunk_id,
                "document_id": hit.document_id,
                "chunk_index": hit.chunk_index,
                "score": hit.score,
                "content": hit.content,
            }
        )

    if res.request_id is not None:
        t_audit0 = time.monotonic()
        with connection(cfg) as conn:
            log_retrieval_exposure(
                conn=conn,
                request_id=res.request_id,
                kind="candidates_json",
                content=json.dumps(chunks),
                chunks=exposure.exposed_hits,
            )
            log_retrieval_exposure(
                conn=conn,
                request_id=res.request_id,
                kind="llm_context",
                content=context,
                chunks=exposure.exposed_hits,
            )
            log_retrieval_exposure(
                conn=conn,
                request_id=res.request_id,
                kind="policy_decision",
                content=json.dumps(exposure.policy),
                chunks=exposure.exposed_hits,
            )
        _log(
            f"ask_ai exposures logged elapsed_ms={(time.monotonic() - t_audit0) * 1000:.0f}"
        )
    else:
        _log("ask_ai request_id is None (auditing disabled or failed)")

    result = AskAIResult(request_id=res.request_id, answer=answer, k=k, chunks=chunks)
    _log(f"ask_ai done total_ms={(time.monotonic() - t0) * 1000:.0f}")
    return result


@mcp.tool()
def list_audit_requests(limit: int = 10) -> list[dict]:
    t0 = time.monotonic()
    _log(f"list_audit_requests start limit={limit}")
    if limit <= 0:
        raise ValueError("limit must be > 0")
    if limit > 100:
        raise ValueError("limit must be <= 100")

    cfg = load_mariadb_config()
    with connection(cfg) as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT id, user_id, feature, source, query, k, embedding_model, candidates_returned, created_at "
                "FROM retrieval_requests ORDER BY id DESC LIMIT %s",
                (limit,),
            )
            rows = cur.fetchall()
        finally:
            cur.close()

    out: list[dict] = []
    for row in rows:
        out.append(
            {
                "id": int(row[0]),
                "user_id": row[1],
                "feature": row[2],
                "source": row[3],
                "query": str(row[4]),
                "k": int(row[5]),
                "embedding_model": str(row[6]),
                "candidates_returned": int(row[7]),
                "created_at": str(row[8]),
            }
        )
    _log(
        f"list_audit_requests done rows={len(out)} total_ms={(time.monotonic() - t0) * 1000:.0f}"
    )
    return out


@mcp.tool()
def get_audit_details(request_id: int | None = None) -> AuditDetails:
    t0 = time.monotonic()
    _log(f"get_audit_details start request_id={request_id}")
    cfg = load_mariadb_config()

    with connection(cfg) as conn:
        cur = conn.cursor()
        try:
            if request_id is None:
                cur.execute(
                    "SELECT id FROM retrieval_requests ORDER BY id DESC LIMIT 1"
                )
                row = cur.fetchone()
                if not row:
                    raise RuntimeError("No audit requests found")
                request_id = int(row[0])
            elif request_id <= 0:
                raise ValueError("request_id must be > 0")

            cur.execute(
                "SELECT id, user_id, feature, source, query, k, embedding_model, candidates_returned, created_at "
                "FROM retrieval_requests WHERE id = %s",
                (request_id,),
            )
            req = cur.fetchone()
            if not req:
                raise RuntimeError(f"request_id not found: {request_id}")

            request = {
                "id": int(req[0]),
                "user_id": req[1],
                "feature": req[2],
                "source": req[3],
                "query": str(req[4]),
                "k": int(req[5]),
                "embedding_model": str(req[6]),
                "candidates_returned": int(req[7]),
                "created_at": str(req[8]),
            }

            cur.execute(
                "SELECT rank, chunk_id, score, document_id, chunk_index, content "
                "FROM retrieval_candidates WHERE request_id = %s ORDER BY rank",
                (request_id,),
            )
            cand_rows = cur.fetchall()
            candidates: list[dict] = []
            for r in cand_rows:
                candidates.append(
                    {
                        "rank": int(r[0]),
                        "chunk_id": int(r[1]),
                        "score": float(r[2]),
                        "document_id": int(r[3]),
                        "chunk_index": int(r[4]),
                        "content": "" if r[5] is None else str(r[5]),
                    }
                )

            cur.execute(
                "SELECT id, request_id, kind, chunks_exposed, created_at, content "
                "FROM retrieval_exposures WHERE request_id = %s ORDER BY id",
                (request_id,),
            )
            exp_rows = cur.fetchall()
            exposures: list[dict] = []
            for r in exp_rows:
                exposures.append(
                    {
                        "id": int(r[0]),
                        "request_id": int(r[1]),
                        "kind": str(r[2]),
                        "chunks_exposed": int(r[3]),
                        "created_at": str(r[4]),
                        "content": str(r[5]),
                    }
                )
        finally:
            cur.close()

    _log(
        f"get_audit_details done request_id={request_id} candidates={len(candidates)} exposures={len(exposures)} "
        f"total_ms={(time.monotonic() - t0) * 1000:.0f}"
    )
    return AuditDetails(request=request, candidates=candidates, exposures=exposures)


def run_server(*, transport: str = "streamable-http") -> None:
    mcp.run(transport=transport)


if __name__ == "__main__":
    run_server()
