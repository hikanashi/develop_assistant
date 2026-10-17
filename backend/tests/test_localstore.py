from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.config import BACKEND_DIR, configured_path
from app.database import create_database, database_url
from app.models import SEED_INSERT_ORDER, Customer
from app.store import initialize_local_store, seed_database, session_with_store

ROOT = Path(__file__).resolve().parents[1]


def test_localdata_path_uses_environment_spec_setting(tmp_path: Path, monkeypatch):
    spec = tmp_path / "environment.md"
    spec.write_text("| `LOCALDATA_DIR` | `backend/alternate_store` | test path |\n", encoding="utf-8")
    monkeypatch.setattr("app.config.ENVIRONMENT_SPEC", spec)

    assert configured_path("LOCALDATA_DIR") == BACKEND_DIR / "alternate_store"


def test_unconfigured_backend_uses_file_store_and_persists_all_tables(tmp_path: Path):
    data_dir = tmp_path / "localdata"
    database = create_database(environment={}, localdata_dir=data_dir)
    try:
        initialize_local_store(database)
        files = sorted(data_dir.glob("*.json"))
        assert {path.stem for path in files} == set(SEED_INSERT_ORDER)
        assert all(json.loads(path.read_text(encoding="utf-8")) for path in files)

        with session_with_store(database) as session:
            before = session.exec(select(func.count()).select_from(Customer)).one()
        inserted = seed_database(database)
        assert inserted == 0
        with session_with_store(database) as session:
            after = session.exec(select(func.count()).select_from(Customer)).one()
        assert after == before

        customer_id = str(uuid.uuid4())
        with session_with_store(database) as session:
            session.add(Customer(customer_id=customer_id, name="Local test customer"))
            session.commit()
        customer_rows = json.loads((data_dir / "CUSTOMER.json").read_text(encoding="utf-8"))
        assert any(row["customer_id"] == customer_id for row in customer_rows)
    finally:
        database.engine.dispose()

    restarted = create_database(environment={}, localdata_dir=data_dir)
    try:
        initialize_local_store(restarted)
        with session_with_store(restarted) as session:
            assert session.get(Customer, customer_id) is not None
    finally:
        restarted.engine.dispose()


def test_partial_postgres_configuration_names_missing_variables():
    with pytest.raises(ValueError, match="POSTGRES_PASSWORD, POSTGRES_DB"):
        database_url({"POSTGRES_USER": "configured"})


def test_unconfigured_database_url_selects_file_store():
    assert database_url({}) is None
    assert database_url({"DATABASE_URL": "postgresql+psycopg://user:pass@db/name"})
