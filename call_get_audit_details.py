import argparse
import asyncio
import httpx
import json
import textwrap

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from mcp.shared._httpx_utils import create_mcp_http_client


def _truncate(s: str, *, width: int) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(s) <= width:
        return s
    return s[: max(0, width - 1)].rstrip() + "…"


def _structured_result(res: object) -> object:
    sc = getattr(res, "structured_content", None)
    if isinstance(sc, dict) and "result" in sc:
        return sc.get("result")
    return None


def _print_details(details: dict) -> None:
    request = details.get("request") if isinstance(details, dict) else None
    candidates = details.get("candidates") if isinstance(details, dict) else None
    exposures = details.get("exposures") if isinstance(details, dict) else None

    if not isinstance(request, dict):
        print(json.dumps(details, indent=2, ensure_ascii=False, default=str))
        return

    print("Audit request")
    print(f"- id: {request.get('id')}")
    print(f"- created_at: {request.get('created_at')}")
    print(f"- user_id: {request.get('user_id')}")
    print(f"- feature: {request.get('feature')}")
    print(f"- source: {request.get('source')}")
    print(f"- embedding_model: {request.get('embedding_model')}")
    print(
        f"- k: {request.get('k')} candidates_returned: {request.get('candidates_returned')}"
    )

    query = request.get("query")
    if query is not None:
        print("\nQuery")
        print(textwrap.fill(str(query), width=100))

    if isinstance(candidates, list):
        print("\nTop candidates")
        if not candidates:
            print("(none)")
        for c in candidates[:10]:
            if not isinstance(c, dict):
                continue
            rank = c.get("rank")
            score = c.get("score")
            chunk_id = c.get("chunk_id")
            doc_id = c.get("document_id")
            chunk_index = c.get("chunk_index")
            content = "" if c.get("content") is None else str(c.get("content"))
            print(
                f"- #{rank} score={score} chunk_id={chunk_id} doc={doc_id}:{chunk_index} "
                f"text={_truncate(content, width=140)}"
            )

    if isinstance(exposures, list):
        print("\nExposures")
        if not exposures:
            print("(none)")
        for e in exposures:
            if not isinstance(e, dict):
                continue
            eid = e.get("id")
            kind = e.get("kind")
            created_at = e.get("created_at")
            chunks_exposed = e.get("chunks_exposed")
            content = "" if e.get("content") is None else str(e.get("content"))
            print(
                f"- id={eid} kind={kind} created_at={created_at} chunks_exposed={chunks_exposed}"
            )
            if content:
                print(
                    textwrap.indent(
                        textwrap.fill(_truncate(content, width=500), width=100),
                        prefix="  ",
                    )
                )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--request-id",
        type=int,
        default=None,
        help="Audit request id. If omitted, server will return most recent request.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON result instead of a formatted summary.",
    )
    args = parser.parse_args()

    def httpx_client_factory(**kwargs) -> httpx.AsyncClient:
        headers = kwargs.get("headers")
        auth = kwargs.get("auth")
        return create_mcp_http_client(
            headers=headers,
            timeout=httpx.Timeout(60.0, read=600.0),
            auth=auth,
        )

    transport = StreamableHttpTransport(
        url="http://127.0.0.1:8000/mcp",
        httpx_client_factory=httpx_client_factory,
    )
    client = Client(transport)

    tool_args = {} if args.request_id is None else {"request_id": args.request_id}

    async with client:
        res = await client.call_tool("get_audit_details", tool_args)
        result = _structured_result(res)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return
        if isinstance(result, dict):
            _print_details(result)
        else:
            print(res)


if __name__ == "__main__":
    asyncio.run(main())
