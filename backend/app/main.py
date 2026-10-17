from fastapi import FastAPI
from sqlalchemy import text

from app.db import engine
from app.mcp_server import mcp

# MCP は /mcp で提供する (Dify / Claude Code など向け Streamable HTTP)
mcp_app = mcp.http_app(path="/")

app = FastAPI(title="develop_assistant backend", lifespan=mcp_app.lifespan)
app.mount("/mcp", mcp_app)


@app.get("/health")
def health() -> dict[str, str]:
    with engine.connect() as conn:
        conn.execute(text("select 1"))
    return {"status": "ok"}
