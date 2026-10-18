"""REST API 仕様 (OPENAPI_FILE) と、REST・MCP の実装の一致 (ENV-046)。"""

import asyncio
import json
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from app.main import app
from app.mcp_server import MCP_ONLY_TOOLS, mcp

SPEC_PATH = Path(__file__).resolve().parents[2] / "openapi" / "openapi.yaml"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

# openapi/ がない環境 (マウントしていない backend コンテナなど) ではスキップする
needs_spec = pytest.mark.skipif(not SPEC_PATH.exists(), reason="openapi/ がありません")


def load_spec():
    yaml = pytest.importorskip("yaml")  # uvicorn[standard] の依存
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


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

    # パス・クエリのパラメーターは、同名の MCP ツールの引数にある
    for method, path, op_id in operations(spec["paths"]):
        names = {
            spec["components"]["parameters"][p["$ref"].rsplit("/", 1)[1]]["name"]
            if "$ref" in p
            else p["name"]
            for p in spec["paths"][path][method].get("parameters", [])
        }
        assert names <= set(tools[op_id].input_schema["properties"]), op_id


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
