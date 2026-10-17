from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from app.seed_builder import SchemaDesign, _example_seed_rows, _load_schema, build_seed

ROOT = Path(__file__).resolve().parents[2]
DESIGN_ROOT = ROOT / "design" / "database" / "json"


def test_seed_files_match_design_sources():
    if not DESIGN_ROOT.is_dir():
        pytest.skip("Design files are not available in the backend container")
    assert build_seed(check=True)


def test_seed_generation_is_deterministic():
    if not DESIGN_ROOT.is_dir():
        pytest.skip("Design files are not available in the backend container")
    seed_dir = ROOT / "backend" / "seed"
    before = {path.name: path.read_bytes() for path in seed_dir.glob("*.json")}
    assert build_seed()
    after = {path.name: path.read_bytes() for path in seed_dir.glob("*.json")}
    assert after == before


def test_check_mode_does_not_create_missing_seed_directory(tmp_path: Path):
    if not DESIGN_ROOT.is_dir():
        pytest.skip("Design files are not available in the backend container")
    repository = tmp_path / "repository"
    (repository / "design" / "requiments").mkdir(parents=True)
    shutil.copy2(
        ROOT / "design" / "requiments" / "enviroment.md",
        repository / "design" / "requiments" / "enviroment.md",
    )
    shutil.copytree(ROOT / "design" / "database", repository / "design" / "database")
    assert not build_seed(repository_dir=repository, check=True)
    assert not (repository / "backend" / "seed").exists()


def test_all_generated_example_payloads_validate():
    if not DESIGN_ROOT.is_dir():
        pytest.skip("Design files are not available in the backend container")
    schema = json.loads(
        (DESIGN_ROOT / "schemas" / "sys.artifact.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    examples_dir = DESIGN_ROOT / "schemas" / "examples"
    for path in sorted(examples_dir.glob("*.json")):
        examples = json.loads(path.read_text(encoding="utf-8"))
        assert all(not validator.is_valid(value) for value in examples.get("invalid", [])), path
        assert all(validator.is_valid(value) for value in examples.get("valid", [])), path


def test_invalid_schema_is_rejected(tmp_path: Path):
    path = tmp_path / "invalid.schema.json"
    path.write_text(json.dumps({"type": "not-a-json-schema-type"}), encoding="utf-8")
    design = SchemaDesign(
        markdown=tmp_path / "design.md",
        schema_path=path,
        examples_dir=tmp_path / "examples",
        schema_key="invalid",
        schema_version=1,
        record_type="ARTIFACT",
        feature_domain=None,
    )
    with pytest.raises(ValueError, match="Invalid JSON Schema"):
        _load_schema(design)


def test_invalid_valid_example_is_rejected(tmp_path: Path):
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:test:schema:sample:1",
        "type": "string",
    }
    schema_path = tmp_path / "sample.schema.json"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    (examples_dir / "sample.json").write_text(
        json.dumps({"valid": [42], "invalid": []}), encoding="utf-8"
    )
    design = SchemaDesign(
        markdown=tmp_path / "design.md",
        schema_path=schema_path,
        examples_dir=examples_dir,
        schema_key="sample",
        schema_version=1,
        record_type="ARTIFACT",
        feature_domain=None,
    )
    with pytest.raises(ValueError, match="Invalid valid example"):
        _example_seed_rows({schema_path: (design, schema)})


def test_seed_data_covers_all_design_tables():
    if not DESIGN_ROOT.is_dir():
        pytest.skip("Design files are not available in the backend container")
    master = json.loads(
        (ROOT / "backend" / "seed" / "00_sample_master.json").read_text(encoding="utf-8")
    )
    generated_schemas = json.loads(
        (ROOT / "backend" / "seed" / "10_json_schema.json").read_text(encoding="utf-8")
    )
    er_design = (ROOT / "design" / "database" / "er-design.md").read_text(encoding="utf-8")
    expected = {
        *(
            line.strip().split()[0]
            for line in er_design.splitlines()
            if line.startswith("    ") and line.rstrip().endswith("{")
        )
    }
    assert set(master) | set(generated_schemas) == expected
    assert all(rows for rows in master.values())
    assert generated_schemas["JSON_SCHEMA"]
    assert generated_schemas["JSON_SCHEMA"][0]["schema_id"] == str(
        uuid.uuid5(uuid.NAMESPACE_URL, "urn:das:schema:sys.artifact:1")
    )
