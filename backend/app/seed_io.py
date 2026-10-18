"""JSON形式のシードデータの投入とエクスポート。

ファイル形式: {"テーブル名": [{"列名": 値, ...}, ...], ...}
列の型はDBから取得し、UUID / 日時 / 数値は文字列から変換する。
"""

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, MetaData, Table, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert


def _reflect(engine: Engine) -> MetaData:
    metadata = MetaData()
    metadata.reflect(bind=engine)
    if "alembic_version" in metadata.tables:
        metadata.remove(metadata.tables["alembic_version"])
    return metadata


def _coerce(table: Table, row: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in row.items():
        if key not in table.c:
            raise ValueError(f"{table.name} に列 {key} がありません")
        if isinstance(value, str):
            try:
                column_type = table.c[key].type
                # TypeDecorator (UTCDateTime) は内側の型から Python の型を得る
                py_type = getattr(column_type, "impl_instance", column_type).python_type
            except NotImplementedError:
                py_type = None
            if py_type is UUID:
                value = UUID(value)
            elif py_type is datetime:
                value = datetime.fromisoformat(value)
            elif py_type is date:
                value = date.fromisoformat(value)
            elif py_type is Decimal:
                value = Decimal(value)
        result[key] = value
    return result


def load_seed(engine: Engine, seed_dir: Path) -> int:
    """seed_dir 内の *.json をファイル名順に読み込み、外部キー順に投入する。
    主キー重複の行はスキップするため繰り返し実行できる。"""
    files = sorted(seed_dir.glob("*.json"))
    data: dict[str, list[dict[str, Any]]] = {}
    for path in files:
        for table_name, rows in json.loads(path.read_text(encoding="utf-8")).items():
            data.setdefault(table_name, []).extend(rows)
    return insert_rows(engine, data)


def insert_rows(engine: Engine, data: dict[str, list[dict[str, Any]]]) -> int:
    """{"テーブル名": [行...]} を外部キー順に投入する。主キー重複の行はスキップする。"""
    if not data:
        return 0
    metadata = _reflect(engine)
    unknown = set(data) - set(metadata.tables)
    if unknown:
        raise ValueError(f"存在しないテーブル: {sorted(unknown)}")

    count = 0
    with engine.begin() as conn:
        for table in metadata.sorted_tables:
            rows = data.get(table.name)
            if not rows:
                continue
            stmt = postgres_insert(table).on_conflict_do_nothing()
            # 列の組が異なる行 (デフォルト値を使う行と明示する行) は、組ごとに分けて挿入する
            groups: dict[frozenset[str], list[dict[str, Any]]] = {}
            for row in rows:
                groups.setdefault(frozenset(row), []).append(_coerce(table, row))
            for group in groups.values():
                conn.execute(stmt, group)
            count += len(rows)
    return count


def _json_default(value: Any) -> Any:
    if isinstance(value, (UUID, datetime, date, Decimal)):
        return value.isoformat() if isinstance(value, (datetime, date)) else str(value)
    raise TypeError(f"JSON化できない型: {type(value)}")


def read_tables(engine: Engine) -> dict[str, list[dict[str, Any]]]:
    """全テーブルの行を外部キー順に取得する。"""
    metadata = _reflect(engine)
    data: dict[str, list[dict[str, Any]]] = {}
    with engine.connect() as conn:
        for table in metadata.sorted_tables:
            rows = conn.execute(select(table)).mappings().all()
            data[table.name] = [dict(row) for row in rows]
    return data


def export_seed(engine: Engine, output: Path) -> int:
    """全テーブルを外部キー順にJSONへ出力する。出力はそのままシードとして使える。"""
    data = read_tables(engine)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )
    return sum(len(rows) for rows in data.values())
