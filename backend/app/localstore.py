"""ファイルストア: .env がなく DB の接続情報が未設定のときの保存先。

PostgreSQL の代わりにメモリ上の SQLite を使い、コミットのたびに全テーブルを
localdata/<テーブル名>.json (行の配列。DB のレコードと同じ列・値) へ書き出す。
起動時に localdata/*.json があればそれを読み込み、なければ seed/*.json を投入する。
サービス層・REST・MCP は PostgreSQL のときと同じコードで動く。
外部キー・CHECK 制約・一意制約は適用されるが、PostgreSQL のトリガー (不変性の保護) は適用されない。
"""

import json
import threading
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

import app.models  # noqa: F401  (SQLModel.metadata にテーブルを登録する)
from app.seed_io import _json_default, insert_rows, load_seed, read_tables

# メモリ上の SQLite は接続が 1 本のため、セッションを同時に使わないよう直列化する。
# FastAPI はセッションの開始と終了を別のスレッドで行うことがあるため、RLock ではなく Lock を使う
LOCK = threading.Lock()


def create_file_engine() -> Engine:
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.create_function("gen_random_uuid", 0, lambda: str(uuid.uuid4()))
        dbapi_connection.execute("PRAGMA foreign_keys = ON")

    return engine


def read_localdata(localdata_dir: Path) -> dict[str, list[dict[str, Any]]]:
    return {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(localdata_dir.glob("*.json"))
    }


def persist(engine: Engine, localdata_dir: Path) -> None:
    """全テーブルを localdata/<テーブル名>.json へ書き出す (内容が変わったファイルだけ置き換える)。"""
    localdata_dir.mkdir(parents=True, exist_ok=True)
    for table_name, rows in read_tables(engine).items():
        text = json.dumps(rows, ensure_ascii=False, indent=2, default=_json_default) + "\n"
        path = localdata_dir / f"{table_name}.json"
        if path.exists() and path.read_text(encoding="utf-8") == text:
            continue
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)


def open_store(localdata_dir: Path, seed_dir: Path) -> Engine:
    """ファイルストアを開く。localdata に JSON がなければ (初回起動) seed を投入して書き出す。"""
    engine = create_file_engine()
    SQLModel.metadata.create_all(engine)
    data = read_localdata(localdata_dir) if localdata_dir.is_dir() else {}
    if data:
        insert_rows(engine, data)
    else:
        load_seed(engine, seed_dir)
        persist(engine, localdata_dir)

    @event.listens_for(Session, "after_commit")
    def _persist_on_commit(session: Session) -> None:
        if session.get_bind().engine is engine:
            persist(engine, localdata_dir)

    return engine
