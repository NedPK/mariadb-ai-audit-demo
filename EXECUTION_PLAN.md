# Execution Plan — Explainable AI on MariaDB Cloud (MCP + Vector Search)

## 0) Guiding Constraints (Non‑Negotiables)

- **System of record**: MariaDB Cloud is the only system of record for documents, embeddings, queries, and traces.
- **Vector search**: All similarity search is executed in MariaDB (no external vector DB).
- **RAG context**: The model may use only retrieved chunks as context; never fabricate sources.
- **Traceability**: Every interaction is tied to a `trace_id` that can be used to reproduce “what was retrieved and why”.
- **MCP-first**: MCP tools are the primary interface (no web UI unless explicitly requested).
- **Demo-first**: Clarity, correctness, and explainability over completeness.

## 1) Demo Narrative (5–10 minutes)

- **Scene A: Ask a question**
  - User calls `ask_ai(question, ...)`.
  - System stores a new `trace_id`.
  - System performs vector search in MariaDB and returns an answer based strictly on retrieved chunks.
- **Scene B: Explain the answer**
  - User calls `explain_answer(trace_id)`.
  - System shows the retrieved chunks, similarity scores, and how they were used.
- **Scene C: Search past questions**
  - User calls `search_past_questions(query)`.
  - System runs vector search over prior questions/prompts (stored in MariaDB) and returns similar past interactions.

## 2) Architecture Overview (What we will build)

- **MCP Server**
  - Exposes tools: `ask_ai`, `explain_answer`, `search_past_questions`.
  - Minimal helpers only if needed (e.g., `ingest_docs`, `healthcheck`).
- **MariaDB schema**
  - Tables for:
    - Document chunks + embeddings
    - Traces (per interaction) with `trace_id`
    - Retrieval events (per trace): chunk ids + similarity scores + rank
    - Prompts/questions + embeddings (for `search_past_questions`)
- **Embedding + LLM provider**
  - Pluggable via environment variables.
  - No keys in source control.

## 3) Implementation Milestones (Step-by-step; code + tests each step)

### Milestone 1 — Project skeleton + configuration

- **Outcome**: You can start the MCP server locally; it can connect to MariaDB Cloud.
- **Deliverables**:
  - Config loader for DB DSN + AI provider settings via env vars.
  - DB connection module (single place).
  - Basic health tool/command path that checks DB connectivity.
- **Tests**:
  - Unit test: configuration parsing and required env var validation.
  - Integration smoke test (optional): DB connect + `SELECT 1`.
- **Acceptance criteria**:
  - Failing fast with clear errors when env vars are missing.

### Milestone 2 — MariaDB schema + migrations/bootstrap

- **Outcome**: Database tables exist and enforce traceability.
- **Deliverables**:
  - SQL schema (or simple migration script) creating:
    - `documents` (optional) / `chunks`
    - `chunk_embeddings` or `chunks` with embedding column
    - `traces`
    - `trace_retrievals` (trace_id, chunk_id, score, rank, metadata)
    - `questions` (question text, embedding, created_at, trace_id)
  - Idempotent schema setup command.
- **Tests**:
  - Integration test: schema creation and basic inserts.
- **Acceptance criteria**:
  - Given a `trace_id`, you can query and list retrieval rows.

### Milestone 3 — Document ingestion (chunks + embeddings)

- **Outcome**: You can ingest a small demo corpus into MariaDB.
- **Deliverables**:
  - Simple ingestor that:
    - Loads documents from a local folder (or a small set of files)
    - Chunks text deterministically (stable chunk ids)
    - Generates embeddings
    - Writes chunks + embeddings to MariaDB
  - Optional MCP helper tool: `ingest_docs(path, ...)` (only if it helps the demo).
- **Tests**:
  - Unit test: chunking stability (same input => same chunk boundaries/ids).
  - Integration test: ingest inserts expected rows.
- **Acceptance criteria**:
  - You can ingest and then retrieve rows from `chunks`.

### Milestone 4 — Retrieval in MariaDB (vector similarity search)

- **Outcome**: Given a query embedding, MariaDB returns top‑K relevant chunks with scores.
- **Deliverables**:
  - SQL query for similarity search (top‑K) using MariaDB vector capabilities.
  - Retrieval function returning:
    - chunk_id
    - chunk text
    - similarity score
    - any doc metadata
- **Tests**:
  - Integration test: retrieval returns deterministic shape; topK count respected.
- **Acceptance criteria**:
  - No external retrieval paths; retrieval is visibly “from MariaDB”.

### Milestone 5 — `ask_ai` MCP tool (RAG + trace_id)

- **Outcome**: Full RAG flow: store trace, retrieve chunks, generate answer based on context only.
- **Deliverables**:
  - `ask_ai` tool that:
    - Creates `trace_id`
    - Stores the question (+ optional embedding)
    - Retrieves top‑K chunks from MariaDB
    - Stores retrieval events (`trace_retrievals`)
    - Calls LLM with a strict prompt template that:
      - forbids using non-retrieved knowledge
      - returns an answer and optionally short citations (chunk ids)
    - Returns: `trace_id`, answer, and minimal metadata
- **Tests**:
  - Unit test: prompt template contains explicit constraints.
  - Integration test: `ask_ai` stores trace + retrieval rows.
- **Acceptance criteria**:
  - For a known query, `trace_retrievals` rows match returned chunks.

### Milestone 6 — `explain_answer` MCP tool (explainability)

- **Outcome**: You can explain any answer by `trace_id`.
- **Deliverables**:
  - `explain_answer(trace_id)` tool that returns:
    - original question
    - retrieved chunks (text, chunk_id)
    - similarity scores + rank
    - (optional) final LLM prompt context block used
- **Tests**:
  - Integration test: calling `explain_answer` after `ask_ai` returns consistent data.
- **Acceptance criteria**:
  - Explanation contains explicit chunk references and scores.

### Milestone 7 — `search_past_questions` MCP tool (semantic search over history)

- **Outcome**: You can semantically search prior prompts/questions stored in MariaDB.
- **Deliverables**:
  - Store question embeddings for each `ask_ai` call.
  - `search_past_questions(query, top_k)` tool:
    - embeds query
    - runs vector search against stored question embeddings
    - returns prior questions + trace_ids + timestamps
- **Tests**:
  - Integration test: after multiple `ask_ai` calls, search returns nearest questions.
- **Acceptance criteria**:
  - Result items contain `trace_id` enabling immediate `explain_answer` follow-up.

### Milestone 8 — Demo script + guardrails

- **Outcome**: A repeatable 5–10 minute demo run.
- **Deliverables**:
  - A short `DEMO.md` script (optional) describing exact commands/tool calls.
  - Guardrails:
    - clear errors when DB is empty (e.g., no chunks ingested)
    - safe defaults (`top_k`, max context length)
    - logs include `trace_id`
- **Tests**:
  - Minimal end-to-end smoke test: ingest -> ask_ai -> explain_answer -> search.
- **Acceptance criteria**:
  - Demo can be executed end-to-end without manual DB poking.

## 4) Data Contracts (Minimal)

- **`trace_id`**: UUID string returned by `ask_ai` and accepted by `explain_answer`.
- **Chunk identity**: stable `chunk_id` (string or integer) used everywhere (retrieval logs, explanations).
- **Retrieval record**: `{trace_id, chunk_id, score, rank, created_at}`.

## 5) Operational Checklist (Before demo)

- **Environment**:
  - `MARIADB_HOST`, `MARIADB_PORT`, `MARIADB_USER`, `MARIADB_PASSWORD`, `MARIADB_DATABASE`
  - AI provider keys (if needed) as env vars only

- **Run it (using local virtualenv)**:
  - Install deps:
    - `.venv/bin/python -m pip install -r requirements.txt`
  - Run tests:
    - `.venv/bin/python -m pytest -q`
  - Create your local env file (one-time):
    - `cp .env.example .env.local`
    - Edit `.env.local` and fill in `MARIADB_USER`, `MARIADB_PASSWORD`, `MARIADB_DATABASE` (and host/port if needed)
  - Run CLI healthcheck:
    - `.venv/bin/python run_cli.py healthcheck`
- **DB ready**:
  - schema applied
  - demo corpus ingested
- **Smoke run**:
  - call `ask_ai` once; then `explain_answer(trace_id)`; then `search_past_questions`.

## 6) Definition of Done

- **Working MCP-driven RAG flow** with MariaDB vector search.
- **Explainability**: `explain_answer(trace_id)` returns retrieved chunks and similarity scores.
- **Traceability**: All stored and queryable in MariaDB by `trace_id`.
- **Demo-ready**: a clean, repeatable 5–10 minute run.
