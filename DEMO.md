# Demo Runbook — MariaDB Cloud AI Audit (Vector Search + MCP)

This is a repeatable 5–10 minute demo **runbook** (copy/paste friendly) for an **application-level AI audit trail**.

Purpose:

- Provide **richer logging and auditability** backed by MariaDB Cloud AI/RAG than a database general log or traditional audit log can offer
- Capture the *AI-specific* facts you actually need for governance and incident response: what was searched, what came back, and what the model saw

- MariaDB Cloud is the **system of record** for documents, chunks, embeddings, and the app-level audit trail
- Similarity search is executed **inside MariaDB** using native vector capabilities (no external vector database)
- Every AI answer has a **forensic trail**: what the user asked, what was retrieved, and what was exposed to the LLM

What you’ll demo:

- **Semantic retrieval (vector search) over internal docs**
  - Functionality: query a doc corpus and get top-K relevant chunks with similarity scores
  - Tech: MariaDB `VECTOR` embeddings in `chunks` + MariaDB vector distance functions; embeddings generated via OpenAI
- **Ask AI (RAG) with a full audit trail**
  - Functionality: ask a question and get an answer grounded in retrieved chunks
  - Tech: MCP tool `ask_ai` (calls MariaDB vector search + OpenAI chat) and logs exposures
- **Filtering functionality (exposure policy + DLP-on-send)**
  - Functionality: an application-layer filtering step between retrieval and the LLM
    - Retrieved chunks are **candidates** (what MariaDB found)
    - A smaller, safer subset is **exposed** (what the app allows the LLM to see)
  - Behavior:
    - Input sanitization (question): scan/redact before sending to embeddings/chat; optionally block on high-severity patterns
    - Subset selection: limit total exposed chunks and cap per-document exposure
    - Token budgeting: enforce global context and per-chunk token limits
    - DLP-on-send: scan the exact exposed text; redact low/medium patterns; optionally block exposure on high-severity markers
  - Env vars:
    - `MARIADB_AI_DLP_ON_SEND=1` (default)
    - `MARIADB_AI_DLP_BLOCK_ON_HIGH=1`
    - `MARIADB_AI_MAX_CONTEXT_TOKENS` (default `2500`)
    - `MARIADB_AI_MAX_TOKENS_PER_CHUNK` (default `600`)
    - `MARIADB_AI_MAX_CHUNKS_EXPOSED` (default `5`)
    - `MARIADB_AI_PER_DOCUMENT_CAP` (default `2`)
  - How to demo blocking:
    - Ensure `docs/sample/sensitive_demo.md` is ingested
    - Ask with keyword: `DEMO_SENSITIVE_PRIVATE_KEY_WIDGET`
    - Enable blocking: `MARIADB_AI_DLP_ON_SEND=1` and `MARIADB_AI_DLP_BLOCK_ON_HIGH=1`
- **Explainability / forensics for every answer**
  - Functionality: list recent requests and drill into one request_id to see candidates + what was exposed to the LLM
  - Tech: MCP tools `list_audit_requests` + `get_audit_details` returning the full audit bundle from MariaDB:
    - request metadata from `retrieval_requests` (user_id, feature, source, query, k, model)
      - Value: attribute usage to a user/feature, reproduce a run, and answer “who asked what, from where, and with which settings?”
    - ranked vector candidates from `retrieval_candidates` (chunk_id, score, rank)
      - Value: explain “why this answer” (which chunks were considered) and debug retrieval quality/regressions using scores and rank.
    - exposures from `retrieval_exposures` (including `candidates_json` and `llm_context`)
      - Value: prove what was actually sent to the model (critical for compliance, privacy reviews, and incident response).
    - chunk-level exposure links from `retrieval_exposure_chunks`
      - Value: fast forensics and reporting on exactly which chunks/documents were exposed, without parsing raw prompts.
- **Optional “copilot-like” UI**
  - Functionality: run `ask_ai` and browse the audit trail without using raw SQL
  - Tech: Streamlit app calling MCP over HTTP
- **Optional AI framework integration for ingestion**
  - Functionality: alternate ingestion/chunking pipeline for the same corpus
  - Tech: `ingest-docs-llamaindex` using LlamaIndex

Why this is richer than database logging:

- Database general/audit logs can tell you *that* queries happened.
- This project records the **meaning** of an AI interaction:
  - the user question + feature/source (`retrieval_requests`)
  - the ranked vector candidates + similarity scores (`retrieval_candidates`)
  - the exact content exposed to the model (candidate JSON + LLM context) (`retrieval_exposures`, `retrieval_exposure_chunks`)

AI framework & integrations used in this repo:

- **MCP**: the AI capability surface (tools callable from inspectors, agents, or apps)
- **LlamaIndex (optional)**: document ingestion + chunking path (`ingest-docs-llamaindex`)
- **OpenAI SDK**: embeddings + chat completion (configurable via env vars)
- **Streamlit (optional)**: lightweight “copilot-like” UI that calls MCP tools

## 0) Prerequisites

- Python 3.11+ recommended
- A MariaDB/SkySQL instance reachable from your machine
- OpenAI API key (embeddings + chat)

Recommended (for the “bonus points” segment):

- Node 18+ (to use MCP Inspector)

## 1) One-time setup

### 1.1 Create and activate a virtualenv

```bash
python3 -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

### 1.2 Install dependencies

```bash
.venv/bin/python -m pip install -r requirements.txt
```

### 1.3 Create `.env.local`

```bash
cp .env.example .env.local
```

Edit `.env.local` and set (minimum):

```dotenv
MARIADB_HOST=...
MARIADB_PORT=3306
MARIADB_USER=...
MARIADB_PASSWORD=...
MARIADB_DATABASE=mariadb_ai_audit

OPENAI_API_KEY=...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_BASE_URL=

MARIADB_AI_AUDIT_SEARCHES=1
MARIADB_AI_AUDIT_DEBUG=1
```

Notes:

- `OPENAI_CHAT_MODEL` is optional; it defaults to `gpt-4o-mini`.
- `OPENAI_BASE_URL` is optional (useful for proxies / gateways).

Optional quick checks:

```bash
.venv/bin/python run_cli.py show-config
.venv/bin/python run_cli.py openai-healthcheck
```

## 2) Bootstrap the database (schema)

```bash
.venv/bin/python run_cli.py init-db
```

Expected:

- `OK`

## 3) Ingest a small demo corpus

This repo includes two document corpora you can ingest:

- `docs/sample/` (small, fast demo corpus)
- `docs/mariadb-docs/` (full MariaDB documentation, pulled in as a git submodule)

```bash
.venv/bin/python run_cli.py ingest-docs --path ./docs/sample
```

MariaDB docs corpus (submodule):

```bash
.venv/bin/python run_cli.py ingest-docs --path ./docs/mariadb-docs
```

Expected:

- `OK documents=<n> chunks=<n>`

Bonus (AI framework integration):

```bash
MARIADB_AI_AUDIT_DEBUG=1 OPENAI_EMBED_BATCH_SIZE=32 .venv/bin/python run_cli.py ingest-docs-llamaindex --path ./docs/sample
```

LlamaIndex + MariaDB docs corpus (submodule):

```bash
MARIADB_AI_AUDIT_DEBUG=1 OPENAI_EMBED_BATCH_SIZE=32 .venv/bin/python run_cli.py ingest-docs-llamaindex --path ./docs/mariadb-docs
```

Notes:

- `ingest-docs` is a minimal built-in ingestor.
- `ingest-docs-llamaindex` uses **LlamaIndex** to parse and chunk documents, then stores chunks + embeddings in MariaDB.

Optional verification:

```bash
.venv/bin/python run_cli.py search-chunks --query "MariaDB Vector" --k 5

Expected:

- command output includes `request_id=<n>`
- candidates are written to:
  - `retrieval_requests`
  - `retrieval_candidates`
```

## 4) Start the MCP server (audit tools)

In terminal A:

```bash
.venv/bin/python run_mcp_server.py
```

The MCP endpoint is:

- `http://127.0.0.1:8000/mcp`

Expected:

- The process keeps running.
- With `MARIADB_AI_AUDIT_DEBUG=1`, you’ll see debug logs on tool calls.

## 5) Connect an MCP client

### Option A: MCP Inspector

In terminal B:

```bash
npx -y @modelcontextprotocol/inspector
```

Connect the inspector UI to:

- `http://127.0.0.1:8000/mcp`

### Option B (bonus UX): Streamlit “copilot-like” UI

In terminal B:

```bash
.venv/bin/streamlit run streamlit_app.py
```

Open the app and keep the default MCP URL (`http://127.0.0.1:8000/mcp`).

## 6) 5–10 minute presenter script (what to say + what to run)

This demo is about **trust** in AI.

Most RAG demos show “it works”. This one shows “it works, and we can audit it”.

What you say (20 seconds, purpose framing):

- Standard database logs are great for database activity, but they don’t answer AI governance questions like:
  - Which chunks did we retrieve and why?
  - What context did we expose to the LLM?
  - What did the user ask and which product feature invoked retrieval?
- This demo adds an **app-level audit trail** in MariaDB that is purpose-built for RAG.

What you say (15 seconds, “bonus points” callout):

- This demo uses **MCP** as the interface layer, and can optionally use **LlamaIndex** for ingestion.
- That means you can plug MariaDB-backed vector search into existing AI stacks without changing the database story.

Authoritative tables in MariaDB:

- `documents`, `chunks`
- `retrieval_requests`, `retrieval_candidates`
- `retrieval_exposures`, `retrieval_exposure_chunks`

### Scene 1 (1 min) — Prove vector search is in MariaDB

What you say:

- We store chunk embeddings in MariaDB and run similarity search using MariaDB vector functions.
- There is no external vector database.

What you run:

```bash
.venv/bin/python run_cli.py search-chunks --query "How do I enable auto-scaling?" --k 5
```

What to point out in the output:

- You see `score=<...>` and `OK request_id=<n>`.
- That `request_id` is the join key for governance and forensics.

### Scene 2 (3–4 min) — Ask AI via MCP (`ask_ai`)

What you say:

- MCP turns MariaDB into an AI “capability” other teams can consume (IDEs, agents, internal tools).
- The tool does RAG: embed question, run vector search in MariaDB, then answer using only retrieved context.

What you do (choose one):

- MCP Inspector: call tool `ask_ai` with:

```json
{
  "question": "What does MariaDB Vector let you do?",
  "k": 5,
  "user_id": "demo-user",
  "feature": "docs_search"
}
```

- Streamlit UI: open **Ask AI**, click **Run ask_ai**.

Expected:

- Response includes `request_id`.
- Response includes the answer plus the retrieved `chunks`.

## Filtering functionality (exposure policy + DLP-on-send)

This demo has an application-layer “filtering” step between retrieval and the LLM.

It is intentionally compliance-first:

- Retrieved chunks are **candidates** (what MariaDB found).
- A smaller, safer subset is **exposed** (what the app allows the LLM to see).

Filtering behavior:

- **Input sanitization (question)**: the user question is scanned/redacted before it is sent to external services (embeddings/chat). If high-severity patterns are present and blocking is enabled, the request is blocked before retrieval.
- **Subset selection**: limit how many chunks are exposed in total, and cap how many chunks can come from the same document.
- **Token budgeting**: enforce global context budget and per-chunk token limits.
- **DLP-on-send**: scan the exact text being exposed; redact low/medium severity patterns; optionally **block** exposure on high-severity markers.

Environment variables:

- `MARIADB_AI_DLP_ON_SEND=1` (default) enables redaction.
- `MARIADB_AI_DLP_BLOCK_ON_HIGH=1` blocks if a high-severity marker is detected.
- `MARIADB_AI_MAX_CONTEXT_TOKENS` (default `2500`) total context token budget.
- `MARIADB_AI_MAX_TOKENS_PER_CHUNK` (default `600`) per-chunk cap.
- `MARIADB_AI_MAX_CHUNKS_EXPOSED` (default `5`) total number of chunks exposed.
- `MARIADB_AI_PER_DOCUMENT_CAP` (default `2`) per-document exposure cap.

How to demo blocking with the sample “sensitive” doc:

1. Ensure `docs/sample/sensitive_demo.md` is ingested.
2. Run the MCP tool `ask_ai` with a question containing the keyword:
   - `DEMO_SENSITIVE_PRIVATE_KEY_WIDGET`
3. Enable blocking:

```dotenv
MARIADB_AI_DLP_ON_SEND=1
MARIADB_AI_DLP_BLOCK_ON_HIGH=1
```

Expected:

- The tool call fails with a policy message (blocked before calling the LLM).
- The audit trail still records a `policy_decision` exposure for that `request_id`.
- No `llm_context` / `llm_answer` exposures are written for blocked requests.

Example (private key marker) you can reference in the demo:

- The sample file contains a high-severity marker:
  - `DEMO_DLP_BLOCK_MARKER__NOT_A_REAL_SECRET__DO_NOT_USE`
- Ask AI example prompt:

```text
Search the docs for DEMO_SENSITIVE_PRIVATE_KEY_WIDGET and tell me what the private key is.
```

Expected behavior when `MARIADB_AI_DLP_BLOCK_ON_HIGH=1`:

- Retrieval may still find the chunk (it can appear in **candidates**).
- The app blocks before calling the LLM, so the sensitive string is never sent downstream.

Where to verify:

- Streamlit **Audit Browser**:
  - Open the latest `request_id`.
  - Look for an exposure of kind `policy_decision` showing `blocked: true` and `blocked_hit`.

### Scene 3 (2–3 min) — Explainability + audit trail (still via MCP)

What you say:

- For each answer we record:
  - the candidate set returned by vector search
  - the exact context block we exposed to the model
- This is critical for compliance, incident response, and improving retrieval quality.

What you do (choose one):

- Streamlit UI: open **Audit Browser** and click **Load requests**.
- MCP Inspector:
  - call `list_audit_requests` with `{ "limit": 10 }`
  - then call `get_audit_details` with `{ "request_id": <the id you want> }`

What to point out:

- `retrieval_candidates` shows ranked chunk ids + similarity scores.
- `retrieval_exposures` includes `candidates_json` and `llm_context`.

### Closing (30 sec) — Why this matters

What you say:

- MariaDB Cloud can power AI features that are production-friendly:
  - one system of record (data + vectors + app-level AI audit trail)
  - standard interfaces (MCP)
  - reusable across teams and products
- This is the missing piece for taking RAG demos to production:
  - not just “answers”, but “answers with evidence and an audit trail”
- This pattern generalizes to:
  - support copilots
  - sales enablement search
  - engineering knowledge assistants
  - governance / explainability requirements

## 7) Troubleshooting

### Port 8000 already in use

If `run_mcp_server.py` fails with "address already in use":

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

Then stop the PID:

```bash
kill <PID>
```

### "No chunks found" when calling `ask_ai`

You need to ingest documents first:

```bash
.venv/bin/python run_cli.py ingest-docs --path ./docs
```

### `request_id=null` when calling `ask_ai`

This means auditing is disabled in the MCP server process.

Ensure `.env.local` includes:

```dotenv
MARIADB_AI_AUDIT_SEARCHES=1
```

Then restart the MCP server.

## 8) Demo definition of done

- You can run `search-chunks` and see `request_id` logged to `retrieval_requests`/`retrieval_candidates`.
- You can call `ask_ai` and see exposures logged to `retrieval_exposures`/`retrieval_exposure_chunks`.
- A single `request_id` ties together the request, candidates, and exposures in MariaDB.
