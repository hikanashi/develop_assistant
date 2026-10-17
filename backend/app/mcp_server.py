from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent
from sqlalchemy.exc import IntegrityError

from .models import TABLE_MODELS
from .services import (
    SchemaValidationError,
    fetch_records,
    json_for_response,
    model_from_record,
    schema_rows,
    serialize_record,
    validate_record,
    validate_record_columns,
)
from .store import session_with_store


def configure_mcp(database) -> FastMCP:
    server = FastMCP("develop_assistant")

    def tool_result(payload: dict[str, Any], is_error: bool) -> CallToolResult:
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(payload, ensure_ascii=False),
                )
            ],
            structuredContent=payload,
            isError=is_error,
        )

    @server.tool()
    def list_records(table_name: str) -> list[dict[str, Any]]:
        """List records from one of the database tables."""
        normalized = table_name.upper()
        if normalized not in TABLE_MODELS:
            raise ValueError(f"Unknown table: {table_name}")
        with session_with_store(database) as session:
            return json_for_response(fetch_records(session, normalized))

    @server.tool()
    def create_record(table_name: str, record: dict[str, Any]) -> Any:
        """Validate and insert a record into one of the database tables."""
        normalized = table_name.upper()
        model = TABLE_MODELS.get(normalized)
        if model is None:
            raise ValueError(f"Unknown table: {table_name}")
        session = session_with_store(database)
        try:
            try:
                validate_record_columns(model, normalized, record)
                validate_record(session, normalized, record)
                instance = model_from_record(model, record)
                session.add(instance)
                session.commit()
            except SchemaValidationError as exc:
                session.rollback()
                return tool_result(exc.payload, True)
            except IntegrityError:
                session.rollback()
                return tool_result(
                    {
                        "error": "database_integrity_violation",
                        "detail": "A uniqueness, check, or foreign-key constraint was violated.",
                    },
                    True,
                )
            except (TypeError, ValueError) as exc:
                session.rollback()
                return tool_result({"error": "invalid_record", "detail": str(exc)}, True)
        finally:
            session.close()
        return tool_result(
            json_for_response(
                {
                    "table": normalized,
                    "record": serialize_record(model, instance),
                }
            ),
            False,
        )

    @server.tool()
    def get_json_schemas() -> list[dict[str, Any]]:
        """Retrieve the registered JSON Schemas and their identifiers."""
        with session_with_store(database) as session:
            return json_for_response(schema_rows(session))

    return server
