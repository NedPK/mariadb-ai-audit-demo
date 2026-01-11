from __future__ import annotations

from pathlib import Path

import mariadb

from mariadb_ai_audit.config import MariaDBConfig
from mariadb_ai_audit.db import connection
from mariadb_ai_audit.ingest import IngestError, IngestResult
from mariadb_ai_audit.openai_embedder import OpenAIEmbedder


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(format(x, ".10g") for x in vec) + "]"


def ingest_docs_llamaindex(
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

    try:
        from llama_index.core import SimpleDirectoryReader
        from llama_index.core.node_parser import TokenTextSplitter
    except Exception as exc:
        raise IngestError(
            "LlamaIndex is not installed. Install requirements.txt (or add llama-index) to use ingest-docs-llamaindex."
        ) from exc

    if not docs_path.exists() or not docs_path.is_dir():
        raise IngestError(
            f"Docs path does not exist or is not a directory: {docs_path}"
        )

    required_exts = ["." + e.lstrip(".") for e in sorted(extensions)]

    reader = SimpleDirectoryReader(
        input_dir=str(docs_path),
        recursive=True,
        required_exts=required_exts,
    )
    documents = reader.load_data()
    if not documents:
        raise IngestError(f"No matching files found under: {docs_path}")

    splitter = TokenTextSplitter(chunk_size=chunk_tokens, chunk_overlap=overlap_tokens)
    nodes = splitter.get_nodes_from_documents(documents)
    if not nodes:
        raise IngestError("No chunks produced")

    by_source: dict[str, list[str]] = {}
    for n in nodes:
        text = getattr(n, "text", None)
        if not isinstance(text, str) or not text.strip():
            continue

        md = getattr(n, "metadata", None)
        source = None
        if isinstance(md, dict):
            source = md.get("file_path") or md.get("filename") or md.get("source")
        if not source:
            source = "unknown"

        by_source.setdefault(str(source), []).append(text)

    if not by_source:
        raise IngestError("No chunks produced")

    doc_count = 0
    chunk_count = 0

    with connection(cfg) as conn:
        cur = conn.cursor()
        try:
            for source, chunk_texts in by_source.items():
                chunk_texts = [c for c in chunk_texts if c.strip()]
                if not chunk_texts:
                    continue

                cur.execute(
                    "INSERT INTO documents (source) VALUES (?)",
                    (source,),
                )
                document_id = cur.lastrowid

                vectors = embedder.embed_texts(chunk_texts)
                if len(vectors) != len(chunk_texts):
                    raise IngestError("Embedding count does not match chunk count")

                rows: list[tuple[int, int, str, str]] = []
                for idx, (chunk_text, vec) in enumerate(zip(chunk_texts, vectors)):
                    rows.append(
                        (
                            int(document_id),
                            idx,
                            chunk_text,
                            _vector_literal(vec),
                        )
                    )

                cur.executemany(
                    "INSERT INTO chunks (document_id, chunk_index, content, embedding) VALUES (?, ?, ?, VEC_FromText(?))",
                    rows,
                )

                doc_count += 1
                chunk_count += len(rows)

            conn.commit()
        except mariadb.Error as exc:
            conn.rollback()
            raise IngestError(str(exc)) from exc
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    return IngestResult(documents=doc_count, chunks=chunk_count)
