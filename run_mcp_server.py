"""Convenience runner for the MCP server.

Loads .env.local/.env and starts the MCP server over HTTP.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mariadb_ai_audit.dotenv import load_dotenv
from mariadb_ai_audit.mcp_server import run_server

load_dotenv((".env.local", ".env"), override=True)


if __name__ == "__main__":
    run_server(transport="streamable-http")
