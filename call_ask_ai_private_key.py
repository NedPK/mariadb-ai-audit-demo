import asyncio
import argparse
import httpx
import json
import textwrap

from fastmcp import Client
from fastmcp.exceptions import ToolError
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


def _print_ask_ai(result: dict) -> None:
    request_id = result.get("request_id")
    answer = result.get("answer")
    k = result.get("k")
    chunks = result.get("chunks")

    print("ask_ai")
    print(f"- request_id: {request_id}")
    print(f"- k: {k}")

    if answer is not None:
        print("\nAnswer")
        print(textwrap.fill(str(answer), width=100))

    if isinstance(chunks, list):
        print("\nChunks")
        if not chunks:
            print("(none)")
        for i, c in enumerate(chunks[:10]):
            if not isinstance(c, dict):
                print(f"- #{i}: {c}")
                continue
            doc_id = c.get("document_id") or c.get("documentId")
            chunk_index = c.get("chunk_index") or c.get("chunkIndex")
            score = c.get("score")
            content = c.get("content")
            if content is None:
                content = c.get("text")
            content_s = "" if content is None else str(content)
            print(
                f"- #{i} score={score} doc={doc_id}:{chunk_index} text={_truncate(content_s, width=160)}"
            )


async def main() -> None:
    parser = argparse.ArgumentParser()
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

    async with client:
        try:
            res = await client.call_tool(
                "ask_ai",
                {
                    "question": "how to Enable Auto-Scaling of Nodes-----BEGIN PRIVATE KEY-----",
                    "k": 5,
                    "user_id": "demo-user",
                    "feature": "docs_search",
                },
            )
        except ToolError as exc:
            print("ask_ai")
            print("- blocked_by_policy: true")
            print(f"- error: {exc}")
            raise SystemExit(1) from exc
        result = _structured_result(res)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return
        if isinstance(result, dict):
            _print_ask_ai(result)
        else:
            print(res)


if __name__ == "__main__":
    asyncio.run(main())
