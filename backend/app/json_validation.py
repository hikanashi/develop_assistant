"""JSON Schema (draft 2020-12) による値の検証。DBには依存しない。

エラーは、呼び出し元 (AI / 人間) が自己修正できるよう、違反箇所の JSON Pointer・
違反した制約・メッセージを持つ辞書として返す。
"""

from collections.abc import Iterable
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

META_SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"
_MAX_MESSAGE_LENGTH = 500
_MAX_CAUSE_DEPTH = 3


def _pointer(parts: Iterable[Any]) -> str:
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def _sort_key(error: ValidationError) -> tuple[list[str], list[str]]:
    return [str(p) for p in error.absolute_path], [str(p) for p in error.absolute_schema_path]


def _describe(error: ValidationError, depth: int = 0) -> dict[str, Any]:
    item: dict[str, Any] = {
        "path": _pointer(error.absolute_path),
        "schemaPath": _pointer(error.absolute_schema_path),
        "validator": error.validator,
        "message": error.message[:_MAX_MESSAGE_LENGTH],
    }
    # anyOf / oneOf は、どの分岐でどう違反したかが修正の手がかりになる
    if error.context and depth < _MAX_CAUSE_DEPTH:
        item["causes"] = [_describe(c, depth + 1) for c in sorted(error.context, key=_sort_key)]
    return item


def _collect(validator: Draft202012Validator, instance: Any) -> list[dict[str, Any]]:
    return [_describe(e) for e in sorted(validator.iter_errors(instance), key=_sort_key)]


def validate_instance(schema: dict[str, Any], instance: Any) -> list[dict[str, Any]]:
    """instance が schema に適合しなければ、違反を全て返す。適合すれば空リスト。"""
    return _collect(Draft202012Validator(schema, format_checker=FormatChecker()), instance)


def custom_error(path: str, validator: str, message: str) -> dict[str, Any]:
    """jsonschema 以外の検証で、同じ形式のエラーを作る。"""
    return {"path": path, "schemaPath": "", "validator": validator, "message": message}


def check_schema_document(schema: Any) -> list[dict[str, Any]]:
    """schema 自体が draft 2020-12 のスキーマとして正しいかを検証する。"""
    meta = Draft202012Validator(Draft202012Validator.META_SCHEMA, format_checker=FormatChecker())
    errors = _collect(meta, schema)
    if errors:
        return errors
    if not isinstance(schema, dict):
        return [custom_error("", "type", "スキーマは JSON オブジェクトで指定してください")]
    if schema.get("$schema", META_SCHEMA_URI) != META_SCHEMA_URI:
        return [
            custom_error(
                "/$schema", "const", f"$schema は {META_SCHEMA_URI} (draft 2020-12) にしてください"
            )
        ]
    return []
