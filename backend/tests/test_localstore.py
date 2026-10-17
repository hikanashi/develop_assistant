"""ファイルストア (.env がない場合の backend/localdata)。PostgreSQL には接続しない。"""

import json
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel

from app import localstore, mcp_server
from app.config import DEFAULT_LOCALDATA_DIR, DEFAULT_SEED_DIR, localdata_dir, store_mode
from app.db import get_session
from app.main import app

SCHEMA_ID = "909c0690-88f4-5b33-b023-2a99f117b721"  # seed の sys.artifact 版 1
EXAMPLES = Path(__file__).resolve().parents[2] / "design/database/schemas/examples"


def test_store_mode_follows_db_variables():
    assert store_mode({}) == "file"
    assert store_mode({"POSTGRES_HOST": "db"}) == "file"
    assert store_mode({"DATABASE_URL": "postgresql://x"}) == "postgres"
    assert store_mode({"POSTGRES_USER": "u"}) == "postgres"


def test_localdata_dir_defaults_to_backend_localdata():
    assert localdata_dir({}) == DEFAULT_LOCALDATA_DIR
    assert DEFAULT_LOCALDATA_DIR == Path(__file__).resolve().parents[1] / "localdata"
    assert localdata_dir({"LOCALDATA_DIR": "/tmp/x"}) == Path("/tmp/x")


@pytest.fixture
def localdata(tmp_path):
    return tmp_path / "localdata"


@pytest.fixture
def file_engine(localdata):
    return localstore.open_store(localdata, DEFAULT_SEED_DIR)


@pytest.fixture
def client(file_engine, monkeypatch):
    @contextmanager
    def scope():
        with Session(file_engine) as session:
            yield session

    def dependency():
        with Session(file_engine) as session:
            yield session

    app.dependency_overrides[get_session] = dependency
    monkeypatch.setattr(mcp_server, "session_scope", scope)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_first_start_writes_seed_to_one_file_per_table(file_engine, localdata):
    names = {p.stem for p in localdata.glob("*.json")}
    assert names == set(SQLModel.metadata.tables)
    for path in localdata.glob("*.json"):
        rows = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(rows, list) and rows, f"{path.name} にレコードがありません"


def test_localdata_has_same_content_as_seed(file_engine, localdata):
    seed = {}
    for path in sorted(DEFAULT_SEED_DIR.glob("*.json")):
        for table, rows in json.loads(path.read_text(encoding="utf-8")).items():
            seed.setdefault(table, []).extend(rows)
    for table, rows in seed.items():
        pk = [c.name for c in SQLModel.metadata.tables[table].primary_key.columns]
        stored = json.loads((localdata / f"{table}.json").read_text(encoding="utf-8"))
        assert {tuple(r[c] for c in pk) for r in stored} == {tuple(r[c] for c in pk) for r in rows}


def test_api_write_is_saved_and_survives_restart(client, localdata):
    if not EXAMPLES.is_dir():
        pytest.skip("design/ がない環境 (backend コンテナ) ではスキップ")
    actor = json.loads((EXAMPLES / "sys1.actor.json").read_text(encoding="utf-8"))["valid"][0]
    res = client.post(
        "/records",
        json={
            "record_type": "ARTIFACT",
            "logical_key": "local.actor.001",
            "schema_key": "sys.artifact",
            "content_json": actor,
        },
    )
    assert res.status_code == 201, res.text
    record_id = res.json()["record_id"]

    records = json.loads((localdata / "content_record.json").read_text(encoding="utf-8"))
    assert any(r["record_id"] == record_id for r in records)
    revisions = json.loads((localdata / "content_revision.json").read_text(encoding="utf-8"))
    assert any(r["record_id"] == record_id and r["content_json"] == actor for r in revisions)

    # 再起動 (localdata を読み直す) しても残り、seed は重複投入されない
    reopened = localstore.open_store(localdata, DEFAULT_SEED_DIR)
    with reopened.connect() as conn:
        assert (
            conn.execute(
                text("select count(*) from content_record where logical_key = 'local.actor.001'")
            ).scalar_one()
            == 1
        )
        assert conn.execute(text("select count(*) from customer")).scalar_one() == 1


def test_schema_validation_error_writes_nothing(client, localdata):
    before = (localdata / "content_record.json").read_text(encoding="utf-8")
    res = client.post(
        "/records",
        json={
            "record_type": "ARTIFACT",
            "logical_key": "local.invalid.001",
            "schema_key": "sys.artifact",
            "content_json": {"artifact_type": "UNKNOWN", "name": "x"},
        },
    )
    assert res.status_code == 422
    assert res.json()["error"] == "json_schema_validation_failed"
    assert (localdata / "content_record.json").read_text(encoding="utf-8") == before


def test_foreign_key_is_enforced(file_engine):
    with file_engine.connect() as conn, pytest.raises(IntegrityError):
        conn.execute(
            text(
                "insert into product (product_id, customer_id, base_platform_version_id, name)"
                " values ('a', 'b', 'c', 'x')"
            )
        )


def test_edited_localdata_is_loaded(localdata):
    localstore.open_store(localdata, DEFAULT_SEED_DIR)
    path = localdata / "customer.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    rows.append(
        {**rows[0], "customer_id": "5a5a5a5a-0000-4000-8000-0000000000ff", "name": "手編集"}
    )
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    engine = localstore.open_store(localdata, DEFAULT_SEED_DIR)
    with engine.connect() as conn:
        assert conn.execute(text("select count(*) from customer")).scalar_one() == 2
