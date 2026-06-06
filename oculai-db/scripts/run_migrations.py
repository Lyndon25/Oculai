#!/usr/bin/env python3
"""Oculai Schema Migration Runner.

Applies numbered .sql migration files from schema/migrations/ in order,
skipping any already recorded in the schema_version tracking table.

Usage:
    python scripts/run_migrations.py                          # uses env vars for DB conn
    python scripts/run_migrations.py --dsn postgresql://...   # explicit DSN
    python scripts/run_migrations.py --host localhost --port 5433 --user oculai --password oculai_dev --dbname oculai

Each migration runs in a transaction. On failure, the migration is rolled back
and the script exits with non-zero status so the caller can retry.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path
from textwrap import dedent

# --- PostgreSQL driver selection ---
# Try asyncpg first (already in project deps), fall back to psycopg2.
_DRIVER: str | None = None
_Connection: type | None = None


def _get_driver():
    global _DRIVER, _Connection
    if _DRIVER is not None:
        return _DRIVER

    try:
        import asyncpg  # noqa: F401

        _DRIVER = "asyncpg"
        return _DRIVER
    except ImportError:
        pass

    try:
        import psycopg2  # noqa: F401

        _DRIVER = "psycopg2"
        return _DRIVER
    except ImportError:
        pass

    print(
        "ERROR: Neither asyncpg nor psycopg2 is installed. "
        "Install one: pip install asyncpg",
        file=sys.stderr,
    )
    sys.exit(1)


# ============================================================
# asyncpg implementation
# ============================================================


async def _run_asyncpg(dsn: str, migrations_dir: Path) -> int:
    import asyncio

    import asyncpg

    conn: asyncpg.Connection = await asyncpg.connect(dsn)
    try:
        # Ensure tracking table exists (idempotent)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version     TEXT PRIMARY KEY,
                applied_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                checksum    TEXT,
                description TEXT
            )
            """
        )

        # Get already-applied versions
        applied = {
            row["version"]
            for row in await conn.fetch("SELECT version FROM schema_version")
        }

        # Find migration files
        files = sorted(migrations_dir.glob("*.sql"))
        if not files:
            print("No migration files found.")
            return 0

        pending = [f for f in files if f.stem not in applied]
        if not pending:
            print(f"All {len(files)} migrations already applied. Nothing to do.")
            return 0

        print(f"Found {len(files)} total, {len(pending)} pending migrations.")

        for sql_file in pending:
            version = sql_file.stem
            sql = sql_file.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode()).hexdigest()[:16]

            print(f"  Applying {version}...", end=" ", flush=True)

            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_version (version, checksum, description) "
                    "VALUES ($1, $2, $3) "
                    "ON CONFLICT (version) DO UPDATE SET applied_at = now(), checksum = $2",
                    version,
                    checksum,
                    f"Migration {version}",
                )

            print("OK")

        return 0

    finally:
        await conn.close()


# ============================================================
# psycopg2 implementation
# ============================================================


def _run_psycopg2(dsn: str, migrations_dir: Path) -> int:
    import psycopg2

    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    try:
        cur = conn.cursor()

        # Ensure tracking table exists
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version     TEXT PRIMARY KEY,
                applied_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                checksum    TEXT,
                description TEXT
            )
            """
        )
        conn.commit()

        # Get already-applied versions
        cur.execute("SELECT version FROM schema_version")
        applied = {row[0] for row in cur.fetchall()}

        # Find migration files
        files = sorted(migrations_dir.glob("*.sql"))
        if not files:
            print("No migration files found.")
            return 0

        pending = [f for f in files if f.stem not in applied]
        if not pending:
            print(f"All {len(files)} migrations already applied. Nothing to do.")
            return 0

        print(f"Found {len(files)} total, {len(pending)} pending migrations.")

        for sql_file in pending:
            version = sql_file.stem
            sql = sql_file.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode()).hexdigest()[:16]

            print(f"  Applying {version}...", end=" ", flush=True)

            cur.execute(sql)
            cur.execute(
                "INSERT INTO schema_version (version, checksum, description) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (version) DO UPDATE SET applied_at = now(), checksum = %s",
                (version, checksum, f"Migration {version}", checksum),
            )
            conn.commit()

            print("OK")

        cur.close()
        return 0

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ============================================================
# CLI entry point
# ============================================================


def _build_dsn(args: argparse.Namespace) -> str:
    """Build a PostgreSQL DSN from CLI args or environment variables."""
    if args.dsn:
        return args.dsn

    host = args.host or os.environ.get("DB_HOST", "localhost")
    port = args.port or int(os.environ.get("DB_PORT", "5432"))
    user = args.user or os.environ.get("DB_USER", "oculai")
    password = args.password or os.environ.get("DB_PASSWORD", "oculai_dev")
    dbname = args.dbname or os.environ.get("DB_NAME", "oculai")

    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


def _find_migrations_dir(args: argparse.Namespace) -> Path:
    """Find the migrations directory."""
    if args.migrations_dir:
        p = Path(args.migrations_dir)
    else:
        # Default: schema/migrations/ relative to this script's parent
        script_dir = Path(__file__).resolve().parent.parent
        p = script_dir / "schema" / "migrations"

    if not p.is_dir():
        print(f"ERROR: Migrations directory not found: {p}", file=sys.stderr)
        sys.exit(1)

    return p


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Oculai Schema Migration Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=dedent("""\
            Examples:
              %(prog)s --host localhost --port 5433
              %(prog)s --dsn postgresql://oculai:pass@localhost:5433/oculai
              %(prog)s --migrations-dir ./my-migrations
        """),
    )
    parser.add_argument("--dsn", help="Full PostgreSQL connection DSN")
    parser.add_argument("--host", help="DB host (default: DB_HOST env or localhost)")
    parser.add_argument("--port", type=int, help="DB port (default: DB_PORT env or 5432)")
    parser.add_argument("--user", help="DB user (default: DB_USER env or oculai)")
    parser.add_argument("--password", help="DB password (default: DB_PASSWORD env or oculai_dev)")
    parser.add_argument("--dbname", help="DB name (default: DB_NAME env or oculai)")
    parser.add_argument(
        "--migrations-dir",
        help="Path to migrations directory (default: ../schema/migrations relative to script)",
    )

    args = parser.parse_args()
    dsn = _build_dsn(args)
    migrations_dir = _find_migrations_dir(args)

    driver = _get_driver()

    if driver == "asyncpg":
        import asyncio

        return asyncio.run(_run_asyncpg(dsn, migrations_dir))
    else:
        return _run_psycopg2(dsn, migrations_dir)


if __name__ == "__main__":
    sys.exit(main())
