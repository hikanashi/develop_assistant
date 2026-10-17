"""設計ファイル (design/database/schemas/) から初期投入データ (backend/seed/) を生成する。

DBには接続しない。出力は同じ入力から常に同じ内容になる (ID は UUIDv5 で決定的に生成)。
"""

import json
import re
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from app.json_validation import check_schema_document, validate_instance

BACKEND_DIR = Path(__file__).resolve().parents[1]
# コンテナには backend/ しかマウントされず、design/ は存在しない (ホストでの build-seed 専用)
DEFAULT_DESIGN_DIR = BACKEND_DIR.parent / "design" / "database" / "schemas"
DEFAULT_SEED_DIR = BACKEND_DIR / "seed"

SCHEMA_FILE = "sys.artifact.schema.json"
EXAMPLES_DIR = "examples"
SCHEMA_SEED_FILE = "10_json_schema.json"
EXAMPLES_SEED_FILE = "20_artifact_examples.json"

# json-schema-design.md「方針」: 単一スキーマは ARTIFACT 用で feature_domain は NULL
RECORD_TYPE = "ARTIFACT"
CHANGE_REASON = "examples からの初期投入"

_SCHEMA_ID_PATTERN = re.compile(r"^urn:das:schema:(?P<key>.+):(?P<version>[1-9][0-9]*)$")


class SeedBuildError(Exception):
    pass


def schema_id_for(schema_uri: str) -> UUID:
    return uuid5(NAMESPACE_URL, schema_uri)


def record_id_for(logical_key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"urn:das:seed:record:{logical_key}")


def revision_id_for(logical_key: str, revision_no: int) -> UUID:
    return uuid5(NAMESPACE_URL, f"urn:das:seed:revision:{logical_key}:{revision_no}")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SeedBuildError(f"{path} がありません") from None
    except json.JSONDecodeError as e:
        raise SeedBuildError(f"{path} がJSONとして不正です: {e}") from e


def load_schema(design_dir: Path) -> dict[str, Any]:
    """スキーマ文書を読み込み、メタスキーマで検証する。"""
    schema = _read_json(design_dir / SCHEMA_FILE)
    errors = check_schema_document(schema)
    if errors:
        raise SeedBuildError(
            f"{SCHEMA_FILE} がJSON Schemaとして不正です: "
            + "; ".join(f"{e['path']} {e['message']}" for e in errors)
        )
    return schema


def _parse_schema_id(schema: dict[str, Any]) -> tuple[str, int]:
    uri = schema.get("$id")
    match = _SCHEMA_ID_PATTERN.match(uri) if isinstance(uri, str) else None
    if not match:
        raise SeedBuildError(
            f"$id は urn:das:schema:<schema_key>:<schema_version> の形式で指定してください: {uri!r}"
        )
    return match["key"], int(match["version"])


def build_json_schema_seed(schema: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    """JSON_SCHEMA の行を作る。既存ファイルにある別の版は残す (登録済みスキーマは不変)。"""
    key, version = _parse_schema_id(schema)
    rows = {
        (row["schema_key"], row["schema_version"]): row for row in existing.get("json_schema", [])
    }
    current = rows.get((key, version))
    if current is not None and current["schema_json"] != schema:
        raise SeedBuildError(
            f"{key} の版 {version} は登録済みで内容が異なります。"
            f"登録済みスキーマは変更できないため、$id の版を上げてください"
        )
    rows[(key, version)] = {
        "schema_id": str(schema_id_for(schema["$id"])),
        "schema_key": key,
        "schema_version": version,
        "record_type": RECORD_TYPE,
        "feature_domain": None,
        "schema_json": schema,
    }
    return {"json_schema": [rows[k] for k in sorted(rows)]}


def build_examples_seed(schema: dict[str, Any], examples_dir: Path) -> dict[str, Any]:
    """examples の valid を CONTENT_RECORD / CONTENT_REVISION の行に変換する。"""
    schema_id = str(schema_id_for(schema["$id"]))
    records: list[dict[str, Any]] = []
    revisions: list[dict[str, Any]] = []
    problems: list[str] = []
    for path in sorted(examples_dir.glob("*.json")):
        for index, instance in enumerate(_read_json(path).get("valid", []), start=1):
            errors = validate_instance(schema, instance)
            if errors:
                first = errors[0]
                problems.append(
                    f"{path.name} valid[{index - 1}]: {first['path']} {first['message']}"
                )
                continue
            logical_key = f"{path.stem}.{index:03d}"
            record_id = str(record_id_for(logical_key))
            records.append(
                {
                    "record_id": record_id,
                    "origin_platform_id": None,
                    "origin_product_id": None,
                    "record_type": RECORD_TYPE,
                    "feature_domain": None,
                    "logical_key": logical_key,
                }
            )
            revisions.append(
                {
                    "revision_id": str(revision_id_for(logical_key, 1)),
                    "record_id": record_id,
                    "schema_id": schema_id,
                    "revision_no": 1,
                    "content_json": instance,
                    "change_reason": CHANGE_REASON,
                }
            )
    if problems:
        raise SeedBuildError("スキーマに適合しない正常例があります:\n" + "\n".join(problems))
    if not records:
        raise SeedBuildError(f"{examples_dir} に正常例がありません")
    return {"content_record": records, "content_revision": revisions}


def _dump(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def build_seed(design_dir: Path, seed_dir: Path, *, check: bool = False) -> list[Path]:
    """生成ファイルを書き込む。check=True のときは書き込まず、内容が異なるファイルを返す。
    書き込んだ (または異なる) ファイルのパスを返す。"""
    schema = load_schema(design_dir)

    schema_path = seed_dir / SCHEMA_SEED_FILE
    existing = _read_json(schema_path) if schema_path.exists() else {}
    outputs = {
        schema_path: _dump(build_json_schema_seed(schema, existing)),
        seed_dir / EXAMPLES_SEED_FILE: _dump(
            build_examples_seed(schema, design_dir / EXAMPLES_DIR)
        ),
    }

    changed = [
        path
        for path, text in outputs.items()
        if not path.exists() or path.read_text(encoding="utf-8") != text
    ]
    if not check:
        seed_dir.mkdir(parents=True, exist_ok=True)
        for path in changed:
            path.write_text(outputs[path], encoding="utf-8")
    return changed
