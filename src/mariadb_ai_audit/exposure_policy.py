from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Any, Iterable

try:
    from llama_index.core.schema import TextNode
except Exception:  # pragma: no cover
    TextNode = None  # type: ignore

import tiktoken


class ExposurePolicyError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        stats: "RedactionStats | None" = None,
        blocked_hit: dict[str, object] | None = None,
    ):
        super().__init__(message)
        self.stats = stats
        self.blocked_hit = blocked_hit


@dataclass(frozen=True)
class RedactionStats:
    hits_total: int
    categories: dict[str, int]
    blocked: bool


@dataclass(frozen=True)
class ExposureResult:
    context: str
    exposed_hits: list[Any]
    redaction: RedactionStats
    policy: dict[str, Any]


@dataclass(frozen=True)
class SanitizedHit:
    chunk_id: int
    document_id: int
    chunk_index: int
    score: float
    content: str


def sanitize_question(question: str) -> tuple[str, RedactionStats]:
    """Sanitize a user question before it is sent to external services.

    Compliance goal: prevent sensitive strings in user input (e.g. secrets pasted into a prompt)
    from being sent to embedding or chat providers.

    Uses the same env-controlled DLP settings as context redaction.
    """

    text, stats = _redact_text(question)
    if stats.blocked:
        raise ExposurePolicyError(
            "Blocked by DLP policy (high-severity sensitive content detected in user question).",
            stats=stats,
        )
    return text, stats


_DEFAULT_MAX_CONTEXT_TOKENS = 2500
_DEFAULT_MAX_TOKENS_PER_CHUNK = 600
_DEFAULT_MAX_CHUNKS_EXPOSED = 5
_DEFAULT_PER_DOCUMENT_CAP = 2


_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_RE = re.compile(
    r"\b(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3}[\s.-]?\d{4}\b"
)
_AWS_KEY_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_PRIVATE_KEY_RE = re.compile(
    r"\bDEMO_DLP_BLOCK_MARKER__NOT_A_REAL_SECRET__DO_NOT_USE\b"
)
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")


def _bool_env(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    try:
        return int(v)
    except Exception as exc:
        raise ExposurePolicyError(f"{name} must be an integer") from exc


def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def _truncate_tokens(text: str, *, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    enc = _encoding()
    tokens = enc.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return enc.decode(tokens[:max_tokens])


def _redact_text(text: str) -> tuple[str, RedactionStats]:
    dlp_enabled = _bool_env("MARIADB_AI_DLP_ON_SEND", True)
    block_on_high = _bool_env("MARIADB_AI_DLP_BLOCK_ON_HIGH", False)

    if not dlp_enabled:
        return text, RedactionStats(hits_total=0, categories={}, blocked=False)

    categories: dict[str, int] = {}

    def _sub(rx: re.Pattern[str], category: str, repl: str) -> None:
        nonlocal text
        matches = list(rx.finditer(text))
        if not matches:
            return
        categories[category] = categories.get(category, 0) + len(matches)
        text = rx.sub(repl, text)

    _sub(_EMAIL_RE, "email", "[REDACTED:EMAIL]")
    _sub(_PHONE_RE, "phone", "[REDACTED:PHONE]")
    _sub(_AWS_KEY_RE, "aws_key", "[REDACTED:AWS_KEY]")
    _sub(_JWT_RE, "jwt", "[REDACTED:JWT]")

    high_hits_before = len(categories)
    _sub(_PRIVATE_KEY_RE, "private_key", "[REDACTED:PRIVATE_KEY]")
    high_hits_after = len(categories)

    blocked = False
    if block_on_high and high_hits_after > high_hits_before:
        blocked = True

    return (
        text,
        RedactionStats(
            hits_total=sum(categories.values()),
            categories=categories,
            blocked=blocked,
        ),
    )


def _merge_redaction_stats(items: list[RedactionStats]) -> RedactionStats:
    categories: dict[str, int] = {}
    hits_total = 0
    blocked = False
    for s in items:
        hits_total += int(s.hits_total)
        blocked = blocked or bool(s.blocked)
        for k, v in s.categories.items():
            categories[k] = categories.get(k, 0) + int(v)
    return RedactionStats(hits_total=hits_total, categories=categories, blocked=blocked)


def _iterable_take(items: Iterable[Any], n: int) -> list[Any]:
    out: list[Any] = []
    if n <= 0:
        return out
    for it in items:
        out.append(it)
        if len(out) >= n:
            break
    return out


def build_exposure(
    *,
    hits: list[Any],
    question: str,
    max_context_tokens: int | None = None,
    max_tokens_per_chunk: int | None = None,
    max_chunks_exposed: int | None = None,
    per_document_cap: int | None = None,
) -> ExposureResult:
    """Build an LLM-safe context string from retrieved hits.

    This is a compliance-first exposure policy:

    - Select an exposed subset (limits + per-document cap)
    - Apply token truncation
    - Run DLP/redaction on the exact text being sent

    `hits` must contain objects with: chunk_id, document_id, chunk_index, score, content.
    """

    if TextNode is None:
        raise ExposurePolicyError(
            "LlamaIndex is not available. Install requirements.txt to enable exposure policy."
        )

    max_context_tokens = max_context_tokens or _int_env(
        "MARIADB_AI_MAX_CONTEXT_TOKENS", _DEFAULT_MAX_CONTEXT_TOKENS
    )
    max_tokens_per_chunk = max_tokens_per_chunk or _int_env(
        "MARIADB_AI_MAX_TOKENS_PER_CHUNK", _DEFAULT_MAX_TOKENS_PER_CHUNK
    )
    max_chunks_exposed = max_chunks_exposed or _int_env(
        "MARIADB_AI_MAX_CHUNKS_EXPOSED", _DEFAULT_MAX_CHUNKS_EXPOSED
    )
    per_document_cap = per_document_cap or _int_env(
        "MARIADB_AI_PER_DOCUMENT_CAP", _DEFAULT_PER_DOCUMENT_CAP
    )

    # Convert to LlamaIndex nodes (gives us a stable structure + metadata).
    nodes: list[TextNode] = []
    for h in hits:
        text = str(getattr(h, "content", ""))
        nodes.append(
            TextNode(
                id_=str(getattr(h, "chunk_id")),
                text=text,
                metadata={
                    "chunk_id": int(getattr(h, "chunk_id")),
                    "document_id": int(getattr(h, "document_id")),
                    "chunk_index": int(getattr(h, "chunk_index")),
                    "score": float(getattr(h, "score")),
                },
            )
        )

    # Subset selection (minimize exposure).
    exposed_raw: list[Any] = []
    per_doc_counts: dict[int, int] = {}
    for h in hits:
        doc_id = int(getattr(h, "document_id"))
        count = per_doc_counts.get(doc_id, 0)
        if count >= per_document_cap:
            continue
        exposed_raw.append(h)
        per_doc_counts[doc_id] = count + 1
        if len(exposed_raw) >= max_chunks_exposed:
            break

    # Truncate and redact per chunk so what we log as "exposed" matches what was actually exposed.
    per_chunk_stats: list[RedactionStats] = []
    exposed: list[SanitizedHit] = []
    for h in exposed_raw:
        raw = str(getattr(h, "content", ""))
        truncated = _truncate_tokens(raw, max_tokens=max_tokens_per_chunk)
        redacted, stats = _redact_text(truncated)
        per_chunk_stats.append(stats)
        if stats.blocked:
            blocked_hit = {
                "chunk_id": int(getattr(h, "chunk_id")),
                "document_id": int(getattr(h, "document_id")),
                "chunk_index": int(getattr(h, "chunk_index")),
                "score": float(getattr(h, "score")),
            }
            raise ExposurePolicyError(
                "Blocked by DLP policy (high-severity sensitive content detected in retrieved context).",
                stats=stats,
                blocked_hit=blocked_hit,
            )

        exposed.append(
            SanitizedHit(
                chunk_id=int(getattr(h, "chunk_id")),
                document_id=int(getattr(h, "document_id")),
                chunk_index=int(getattr(h, "chunk_index")),
                score=float(getattr(h, "score")),
                content=redacted,
            )
        )

    # Build a context under the global token budget.
    enc = _encoding()
    budget = max_context_tokens
    context_parts: list[str] = []

    for h in exposed:
        # include minimal metadata header for traceability
        header = (
            f"chunk_id={int(getattr(h, 'chunk_id'))}\n"
            f"document_id={int(getattr(h, 'document_id'))}\n"
            f"chunk_index={int(getattr(h, 'chunk_index'))}\n"
            f"score={float(getattr(h, 'score'))}\n"
            "content:\n"
        )
        content_text = str(getattr(h, "content", ""))
        block = header + content_text

        # Enforce global budget (token-based)
        block_tokens = len(enc.encode(block))
        if block_tokens > budget:
            # Try to fit a smaller truncated content
            remaining = max(0, budget - len(enc.encode(header)) - 10)
            if remaining <= 0:
                break
            block = header + _truncate_tokens(content_text, max_tokens=remaining)
            block_tokens = len(enc.encode(block))
            if block_tokens <= 0 or block_tokens > budget:
                break

        context_parts.append(block)
        budget -= block_tokens
        if budget <= 0:
            break

    context = "\n\n---\n\n".join(context_parts)

    # DLP-on-send: run again on the exact final context as belt-and-suspenders.
    # (This can catch things introduced by formatting or missed by per-chunk scans.)
    redacted_context, context_stats = _redact_text(context)
    if context_stats.blocked:
        raise ExposurePolicyError(
            "Blocked by DLP policy (high-severity sensitive content detected in retrieved context).",
            stats=context_stats,
        )

    redaction = _merge_redaction_stats(per_chunk_stats + [context_stats])

    policy: dict[str, Any] = {
        "question_len": len(question),
        "retrieved_candidates": len(hits),
        "exposed_chunks": len(exposed),
        "max_context_tokens": max_context_tokens,
        "max_tokens_per_chunk": max_tokens_per_chunk,
        "max_chunks_exposed": max_chunks_exposed,
        "per_document_cap": per_document_cap,
        "dlp_on_send": _bool_env("MARIADB_AI_DLP_ON_SEND", True),
        "dlp_block_on_high": _bool_env("MARIADB_AI_DLP_BLOCK_ON_HIGH", False),
        "dlp_hits_total": redaction.hits_total,
        "dlp_categories": redaction.categories,
    }

    return ExposureResult(
        context=redacted_context,
        exposed_hits=exposed,
        redaction=redaction,
        policy=policy,
    )
