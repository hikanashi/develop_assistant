from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.database import create_database
from app.main import create_app
from app.mcp_server import configure_mcp
from app.store import initialize_local_store


def test_health_read_and_json_schema_validation_in_file_store(tmp_path: Path):
    database = create_database(environment={}, localdata_dir=tmp_path / "localdata")
    app = create_app(database)
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok", "storage": "file"}
        schemas = client.get("/api/schemas").json()
        assert len(schemas) == 1
        schema_id = schemas[0]["schema_id"]
        assert client.get("/api/CONTENT_RECORD").json()["records"]

        record_id = str(uuid.uuid4())
        response = client.post(
            "/api/CONTENT_RECORD",
            json={
                "record_id": record_id,
                "record_type": "ARTIFACT",
                "feature_domain": None,
                "logical_key": f"api.test.{record_id}",
            },
        )
        assert response.status_code == 201

        invalid_revision_id = str(uuid.uuid4())
        invalid = client.post(
            "/api/CONTENT_REVISION",
            json={
                "revision_id": invalid_revision_id,
                "record_id": record_id,
                "schema_id": schema_id,
                "revision_no": 1,
                "content_json": {"artifact_type": "UNKNOWN"},
                "change_reason": "invalid test",
            },
        )
        assert invalid.status_code == 422
        payload = invalid.json()
        assert payload["error"] == "json_schema_validation_failed"
        assert payload["schema"]["schema_id"] == schema_id
        assert payload["errors"]
        revisions = client.get("/api/CONTENT_REVISION").json()["records"]
        assert all(row["revision_id"] != invalid_revision_id for row in revisions)

        revision_id = str(uuid.uuid4())
        valid = client.post(
            "/api/CONTENT_REVISION",
            json={
                "revision_id": revision_id,
                "record_id": record_id,
                "schema_id": schema_id,
                "revision_no": 1,
                "content_json": {
                    "artifact_type": "SYSTEM",
                    "process": "SYS.1",
                    "name": "API sample",
                    "purpose": "validate shared API flow",
                    "system_level": "SYSTEM_OF_INTEREST",
                    "operational_environment": [],
                },
                "change_reason": "valid test",
            },
        )
        assert valid.status_code == 201
        stored = json.loads((tmp_path / "localdata" / "CONTENT_REVISION.json").read_text())
        assert any(row["revision_id"] == revision_id for row in stored)

        schema_record = {
            "schema_id": str(uuid.uuid4()),
            "schema_key": "test.api-schema",
            "schema_version": 1,
            "record_type": "ARTIFACT",
            "feature_domain": None,
            "schema_json": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "urn:das:schema:test.api-schema:1",
                "type": "array",
                "items": {"type": "string"},
            },
        }
        registered = client.post("/api/JSON_SCHEMA", json=schema_record)
        assert registered.status_code == 201
        assert registered.json()["record"]["schema_json"] == schema_record["schema_json"]
        dynamic_revision = client.post(
            "/api/CONTENT_REVISION",
            json={
                "revision_id": str(uuid.uuid4()),
                "record_id": record_id,
                "schema_id": schema_record["schema_id"],
                "revision_no": 2,
                "content_json": ["dynamic JSON Schema payload"],
                "change_reason": "verify schema-driven JSON type",
            },
        )
        assert dynamic_revision.status_code == 201
        assert dynamic_revision.json()["record"]["content_json"] == ["dynamic JSON Schema payload"]

        invalid_schema = {**schema_record, "schema_id": str(uuid.uuid4())}
        invalid_schema["schema_json"] = {**schema_record["schema_json"], "type": "not-a-type"}
        rejected_schema = client.post("/api/JSON_SCHEMA", json=invalid_schema)
        assert rejected_schema.status_code == 422
        assert rejected_schema.json()["error"] == "json_schema_definition_invalid"

        mismatched_id_schema = {**schema_record, "schema_id": str(uuid.uuid4())}
        mismatched_id_schema["schema_json"] = {
            **schema_record["schema_json"],
            "$id": "urn:das:schema:wrong:1",
        }
        rejected_id = client.post("/api/JSON_SCHEMA", json=mismatched_id_schema)
        assert rejected_id.status_code == 422
        assert rejected_id.json()["errors"][0]["path"] == "/$id"


def test_mcp_validation_failure_is_structured(tmp_path: Path):
    database = create_database(environment={}, localdata_dir=tmp_path / "localdata")
    initialize_local_store(database)
    server = configure_mcp(database)
    schema_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "urn:das:schema:sys.artifact:1"))
    result = asyncio.run(
        server.call_tool(
            "create_record",
            {
                "table_name": "CONTENT_REVISION",
                "record": {
                    "revision_id": str(uuid.uuid4()),
                    "record_id": str(uuid.uuid4()),
                    "schema_id": schema_id,
                    "revision_no": 1,
                    "content_json": {"artifact_type": "UNKNOWN"},
                    "change_reason": "invalid MCP test",
                },
            },
        )
    )
    try:
        assert result.isError
        assert result.structuredContent["error"] == "json_schema_validation_failed"
        assert result.structuredContent["schema"]["schema_id"] == schema_id
        assert result.structuredContent["errors"]
    finally:
        database.engine.dispose()
