# MariaDB AI Audit Demo

A small demo app showing **in-database vector search + auditable RAG** on MariaDB.

- **MariaDB** is the system of record for documents, chunks, embeddings, and the app-level audit trail.
- **MCP** exposes the capabilities as tools (`ask_ai`, `list_audit_requests`, `get_audit_details`).
- **Streamlit** provides a lightweight “copilot-like” UI over MCP.
- **LlamaIndex** is used for ingestion (optional) and safe prompt/context shaping.

## What this demo does

- **Vector search in MariaDB**
  - Chunks are embedded and stored in MariaDB (`VECTOR` column in `chunks`).
  - Retrieval uses MariaDB vector distance functions.

- **Ask AI (RAG) with an audit trail**
  - Each question is logged to `retrieval_requests`.
  - Ranked candidates are logged to `retrieval_candidates`.
  - Exposures (what was actually sent downstream) are logged to `retrieval_exposures` and `retrieval_exposure_chunks`.

- **Filtering (exposure policy + DLP-on-send)**
  - Retrieved chunks are **candidates** (what MariaDB found), but only a smaller subset is **exposed** to the LLM.
  - The app enforces per-document caps and token budgets, redacts common sensitive patterns, and can optionally block on high-severity markers.

- **Explainability / forensics for every answer**
  - For a given `request_id`, you can inspect what was retrieved (candidates) and what was actually exposed to the LLM (exposures).

- **Optional UI + ingestion paths**
  - Streamlit UI (Ask AI + Audit Browser) over MCP.
  - Ingest with a minimal built-in ingestor or an optional LlamaIndex-based pipeline.

## Hosted demo (no local install)

If you just want to try the demo UI, open:

- [nedpk-mariadb-ai-audit-demo.streamlit.app](https://nedpk-mariadb-ai-audit-demo.streamlit.app)

The app has two tabs:

- **Ask AI**: submit a question (requires `user_id`). The server retrieves top-k chunks from MariaDB vector search, applies an exposure policy (filtering/DLP), then calls the LLM. The response includes the `request_id` you can audit.
- **Audit Browser**: browse recent retrieval requests and drill into candidates and exposures (including policy decisions) captured by the application-level audit trail.

## Repository setup

### Clone (includes a docs submodule)

This repo includes `docs/mariadb-docs` as a **git submodule**.

```bash
git clone https://github.com/NedPK/mariadb-ai-audit-demo.git
cd mariadb-ai-audit-demo
git submodule update --init --recursive
```

### Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### Configure environment variables

Create `.env.local` from the example file:

```bash
cp .env.example .env.local
```

Set at minimum:

- `MARIADB_HOST`, `MARIADB_PORT`, `MARIADB_USER`, `MARIADB_PASSWORD`
- `MARIADB_DATABASE` (optional; defaults to `mariadb_ai_audit`)
- `OPENAI_API_KEY`

Optional:

- `OPENAI_BASE_URL` (proxy/gateway)
- `MARIADB_AI_AUDIT_SEARCHES=1` (enable audit logging)
- `MARIADB_AI_AUDIT_DEBUG=1` (verbose logs)

## Run the demo

### 1) Initialize schema

```bash
.venv/bin/python run_cli.py init-db
```

### 2) Ingest docs

This repo includes two document corpora you can ingest:

- `docs/sample/` (small, fast demo corpus)
- `docs/mariadb-docs/` (full MariaDB documentation, pulled in as a git submodule)

Minimal ingestor:

```bash
.venv/bin/python run_cli.py ingest-docs --path ./docs/sample
```

MariaDB docs corpus (submodule):

```bash
.venv/bin/python run_cli.py ingest-docs --path ./docs/mariadb-docs
```

LlamaIndex ingestor (optional):

```bash
MARIADB_AI_AUDIT_DEBUG=1 OPENAI_EMBED_BATCH_SIZE=32 .venv/bin/python run_cli.py ingest-docs-llamaindex --path ./docs/sample
```

LlamaIndex + MariaDB docs corpus (submodule):

```bash
MARIADB_AI_AUDIT_DEBUG=1 OPENAI_EMBED_BATCH_SIZE=32 .venv/bin/python run_cli.py ingest-docs-llamaindex --path ./docs/mariadb-docs
```

### 3) Start the MCP server

```bash
.venv/bin/python run_mcp_server.py
```

Default MCP endpoint:

- `http://127.0.0.1:8000/mcp`

### 4) Run the Streamlit UI

```bash
.venv/bin/python -m streamlit run streamlit_app.py
```

## Audit trail: how to read it

- **Request (`request_id`)**: one retrieval event (one `ask_ai` / vector search request)
  - Stored in `retrieval_requests`

- **Candidates**: the ranked chunks returned by MariaDB vector search
  - Stored in `retrieval_candidates`

- **Exposures**: what the application actually exposed downstream for that request
  - Stored in `retrieval_exposures` (each row has its own **exposure id**)
  - Relationship: **one request_id → many exposure rows**

## Security / demo notes

- `.env.local` is intentionally **gitignored**. Do not commit API keys or DB passwords.
- `docs/sample/sensitive_demo.md` contains demo “sensitive” content to exercise DLP blocking. If you publish this repo publicly, GitHub secret scanning may flag certain patterns (even if they are fake).
- The demo uses `PyMySQL` (pure Python) for MariaDB connectivity to keep deployments simple (e.g. Streamlit Cloud) and avoid native `mariadb_config` build dependencies.

## Demo runbook

See `DEMO.md` for a 5–10 minute presenter script and expected output.
