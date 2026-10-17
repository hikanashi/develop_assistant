import json
from pathlib import Path

import pytest

from app.json_validation import validate_instance
from app.seed_builder import (
    DEFAULT_DESIGN_DIR,
    DEFAULT_SEED_DIR,
    SeedBuildError,
    build_json_schema_seed,
    build_seed,
    schema_id_for,
)

SCHEMA = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "urn:das:schema:t.x:1"}
TABLES = [
    "customer",
    "platform",
    "platform_version",
    "product",
    "product_version",
    "content_record",
    "content_revision",
    "revision_parent",
    "json_schema",
    "platform_schema_binding",
    "platform_version_content",
    "product_version_content",
]


needs_design = pytest.mark.skipif(
    not DEFAULT_DESIGN_DIR.exists(), reason="design/ がない環境 (backend コンテナ) ではスキップ"
)


@needs_design
def test_committed_seed_matches_design():
    assert build_seed(DEFAULT_DESIGN_DIR, DEFAULT_SEED_DIR, check=True) == []


@needs_design
def test_build_seed_is_idempotent(tmp_path):
    assert len(build_seed(DEFAULT_DESIGN_DIR, tmp_path)) == 2
    assert build_seed(DEFAULT_DESIGN_DIR, tmp_path) == []
    for name in ("10_json_schema.json", "20_artifact_examples.json"):
        assert (tmp_path / name).read_text("utf-8") == (DEFAULT_SEED_DIR / name).read_text("utf-8")


def test_examples_seed_references_registered_schema():
    schema_rows = json.loads((DEFAULT_SEED_DIR / "10_json_schema.json").read_text("utf-8"))
    examples = json.loads((DEFAULT_SEED_DIR / "20_artifact_examples.json").read_text("utf-8"))
    (row,) = schema_rows["json_schema"]
    assert row["schema_key"] == "sys.artifact" and row["schema_version"] == 1
    assert row["record_type"] == "ARTIFACT" and row["feature_domain"] is None
    assert row["schema_id"] == str(schema_id_for(row["schema_json"]["$id"]))
    records = {r["record_id"] for r in examples["content_record"]}
    assert len(records) == len(examples["content_record"])
    for revision in examples["content_revision"]:
        assert revision["record_id"] in records
        assert revision["schema_id"] == row["schema_id"]
        assert validate_instance(row["schema_json"], revision["content_json"]) == []


def test_sample_master_covers_all_tables_and_is_valid():
    master = json.loads((DEFAULT_SEED_DIR / "00_sample_master.json").read_text("utf-8"))
    schema_rows = json.loads((DEFAULT_SEED_DIR / "10_json_schema.json").read_text("utf-8"))
    (schema,) = schema_rows["json_schema"]
    covered = {t for t, rows in master.items() if rows} | {"json_schema"}
    assert covered == set(TABLES)
    for binding in master["platform_schema_binding"]:
        assert binding["schema_id"] == schema["schema_id"]
    for revision in master["content_revision"]:
        assert revision["schema_id"] == schema["schema_id"]
        assert validate_instance(schema["schema_json"], revision["content_json"]) == []


def test_new_schema_version_keeps_old_rows():
    old = build_json_schema_seed(SCHEMA, {})
    new_schema = {**SCHEMA, "$id": "urn:das:schema:t.x:2"}
    rows = build_json_schema_seed(new_schema, old)["json_schema"]
    assert [r["schema_version"] for r in rows] == [1, 2]
    assert rows[0] == old["json_schema"][0]


def test_changed_schema_with_same_version_is_rejected():
    old = build_json_schema_seed(SCHEMA, {})
    with pytest.raises(SeedBuildError, match="版を上げて"):
        build_json_schema_seed({**SCHEMA, "title": "changed"}, old)


def write_design(root: Path, schema: dict, valid: list) -> Path:
    (root / "examples").mkdir(parents=True)
    (root / "sys.artifact.schema.json").write_text(json.dumps(schema), encoding="utf-8")
    (root / "examples" / "t.json").write_text(json.dumps({"valid": valid}), encoding="utf-8")
    return root


def test_invalid_example_stops_generation(tmp_path):
    schema = {**SCHEMA, "type": "object", "required": ["name"]}
    design = write_design(tmp_path / "design", schema, [{"name": "ok"}, {}])
    seed = tmp_path / "seed"
    with pytest.raises(SeedBuildError, match="t.json valid\\[1\\]"):
        build_seed(design, seed)
    assert not seed.exists()


def test_invalid_schema_stops_generation(tmp_path):
    design = write_design(tmp_path / "design", {**SCHEMA, "type": "bogus"}, [{}])
    with pytest.raises(SeedBuildError, match="JSON Schemaとして不正"):
        build_seed(design, tmp_path / "seed")


def test_default_seed_dir_is_inside_backend():
    # コンテナ (/app) でも seed を見つけられるよう、backend/ からの相対で決まること
    assert DEFAULT_SEED_DIR == Path(__file__).resolve().parents[1] / "seed"
