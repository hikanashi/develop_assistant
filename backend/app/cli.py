from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from alembic.config import Config

from alembic import command

from .config import BACKEND_DIR
from .database import create_database
from .seed_builder import build_seed
from .store import export_database, initialize_local_store, seed_database


def _run_migrations(database) -> None:
    if not database.uses_postgres:
        raise RuntimeError("Alembic migrations require PostgreSQL; the file store uses SQLite")
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")


def _init_database() -> None:
    database = create_database()
    try:
        if database.uses_postgres:
            _run_migrations(database)
            inserted = seed_database(database)
        else:
            print("No PostgreSQL configuration found; backend will initialize the file store.")
            inserted = 0
        print(f"Initialization complete; {inserted} seed row(s) inserted.")
    finally:
        database.engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("seed", help="Load JSON seed files into the configured store")
    export_parser = subparsers.add_parser("export", help="Export all records as JSON seed data")
    export_parser.add_argument("-o", "--output", type=Path)
    build_parser = subparsers.add_parser(
        "build-seed", help="Generate JSON seeds from the design documents"
    )
    build_parser.add_argument("--check", action="store_true")
    subparsers.add_parser("init-db", help="Apply migrations and load seed data when configured")
    args = parser.parse_args(argv)

    try:
        if args.command == "build-seed":
            return 0 if build_seed(check=args.check) or not args.check else 1
        if args.command == "init-db":
            _init_database()
            return 0
        database = create_database()
        try:
            initialize_local_store(database)
            if args.command == "seed":
                count = seed_database(database)
                print(f"Inserted {count} row(s).")
            else:
                content = (
                    json.dumps(
                        export_database(database),
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                        default=str,
                    )
                    + "\n"
                )
                if args.output is None:
                    sys.stdout.write(content)
                else:
                    args.output.write_text(content, encoding="utf-8")
                    print(f"Exported data to {args.output}")
        finally:
            database.engine.dispose()
    except (OSError, TypeError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Command failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
