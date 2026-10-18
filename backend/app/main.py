from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import OPENAPI_FILE
from app.db import engine
from app.mcp_server import mcp
from app.routers import json_schemas, records
from app.services import ServiceError, invalid_request

# MCP は /mcp で提供する (Dify / Claude Code など向け Streamable HTTP)
mcp_app = mcp.http_app(path="/")

app = FastAPI(title="develop_assistant backend", lifespan=mcp_app.lifespan, docs_url=None)
app.mount("/mcp", mcp_app)
app.include_router(json_schemas.router)
app.include_router(records.router)

_HTTP_ERROR_CODES = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}


@app.exception_handler(ServiceError)
def service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
    """業務エラーと JSON Schema の検証エラー (422) を、ガイドラインのエラー形式で応答する。"""
    return JSONResponse(status_code=exc.status_code, content=exc.payload())


@app.exception_handler(RequestValidationError)
def request_validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    error = invalid_request(exc.errors())
    return JSONResponse(status_code=error.status_code, content=error.payload())


@app.exception_handler(StarletteHTTPException)
def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _HTTP_ERROR_CODES.get(exc.status_code, "HTTP_ERROR")
    body = {"code": code, "message": str(exc.detail), "details": None}
    return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)


@app.exception_handler(Exception)
def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    body = {
        "code": "INTERNAL_ERROR",
        "message": "サーバー内部エラーが発生しました",
        "details": None,
    }
    return JSONResponse(status_code=500, content=body)


# OPENAPI_FILE (REST API の仕様) を配信し、Swagger UI (/docs) で表示する。仕様内の外部参照
# ($ref: /v1/schemas/...) は、この仕様を配信しているホストを基準に解決される (ENV-047)。
@app.get("/openapi.yaml", include_in_schema=False)
def openapi_spec() -> FileResponse:
    return FileResponse(OPENAPI_FILE, media_type="application/yaml")


@app.get("/docs", include_in_schema=False)
def swagger_ui() -> HTMLResponse:
    return get_swagger_ui_html(openapi_url="/openapi.yaml", title="develop_assistant backend API")


# 運用用のヘルスチェック。OpenAPI 仕様 (REST API) の対象外で、認証も要求しない。
@app.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    with engine.connect() as conn:
        conn.execute(text("select 1"))
    return {"status": "ok"}
