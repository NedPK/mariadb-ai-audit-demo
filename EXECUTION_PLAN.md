# Execution Plan — Auditable RAG on MariaDB (MCP + Vector Search + Streamlit)

## 0) Guiding Constraints (Non‑Negotiables)

- **System of record**: MariaDB Cloud is the only system of record for documents, embeddings, queries, and the application audit trail.
- **Vector search**: All similarity search is executed in MariaDB (no external vector DB).
- **RAG context**: The model may use only retrieved chunks as context; never fabricate sources.
- **Traceability**: Every interaction is tied to a `request_id` in MariaDB that can be used to reproduce “what was retrieved and why”.
- **MCP-first**: MCP tools are the primary interface; Streamlit is an optional UI over the same MCP tools.
- **Demo-first**: Clarity, correctness, and explainability over completeness.

## 1) Demo Narrative (5–10 minutes)

- **Scene A: Ask a question**
  - User calls `ask_ai(question, k, user_id, feature)`.
  - System creates a new `request_id` in MariaDB.
  - System performs vector search in MariaDB and returns an answer grounded strictly in retrieved chunks.
- **Scene B: Audit the answer (forensics)**
  - User calls `list_audit_requests(limit)` then `get_audit_details(request_id)`.
  - System shows:
    - candidates (ranked chunks + similarity scores)
    - exposures (what was actually exposed to the LLM)
    - policy decision (DLP stats and block reason when applicable)

## 2) Architecture Overview (What we will build)

- **MCP Server**
  - Exposes tools: `ask_ai`, `list_audit_requests`, `get_audit_details`.
  - Uses MariaDB as the system of record for docs, vectors, and audit trail.
- **Streamlit UI (optional)**
  - Calls MCP tools over HTTP.
  - Provides Ask AI and Audit Browser views.
- **MariaDB schema**
  - Tables for:
    - `documents`, `chunks`
    - `retrieval_requests`, `retrieval_candidates`
    - `retrieval_exposures`, `retrieval_exposure_chunks`
- **Embedding + LLM provider**
  - Pluggable via environment variables.
  - No keys in source control.

## 2.1) Exposure Policy + DLP Blocking (Compliance-first)

This demo intentionally distinguishes between:

- **Candidates**: what MariaDB retrieved (ranked chunks)
- **Exposures**: what the application allowed to be exposed downstream (especially to the LLM)

Exposure policy behavior:

- **Subset selection**: only a limited number of chunks are exposed (with per-document caps)
- **Token budgeting**: enforce `MARIADB_AI_MAX_CONTEXT_TOKENS` and `MARIADB_AI_MAX_TOKENS_PER_CHUNK`
- **DLP-on-send**: scan the exact text being sent; redact low-severity patterns; optionally block on high-severity patterns

Blocking behavior (when enabled with `MARIADB_AI_DLP_BLOCK_ON_HIGH=1`):

- The request is **blocked before calling the LLM**.
- The audit trail still records a `policy_decision` exposure including:
  - `blocked: true`
  - `dlp_categories` (what matched)
  - `blocked_hit` (which retrieved chunk triggered the block)

Demo marker used for a public repo:

- `DEMO_DLP_BLOCK_MARKER__NOT_A_REAL_SECRET__DO_NOT_USE`

Expected exposures for one request_id:

- **Allowed** request:
  - `policy_decision`
  - `llm_context`
  - `candidates_json`

- **Blocked** request:
  - `policy_decision` only (no `llm_context`)

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

- **Outcome**: Database tables exist and enforce request-level traceability.
- **Deliverables**:
  - SQL schema creating:
    - `documents`, `chunks` (with `VECTOR` embeddings)
    - `retrieval_requests` (request_id, user_id, feature, query, k, model, timestamps)
    - `retrieval_candidates` (rank, chunk_id, score, document_id, chunk_index, content)
    - `retrieval_exposures` (kind, content, chunks_exposed)
    - `retrieval_exposure_chunks` (chunk-level linkage for each exposure)
  - Idempotent schema setup command.
- **Tests**:
  - Integration test: schema creation and basic inserts.
- **Acceptance criteria**:
  - Given a `request_id`, you can query and list candidates and exposures.

### Milestone 3 — Document ingestion (chunks + embeddings)

- **Outcome**: You can ingest a small demo corpus into MariaDB.
- **Deliverables**:
  - Simple ingestor that:
    - Loads documents from a local folder (or a small set of files)
    - Chunks text deterministically (stable chunk ids)
    - Generates embeddings
    - Writes chunks + embeddings to MariaDB
  - Recommended LlamaIndex ingestion command (with progress + batching):
    - `MARIADB_AI_AUDIT_DEBUG=1 OPENAI_EMBED_BATCH_SIZE=32 python run_cli.py ingest-docs-llamaindex --path ./docs`
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

### Milestone 5 — `ask_ai` MCP tool (RAG + request_id)

- **Outcome**: Full RAG flow: store request, retrieve chunks, generate answer based on context only.
- **Deliverables**:
  - `ask_ai` tool that:
    - Requires `user_id` (for auditability) and accepts an optional `feature` label
    - Stores the request in `retrieval_requests` and candidates in `retrieval_candidates`
    - Applies an exposure policy before calling the LLM:
      - limits which chunks are exposed
      - enforces token budgets
      - runs DLP-on-send and can block on high-severity patterns
    - Logs exposures to `retrieval_exposures`:
      - `policy_decision` (DLP stats, block reason, blocked_hit)
      - `llm_context` (when allowed)
      - `candidates_json`
    - Returns: `request_id`, answer, and exposed chunks
- **Tests**:
  - Unit test: prompt template contains explicit constraints.
  - Integration test: `ask_ai` stores trace + retrieval rows.
- **Acceptance criteria**:
  - For a known query, `retrieval_candidates` rows match returned candidates.
  - Exposures reflect what was actually sent to the LLM.

### Milestone 6 — Audit browser tools (`list_audit_requests`, `get_audit_details`)

- **Outcome**: You can browse recent requests and drill into one `request_id`.
- **Deliverables**:
  - `list_audit_requests(limit)` returns recent `retrieval_requests`.
  - `get_audit_details(request_id)` returns the full audit bundle:
    - request metadata
    - candidates
    - exposures (including policy_decision)
- **Acceptance criteria**:
  - A single `request_id` ties together the request, candidates, and exposures.

### Milestone 7 — Streamlit UI (optional)

- **Outcome**: A copilot-like UI over MCP.
- **Deliverables**:
  - Ask AI view:
    - requires user to enter `user_id` before submitting
    - `feature` is a demo-only selectbox label stored in the audit trail
    - `k` is explained as “Top-k chunks to retrieve”
  - Audit Browser view:
    - request_id is the central control
    - exposures are selectable and show metadata + content

### Milestone 8 — Demo script + guardrails

- **Outcome**: A repeatable 5–10 minute demo run.
- **Deliverables**:
  - A short `DEMO.md` script (optional) describing exact commands/tool calls.
  - Guardrails:
    - clear errors when DB is empty (e.g., no chunks ingested)
    - safe defaults (`top_k`, max context length)
    - logs include `request_id`
- **Tests**:
  - Minimal end-to-end smoke test: ingest -> ask_ai -> list_audit_requests -> get_audit_details.
- **Acceptance criteria**:
  - Demo can be executed end-to-end without manual DB poking.

## 4) Data Contracts (Minimal)

- **`request_id`**: integer identifier returned by `ask_ai` and used to join request, candidates, and exposures.
- **Chunk identity**: stable `chunk_id` (string or integer) used everywhere (retrieval logs, explanations).
- **Candidate record**: `{request_id, chunk_id, score, rank, created_at}`.

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
  - call `ask_ai` once; then inspect via `list_audit_requests` / `get_audit_details`.

## 6) Definition of Done

- **Working MCP-driven RAG flow** with MariaDB vector search.
- **Explainability**: `get_audit_details(request_id)` returns candidates and exposures.
- **Traceability**: All stored and queryable in MariaDB by `request_id`.
- **Demo-ready**: a clean, repeatable 5–10 minute run.
