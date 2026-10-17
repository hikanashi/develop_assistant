from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import Session

DB_VARIABLES = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")


@dataclass(frozen=True)
class Database:
    engine: Engine
    session_factory: sessionmaker[Session]
    localdata_dir: Path | None

    @property
    def uses_postgres(self) -> bool:
        return self.localdata_dir is None


def database_url(environment: Mapping[str, str]) -> str | URL | None:
    url = environment.get("DATABASE_URL", "").strip()
    present = [name for name in DB_VARIABLES if environment.get(name)]
    if url and present:
        missing = [name for name in DB_VARIABLES if not environment.get(name)]
        if missing:
            raise ValueError(
                "Incomplete PostgreSQL configuration; missing environment variable(s): "
                + ", ".join(missing)
            )
        raise ValueError(
            "Set either DATABASE_URL or all of POSTGRES_USER, POSTGRES_PASSWORD, "
            "and POSTGRES_DB, not both"
        )
    if url:
        return url
    if not present:
        return None
    missing = [name for name in DB_VARIABLES if not environment.get(name)]
    if missing:
        raise ValueError(
            "Incomplete PostgreSQL configuration; missing environment variable(s): "
            + ", ".join(missing)
        )
    return URL.create(
        "postgresql+psycopg",
        username=environment["POSTGRES_USER"],
        password=environment["POSTGRES_PASSWORD"],
        host=environment.get("POSTGRES_HOST", "db"),
        port=int(environment.get("POSTGRES_PORT", "5432")),
        database=environment["POSTGRES_DB"],
    )


def create_database(
    environment: Mapping[str, str] | None = None,
    localdata_dir: str | Path | None = None,
) -> Database:
    current_environment = os.environ if environment is None else environment
    url = database_url(current_environment)
    if url is None:
        from .config import LOCALDATA_DIR

        configured_localdata = (
            Path(localdata_dir)
            if localdata_dir is not None
            else Path(current_environment.get("LOCALDATA_DIR", LOCALDATA_DIR))
        )
        if not configured_localdata.is_absolute():
            from .config import BACKEND_DIR

            configured_localdata = BACKEND_DIR / configured_localdata
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
        resolved_localdata: Path | None = configured_localdata
    else:
        engine = create_engine(url, pool_pre_ping=True)
        resolved_localdata = None
    factory = sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
        autoflush=False,
    )
    return Database(engine, factory, resolved_localdata)


def _enable_sqlite_foreign_keys(connection, _record) -> None:
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
