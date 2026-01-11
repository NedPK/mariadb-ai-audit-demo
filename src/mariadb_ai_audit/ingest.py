from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pymysql import MySQLError

from mariadb_ai_audit.config import MariaDBConfig
from mariadb_ai_audit.db import connection
from mariadb_ai_audit.openai_embedder import OpenAIEmbedder


class IngestError(RuntimeError):
    pass


@dataclass(frozen=True)
class IngestResult:
    documents: int
    chunks: int


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(format(x, ".10g") for x in vec) + "]"


def _iter_files(root: Path, *, extensions: set[str]) -> list[Path]:
    if not root.exists() or not root.is_dir():
        raise IngestError(f"Docs path does not exist or is not a directory: {root}")

    paths: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower().lstrip(".") in extensions:
            paths.append(p)

    paths.sort()
    return paths


def _chunk_text_by_tokens(
    text: str,
    *,
    encoding_name: str,
    chunk_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    if chunk_tokens <= 0:
        raise IngestError("chunk_tokens must be > 0")
    if overlap_tokens < 0:
        raise IngestError("overlap_tokens must be >= 0")
    if overlap_tokens >= chunk_tokens:
        raise IngestError("overlap_tokens must be < chunk_tokens")

    import tiktoken

    enc = tiktoken.get_encoding(encoding_name)
    tokens = enc.encode(text)
    if not tokens:
        return []

    chunks: list[str] = []
    i = 0
    step = chunk_tokens - overlap_tokens
    while i < len(tokens):
        window = tokens[i : i + chunk_tokens]
        chunks.append(enc.decode(window))
        i += step

    return chunks


def _encoding_name_for_openai_model(model: str) -> str:
    import tiktoken

    try:
        enc = tiktoken.encoding_for_model(model)
        return enc.name
    except KeyError:
        return "cl100k_base"


def ingest_docs(
    *,
    cfg: MariaDBConfig,
    embedder: OpenAIEmbedder,
    docs_path: Path,
    extensions: set[str],
    chunk_tokens: int = 400,
    overlap_tokens: int = 50,
) -> IngestResult:
    if not cfg.database:
        raise IngestError("MARIADB_DATABASE must be set to ingest docs")

    files = _iter_files(docs_path, extensions=extensions)
    if not files:
        raise IngestError(f"No matching files found under: {docs_path}")

    encoding_name = _encoding_name_for_openai_model(embedder.model)

    doc_count = 0
    chunk_count = 0

    with connection(cfg) as conn:
        cur = conn.cursor()
        try:
            for path in files:
                content = path.read_text(encoding="utf-8")
                chunks = _chunk_text_by_tokens(
                    content,
                    encoding_name=encoding_name,
                    chunk_tokens=chunk_tokens,
                    overlap_tokens=overlap_tokens,
                )
                if not chunks:
                    continue

                rel = str(path)
                cur.execute(
                    "INSERT INTO documents (source) VALUES (%s)",
                    (rel,),
                )
                document_id = cur.lastrowid

                vectors = embedder.embed_texts(chunks)
                if len(vectors) != len(chunks):
                    raise IngestError("Embedding count does not match chunk count")

                rows: list[tuple[int, int, str, str]] = []
                for idx, (chunk_text, vec) in enumerate(zip(chunks, vectors)):
                    rows.append(
                        (
                            int(document_id),
                            idx,
                            chunk_text,
                            _vector_literal(vec),
                        )
                    )

                cur.executemany(
                    "INSERT INTO chunks (document_id, chunk_index, content, embedding) VALUES (%s, %s, %s, VEC_FromText(%s))",
                    rows,
                )

                doc_count += 1
                chunk_count += len(rows)

            conn.commit()
        except MySQLError as exc:
            conn.rollback()
            raise IngestError(str(exc)) from exc
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    return IngestResult(documents=doc_count, chunks=chunk_count)
