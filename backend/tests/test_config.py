import pytest
from sqlalchemy.engine import URL

from app.config import _database_url


def test_database_url_requires_connection_settings(monkeypatch):
    for name in ("DATABASE_URL", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match="POSTGRES_USER"):
        _database_url()


def test_database_url_uses_postgres_environment(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_USER", "user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss/word")
    monkeypatch.setenv("POSTGRES_DB", "database")

    url = _database_url()

    assert isinstance(url, URL)
    assert url.username == "user"
    assert url.password == "p@ss/word"
    assert url.host == "localhost"
    assert url.database == "database"
