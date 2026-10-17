from sqlmodel import SQLModel

import app.models  # noqa: F401
from alembic import context
from app.config import STORE_MODE

if STORE_MODE == "file":
    raise SystemExit(
        "DB の接続情報 (.env) が未設定のため、ファイルストア (backend/localdata) で動作します。"
        "マイグレーションは PostgreSQL 用です。.env を作成してから実行してください"
    )

from app.db import engine

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=engine.url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
