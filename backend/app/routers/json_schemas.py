import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app import services
from app.db import get_session
from app.schemas import JsonSchemaIn, JsonSchemaOut, JsonSchemaSummary, RecordType, SchemaRef

# operation_id は OPENAPI_FILE の operationId、MCP のツール名と一致させる (ENV-046)
router = APIRouter(prefix="/v1/schemas", tags=["json-schema"])

SessionDep = Annotated[Session, Depends(get_session)]
VersionQuery = Annotated[int | None, Query(ge=1)]


@router.get("", response_model=list[JsonSchemaSummary], operation_id="listSchemas")
def list_schemas(
    session: SessionDep,
    schema_key: Annotated[str | None, Query(alias="schemaKey")] = None,
    record_type: Annotated[RecordType | None, Query(alias="recordType")] = None,
):
    return services.list_schemas(session, schema_key, record_type)


@router.get("/by-key/{schemaKey}", response_model=JsonSchemaOut, operation_id="getSchemaByKey")
def get_schema_by_key(session: SessionDep, schemaKey: str, version: VersionQuery = None):
    """schemaKey のスキーマを取得する。version を省略すると最新版。"""
    return services.get_schema(session, SchemaRef(schema_key=schemaKey, schema_version=version))


@router.get(
    "/by-key/{schemaKey}/schema-json",
    response_model=dict[str, Any],
    operation_id="getSchemaJsonByKey",
)
def get_schema_json_by_key(session: SessionDep, schemaKey: str, version: VersionQuery = None):
    """schemaKey のスキーマ本体 (schemaJson) だけを返す。OpenAPI の外部参照 (URL) に使う。"""
    return services.get_schema_json(
        session, SchemaRef(schema_key=schemaKey, schema_version=version)
    )


@router.get("/{schemaId}", response_model=JsonSchemaOut, operation_id="getSchema")
def get_schema(session: SessionDep, schemaId: uuid.UUID):
    return services.get_schema(session, SchemaRef(schema_id=schemaId))


@router.get("/{schemaId}/schema-json", response_model=dict[str, Any], operation_id="getSchemaJson")
def get_schema_json(session: SessionDep, schemaId: uuid.UUID):
    """schemaId のスキーマ本体 (schemaJson) だけを返す。OpenAPI の外部参照 (URL) に使う。"""
    return services.get_schema_json(session, SchemaRef(schema_id=schemaId))


@router.post(
    "",
    response_model=JsonSchemaOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="createSchema",
)
def create_schema(session: SessionDep, body: JsonSchemaIn):
    """新しいスキーマ (版) を登録する。登録済みのスキーマは更新できない。"""
    return services.register_schema(session, body)
