from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlmodel import Session

from app.config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    """FastAPI の依存関係。リクエスト単位のセッションを返し、例外時はロールバックする。"""
    with Session(engine) as session:
        yield session


# MCPツールなど、FastAPI 外から同じセッションを使うための入口
session_scope = contextmanager(get_session)
