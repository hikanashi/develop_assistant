from fastmcp import FastMCP
from sqlalchemy import text

from app.db import engine

mcp = FastMCP("develop-assistant")


@mcp.tool
def db_version() -> str:
    """接続中のPostgreSQLのバージョンを返す。"""
    with engine.connect() as conn:
        return conn.execute(text("select version()")).scalar_one()
