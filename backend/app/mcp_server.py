import json
import sqlite3
import uuid
from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import ValidationError
from sqlalchemy import text
from sqlmodel import Session

from app import services
from app.config import LOCALDATA_DIR, STORE_MODE
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
    """サービス層を呼び、エラーは構造化した JSON をメッセージとする ToolError にする。

    検証エラーの JSON には errors と、スキーマの再取得方法 (refetch) が含まれる。
    """
    try:
        with session_scope() as session:
            result = action(session)
    except (services.SchemaValidationError, services.ServiceError) as e:
        raise ToolError(json.dumps(e.payload(), ensure_ascii=False)) from None
    except ValidationError as e:
        payload = {"error": "invalid_input", "message": str(e)}
        raise ToolError(json.dumps(payload, ensure_ascii=False)) from None
    return json.loads(json.dumps(result, default=_encode))


def _encode(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    raise TypeError(type(value))


@mcp.tool
def db_version() -> str:
    """接続中のPostgreSQLのバージョンを返す。.env がないファイルストアでは、その旨を返す。"""
    if STORE_MODE == "file":
        return f"file store (SQLite {sqlite3.sqlite_version}, {LOCALDATA_DIR})"
    with engine.connect() as conn:
        return conn.execute(text("select version()")).scalar_one()


@mcp.tool
def list_json_schemas(schema_key: str | None = None, record_type: RecordType | None = None):
    """登録済みの JSON Schema (schema_json を除く) を一覧する。"""
    return _run(lambda s: services.list_schemas(s, schema_key, record_type))


@mcp.tool
def get_json_schema(
    schema_id: uuid.UUID | None = None,
    schema_key: str | None = None,
    schema_version: int | None = None,
):
    """JSON Schema を取得する。schema_id か schema_key のどちらかを指定する。

    schema_key だけを指定すると最新版を返す。content_json の検証エラーが出たときは、
    このツールでスキーマを再取得し、errors の path の箇所を修正して再送する。
    """
    return _run(
        lambda s: services.get_schema(
            s, SchemaRef(schema_id=schema_id, schema_key=schema_key, schema_version=schema_version)
        )
    )


@mcp.tool
def register_json_schema(
    schema_key: str,
    schema_version: int,
    record_type: RecordType,
    schema_json: dict[str, Any],
    feature_domain: FeatureDomain | None = None,
):
    """新しい JSON Schema (版) を登録する。登録済みのスキーマは更新できないため、
    変更するときは同じ schema_key で schema_version を増やして登録する。
    """
    return _run(
        lambda s: services.register_schema(
            s,
            JsonSchemaIn(
                schema_key=schema_key,
                schema_version=schema_version,
                record_type=record_type,
                feature_domain=feature_domain,
                schema_body=schema_json,
            ),
        )
    )


@mcp.tool
def create_record(
    record_type: RecordType,
    logical_key: str,
    content_json: dict[str, Any],
    schema_id: uuid.UUID | None = None,
    schema_key: str | None = None,
    schema_version: int | None = None,
    feature_domain: FeatureDomain | None = None,
    origin_platform_id: uuid.UUID | None = None,
    origin_product_id: uuid.UUID | None = None,
    change_reason: str | None = None,
):
    """レコードと最初のリビジョンを作成する。

    content_json は指定したスキーマ (schema_id、または schema_key の最新版) で検証され、
    適合しない場合は何も保存されずエラーの詳細が返る。
    """
    return _run(
        lambda s: services.create_record(
            s,
            RecordIn(
                record_type=record_type,
                logical_key=logical_key,
                content_json=content_json,
                schema_id=schema_id,
                schema_key=schema_key,
                schema_version=schema_version,
                feature_domain=feature_domain,
                origin_platform_id=origin_platform_id,
                origin_product_id=origin_product_id,
                change_reason=change_reason,
            ),
        )
    )


@mcp.tool
def add_revision(
    record_id: uuid.UUID,
    content_json: dict[str, Any],
    schema_id: uuid.UUID | None = None,
    schema_key: str | None = None,
    schema_version: int | None = None,
    change_reason: str | None = None,
):
    """既存レコードに新しいリビジョンを追加する。検証の扱いは create_record と同じ。"""
    return _run(
        lambda s: services.add_revision(
            s,
            record_id,
            RevisionIn(
                content_json=content_json,
                schema_id=schema_id,
                schema_key=schema_key,
                schema_version=schema_version,
                change_reason=change_reason,
            ),
        )
    )


@mcp.tool
def get_record(record_id: uuid.UUID):
    """レコードと全リビジョンを取得する。"""
    return _run(lambda s: services.get_record(s, record_id))
