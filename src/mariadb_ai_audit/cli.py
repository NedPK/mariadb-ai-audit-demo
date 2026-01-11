from __future__ import annotations

import argparse
from pathlib import Path
import os
import sys

from mariadb_ai_audit.config import ConfigError, load_mariadb_config
from mariadb_ai_audit.db import DatabaseError, healthcheck
from mariadb_ai_audit.ingest import IngestError, ingest_docs
from mariadb_ai_audit.ingest_llamaindex import ingest_docs_llamaindex
from mariadb_ai_audit.openai_embedder import build_openai_embedder
from mariadb_ai_audit.retrieval import RetrievalError, search_chunks
from mariadb_ai_audit.schema import SchemaError, apply_schema


def main(argv: list[str] | None = None) -> int:
    """Entry point for the demo CLI.

    Commands:
    - healthcheck: verifies MariaDB connectivity by running SELECT 1.
    - init-db: applies the idempotent demo schema from sql/schema.sql.

    Returns:
    - 0 on success
    - 1 on failure (prints an ERROR message to stderr)
    """
    parser = argparse.ArgumentParser(prog="mariadb-ai-audit")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("healthcheck")
    sub.add_parser("init-db")
    sub.add_parser("show-config")

    ingest = sub.add_parser("ingest-docs")
    ingest.add_argument(
        "--path",
        default="./docs",
        help="Path to a folder containing docs to ingest.",
    )
    ingest.add_argument(
        "--chunk-tokens",
        type=int,
        default=400,
        help="Chunk size in tokens.",
    )
    ingest.add_argument(
        "--overlap-tokens",
        type=int,
        default=50,
        help="Chunk overlap in tokens.",
    )

    ingest_li = sub.add_parser("ingest-docs-llamaindex")
    ingest_li.add_argument(
        "--path",
        default="./docs",
        help="Path to a folder containing docs to ingest.",
    )
    ingest_li.add_argument(
        "--chunk-tokens",
        type=int,
        default=400,
        help="Chunk size in tokens.",
    )
    ingest_li.add_argument(
        "--overlap-tokens",
        type=int,
        default=50,
        help="Chunk overlap in tokens.",
    )

    search = sub.add_parser("search-chunks")
    search.add_argument(
        "--query",
        required=True,
        help="Query text to search for.",
    )
    search.add_argument(
        "--k",
        type=int,
        default=5,
        help="Number of chunks to return.",
    )

    openai_hc = sub.add_parser("openai-healthcheck")
    openai_hc.add_argument(
        "--text",
        default="ping",
        help="Text to embed for the connectivity check.",
    )

    args = parser.parse_args(argv)

    if args.command == "healthcheck":
        try:
            cfg = load_mariadb_config()
            healthcheck(cfg)
        except (ConfigError, DatabaseError) as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            return 1
        sys.stdout.write("OK\n")
        return 0

    if args.command == "init-db":
        try:
            cfg = load_mariadb_config()
            apply_schema(cfg)
        except (ConfigError, DatabaseError, SchemaError) as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            return 1
        sys.stdout.write("OK\n")
        return 0

    if args.command == "show-config":
        try:
            cfg = load_mariadb_config()
        except ConfigError as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            return 1

        sys.stdout.write(f"MARIADB_HOST={cfg.host}\n")
        sys.stdout.write(f"MARIADB_PORT={cfg.port}\n")
        sys.stdout.write(f"MARIADB_USER={cfg.user}\n")
        sys.stdout.write(f"MARIADB_DATABASE={cfg.database}\n")
        sys.stdout.write(
            "MARIADB_AI_AUDIT_SEARCHES=" f"{os.getenv('MARIADB_AI_AUDIT_SEARCHES')}\n"
        )
        sys.stdout.write(
            "MARIADB_AI_AUDIT_DEBUG=" f"{os.getenv('MARIADB_AI_AUDIT_DEBUG')}\n"
        )
        sys.stdout.write(
            "MARIADB_AI_AUDIT_STRICT=" f"{os.getenv('MARIADB_AI_AUDIT_STRICT')}\n"
        )
        return 0

    if args.command == "ingest-docs":
        try:
            cfg = load_mariadb_config()
            embedder = build_openai_embedder()
            res = ingest_docs(
                cfg=cfg,
                embedder=embedder,
                docs_path=Path(args.path),
                extensions={"md", "txt"},
                chunk_tokens=args.chunk_tokens,
                overlap_tokens=args.overlap_tokens,
            )
        except (ConfigError, DatabaseError, IngestError) as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            return 1

        sys.stdout.write(f"OK documents={res.documents} chunks={res.chunks}\n")
        return 0

    if args.command == "ingest-docs-llamaindex":
        try:
            cfg = load_mariadb_config()
            embedder = build_openai_embedder()
            res = ingest_docs_llamaindex(
                cfg=cfg,
                embedder=embedder,
                docs_path=Path(args.path),
                extensions={"md", "txt"},
                chunk_tokens=args.chunk_tokens,
                overlap_tokens=args.overlap_tokens,
            )
        except (ConfigError, DatabaseError, IngestError) as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            return 1

        sys.stdout.write(f"OK documents={res.documents} chunks={res.chunks}\n")
        return 0

    if args.command == "search-chunks":
        try:
            cfg = load_mariadb_config()
            embedder = build_openai_embedder()
            res = search_chunks(
                cfg=cfg,
                embedder=embedder,
                query=args.query,
                k=args.k,
                source="cli:search-chunks",
            )
        except (ConfigError, DatabaseError, RetrievalError) as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            return 1

        for hit in res.hits:
            sys.stdout.write(
                f"chunk_id={hit.chunk_id} document_id={hit.document_id} chunk_index={hit.chunk_index} score={hit.score}\n"
            )
            sys.stdout.write(f"{hit.content}\n\n")

        sys.stdout.write(f"OK request_id={res.request_id} hits={len(res.hits)}\n")
        return 0

    if args.command == "openai-healthcheck":
        try:
            embedder = build_openai_embedder()
            vectors = embedder.embed_texts([args.text])
            if not vectors or not vectors[0]:
                raise RuntimeError("OpenAI returned an empty embedding")
        except Exception as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            return 1

        sys.stdout.write(f"OK model={embedder.model} dim={len(vectors[0])}\n")
        return 0

    sys.stderr.write("ERROR: Unknown command\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
