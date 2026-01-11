import asyncio
import dataclasses
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import streamlit as st
from fastmcp import Client
from fastmcp.exceptions import ToolError
from fastmcp.client.transports import StreamableHttpTransport
from mcp.shared._httpx_utils import create_mcp_http_client


def _secret_get(name: str) -> object | None:
    try:
        secrets = st.secrets  # type: ignore[attr-defined]
    except Exception:
        return None

    try:
        if name in secrets:
            return secrets.get(name)
    except Exception:
        pass

    for section in ("general", "env", "settings"):
        try:
            bucket = secrets.get(section)
        except Exception:
            bucket = None
        if isinstance(bucket, dict) and name in bucket:
            return bucket.get(name)

    return None


def _setting(name: str, default: str) -> str:
    v = os.getenv(name)
    if v is not None and str(v).strip() != "":
        return str(v)
    sv = _secret_get(name)
    if sv is None:
        return default
    return str(sv)


DEFAULT_MCP_URL = _setting("MCP_URL", "http://127.0.0.1:8000/mcp")
MCP_MODE = _setting("MCP_MODE", "http").strip().lower()

_SRC = Path(__file__).resolve().parent / "src"
if MCP_MODE == "direct" and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _run(coro):
    return asyncio.run(coro)


def _make_client(mcp_url: str) -> Client:
    def httpx_client_factory(**kwargs) -> httpx.AsyncClient:
        headers = kwargs.get("headers")
        auth = kwargs.get("auth")
        return create_mcp_http_client(
            headers=headers,
            timeout=httpx.Timeout(60.0, read=600.0),
            auth=auth,
        )

    transport = StreamableHttpTransport(
        url=mcp_url,
        httpx_client_factory=httpx_client_factory,
    )
    return Client(transport)


def _structured_result(res: object) -> Any:
    sc = getattr(res, "structured_content", None)
    if isinstance(sc, dict):
        if "result" in sc:
            return sc.get("result")
        return sc
    return sc


def _normalize_result(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    if isinstance(obj, list):
        return [_normalize_result(x) for x in obj]
    if isinstance(obj, tuple):
        return [_normalize_result(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _normalize_result(v) for k, v in obj.items()}
    return obj


async def _call_tool(mcp_url: str, name: str, args: dict) -> Any:
    if MCP_MODE == "direct":
        from mariadb_ai_audit.mcp_server import get_audit_details, list_audit_requests
        from mariadb_ai_audit.mcp_server import ask_ai as ask_ai_tool

        def _direct_call() -> Any:
            if name == "ask_ai":
                return ask_ai_tool(**args)
            if name == "list_audit_requests":
                return list_audit_requests(**args)
            if name == "get_audit_details":
                return get_audit_details(**args)
            raise RuntimeError(f"Unknown tool: {name}")

        return _normalize_result(await asyncio.to_thread(_direct_call))

    client = _make_client(mcp_url)
    async with client:
        res = await client.call_tool(name, args)
    parsed = _structured_result(res)
    return _normalize_result(res if parsed is None else parsed)


def _render_mcp_connection_error(exc: Exception, *, mcp_url: str) -> None:
    msg = str(exc)
    st.error(
        "Failed to connect to the MCP server.\n\n"
        f"- MCP URL: {mcp_url}\n"
        "- Check that `run_mcp_server.py` is running (expected at http://127.0.0.1:8000/mcp by default)\n"
        "- Check there is no firewall/VPN/proxy blocking localhost\n"
        "- If you changed ports, set the MCP_URL environment variable accordingly\n\n"
        f"Error: {msg}"
    )


def _render_tool_error(exc: ToolError) -> None:
    msg = str(exc)

    lowered = msg.lower()
    if "blocked by dlp policy" in lowered or "blocked by policy" in lowered:
        st.error(
            "Blocked by policy.\n\n"
            "This request matched the demo DLP rules, so the app prevented sending sensitive content to the LLM."
        )
    else:
        st.error("Tool call failed.")

    with st.expander("Details"):
        st.code(msg)


st.set_page_config(page_title="MariaDB AI Audit", layout="wide")

with st.expander("Runtime settings", expanded=False):
    st.write({"MCP_MODE": MCP_MODE, "MCP_URL": DEFAULT_MCP_URL})

st.markdown(
    """
<style>
  .mdb-wrap { max-width: 1200px; margin: 0 auto; }
  .stApp {
    background:
      radial-gradient(1200px 700px at 10% 0%, rgba(0, 168, 232, 0.22), rgba(0,0,0,0) 60%),
      radial-gradient(1200px 800px at 90% 10%, rgba(0, 214, 168, 0.14), rgba(0,0,0,0) 62%),
      linear-gradient(180deg, #f6fbff 0%, #eef7ff 100%);
  }
  /* Make Streamlit components readable on light background */
  .stApp, .stMarkdown, .stText, .stTextInput, .stTextArea, .stSelectbox, .stNumberInput {
    color: rgba(8, 18, 32, 0.92);
  }
  .mdb-topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border: 1px solid rgba(10, 26, 44, 0.12);
    border-radius: 14px;
    padding: 10px 14px;
    background: rgba(255,255,255,0.70);
    margin: 0.25rem 0 0.6rem 0;
  }
  .mdb-brand {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    font-weight: 600;
    letter-spacing: 0.2px;
  }
  .mdb-dot {
    width: 10px;
    height: 10px;
    border-radius: 999px;
    background: linear-gradient(135deg, #00a8e8, #00d6a8);
    box-shadow: 0 0 0 4px rgba(0, 168, 232, 0.12);
  }
  .mdb-breadcrumb { color: rgba(8, 18, 32, 0.60); font-size: 0.85rem; }
  .mdb-hero {
    border: 1px solid rgba(10, 26, 44, 0.12);
    border-radius: 16px;
    padding: 18px 20px;
    margin: 0 0 1rem 0;
    background:
      linear-gradient(90deg, rgba(255,255,255,0.82) 0%, rgba(255,255,255,0.70) 70%),
      radial-gradient(900px 520px at 18% 35%, rgba(0, 168, 232, 0.18), rgba(0,0,0,0) 55%),
      radial-gradient(900px 520px at 60% 25%, rgba(0, 214, 168, 0.12), rgba(0,0,0,0) 60%);
  }
  .mdb-hero h1 { margin: 0.15rem 0 0 0; font-size: 1.55rem; line-height: 1.2; color: rgba(8, 18, 32, 0.96); }
  .mdb-hero p { margin: 0.4rem 0 0 0; color: rgba(8, 18, 32, 0.70); max-width: 900px; }
  .mdb-card {
    border: 1px solid rgba(10, 26, 44, 0.12);
    border-radius: 14px;
    padding: 16px 16px 10px 16px;
    background: rgba(255,255,255,0.78);
  }
  .mdb-card h3 { margin: 0 0 0.25rem 0; font-size: 1.1rem; }
  .mdb-section-title { margin: 0; font-size: 1.05rem; font-weight: 650; }
  .mdb-muted { color: rgba(8, 18, 32, 0.68); font-size: 0.9rem; }
  .stButton>button { border-radius: 10px; }
</style>
""",
    unsafe_allow_html=True,
)

mcp_url = DEFAULT_MCP_URL

st.markdown('<div class="mdb-wrap">', unsafe_allow_html=True)
st.markdown(
    """
<div class="mdb-hero">
  <h1>MariaDB AI Audit</h1>
  <p>MariaDB Serverless RAG with auditability: MCP tools power the UI; LlamaIndex enforces safe context.</p>
</div>
""",
    unsafe_allow_html=True,
)

page_tabs = st.tabs(["Ask AI", "Audit Browser"])


with page_tabs[0]:
    st.markdown('<div class="mdb-section-title">Ask AI</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="mdb-muted">You are prompted to ask a question to a MariaDB knowledge base version uploaded to a serverless MariaDB instance in MariaDB Cloud. The server retrieves the top-k chunks from MariaDB vector search, then applies an exposure policy before calling the LLM.</div>',
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        question = st.text_area(
            "Question", value="how to Enable Auto-Scaling of Nodes", height=120
        )
    with col2:
        k = st.number_input(
            "Top-k chunks to retrieve",
            min_value=1,
            max_value=50,
            value=5,
            step=1,
            help=(
                "How many chunks MariaDB vector search returns before the exposure policy runs. "
                "Higher k can improve recall, but increases context size and the chance of hitting DLP blocks."
            ),
        )
        user_id = st.text_input(
            "user_id (required)",
            value="",
            placeholder="e.g. alice@company.com",
            help=(
                "Required for the application-level audit trail. We'll log it with each retrieval request so you can "
                "trace who asked what and when."
            ),
        )
        st.caption(
            "Feature is demo-only metadata: it is stored in the audit trail for grouping/filtering. "
            "It does not change model behavior."
        )
        feature_choice = st.selectbox(
            "Feature (demo label)",
            options=[
                "docs_search",
                "incident_response",
                "security_review",
                "compliance_audit",
                "support_triage",
                "Custom…",
            ],
            index=0,
        )
        feature = feature_choice
        if feature_choice == "Custom…":
            feature = st.text_input(
                "Custom feature label",
                value="",
                placeholder="e.g. my_feature",
                help="Optional free-form label stored in the audit trail (demo purposes).",
            )

    can_submit = bool(user_id.strip())
    if not can_submit:
        st.warning("Enter a user_id to enable Ask AI (required for auditing).")

    if st.button("Run ask_ai", type="primary", disabled=not can_submit):
        try:
            with st.spinner("Calling ask_ai..."):
                result = _run(
                    _call_tool(
                        mcp_url,
                        "ask_ai",
                        {
                            "question": question,
                            "k": int(k),
                            "user_id": user_id.strip(),
                            "feature": feature,
                        },
                    )
                )
        except ToolError as exc:
            _render_tool_error(exc)
            st.stop()
        except Exception as exc:
            if (
                "failed to connect" in str(exc).lower()
                or "connection attempts failed" in str(exc).lower()
            ):
                _render_mcp_connection_error(exc, mcp_url=mcp_url)
                st.stop()
            raise

        if not isinstance(result, dict):
            st.error("Unexpected result")
            st.write(result)
        else:
            st.success("Done")
            st.write({"request_id": result.get("request_id"), "k": result.get("k")})

            st.markdown("### Answer")
            st.write(result.get("answer"))

            chunks = result.get("chunks")
            st.markdown("### Chunks")
            if isinstance(chunks, list) and chunks:
                st.dataframe(chunks, use_container_width=True)
            else:
                st.info("No chunks returned")

            with st.expander("Raw JSON"):
                st.json(result)


with page_tabs[1]:
    st.markdown(
        '<div class="mdb-section-title">Audit Browser</div>', unsafe_allow_html=True
    )
    st.markdown(
        '<div class="mdb-muted">Browse retrieval requests, candidates, and exposures (including policy decisions) captured by the application-level audit trail.</div>',
        unsafe_allow_html=True,
    )

    st.info(
        "Load the most recent retrieval requests, then drill into candidates and exposures. "
        "If you don't see any requests yet, run Ask AI once (auditing must be enabled)."
    )

    col_req, col_actions, col_limit = st.columns([3, 1, 1])
    with col_req:
        request_id_input = st.text_input(
            "Request ID",
            value="",
            placeholder="Leave empty to use the most recent request",
            help="Optional. If set, Audit Browser will show details for that specific request id.",
        )
    with col_actions:
        load = st.button("Load", type="primary")
        auto_load = st.checkbox("Auto-load", value=True)
    with col_limit:
        top = st.number_input(
            "Limit",
            min_value=1,
            max_value=100,
            value=10,
            step=1,
            help="How many recent requests to list.",
        )

    auto_key = "_audit_autoload_done"
    should_load = bool(load) or (
        bool(auto_load) and not bool(st.session_state.get(auto_key, False))
    )
    if should_load:
        st.session_state[auto_key] = True
        try:
            with st.spinner("Loading audit requests..."):
                requests = _run(
                    _call_tool(mcp_url, "list_audit_requests", {"limit": int(top)})
                )
        except ToolError as exc:
            _render_tool_error(exc)
            st.stop()
        except Exception as exc:
            if (
                "failed to connect" in str(exc).lower()
                or "connection attempts failed" in str(exc).lower()
            ):
                _render_mcp_connection_error(exc, mcp_url=mcp_url)
                st.stop()
            raise

        if not isinstance(requests, list):
            st.error("Unexpected list_audit_requests result")
            st.write(requests)
        elif not requests:
            st.info("No audit requests found")
        else:
            st.dataframe(requests, use_container_width=True)

            default_id = requests[0].get("id")
            if request_id_input.strip():
                selected_id = request_id_input.strip()
            else:
                selected_id = str(default_id)

            st.markdown("### Details")
            st.caption(
                "A single retrieval request and everything captured about it: what was asked, what MariaDB returned, and what was exposed to the LLM."
            )
            try:
                with st.spinner("Loading details..."):
                    args = {}
                    try:
                        if selected_id:
                            args = {"request_id": int(selected_id)}
                    except Exception:
                        args = {}
                    details = _run(_call_tool(mcp_url, "get_audit_details", args))
            except ToolError as exc:
                _render_tool_error(exc)
                st.stop()

            if not isinstance(details, dict):
                st.error("Unexpected get_audit_details result")
                st.write(details)
            else:
                st.markdown("#### Request")
                st.caption(
                    "The top-level audit record: user_id, feature label, original question, k, embedding model, and timestamps."
                )
                st.json(details.get("request"))

                st.markdown("#### Candidates")
                st.caption(
                    "All chunks returned by MariaDB vector search (ranked). This is what the database retrieved before any exposure/DLP policy ran."
                )
                candidates = details.get("candidates")
                if isinstance(candidates, list) and candidates:
                    st.dataframe(candidates, use_container_width=True)
                else:
                    st.info("No candidates")

                st.markdown("#### Exposures")
                st.caption(
                    "Exposure records are written by the application for a single request_id. A request can have multiple exposures (each has its own exposure id), "
                    "for example: policy_decision, llm_context, candidates_json."
                )
                exposures = details.get("exposures")
                if not isinstance(exposures, list) or not exposures:
                    st.info("No exposures")
                else:
                    dict_exposures = [e for e in exposures if isinstance(e, dict)]
                    by_kind: dict[str, list[dict]] = {}
                    for e in dict_exposures:
                        kind = e.get("kind")
                        if isinstance(kind, str) and kind.strip() != "":
                            by_kind.setdefault(kind, []).append(e)
                    if dict_exposures:
                        st.markdown("##### Inspect exposure")
                        st.caption(
                            "Choose one exposure record to inspect (e.g. policy_decision, llm_context)."
                        )
                        option_labels: list[str] = []
                        label_to_exp: dict[str, dict] = {}
                        for e in dict_exposures:
                            eid = e.get("id")
                            kind = e.get("kind")
                            label = f"{eid} • {kind}" if kind is not None else str(eid)
                            option_labels.append(label)
                            label_to_exp[label] = e

                        selected_label = st.selectbox(
                            "",
                            options=option_labels,
                            index=0,
                            label_visibility="collapsed",
                        )
                        selected = label_to_exp.get(selected_label)
                        if isinstance(selected, dict):
                            st.markdown("##### Exposure metadata")
                            st.json(
                                {
                                    "id": selected.get("id"),
                                    "request_id": selected.get("request_id"),
                                    "kind": selected.get("kind"),
                                    "chunks_exposed": selected.get("chunks_exposed"),
                                    "created_at": selected.get("created_at"),
                                }
                            )
                            st.markdown("##### Content")
                            st.caption(
                                "The payload recorded for this exposure. For policy_decision this is JSON; for llm_context it is the exact text sent to the model."
                            )
                            content = selected.get("content")
                            if isinstance(content, str):
                                st.code(content)
                            else:
                                st.write(content)

                            llm_answer = None
                            llm_items = by_kind.get("llm_answer")
                            if isinstance(llm_items, list) and llm_items:
                                llm_answer = llm_items[-1].get("content")

                            llm_why = None
                            llm_why_items = by_kind.get("llm_why")
                            if isinstance(llm_why_items, list) and llm_why_items:
                                llm_why = llm_why_items[-1].get("content")

                            policy_meta = None
                            policy_items = by_kind.get("policy_decision")
                            if isinstance(policy_items, list) and policy_items:
                                policy_meta = policy_items[-1].get("content")

                            st.markdown("##### LLM response")
                            if isinstance(llm_answer, str) and llm_answer.strip() != "":
                                st.code(llm_answer)
                            else:
                                st.info(
                                    "No llm_answer exposure found for this request."
                                )

                            st.markdown("##### Why")
                            st.caption(
                                "Human-readable explanation for why the LLM responded this way."
                            )
                            if isinstance(llm_why, str) and llm_why.strip() != "":
                                st.code(llm_why)
                            else:
                                st.info("No llm_why exposure found for this request.")

                            st.markdown("##### Policy metadata")
                            st.caption("Raw policy metadata captured for this request.")
                            if (
                                isinstance(policy_meta, str)
                                and policy_meta.strip() != ""
                            ):
                                st.code(policy_meta)
                            else:
                                st.info(
                                    "No policy_decision exposure found for this request."
                                )

                    # Show a compact table (no huge content column) so `kind` stays visible.
                    table_cols = [
                        "id",
                        "request_id",
                        "kind",
                        "chunks_exposed",
                        "created_at",
                    ]
                    table_rows: list[dict] = []
                    for e in exposures:
                        if not isinstance(e, dict):
                            continue
                        row = {k: e.get(k) for k in table_cols if k in e}
                        table_rows.append(row if row else e)
                    st.dataframe(
                        table_rows if table_rows else exposures,
                        use_container_width=True,
                    )

                with st.expander("Raw JSON"):
                    st.json(details)

st.markdown("</div>", unsafe_allow_html=True)
