import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app import services
from app.db import get_session
from app.schemas import JsonSchemaIn, JsonSchemaOut, JsonSchemaSummary, RecordType, SchemaRef

router = APIRouter(prefix="/schemas", tags=["json-schema"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[JsonSchemaSummary])
def list_json_schemas(
    session: SessionDep, schema_key: str | None = None, record_type: RecordType | None = None
):
    return services.list_schemas(session, schema_key, record_type)


@router.get("/by-key/{schema_key}", response_model=JsonSchemaOut)
def get_json_schema_by_key(
    session: SessionDep, schema_key: str, version: Annotated[int | None, Query(ge=1)] = None
):
    """schema_key のスキーマを取得する。version を省略すると最新版。"""
    return services.get_schema(session, SchemaRef(schema_key=schema_key, schema_version=version))


@router.get("/{schema_id}", response_model=JsonSchemaOut)
def get_json_schema(session: SessionDep, schema_id: uuid.UUID):
    return services.get_schema(session, SchemaRef(schema_id=schema_id))


@router.post("", response_model=JsonSchemaOut, status_code=status.HTTP_201_CREATED)
def register_json_schema(session: SessionDep, body: JsonSchemaIn):
    """新しいスキーマ (版) を登録する。登録済みのスキーマは更新できない。"""
    return services.register_schema(session, body)
