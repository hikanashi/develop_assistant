import json
import uuid
from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import ValidationError
from sqlalchemy import text
from sqlmodel import Session

from app import services
from app.db import engine, session_scope
from app.schemas import (
    FeatureDomain,
    JsonSchemaIn,
    RecordIn,
    RecordType,
    RevisionIn,
    SchemaRef,
)

mcp = FastMCP("develop-assistant")


def _run(action: Callable[[Session], Any]) -> Any:
    """サービス層を呼び、エラーは REST と同じ形式 (code / message / details) の JSON を
    メッセージとする ToolError にする。検証エラーの details には errors と、
    スキーマの再取得方法 (refetch) が含まれる。
    """
    try:
        with session_scope() as session:
            result = action(session)
    except services.ServiceError as e:
        raise ToolError(json.dumps(e.payload(), ensure_ascii=False)) from None
    except ValidationError as e:
        error = services.invalid_request(e.errors())
        raise ToolError(json.dumps(error.payload(), ensure_ascii=False)) from None
    return json.loads(json.dumps(result, default=_encode))


def _encode(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    raise TypeError(type(value))


# MCP ツールは REST API の operation に 1 対 1 で対応する薄いアダプターで、ツール名は operationId、
# 引数名は REST と同じ camelCase とする。処理は services.py にだけ実装する (ENV-046)。
# REST API にない処理だけ、MCP 専用のツールとしてよい (MCP_ONLY_TOOLS)。
MCP_ONLY_TOOLS = frozenset({"db_version"})


@mcp.tool
def db_version() -> str:
    """接続中のPostgreSQLのバージョンを返す。(MCP 専用)"""
    with engine.connect() as conn:
        return conn.execute(text("select version()")).scalar_one()


@mcp.tool(name="listSchemas")
def list_schemas(schemaKey: str | None = None, recordType: RecordType | None = None):
    """登録済みの JSON Schema (schemaJson を除く) を一覧する。"""
    return _run(lambda s: services.list_schemas(s, schemaKey, recordType))


@mcp.tool(name="getSchema")
def get_schema(schemaId: uuid.UUID):
    """schemaId で JSON Schema を取得する。

    contentJson の検証エラーが出たときは、このツールでスキーマを再取得し、
    errors の path の箇所を修正して再送する。
    """
    return _run(lambda s: services.get_schema(s, SchemaRef(schema_id=schemaId)))


@mcp.tool(name="getSchemaByKey")
def get_schema_by_key(schemaKey: str, version: int | None = None):
    """schemaKey で JSON Schema を取得する。version を省略すると最新版を返す。"""
    return _run(
        lambda s: services.get_schema(s, SchemaRef(schema_key=schemaKey, schema_version=version))
    )


@mcp.tool(name="getSchemaJson")
def get_schema_json(schemaId: uuid.UUID):
    """schemaId の JSON Schema 本体 (schemaJson) だけを返す。"""
    return _run(lambda s: services.get_schema_json(s, SchemaRef(schema_id=schemaId)))


@mcp.tool(name="getSchemaJsonByKey")
def get_schema_json_by_key(schemaKey: str, version: int | None = None):
    """schemaKey の JSON Schema 本体 (schemaJson) だけを返す。version を省略すると最新版。"""
    return _run(
        lambda s: services.get_schema_json(
            s, SchemaRef(schema_key=schemaKey, schema_version=version)
        )
    )


@mcp.tool(name="createSchema")
def create_schema(
    schemaKey: str,
    schemaVersion: int,
    recordType: RecordType,
    schemaJson: dict[str, Any],
    featureDomain: FeatureDomain | None = None,
):
    """新しい JSON Schema (版) を登録する。登録済みのスキーマは更新できないため、
    変更するときは同じ schemaKey で schemaVersion を増やして登録する。
    """
    return _run(
        lambda s: services.register_schema(
            s,
            JsonSchemaIn(
                schema_key=schemaKey,
                schema_version=schemaVersion,
                record_type=recordType,
                feature_domain=featureDomain,
                schema_body=schemaJson,
            ),
        )
    )


@mcp.tool(name="createRecord")
def create_record(
    recordType: RecordType,
    logicalKey: str,
    contentJson: dict[str, Any],
    schemaId: uuid.UUID | None = None,
    schemaKey: str | None = None,
    schemaVersion: int | None = None,
    featureDomain: FeatureDomain | None = None,
    originPlatformId: uuid.UUID | None = None,
    originProductId: uuid.UUID | None = None,
    changeReason: str | None = None,
):
    """レコードと最初のリビジョンを作成する。

    contentJson は指定したスキーマ (schemaId、または schemaKey の最新版) で検証され、
    適合しない場合は何も保存されずエラーの詳細が返る。
    """
    return _run(
        lambda s: services.create_record(
            s,
            RecordIn(
                record_type=recordType,
                logical_key=logicalKey,
                content_json=contentJson,
                schema_id=schemaId,
                schema_key=schemaKey,
                schema_version=schemaVersion,
                feature_domain=featureDomain,
                origin_platform_id=originPlatformId,
                origin_product_id=originProductId,
                change_reason=changeReason,
            ),
        )
    )


@mcp.tool(name="createRevision")
def create_revision(
    recordId: uuid.UUID,
    contentJson: dict[str, Any],
    schemaId: uuid.UUID | None = None,
    schemaKey: str | None = None,
    schemaVersion: int | None = None,
    changeReason: str | None = None,
):
    """既存レコードに新しいリビジョンを追加する。検証の扱いは createRecord と同じ。"""
    return _run(
        lambda s: services.add_revision(
            s,
            recordId,
            RevisionIn(
                content_json=contentJson,
                schema_id=schemaId,
                schema_key=schemaKey,
                schema_version=schemaVersion,
                change_reason=changeReason,
            ),
        )
    )


@mcp.tool(name="getRecord")
def get_record(recordId: uuid.UUID):
    """レコードと全リビジョンを取得する。"""
    return _run(lambda s: services.get_record(s, recordId))
