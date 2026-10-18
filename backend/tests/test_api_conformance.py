"""REST API 仕様 (OPENAPI_FILE) と、REST・MCP の実装の一致 (ENV-046)。"""

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client
from fastmcp.exceptions import ToolError

from app.db import get_session
from app.main import app
from app.mcp_server import MCP_ONLY_TOOLS, mcp

SPEC_PATH = Path(__file__).resolve().parents[2] / "openapi" / "openapi.yaml"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

# openapi/ がない環境 (マウントしていない backend コンテナなど) ではスキップする
needs_spec = pytest.mark.skipif(not SPEC_PATH.exists(), reason="openapi/ がありません")


def load_spec():
    yaml = pytest.importorskip("yaml")  # uvicorn[standard] の依存
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


def resolve_schema(schema, components):
    if "$ref" in schema:
        target = components
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        schema = {
            **resolve_schema(target, components),
            **{k: v for k, v in schema.items() if k != "$ref"},
        }

    resolved = {
        key: resolve_schema(value, components) if isinstance(value, dict) else value
        for key, value in schema.items()
        if key != "allOf"
    }
    for part in schema.get("allOf", []):
        part = resolve_schema(part, components)
        if "properties" in part:
            resolved["properties"] = {**resolved.get("properties", {}), **part["properties"]}
        if "required" in part:
            resolved["required"] = list(
                dict.fromkeys(resolved.get("required", []) + part["required"])
            )
        for key, value in part.items():
            if key not in {"properties", "required"}:
                resolved.setdefault(key, value)
    for key in ("anyOf", "oneOf"):
        if key in resolved:
            resolved[key] = [resolve_schema(part, components) for part in resolved[key]]
    return resolved


def schema_contract(schema):
    if "type" in schema and isinstance(schema["type"], list):
        alternatives = []
        for value in schema["type"]:
            branch = {**schema, "type": value}
            if value == "null":
                branch = {"type": value}
            alternatives.append(schema_contract(branch))
        return "union", tuple(sorted(alternatives, key=repr))
    if "anyOf" in schema or "oneOf" in schema:
        key = "anyOf" if "anyOf" in schema else "oneOf"
        return "union", tuple(sorted((schema_contract(part) for part in schema[key]), key=repr))
    return tuple(
        (key, tuple(value) if isinstance(value, list) else value)
        for key, value in sorted(schema.items())
        if key
        in {
            "type",
            "format",
            "enum",
            "minimum",
            "maximum",
            "exclusiveMinimum",
            "exclusiveMaximum",
            "minLength",
            "maxLength",
            "pattern",
            "minItems",
            "maxItems",
        }
    )


def operation_inputs(operation, components):
    properties = {}
    required = set()
    for parameter in operation.get("parameters", []):
        parameter = resolve_schema(parameter, components)
        properties[parameter["name"]] = resolve_schema(parameter["schema"], components)
        if parameter.get("required"):
            required.add(parameter["name"])

    request_body = operation.get("requestBody")
    if request_body:
        body = resolve_schema(request_body, components)
        if body.get("required"):
            schema = resolve_schema(body["content"]["application/json"]["schema"], components)
            properties.update(schema.get("properties", {}))
            required.update(schema.get("required", []))
    return properties, required


def operations(paths):
    return {
        (method, path, op["operationId"])
        for path, item in paths.items()
        for method, op in item.items()
        if method in HTTP_METHODS
    }


@needs_spec
def test_rest_routes_match_spec():
    spec = load_spec()
    assert operations(app.openapi()["paths"]) == operations(spec["paths"])


@needs_spec
def test_mcp_tools_match_spec_operations():
    spec = load_spec()
    operation_ids = {op_id for _, _, op_id in operations(spec["paths"])}

    async def list_tools():
        async with Client(mcp) as c:
            return {t.name: t for t in await c.list_tools()}

    tools = asyncio.run(list_tools())
    assert set(tools) - MCP_ONLY_TOOLS == operation_ids
    # REST API にある処理を、MCP 専用のツールにしない
    assert not MCP_ONLY_TOOLS & operation_ids

    components = spec
    for method, path, op_id in operations(spec["paths"]):
        operation = spec["paths"][path][method]
        properties, required = operation_inputs(operation, components)
        input_schema = tools[op_id].input_schema
        assert set(input_schema["properties"]) == set(properties), op_id
        assert set(input_schema.get("required", [])) == required, op_id
        for name, schema in properties.items():
            expected = schema_contract(resolve_schema(schema, components))
            actual = schema_contract(input_schema["properties"][name])
            assert actual == expected, f"{op_id}.{name}: {actual} != {expected}"


@needs_spec
def test_schema_refs_are_host_less_and_unversioned():
    """スキーマ取得の外部参照は、ホストと版を書かない (ENV-043)。"""
    spec = load_spec()
    refs = []

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("$ref"), str) and not node["$ref"].startswith("#"):
                refs.append(node["$ref"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(spec)
    assert refs
    for ref in refs:
        assert ref.startswith("/v1/schemas/") and ref.endswith("/schema-json"), ref


@needs_spec
def test_spec_is_served_and_shown_in_docs(client):
    """OPENAPI_FILE を /openapi.yaml で配信し、/docs (Swagger UI) で表示する (ENV-047)。"""
    res = client.get("/openapi.yaml")
    assert res.status_code == 200
    assert res.text == SPEC_PATH.read_text(encoding="utf-8")
    assert "/openapi.yaml" in client.get("/docs").text


def call(tool, **args):
    async def run():
        async with Client(mcp) as c:
            return await c.call_tool(tool, args)

    return asyncio.run(run())


def mcp_json(tool, **args):
    return json.loads(call(tool, **args).content[0].text)


def mcp_error(tool, **args):
    with pytest.raises(ToolError) as info:
        call(tool, **args)
    return json.loads(str(info.value)[str(info.value).index("{") :])


def test_rest_and_mcp_return_same_results_and_errors(client):
    schema = {"type": "object", "required": ["title"], "properties": {"title": {"type": "string"}}}
    body = {"schemaKey": "test.parity", "schemaVersion": 1, "recordType": "ARTIFACT"}
    created = client.post("/v1/schemas", json={**body, "schemaJson": schema}).json()

    assert call("getSchema", schemaId=created["schemaId"]).data == created
    assert call("getSchemaByKey", schemaKey="test.parity").data == created
    assert (
        mcp_json("listSchemas", schemaKey="test.parity")
        == client.get("/v1/schemas", params={"schemaKey": "test.parity"}).json()
    )

    record = client.post(
        "/v1/records",
        json={
            "recordType": "ARTIFACT",
            "logicalKey": "parity-1",
            "schemaKey": "test.parity",
            "contentJson": {"title": "a"},
        },
    ).json()
    assert call("getRecord", recordId=record["recordId"]).data == record

    # 同じ入力に対する、検証エラーと業務エラーの内容が同じ
    invalid = {"recordType": "ARTIFACT", "logicalKey": "parity-2", "schemaKey": "test.parity"}
    rest = client.post("/v1/records", json={**invalid, "contentJson": {"title": 1}})
    assert rest.status_code == 422
    assert mcp_error("createRecord", **invalid, contentJson={"title": 1}) == rest.json()

    rest = client.get("/v1/schemas/by-key/no.such")
    assert rest.status_code == 404
    assert mcp_error("getSchemaByKey", schemaKey="no.such") == rest.json()


def test_mcp_input_validation_matches_rest(monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, get_session, lambda: None)
    rest_client = TestClient(app)
    cases = [
        ("createSchema", {}, "post", "/v1/schemas", {}),
        (
            "createSchema",
            {
                "schemaKey": "test.invalid",
                "schemaVersion": 0,
                "recordType": "ARTIFACT",
                "schemaJson": {},
            },
            "post",
            "/v1/schemas",
            {
                "schemaKey": "test.invalid",
                "schemaVersion": 0,
                "recordType": "ARTIFACT",
                "schemaJson": {},
            },
        ),
        (
            "createSchema",
            {
                "schemaKey": "test.invalid",
                "schemaVersion": 1,
                "recordType": "INVALID",
                "schemaJson": {},
            },
            "post",
            "/v1/schemas",
            {
                "schemaKey": "test.invalid",
                "schemaVersion": 1,
                "recordType": "INVALID",
                "schemaJson": {},
            },
        ),
        ("getSchema", {"schemaId": "not-a-uuid"}, "get", "/v1/schemas/not-a-uuid", None),
        (
            "createRecord",
            {"recordType": "ARTIFACT", "logicalKey": "no-schema", "contentJson": {}},
            "post",
            "/v1/records",
            {"recordType": "ARTIFACT", "logicalKey": "no-schema", "contentJson": {}},
        ),
    ]
    for tool, arguments, method, path, body in cases:
        response = (
            getattr(rest_client, method)(path, json=body)
            if body is not None
            else getattr(rest_client, method)(path)
        )
        assert response.status_code == 400
        assert mcp_error(tool, **arguments) == response.json()
