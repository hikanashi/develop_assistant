from __future__ import annotations

import json
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, SchemaError
from sqlalchemy import select
from sqlmodel import Session

from .models import TABLE_MODELS, JsonSchema


class SchemaValidationError(Exception):
    def __init__(self, payload: dict[str, Any]):
        super().__init__(payload["error"])
        self.payload = payload


def _pointer(parts) -> str:
    if not parts:
        return ""
    return "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def _schema_errors(schema: dict[str, Any], value: Any) -> list[dict[str, str]]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        {
            "path": _pointer(error.absolute_path),
            "schema_path": _pointer(error.absolute_schema_path),
            "validator": str(error.validator),
            "message": error.message,
        }
        for error in sorted(
            validator.iter_errors(value),
            key=lambda error: (list(map(str, error.absolute_path)), error.message),
        )
    ]


def validate_schema_row(payload: dict[str, Any]) -> None:
    schema = payload.get("schema_json")
    schema_info = {
        "schema_id": payload.get("schema_id"),
        "schema_key": payload.get("schema_key"),
        "schema_version": payload.get("schema_version"),
    }
    if not isinstance(schema, dict):
        errors = [
            {
                "path": "/schema_json",
                "schema_path": "",
                "validator": "type",
                "message": "schema_json must be a JSON object",
            }
        ]
    else:
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            errors = [
                {
                    "path": "/schema_json",
                    "schema_path": "",
                    "validator": "schema",
                    "message": str(exc),
                }
            ]
        else:
            expected_id = (
                f"urn:das:schema:{payload.get('schema_key')}:{payload.get('schema_version')}"
            )
            if schema.get("$id") == expected_id:
                return
            errors = [
                {
                    "path": "/$id",
                    "schema_path": "",
                    "validator": "const",
                    "message": f"$id must be {expected_id!r}",
                }
            ]
    raise SchemaValidationError(
        {
            "error": "json_schema_definition_invalid",
            "schema": schema_info,
            "errors": errors,
            "hint": "修正してから再送してください",
        }
    )


def validate_content_revision(session: Session, payload: dict[str, Any]) -> None:
    schema_id = payload.get("schema_id")
    schema_row = session.get(JsonSchema, schema_id) if schema_id else None
    if schema_row is None:
        raise SchemaValidationError(
            {
                "error": "json_schema_not_found",
                "schema": {
                    "schema_id": schema_id,
                    "schema_key": None,
                    "schema_version": None,
                },
                "errors": [],
                "hint": "有効なスキーマ ID を指定するか、スキーマ一覧 API から取得してください",
            }
        )
    content = payload.get("content_json")
    errors = _schema_errors(schema_row.schema_json_value, content)
    if errors:
        raise SchemaValidationError(
            {
                "error": "json_schema_validation_failed",
                "schema": {
                    "schema_id": schema_row.schema_id,
                    "schema_key": schema_row.schema_key,
                    "schema_version": schema_row.schema_version,
                },
                "errors": errors,
                "hint": "スキーマを再取得し、errors の path を修正して再送してください",
            }
        )


def validate_record(session: Session, table_name: str, payload: dict[str, Any]) -> None:
    if table_name == "JSON_SCHEMA":
        validate_schema_row(payload)
    elif table_name == "CONTENT_REVISION":
        validate_content_revision(session, payload)


def validate_record_columns(model: type, table_name: str, payload: dict[str, Any]) -> None:
    columns = {column.name for column in model.__table__.columns}
    unknown = sorted(set(payload) - columns)
    if unknown:
        raise ValueError(f"Unknown column(s) for {table_name}: {', '.join(unknown)}")
    missing = sorted(
        column.name
        for column in model.__table__.columns
        if not column.nullable
        and column.default is None
        and column.server_default is None
        and column.name not in payload
    )
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}")


def model_from_record(model: type, payload: dict[str, Any]):
    attributes = {
        column.name: attribute.key
        for attribute in model.__mapper__.column_attrs
        for column in attribute.columns
    }
    return model(**{attributes.get(key, key): value for key, value in payload.items()})


def serialize_record(model: type, record: Any) -> dict[str, Any]:
    return {
        column.name: getattr(record, attribute.key)
        for attribute in model.__mapper__.column_attrs
        for column in attribute.columns
    }


def fetch_records(session: Session, table_name: str) -> list[dict[str, Any]]:
    model = TABLE_MODELS[table_name]
    return [serialize_record(model, row) for row in session.scalars(select(model)).all()]


def schema_rows(session: Session) -> list[dict[str, Any]]:
    return fetch_records(session, "JSON_SCHEMA")


def json_for_response(data: Any) -> Any:
    return json.loads(json.dumps(data, default=str, ensure_ascii=False))
