"""jsonb 列の JSON Schema 検証 (REST / MCP)。DBへの書き込みはテスト終了時に破棄される。"""

import asyncio
import json
import uuid
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from sqlalchemy import text

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
        "/v1/schemas",
        json={
            "schemaKey": KEY,
            "schemaVersion": version,
            "recordType": "ARTIFACT",
            "schemaJson": body or NOTE_V1,
            **extra,
        },
    )


def new_record(client, content, key=None, **extra):
    return client.post(
        "/v1/records",
        json={
            "recordType": "ARTIFACT",
            "logicalKey": key or f"k-{uuid.uuid4()}",
            "schemaKey": KEY,
            "contentJson": content,
            **extra,
        },
    )


def count(db_session, sql, **params):
    return db_session.execute(text(sql), params).scalar_one()


def test_register_and_fetch_schema(client):
    res = register(client)
    assert res.status_code == 201
    created = res.json()
    assert created["schemaJson"] == NOTE_V1

    assert client.get(f"/v1/schemas/{created['schemaId']}").json() == created
    assert client.get(f"/v1/schemas/by-key/{KEY}").json()["schemaVersion"] == 1

    assert register(client, 2, NOTE_V2).status_code == 201
    assert client.get(f"/v1/schemas/by-key/{KEY}").json()["schemaVersion"] == 2
    assert client.get(f"/v1/schemas/by-key/{KEY}", params={"version": 1}).json() == created
    assert [
        s["schemaVersion"] for s in client.get("/v1/schemas", params={"schemaKey": KEY}).json()
    ] == [1, 2]
    assert client.get(f"/v1/schemas/by-key/{KEY}", params={"version": 9}).status_code == 404
    assert client.get(f"/v1/schemas/{uuid.uuid4()}").status_code == 404


def test_register_rejects_invalid_schema(client, db_session):
    res = register(client, body={"type": "nonsense"})
    assert res.status_code == 422
    body = res.json()
    assert body["code"] == "JSON_SCHEMA_VALIDATION_FAILED"
    assert body["details"]["target"] == "schemaJson"
    assert body["details"]["errors"][0]["path"] == "/type"

    res = register(client, body={**NOTE_V1, "$id": "urn:das:schema:test.note:9"})
    assert res.status_code == 422
    assert res.json()["details"]["errors"][0]["path"] == "/$id"
    assert count(db_session, "select count(*) from json_schema where schema_key = :k", k=KEY) == 0


def test_register_duplicate_version_conflicts(client):
    assert register(client).status_code == 201
    res = register(client)
    assert res.status_code == 409
    assert res.json()["code"] == "CONSTRAINT_VIOLATION"


def test_valid_content_creates_record_and_revisions(client, db_session):
    schema = register(client).json()
    res = new_record(client, {"title": "a"}, change_reason="first")
    assert res.status_code == 201
    record = res.json()
    assert [r["revisionNo"] for r in record["revisions"]] == [1]
    assert record["revisions"][0]["schemaId"] == schema["schemaId"]

    res = client.post(
        f"/v1/records/{record['recordId']}/revisions",
        json={"schemaId": schema["schemaId"], "contentJson": {"title": "b"}},
    )
    assert res.status_code == 201
    assert res.json()["revisionNo"] == 2

    fetched = client.get(f"/v1/records/{record['recordId']}").json()
    assert [r["contentJson"]["title"] for r in fetched["revisions"]] == ["a", "b"]
    assert (
        count(
            db_session,
            "select count(*) from revision_parent where relationship = 'PREVIOUS' "
            "and revision_id = :r",
            r=fetched["revisions"][1]["revisionId"],
        )
        == 1
    )


def test_invalid_content_is_rejected_without_writing(client, db_session):
    register(client)
    res = new_record(client, {"title": 1, "extra": True}, key="rejected")
    assert res.status_code == 422
    body = res.json()
    assert body["code"] == "JSON_SCHEMA_VALIDATION_FAILED"
    details = body["details"]
    assert details["target"] == "contentJson"
    assert details["schema"]["schemaKey"] == KEY
    assert details["schema"]["schemaVersion"] == 1
    assert {(e["validator"], e["path"]) for e in details["errors"]} >= {
        ("type", "/title"),
        ("additionalProperties", ""),
    }
    assert details["refetch"]["rest"] == f"GET /v1/schemas/{details['schema']['schemaId']}"
    assert (
        count(db_session, "select count(*) from content_record where logical_key = 'rejected'") == 0
    )

    ok = new_record(client, {"title": "ok"}).json()
    res = client.post(
        f"/v1/records/{ok['recordId']}/revisions", json={"schemaKey": KEY, "contentJson": {}}
    )
    assert res.status_code == 422
    assert (
        count(
            db_session,
            "select count(*) from content_revision where record_id = :r",
            r=ok["recordId"],
        )
        == 1
    )


def test_caller_can_refetch_schema_and_fix(client):
    register(client)
    bad = new_record(client, {"name": "x"})
    assert bad.status_code == 422
    refetched = client.get(bad.json()["details"]["refetch"]["rest"].removeprefix("GET ")).json()
    assert refetched["schemaJson"]["required"] == ["title"]
    assert new_record(client, {"title": "x"}).status_code == 201


def test_new_schema_version_applies_to_new_revisions_only(client):
    v1 = register(client).json()
    record = new_record(client, {"title": "a"}).json()
    register(client, 2, NOTE_V2)

    res = client.post(
        f"/v1/records/{record['recordId']}/revisions",
        json={"schemaKey": KEY, "schemaVersion": 1, "contentJson": {"title": "b"}},
    )
    assert res.status_code == 201

    res = client.post(
        f"/v1/records/{record['recordId']}/revisions",
        json={"schemaKey": KEY, "contentJson": {"title": "c"}},
    )
    assert res.status_code == 422
    assert res.json()["details"]["schema"]["schemaVersion"] == 2
    assert res.json()["details"]["errors"][0]["validator"] == "required"

    res = client.post(
        f"/v1/records/{record['recordId']}/revisions",
        json={"schemaKey": KEY, "contentJson": {"title": "c", "owner": "me"}},
    )
    assert res.status_code == 201
    revisions = client.get(f"/v1/records/{record['recordId']}").json()["revisions"]
    assert revisions[0]["schemaId"] == v1["schemaId"]
    assert revisions[2]["schemaId"] != v1["schemaId"]


def test_error_reports_newer_schema_version(client):
    register(client)
    register(client, 2, NOTE_V2)
    res = client.post(
        "/v1/records",
        json={
            "recordType": "ARTIFACT",
            "logicalKey": "old",
            "schemaKey": KEY,
            "schemaVersion": 1,
            "contentJson": {"title": 1},
        },
    )
    assert res.status_code == 422
    assert res.json()["details"]["schema"]["latestSchemaVersion"] == 2


def test_other_errors(client):
    register(client)
    assert (
        new_record(
            client, {"title": "x"}, recordType="FEATURE", featureDomain="HARDWARE"
        ).status_code
        == 409
    )
    res = client.post(
        "/v1/records", json={"recordType": "ARTIFACT", "logicalKey": "k", "contentJson": {}}
    )  # スキーマの指定なし
    assert res.status_code == 400
    assert res.json()["code"] == "INVALID_REQUEST"
    assert res.json()["details"]["errors"][0]["in"] == "body"
    assert (
        client.post(
            "/v1/records",
            json={
                "recordType": "ARTIFACT",
                "logicalKey": "k",
                "schemaKey": "none",
                "contentJson": {},
            },
        ).status_code
        == 404
    )
    assert client.get(f"/v1/records/{uuid.uuid4()}").status_code == 404
    new_record(client, {"title": "x"}, key="dup")
    assert new_record(client, {"title": "x"}, key="dup").status_code == 409


def test_artifact_schema_from_design_can_be_registered(client):
    path = Path(__file__).resolve().parents[2] / "design/database/schemas"
    schema = json.loads((path / "sys.artifact.schema.json").read_text(encoding="utf-8"))
    # 初期データの sys.artifact と重複させないよう、$id のキーを変えて登録する
    schema["$id"] = "urn:das:schema:sys.artifact.test:1"
    examples = json.loads((path / "examples/sys2.use_case.json").read_text(encoding="utf-8"))
    res = client.post(
        "/v1/schemas",
        json={
            "schemaKey": "sys.artifact.test",
            "schemaVersion": 1,
            "recordType": "ARTIFACT",
            "schemaJson": schema,
        },
    )
    assert res.status_code == 201
    body = {"recordType": "ARTIFACT", "schemaKey": "sys.artifact.test"}
    ok = client.post(
        "/v1/records", json={**body, "logicalKey": "uc1", "contentJson": examples["valid"][0]}
    )
    assert ok.status_code == 201
    ng = client.post(
        "/v1/records", json={**body, "logicalKey": "uc2", "contentJson": examples["invalid"][0]}
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
            "createRecord",
            recordType="ARTIFACT",
            logicalKey="m1",
            schemaKey=KEY,
            contentJson={"title": 1},
        )
    payload = json.loads(str(info.value).removeprefix("Error calling tool 'createRecord': "))
    assert payload["code"] == "JSON_SCHEMA_VALIDATION_FAILED"
    details = payload["details"]
    assert details["errors"][0]["path"] == "/title"
    assert details["refetch"]["mcpTool"] == "getSchema"

    fetched = call(details["refetch"]["mcpTool"], **details["refetch"]["arguments"]).data
    assert fetched["schemaJson"] == NOTE_V1
    assert fetched["schemaId"] == schema["schemaId"]

    created = call(
        "createRecord",
        recordType="ARTIFACT",
        logicalKey="m1",
        schemaKey=KEY,
        contentJson={"title": "fixed"},
    ).data
    assert created["revisions"][0]["contentJson"] == {"title": "fixed"}


def test_error_response_follows_guideline(client):
    res = client.get(f"/v1/records/{uuid.uuid4()}")
    assert res.status_code == 404
    body = res.json()
    assert body == {"code": "RECORD_NOT_FOUND", "message": body["message"], "details": None}
    res = client.get("/v1/unknown")
    assert res.status_code == 404
    assert res.json()["code"] == "NOT_FOUND"
    assert res.json()["details"] is None
    res = client.get("/v1/records/not-a-uuid")
    assert res.status_code == 400
    assert res.json()["details"]["errors"][0]["in"] == "path"


def test_schema_json_endpoints_return_schema_body(client):
    created = register(client).json()
    by_id = client.get(f"/v1/schemas/{created['schemaId']}/schema-json")
    assert by_id.status_code == 200
    assert by_id.json() == NOTE_V1
    register(client, 2, NOTE_V2)
    by_key = f"/v1/schemas/by-key/{KEY}/schema-json"
    assert client.get(by_key, params={"version": 1}).json() == NOTE_V1
    assert client.get(by_key).json() == NOTE_V2  # version を省略すると最新版
    assert client.get(by_key, params={"version": 9}).status_code == 404

    assert call("getSchemaJson", schemaId=created["schemaId"]).data == NOTE_V1
    assert call("getSchemaJsonByKey", schemaKey=KEY).data == NOTE_V2


def test_mcp_invalid_input_uses_error_format(client):
    with pytest.raises(ToolError) as info:
        call("createRecord", recordType="FEATURE", logicalKey="m2", schemaKey=KEY, contentJson={})
    payload = json.loads(str(info.value)[str(info.value).index("{") :])
    assert payload["code"] == "INVALID_REQUEST"
    assert payload["details"]["errors"]


def test_schema_json_omits_id_but_schema_keeps_it(client):
    """外部参照として解決できるよう、スキーマ本体 API は $id (urn:) を除いて返す。"""
    body = {**NOTE_V1, "$id": f"urn:das:schema:{KEY}:1"}
    created = register(client, body=body).json()
    assert created["schemaJson"]["$id"] == body["$id"]
    assert client.get(f"/v1/schemas/{created['schemaId']}").json()["schemaJson"] == body
    assert client.get(f"/v1/schemas/{created['schemaId']}/schema-json").json() == NOTE_V1
    assert client.get(f"/v1/schemas/by-key/{KEY}/schema-json").json() == NOTE_V1
    assert call("getSchemaJsonByKey", schemaKey=KEY).data == NOTE_V1
