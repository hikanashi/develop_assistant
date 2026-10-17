from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db import engine
from app.mcp_server import mcp
from app.routers import json_schemas, records
from app.services import SchemaValidationError, ServiceError

# MCP は /mcp で提供する (Dify / Claude Code など向け Streamable HTTP)
mcp_app = mcp.http_app(path="/")

app = FastAPI(title="develop_assistant backend", lifespan=mcp_app.lifespan)
app.mount("/mcp", mcp_app)
app.include_router(json_schemas.router)
app.include_router(records.router)


@app.exception_handler(SchemaValidationError)
def schema_validation_error_handler(_: Request, exc: SchemaValidationError) -> JSONResponse:
    """JSON Schema の検証エラーは、詳細を含めて 422 で応答する。"""
    return JSONResponse(status_code=422, content=exc.payload())


@app.exception_handler(ServiceError)
def service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.payload())


@app.get("/health")
def health() -> dict[str, str]:
    with engine.connect() as conn:
        conn.execute(text("select 1"))
    return {"status": "ok"}
