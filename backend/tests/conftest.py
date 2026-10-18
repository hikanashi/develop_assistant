from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlmodel import Session

from app import mcp_server
from app.db import engine, get_session
from app.main import app


@pytest.fixture
def db_session():
    """外側のトランザクションに参加するセッション。commit してもテスト終了時に全て破棄される。

    content_revision / json_schema は更新・削除できないため、実際にコミットしてはならない。
    """
    try:
        connection = engine.connect()
    except OperationalError:
        pytest.skip("PostgreSQL に接続できません")
    outer = connection.begin()
    if not connection.execute(text("select to_regclass('content_revision')")).scalar():
        outer.rollback()
        connection.close()
        pytest.skip("マイグレーション未適用")
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    outer.rollback()
    connection.close()


@pytest.fixture
def client(db_session, monkeypatch):
    @contextmanager
    def scope():
        yield db_session

    app.dependency_overrides[get_session] = lambda: db_session
    monkeypatch.setattr(mcp_server, "session_scope", scope)
    yield TestClient(app)
    app.dependency_overrides.clear()
