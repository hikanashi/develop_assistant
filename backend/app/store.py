from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, event, insert, select
from sqlmodel import Session, SQLModel

from .config import SEED_DIR
from .database import Database
from .models import SEED_INSERT_ORDER, TABLE_MODELS
from .services import serialize_record

_write_lock = threading.Lock()


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _rows(session: Session, table_name: str) -> list[dict[str, Any]]:
    model = TABLE_MODELS[table_name]
    result = session.scalars(select(model)).all()
    return [
        {key: _serialize_value(value) for key, value in serialize_record(model, record).items()}
        for record in result
    ]


def persist_local_store(directory: Path, engine) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    with _write_lock, Session(engine) as read_session:
        for table_name in SEED_INSERT_ORDER:
            content = (
                json.dumps(
                    _rows(read_session, table_name),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=directory,
                prefix=f".{table_name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(content)
                temp_path = Path(temporary.name)
            os.replace(temp_path, directory / f"{table_name}.json")


@event.listens_for(Session, "after_commit")
def _persist_after_commit(session: Session) -> None:
    directory = session.info.get("localdata_dir")
    if directory is not None and not session.info.get("skip_localdata_persist"):
        persist_local_store(Path(directory), session.get_bind())


def _parse_datetime_values(model: type, row: dict[str, Any]) -> dict[str, Any]:
    parsed = row.copy()
    for column in model.__table__.columns:
        value = parsed.get(column.name)
        if isinstance(value, str) and isinstance(column.type, DateTime):
            parsed[column.name] = datetime.fromisoformat(value)
    return parsed


def _seed_rows(seed_dir: Path) -> dict[str, list[dict[str, Any]]]:
    files = sorted(seed_dir.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"No JSON seed files found in {seed_dir}")
    all_rows = {table: [] for table in SEED_INSERT_ORDER}
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TypeError(f"Seed file must contain a JSON object: {path}")
        for table_name, rows in data.items():
            if table_name not in TABLE_MODELS:
                raise ValueError(f"Unknown table {table_name} in seed file {path}")
            if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                raise ValueError(f"Table {table_name} must contain an array of objects in {path}")
            all_rows[table_name].extend(rows)
    return all_rows


def insert_seed_data(session: Session, seed_dir: Path = SEED_DIR) -> int:
    rows_by_table = _seed_rows(seed_dir)
    inserted = 0
    for table_name in SEED_INSERT_ORDER:
        inserted += _insert_rows(session, table_name, rows_by_table[table_name])
    return inserted


def _insert_rows(session: Session, table_name: str, rows: list[dict[str, Any]]) -> int:
    model = TABLE_MODELS[table_name]
    primary_key_columns = [column.name for column in model.__table__.primary_key.columns]
    inserted = 0
    for row in rows:
        normalized = _parse_datetime_values(model, row)
        primary_key = tuple(normalized.get(name) for name in primary_key_columns)
        if any(value is None for value in primary_key):
            raise ValueError(f"Seed row for {table_name} is missing its primary key")
        lookup_key = primary_key[0] if len(primary_key) == 1 else primary_key
        if session.get(model, lookup_key) is not None:
            continue
        session.execute(insert(model).values(**normalized))
        inserted += 1
    return inserted


def initialize_local_store(database: Database, seed_dir: Path = SEED_DIR) -> None:
    if database.localdata_dir is None:
        return
    SQLModel.metadata.create_all(database.engine)
    directory = database.localdata_dir
    directory.mkdir(parents=True, exist_ok=True)
    existing_files = list(directory.glob("*.json"))
    with database.session_factory() as session:
        if not existing_files:
            insert_seed_data(session, seed_dir)
            session.commit()
        else:
            for table_name, rows in _seed_rows_from_local(directory).items():
                _insert_rows(session, table_name, rows)
            session.commit()
    persist_local_store(directory, database.engine)


def _seed_rows_from_local(directory: Path) -> dict[str, list[dict[str, Any]]]:
    rows = {table: [] for table in SEED_INSERT_ORDER}
    for path in sorted(directory.glob("*.json")):
        if path.name not in {f"{table}.json" for table in SEED_INSERT_ORDER}:
            continue
        table_name = path.stem
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
            raise ValueError(f"Local data file must contain an array of objects: {path}")
        rows[table_name] = data
    return rows


def seed_database(database: Database, seed_dir: Path = SEED_DIR) -> int:
    if database.localdata_dir is not None:
        initialize_local_store(database, seed_dir)
    with database.session_factory() as session:
        if database.localdata_dir is not None:
            session.info["localdata_dir"] = database.localdata_dir
        inserted = insert_seed_data(session, seed_dir)
        session.commit()
        return inserted


def export_database(database: Database) -> dict[str, list[dict[str, Any]]]:
    if database.localdata_dir is not None:
        result = {}
        for table_name, rows in _seed_rows_from_local(database.localdata_dir).items():
            result[table_name] = rows
        return {table: result[table] for table in SEED_INSERT_ORDER}
    with database.session_factory() as session:
        return {table: _rows(session, table) for table in SEED_INSERT_ORDER}


def session_with_store(database: Database):
    session = database.session_factory()
    if database.localdata_dir is not None:
        session.info["localdata_dir"] = database.localdata_dir
    return session
