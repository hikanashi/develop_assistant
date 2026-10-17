from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlmodel import Session

from app.config import DATABASE_URL, DEFAULT_SEED_DIR, LOCALDATA_DIR, STORE_MODE

if STORE_MODE == "file":
    from app import localstore

    # .env がない場合は PostgreSQL に接続せず、backend/localdata の JSON ファイルに保存する
    engine = localstore.open_store(LOCALDATA_DIR, DEFAULT_SEED_DIR)
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    """FastAPI の依存関係。リクエスト単位のセッションを返し、例外時はロールバックする。"""
    if STORE_MODE == "file":
        with localstore.LOCK, Session(engine) as session:
            yield session
        return
    with Session(engine) as session:
        yield session


# MCPツールなど、FastAPI 外から同じセッションを使うための入口
session_scope = contextmanager(get_session)
