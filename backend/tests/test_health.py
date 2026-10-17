import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app


def test_health():
    with TestClient(app) as client:
        try:
            res = client.get("/health")
        except OperationalError:
            pytest.skip("PostgreSQL に接続できません")
        assert res.json() == {"status": "ok"}
