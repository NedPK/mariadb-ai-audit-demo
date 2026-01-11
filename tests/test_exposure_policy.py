from __future__ import annotations

from dataclasses import dataclass

import pytest

from mariadb_ai_audit.exposure_policy import (
    ExposurePolicyError,
    build_exposure,
    sanitize_question,
)


@dataclass
class _Hit:
    chunk_id: int
    document_id: int
    chunk_index: int
    score: float
    content: str


def test_build_exposure_limits_per_document_and_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MARIADB_AI_DLP_ON_SEND", "0")
    monkeypatch.setenv("MARIADB_AI_MAX_CHUNKS_EXPOSED", "3")
    monkeypatch.setenv("MARIADB_AI_PER_DOCUMENT_CAP", "1")

    hits = [
        _Hit(1, 10, 0, 0.1, "a" * 100),
        _Hit(2, 10, 1, 0.2, "b" * 100),  # same doc, should be dropped by per-doc cap
        _Hit(3, 11, 0, 0.3, "c" * 100),
        _Hit(4, 12, 0, 0.4, "d" * 100),
    ]

    res = build_exposure(hits=hits, question="q")
    assert len(res.exposed_hits) == 3
    assert [h.chunk_id for h in res.exposed_hits] == [1, 3, 4]


def test_build_exposure_redacts_email(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARIADB_AI_DLP_ON_SEND", "1")
    monkeypatch.setenv("MARIADB_AI_DLP_BLOCK_ON_HIGH", "0")

    hits = [
        _Hit(1, 10, 0, 0.1, "contact me at demo.user@example.com please"),
    ]

    res = build_exposure(hits=hits, question="q")
    assert "[REDACTED:EMAIL]" in res.context
    assert res.redaction.categories.get("email", 0) >= 1


def test_build_exposure_blocks_on_private_key_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MARIADB_AI_DLP_ON_SEND", "1")
    monkeypatch.setenv("MARIADB_AI_DLP_BLOCK_ON_HIGH", "1")

    hits = [
        _Hit(
            1,
            10,
            0,
            0.1,
            "DEMO_DLP_BLOCK_MARKER__NOT_A_REAL_SECRET__DO_NOT_USE",
        ),
    ]

    with pytest.raises(ExposurePolicyError):
        build_exposure(hits=hits, question="q")


def test_sanitize_question_redacts_email(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARIADB_AI_DLP_ON_SEND", "1")
    monkeypatch.setenv("MARIADB_AI_DLP_BLOCK_ON_HIGH", "0")

    q, stats = sanitize_question("email me demo.user@example.com")
    assert "[REDACTED:EMAIL]" in q
    assert stats.categories.get("email", 0) >= 1


def test_sanitize_question_blocks_on_private_key_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MARIADB_AI_DLP_ON_SEND", "1")
    monkeypatch.setenv("MARIADB_AI_DLP_BLOCK_ON_HIGH", "1")

    with pytest.raises(ExposurePolicyError):
        sanitize_question("DEMO_DLP_BLOCK_MARKER__NOT_A_REAL_SECRET__DO_NOT_USE")
