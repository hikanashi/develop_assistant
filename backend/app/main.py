from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from .database import Database, create_database
from .mcp_server import configure_mcp
from .models import SEED_INSERT_ORDER, TABLE_MODELS
from .services import (
    SchemaValidationError,
    fetch_records,
    model_from_record,
    schema_rows,
    serialize_record,
    validate_record,
    validate_record_columns,
)
from .store import initialize_local_store, session_with_store


def create_app(database: Database | None = None) -> FastAPI:
    active_database = database or create_database()
    mcp_server = configure_mcp(active_database)
    mcp_server.settings.streamable_http_path = "/"
    mcp_http_app = mcp_server.streamable_http_app()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        initialize_local_store(active_database)
        async with mcp_http_app.router.lifespan_context(mcp_http_app):
            yield
        active_database.engine.dispose()

    app = FastAPI(title="Develop Assistant API", version="0.1.0", lifespan=lifespan)
    app.state.database = active_database

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "storage": "postgresql" if active_database.uses_postgres else "file",
        }

    @app.get("/api/tables")
    def list_tables() -> dict[str, list[str]]:
        return {"tables": list(SEED_INSERT_ORDER)}

    @app.get("/api/schemas")
    def get_schemas() -> list[dict[str, Any]]:
        with session_with_store(active_database) as session:
            return jsonable_encoder(schema_rows(session))

    @app.get("/api/{table_name}")
    def get_records(table_name: str) -> dict[str, Any]:
        normalized = table_name.upper()
        if normalized not in TABLE_MODELS:
            raise HTTPException(status_code=404, detail="Unknown table")
        with session_with_store(active_database) as session:
            return jsonable_encoder(
                {"table": normalized, "records": fetch_records(session, normalized)}
            )

    @app.post("/api/{table_name}", status_code=status.HTTP_201_CREATED)
    def create_record(table_name: str, record: dict[str, Any], request: Request):
        normalized = table_name.upper()
        model = TABLE_MODELS.get(normalized)
        if model is None:
            raise HTTPException(status_code=404, detail="Unknown table")
        session: Session = session_with_store(request.app.state.database)
        try:
            validate_record_columns(model, normalized, record)
            validate_record(session, normalized, record)
            instance = model_from_record(model, record)
            session.add(instance)
            session.commit()
            return jsonable_encoder(
                {"table": normalized, "record": serialize_record(model, instance)}
            )
        except SchemaValidationError as exc:
            session.rollback()
            return JSONResponse(status_code=422, content=exc.payload)
        except (TypeError, ValueError) as exc:
            session.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(
                status_code=409,
                detail="A uniqueness, check, or foreign-key constraint was violated.",
            ) from exc
        finally:
            session.close()

    app.mount("/mcp", mcp_http_app)
    return app


app = create_app()
