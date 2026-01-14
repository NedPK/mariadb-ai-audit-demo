"""Simple keepalive script for MariaDB.

This script:
- adds src/ to sys.path (so you don't need to install the package)
- loads .env.local/.env automatically
- connects to MariaDB and runs SELECT 1 on a fixed interval

It is intended for environments where Streamlit hosting isn't used, but you
still want periodic connectivity checks.
"""

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def _utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(msg: str) -> None:
    sys.stdout.write(f"[{_utc_ts()}] {msg}\n")
    sys.stdout.flush()


def _err(msg: str) -> None:
    sys.stderr.write(f"[{_utc_ts()}] ERROR: {msg}\n")
    sys.stderr.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MariaDB keepalive (SELECT 1)")
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=15 * 60,
        help="Sleep interval between checks (default: 900)",
    )
    parser.add_argument(
        "--max-failures",
        type=int,
        default=0,
        help="Exit after this many consecutive failures (0 means never exit)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single check and exit",
    )
    args = parser.parse_args(argv)

    _SRC = Path(__file__).resolve().parent / "src"
    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))

    from mariadb_ai_audit.config import ConfigError, load_mariadb_config
    from mariadb_ai_audit.db import DatabaseError, healthcheck
    from mariadb_ai_audit.dotenv import load_dotenv

    load_dotenv((".env.local", ".env"), override=True)

    try:
        cfg = load_mariadb_config()
    except ConfigError as exc:
        _err(str(exc))
        return 2

    _log(
        "Starting keepalive "
        f"(host={cfg.host} port={cfg.port} user={cfg.user} database={cfg.database})"
    )

    consecutive_failures = 0

    def run_check() -> bool:
        nonlocal consecutive_failures
        try:
            healthcheck(cfg)
            consecutive_failures = 0
            _log("SELECT 1 ok")
            return True
        except (DatabaseError, Exception) as exc:
            consecutive_failures += 1
            _err(
                f"SELECT 1 failed (consecutive_failures={consecutive_failures}): {exc}"
            )
            if args.max_failures > 0 and consecutive_failures >= args.max_failures:
                _err("Max consecutive failures reached; exiting")
                raise
            return False

    try:
        run_check()
        if args.once:
            return 0 if consecutive_failures == 0 else 1

        while True:
            time.sleep(max(1, args.interval_seconds))
            run_check()

    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
