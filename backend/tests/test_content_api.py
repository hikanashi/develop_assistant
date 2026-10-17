"""jsonb 列の JSON Schema 検証 (REST / MCP)。DBへの書き込みはテスト終了時に破棄される。"""

import asyncio
import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from fastmcp import Client
from fastmcp.exceptions import ToolError
import pytest
from sqlalchemy import text

from app.main import app
from app.mcp_server import mcp

KEY = "test.note"
NOTE_V1 = {
    "type": "object",
    "required": ["title"],
    "properties": {"title": {"type": "string"}},
    "additionalProperties": False,
}
NOTE_V2 = {
    **NOTE_V1,
    "required": ["title", "owner"],
    "properties": {"title": {"type": "string"}, "owner": {"type": "string"}},
}


def register(client, version=1, body=None, **extra):
    return client.post(
        "/schemas",
        json={
            "schema_key": KEY,
            "schema_version": version,
            "record_type": "ARTIFACT",
            "schema_json": body or NOTE_V1,
            **extra,
        },
    )


def new_record(client, content, key=None, **extra):
    return client.post(
        "/records",
        json={
            "record_type": "ARTIFACT",
            "logical_key": key or f"k-{uuid.uuid4()}",
            "schema_key": KEY,
            "content_json": content,
            **extra,
        },
    )


def count(db_session, sql, **params):
    return db_session.execute(text(sql), params).scalar_one()


def test_register_and_fetch_schema(client):
    res = register(client)
    assert res.status_code == 201
    created = res.json()
    assert created["schema_json"] == NOTE_V1

    assert client.get(f"/schemas/{created['schema_id']}").json() == created
    assert client.get(f"/schemas/by-key/{KEY}").json()["schema_version"] == 1

    assert register(client, 2, NOTE_V2).status_code == 201
    assert client.get(f"/schemas/by-key/{KEY}").json()["schema_version"] == 2
    assert client.get(f"/schemas/by-key/{KEY}", params={"version": 1}).json() == created
    assert [
        s["schema_version"] for s in client.get("/schemas", params={"schema_key": KEY}).json()
    ] == [1, 2]
    assert client.get(f"/schemas/by-key/{KEY}", params={"version": 9}).status_code == 404
    assert client.get(f"/schemas/{uuid.uuid4()}").status_code == 404


def test_register_rejects_invalid_schema(client, db_session):
    res = register(client, body={"type": "nonsense"})
    assert res.status_code == 422
    body = res.json()
    assert body["error"] == "json_schema_validation_failed"
    assert body["target"] == "schema_json"
    assert body["errors"][0]["path"] == "/type"

    res = register(client, body={**NOTE_V1, "$id": "urn:das:schema:test.note:9"})
    assert res.status_code == 422
    assert res.json()["errors"][0]["path"] == "/$id"
    assert count(db_session, "select count(*) from json_schema where schema_key = :k", k=KEY) == 0


def test_register_duplicate_version_conflicts(client):
    assert register(client).status_code == 201
    res = register(client)
    assert res.status_code == 409
    assert res.json()["error"] == "constraint_violation"


def test_valid_content_creates_record_and_revisions(client, db_session):
    schema = register(client).json()
    res = new_record(client, {"title": "a"}, change_reason="first")
    assert res.status_code == 201
    record = res.json()
    assert [r["revision_no"] for r in record["revisions"]] == [1]
    assert record["revisions"][0]["schema_id"] == schema["schema_id"]

    res = client.post(
        f"/records/{record['record_id']}/revisions",
        json={"schema_id": schema["schema_id"], "content_json": {"title": "b"}},
    )
    assert res.status_code == 201
    assert res.json()["revision_no"] == 2

    fetched = client.get(f"/records/{record['record_id']}").json()
    assert [r["content_json"]["title"] for r in fetched["revisions"]] == ["a", "b"]
    assert (
        count(
            db_session,
            "select count(*) from revision_parent where relationship = 'PREVIOUS' "
            "and revision_id = :r",
            r=fetched["revisions"][1]["revision_id"],
        )
        == 1
    )


def test_update_record_replaces_record_fields_and_appends_revision(client):
    schema = register(client).json()
    record = new_record(client, {"title": "before"}).json()

    res = client.put(
        f"/records/{record['record_id']}",
        json={
            "record_type": "ARTIFACT",
            "logical_key": "renamed",
            "schema_id": schema["schema_id"],
            "content_json": {"title": "after"},
            "change_reason": "rename and update",
        },
    )

    assert res.status_code == 200
    updated = res.json()
    assert updated["logical_key"] == "renamed"
    assert [revision["revision_no"] for revision in updated["revisions"]] == [1, 2]
    assert updated["revisions"][1]["content_json"] == {"title": "after"}
    assert updated["revisions"][1]["change_reason"] == "rename and update"
    assert updated["revisions"][1]["record_id"] == record["record_id"]


def test_update_record_validation_error_changes_neither_table(client, db_session):
    register(client)
    record = new_record(client, {"title": "before"}, key="original").json()

    res = client.put(
        f"/records/{record['record_id']}",
        json={
            "record_type": "ARTIFACT",
            "logical_key": "changed",
            "schema_key": KEY,
            "content_json": {"title": 1},
        },
    )

    assert res.status_code == 422
    assert res.json()["error"] == "json_schema_validation_failed"
    assert client.get(f"/records/{record['record_id']}").json()["logical_key"] == "original"
    assert count(
        db_session,
        "select count(*) from content_revision where record_id = :r",
        r=record["record_id"],
    ) == 1


def test_update_record_not_found(client):
    register(client)
    res = client.put(
        f"/records/{uuid.uuid4()}",
        json={
            "record_type": "ARTIFACT",
            "logical_key": "missing",
            "schema_key": KEY,
            "content_json": {"title": "x"},
        },
    )
    assert res.status_code == 404
    assert res.json()["error"] == "record_not_found"


def test_record_update_is_exposed_in_openapi():
    openapi = TestClient(app).get("/openapi.json").json()
    operation = openapi["paths"]["/records/{record_id}"]["put"]
    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/RecordUpdateIn"
    )
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/RecordWithRevisions"
    )


def test_invalid_content_is_rejected_without_writing(client, db_session):
    register(client)
    res = new_record(client, {"title": 1, "extra": True}, key="rejected")
    assert res.status_code == 422
    body = res.json()
    assert body["error"] == "json_schema_validation_failed"
    assert body["target"] == "content_json"
    assert body["schema"]["schema_key"] == KEY
    assert body["schema"]["schema_version"] == 1
    assert {(e["validator"], e["path"]) for e in body["errors"]} >= {
        ("type", "/title"),
        ("additionalProperties", ""),
    }
    assert body["refetch"]["rest"] == f"GET /schemas/{body['schema']['schema_id']}"
    assert (
        count(db_session, "select count(*) from content_record where logical_key = 'rejected'") == 0
    )

    ok = new_record(client, {"title": "ok"}).json()
    res = client.post(
        f"/records/{ok['record_id']}/revisions", json={"schema_key": KEY, "content_json": {}}
    )
    assert res.status_code == 422
    assert (
        count(
            db_session,
            "select count(*) from content_revision where record_id = :r",
            r=ok["record_id"],
        )
        == 1
    )


def test_caller_can_refetch_schema_and_fix(client):
    register(client)
    bad = new_record(client, {"name": "x"})
    assert bad.status_code == 422
    refetched = client.get(bad.json()["refetch"]["rest"].removeprefix("GET ")).json()
    assert refetched["schema_json"]["required"] == ["title"]
    assert new_record(client, {"title": "x"}).status_code == 201


def test_new_schema_version_applies_to_new_revisions_only(client):
    v1 = register(client).json()
    record = new_record(client, {"title": "a"}).json()
    register(client, 2, NOTE_V2)

    res = client.post(
        f"/records/{record['record_id']}/revisions",
        json={"schema_key": KEY, "schema_version": 1, "content_json": {"title": "b"}},
    )
    assert res.status_code == 201

    res = client.post(
        f"/records/{record['record_id']}/revisions",
        json={"schema_key": KEY, "content_json": {"title": "c"}},
    )
    assert res.status_code == 422
    assert res.json()["schema"]["schema_version"] == 2
    assert res.json()["errors"][0]["validator"] == "required"

    res = client.post(
        f"/records/{record['record_id']}/revisions",
        json={"schema_key": KEY, "content_json": {"title": "c", "owner": "me"}},
    )
    assert res.status_code == 201
    revisions = client.get(f"/records/{record['record_id']}").json()["revisions"]
    assert revisions[0]["schema_id"] == v1["schema_id"]
    assert revisions[2]["schema_id"] != v1["schema_id"]


def test_error_reports_newer_schema_version(client):
    register(client)
    register(client, 2, NOTE_V2)
    res = client.post(
        "/records",
        json={
            "record_type": "ARTIFACT",
            "logical_key": "old",
            "schema_key": KEY,
            "schema_version": 1,
            "content_json": {"title": 1},
        },
    )
    assert res.status_code == 422
    assert res.json()["schema"]["latest_schema_version"] == 2


def test_other_errors(client):
    register(client)
    assert (
        new_record(
            client, {"title": "x"}, record_type="FEATURE", feature_domain="HARDWARE"
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/records",
            json={"record_type": "ARTIFACT", "logical_key": "k", "content_json": {}},
        ).status_code
        == 422
    )  # スキーマの指定なし
    assert (
        client.post(
            "/records",
            json={
                "record_type": "ARTIFACT",
                "logical_key": "k",
                "schema_key": "none",
                "content_json": {},
            },
        ).status_code
        == 404
    )
    assert client.get(f"/records/{uuid.uuid4()}").status_code == 404
    new_record(client, {"title": "x"}, key="dup")
    assert new_record(client, {"title": "x"}, key="dup").status_code == 409


def test_artifact_schema_from_design_can_be_registered(client):
    path = Path(__file__).resolve().parents[2] / "design/database/schemas"
    schema = json.loads((path / "sys.artifact.schema.json").read_text(encoding="utf-8"))
    # 初期データの sys.artifact と重複させないよう、$id のキーを変えて登録する
    schema["$id"] = "urn:das:schema:sys.artifact.test:1"
    examples = json.loads((path / "examples/sys2.use_case.json").read_text(encoding="utf-8"))
    res = client.post(
        "/schemas",
        json={
            "schema_key": "sys.artifact.test",
            "schema_version": 1,
            "record_type": "ARTIFACT",
            "schema_json": schema,
        },
    )
    assert res.status_code == 201
    body = {"record_type": "ARTIFACT", "schema_key": "sys.artifact.test"}
    ok = client.post(
        "/records", json={**body, "logical_key": "uc1", "content_json": examples["valid"][0]}
    )
    assert ok.status_code == 201
    ng = client.post(
        "/records", json={**body, "logical_key": "uc2", "content_json": examples["invalid"][0]}
    )
    assert ng.status_code == 422


def call(tool, **args):
    async def run():
        async with Client(mcp) as c:
            return await c.call_tool(tool, args)

    return asyncio.run(run())


def test_mcp_returns_validation_errors_as_tool_error(client):
    schema = register(client).json()
    with pytest.raises(ToolError) as info:
        call(
            "create_record",
            record_type="ARTIFACT",
            logical_key="m1",
            schema_key=KEY,
            content_json={"title": 1},
        )
    payload = json.loads(str(info.value).removeprefix("Error calling tool 'create_record': "))
    assert payload["error"] == "json_schema_validation_failed"
    assert payload["errors"][0]["path"] == "/title"
    assert payload["refetch"]["mcp_tool"] == "get_json_schema"

    fetched = call("get_json_schema", **payload["refetch"]["arguments"]).data
    assert fetched["schema_json"] == NOTE_V1
    assert fetched["schema_id"] == schema["schema_id"]

    created = call(
        "create_record",
        record_type="ARTIFACT",
        logical_key="m1",
        schema_key=KEY,
        content_json={"title": "fixed"},
    ).data
    assert created["revisions"][0]["content_json"] == {"title": "fixed"}
