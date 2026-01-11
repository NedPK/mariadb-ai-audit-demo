from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


def _parse_line(line: str) -> tuple[str, str] | None:
    """Parse a single dotenv line.

    Supports:
    - KEY=VALUE
    - export KEY=VALUE
    - optional surrounding single/double quotes
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    if stripped.startswith("export "):
        stripped = stripped[len("export ") :].lstrip()

    if "=" not in stripped:
        return None

    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip()

    if not key:
        return None

    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1]

    return key, value


def load_dotenv(
    paths: Iterable[str | Path] = (".env.local", ".env"),
    *,
    override: bool = False,
) -> None:
    """Load environment variables from dotenv-style files.

    Existing environment variables win by default; set override=True to replace.
    """
    for p in paths:
        path = Path(p)
        if not path.is_file():
            continue

        for line in path.read_text(encoding="utf-8").splitlines():
            parsed = _parse_line(line)
            if parsed is None:
                continue
            key, value = parsed
            if override or os.getenv(key) in (None, ""):
                os.environ[key] = value
