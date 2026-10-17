"""JSON Schema 検証 (DB不要)。"""

import json
from pathlib import Path

from app.json_validation import check_schema_document, validate_instance

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "design" / "database" / "schemas"


def test_valid_instance_has_no_errors():
    schema = {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}}
    assert validate_instance(schema, {"name": "x"}) == []


def test_all_violations_are_reported_with_json_pointer():
    schema = {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "integer"}},
            "a/b": {"type": "string"},
        },
    }
    errors = validate_instance(schema, {"tags": [1, "x"], "a/b": 1})
    by_validator = {(e["validator"], e["path"]) for e in errors}
    assert ("required", "") in by_validator
    assert ("type", "/tags/1") in by_validator
    assert ("type", "/a~1b") in by_validator
    assert all(e["message"] and "schema_path" in e for e in errors)


def test_any_of_reports_causes():
    schema = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
    (error,) = validate_instance(schema, [])
    assert error["validator"] == "anyOf"
    assert len(error["causes"]) == 2


def test_check_schema_document():
    assert check_schema_document({"type": "object"}) == []
    assert check_schema_document({"type": "nonsense"})
    assert check_schema_document({"pattern": "("})
    assert check_schema_document({"$schema": "http://json-schema.org/draft-07/schema#"})


def test_artifact_schema_is_valid_and_examples_are_checked():
    schema = json.loads((SCHEMA_DIR / "sys.artifact.schema.json").read_text(encoding="utf-8"))
    assert check_schema_document(schema) == []
    examples = json.loads((SCHEMA_DIR / "examples" / "sys2.use_case.json").read_text("utf-8"))
    assert all(validate_instance(schema, i) == [] for i in examples["valid"])
    assert all(validate_instance(schema, i) for i in examples["invalid"])
