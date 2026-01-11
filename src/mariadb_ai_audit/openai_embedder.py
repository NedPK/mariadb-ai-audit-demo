from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from mariadb_ai_audit.config import ConfigError


DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"


@dataclass(frozen=True)
class OpenAIEmbeddingConfig:
    api_key: str
    model: str
    base_url: Optional[str]


def load_openai_embedding_config() -> OpenAIEmbeddingConfig:
    """Load OpenAI embedding configuration from environment variables.

    Required:
    - OPENAI_API_KEY

    Optional:
    - OPENAI_EMBEDDING_MODEL (defaults to text-embedding-3-small)
    - OPENAI_BASE_URL (for proxies / custom gateways)
    """

    api_key = os.getenv("OPENAI_API_KEY")
    if api_key is None or api_key.strip() == "":
        raise ConfigError("Missing required environment variable: OPENAI_API_KEY")

    model = os.getenv("OPENAI_EMBEDDING_MODEL") or DEFAULT_OPENAI_EMBEDDING_MODEL
    base_url = os.getenv("OPENAI_BASE_URL")

    return OpenAIEmbeddingConfig(api_key=api_key, model=model, base_url=base_url)


class OpenAIEmbedder:
    """Small wrapper around the OpenAI embeddings API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_OPENAI_EMBEDDING_MODEL,
        base_url: str | None = None,
    ):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url

        import openai  # imported here to keep module import lightweight

        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = openai.OpenAI(**kwargs)

    @property
    def model(self) -> str:
        return self._model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts and return a list of vectors."""
        if not texts:
            return []

        res = self._client.embeddings.create(model=self._model, input=texts)
        # Keep ordering stable: OpenAI returns results aligned to inputs.
        return [item.embedding for item in res.data]


def build_openai_embedder() -> OpenAIEmbedder:
    """Create an OpenAIEmbedder from environment variables."""
    cfg = load_openai_embedding_config()
    return OpenAIEmbedder(api_key=cfg.api_key, model=cfg.model, base_url=cfg.base_url)
