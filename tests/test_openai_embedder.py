from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from mariadb_ai_audit.config import ConfigError
from mariadb_ai_audit.openai_embedder import (
    DEFAULT_OPENAI_EMBEDDING_MODEL,
    OpenAIEmbedder,
    load_openai_embedding_config,
)


def test_load_openai_embedding_config_missing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_EMBEDDING_MODEL", raising=False)

    with pytest.raises(ConfigError) as exc:
        load_openai_embedding_config()

    assert "OPENAI_API_KEY" in str(exc.value)


def test_load_openai_embedding_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.delenv("OPENAI_EMBEDDING_MODEL", raising=False)

    cfg = load_openai_embedding_config()

    assert cfg.api_key == "k"
    assert cfg.model == DEFAULT_OPENAI_EMBEDDING_MODEL


def test_openai_embedder_embed_texts(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch the OpenAI client constructed inside OpenAIEmbedder.
    import mariadb_ai_audit.openai_embedder as mod

    @dataclass
    class _Item:
        embedding: list[float]

    @dataclass
    class _Res:
        data: list[_Item]

    class _Embeddings:
        def create(self, *, model: str, input: list[str]) -> _Res:
            assert model == "m"
            assert input == ["a", "b"]
            return _Res(data=[_Item([1.0, 2.0]), _Item([3.0, 4.0])])

    class _Client:
        def __init__(self, **kwargs: Any) -> None:
            self.embeddings = _Embeddings()

    class _OpenAI:
        def __init__(self, **kwargs: Any) -> None:
            self._kwargs = kwargs

        def __call__(self, **kwargs: Any) -> _Client:
            return _Client(**kwargs)

    # openai.OpenAI is used as a constructor
    class _OpenAIModule:
        OpenAI = _Client

    monkeypatch.setitem(__import__("sys").modules, "openai", _OpenAIModule())

    emb = OpenAIEmbedder(api_key="k", model="m")
    assert emb.embed_texts(["a", "b"]) == [[1.0, 2.0], [3.0, 4.0]]
