import json
from uuid import UUID

import pytest
from sqlalchemy import Column, MetaData, Table, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.exc import OperationalError
from sqlalchemy.types import Integer

from app.config import DATABASE_URL
from app.seed_io import export_seed, load_seed


@pytest.fixture
def engine():
    eng = create_engine(DATABASE_URL)
    try:
        eng.connect().close()
    except OperationalError:
        pytest.skip("PostgreSQL に接続できません")
    metadata = MetaData()
    Table(
        "tmp_seed_test",
        metadata,
        Column("id", PG_UUID(as_uuid=True), primary_key=True),
        Column("n", Integer),
        Column("doc", JSONB),
    )
    metadata.create_all(eng)
    yield eng
    with eng.begin() as conn:
        conn.execute(text("drop table tmp_seed_test"))


def test_seed_roundtrip(engine, tmp_path):
    rid = "6f9619ff-8b86-d011-b42d-00c04fc964ff"
    (tmp_path / "a.json").write_text(
        json.dumps({"tmp_seed_test": [{"id": rid, "n": 1, "doc": {"k": [1, 2]}}]})
    )
    assert load_seed(engine, tmp_path) == 1
    assert load_seed(engine, tmp_path) == 1  # 再投入しても重複しない

    out = tmp_path / "out" / "export.json"
    export_seed(engine, out)
    exported = json.loads(out.read_text())["tmp_seed_test"]
    assert exported == [{"id": rid, "n": 1, "doc": {"k": [1, 2]}}]
    assert UUID(exported[0]["id"])


def test_seed_rows_with_different_columns(engine, tmp_path):
    a, b = "6f9619ff-8b86-d011-b42d-00c04fc964ff", "7f9619ff-8b86-d011-b42d-00c04fc964ff"
    (tmp_path / "a.json").write_text(
        json.dumps({"tmp_seed_test": [{"id": a, "n": 1, "doc": {}}, {"id": b, "doc": {}}]})
    )
    assert load_seed(engine, tmp_path) == 2
