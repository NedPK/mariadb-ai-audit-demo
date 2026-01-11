"""Convenience runner for the demo CLI.

This script:
- adds src/ to sys.path (so you don't need to install the package)
- loads .env.local/.env automatically
- delegates to mariadb_ai_audit.cli.main
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mariadb_ai_audit.dotenv import load_dotenv
from mariadb_ai_audit.cli import main

load_dotenv((".env.local", ".env"), override=True)


if __name__ == "__main__":
    raise SystemExit(main())
