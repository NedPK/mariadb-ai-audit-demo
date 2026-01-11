from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from mariadb_ai_audit.config import ConfigError


DEFAULT_OPENAI_CHAT_MODEL = "gpt-4o-mini"


@dataclass(frozen=True)
class OpenAIChatConfig:
    api_key: str
    model: str
    base_url: Optional[str]


def load_openai_chat_config() -> OpenAIChatConfig:
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key is None or api_key.strip() == "":
        raise ConfigError("Missing required environment variable: OPENAI_API_KEY")

    model = os.getenv("OPENAI_CHAT_MODEL") or DEFAULT_OPENAI_CHAT_MODEL
    base_url = os.getenv("OPENAI_BASE_URL")

    return OpenAIChatConfig(api_key=api_key, model=model, base_url=base_url)


class OpenAIChatClient:
    def __init__(self, *, api_key: str, model: str, base_url: str | None = None):
        self._model = model

        import openai

        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = openai.OpenAI(**kwargs)

    @property
    def model(self) -> str:
        return self._model

    def answer_with_context(self, *, question: str, context: str) -> str:
        res = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a careful assistant. Answer the user's question using ONLY the provided context. "
                        "If the context does not contain the answer, respond in ONE LINE with brief justification, "
                        "in the format: 'I don't know — <reason based on the missing context>'."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Context:\n{context}\n\nQuestion:\n{question}",
                },
            ],
            temperature=0.2,
        )

        text = (res.choices[0].message.content or "").strip()
        if text == "":
            return "I don't know — the provided context does not contain the answer."

        lowered = text.strip().lower()
        if lowered in {"i don't know", "i do not know", "unknown", "n/a", "not sure"}:
            return "I don't know — the provided context does not contain the answer."

        return text


def build_openai_chat_client() -> OpenAIChatClient:
    cfg = load_openai_chat_config()
    return OpenAIChatClient(api_key=cfg.api_key, model=cfg.model, base_url=cfg.base_url)
