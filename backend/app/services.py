"""DB ⇔ JSON の変換と更新処理 (REST / MCP 共通)。

jsonb 列 (content_json) の値は、DBへ書き込む前に JSON_SCHEMA.schema_json で検証する。
検証に失敗した場合は何も書き込まず、エラーの詳細を SchemaValidationError で返す。
"""

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic.alias_generators import to_camel
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.json_validation import (
    META_SCHEMA_URI,
    check_schema_document,
    custom_error,
    validate_instance,
)
from app.models import ContentRecord, ContentRevision, JsonSchema, RevisionParent
from app.schemas import (
    JsonSchemaIn,
    JsonSchemaOut,
    JsonSchemaSummary,
    RecordIn,
    RecordOut,
    RecordWithRevisions,
    RevisionIn,
    RevisionOut,
    SchemaRef,
)


class ServiceError(Exception):
    """業務エラー。REST は status_code の HTTP ステータス、MCP はツールエラーで payload() を返す。

    payload() は API ガイドラインのエラー形式 (code / message / details)。
    """

    def __init__(
        self, status_code: int, code: str, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details

    def payload(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class SchemaValidationError(ServiceError):
    """JSON Schema の検証エラー (422)。details に違反の詳細とスキーマの再取得方法を含める。"""

    def __init__(
        self,
        errors: list[dict[str, Any]],
        *,
        target: str,
        schema: JsonSchema | None = None,
        latest_version: int | None = None,
    ) -> None:
        details: dict[str, Any] = {"target": target}
        if schema is not None:
            schema_id = str(schema.schema_id)
            details["schema"] = {
                "schemaId": schema_id,
                "schemaKey": schema.schema_key,
                "schemaVersion": schema.schema_version,
                "latestSchemaVersion": latest_version,
            }
            details["refetch"] = {
                "rest": f"GET /v1/schemas/{schema_id}",
                "mcpTool": "getSchema",
                "arguments": {"schemaId": schema_id},
            }
            details["hint"] = (
                "スキーマを再取得し、errors の path (JSON Pointer) の箇所を修正して再送してください。"
                "latestSchemaVersion が schemaVersion より大きい場合は、最新版で検証してください。"
            )
        else:
            details["metaSchema"] = META_SCHEMA_URI
            details["hint"] = (
                "errors の path の箇所を修正して再送してください。"
                "schemaJson は JSON Schema draft 2020-12 で記述します。"
            )
        details["errors"] = errors
        super().__init__(
            422,
            "JSON_SCHEMA_VALIDATION_FAILED",
            f"{target} が JSON Schema に適合しません ({len(errors)} 件)",
            details,
        )
        self.errors = errors


_INPUT_SOURCES = {"body", "query", "path", "header"}


def invalid_request(
    errors: Sequence[Mapping[str, Any]],
    *,
    source: str | None = None,
    field_sources: Mapping[str, str] | None = None,
) -> ServiceError:
    """入力項目の指定エラー (必須項目の未指定・型の不一致など。400)。

    errors は Pydantic / FastAPI の検証エラー (loc / msg / type)。REST と MCP で共通に使う。
    """
    items = []
    for e in errors:
        loc = [str(p) for p in e.get("loc", ())]
        item_source = loc.pop(0) if loc and loc[0] in _INPUT_SOURCES else None
        loc = [to_camel(part) for part in loc]
        if loc:
            item_source = item_source or (field_sources or {}).get(loc[0])
        item_source = item_source or source
        error_type = e.get("type", "")
        message = e.get("msg", "")
        if error_type == "missing_argument":
            error_type = "missing"
            message = "Field required"
        item = {
            "path": "/" + "/".join(loc) if loc else "",
            "message": message,
            "type": error_type,
        }
        if item_source:
            item["in"] = item_source
        items.append(item)
    return ServiceError(
        400,
        "INVALID_REQUEST",
        f"入力項目の指定が正しくありません ({len(items)} 件)",
        {"errors": items},
    )


def _flush(session: Session) -> None:
    try:
        session.flush()
    except IntegrityError as e:
        session.rollback()
        detail = str(e.orig).splitlines()[0] if e.orig else str(e)
        raise ServiceError(409, "CONSTRAINT_VIOLATION", detail) from None


def _schema_out(row: JsonSchema) -> JsonSchemaOut:
    return JsonSchemaOut(
        schema_id=row.schema_id,
        schema_key=row.schema_key,
        schema_version=row.schema_version,
        record_type=row.record_type,  # type: ignore[arg-type]
        feature_domain=row.feature_domain,  # type: ignore[arg-type]
        created_at=row.created_at,
        schema_body=row.schema_body,
    )


def _latest_version(session: Session, schema_key: str) -> int | None:
    return session.exec(
        select(func.max(JsonSchema.schema_version)).where(JsonSchema.schema_key == schema_key)
    ).one()


def list_schemas(
    session: Session, schema_key: str | None = None, record_type: str | None = None
) -> list[JsonSchemaSummary]:
    stmt = select(JsonSchema).order_by(JsonSchema.schema_key, JsonSchema.schema_version)
    if schema_key:
        stmt = stmt.where(JsonSchema.schema_key == schema_key)
    if record_type:
        stmt = stmt.where(JsonSchema.record_type == record_type)
    return [JsonSchemaSummary.model_validate(r) for r in session.exec(stmt).all()]


def _find_schema(session: Session, ref: SchemaRef) -> JsonSchema:
    if ref.schema_id is not None:
        row = session.get(JsonSchema, ref.schema_id)
        if row is None:
            raise ServiceError(404, "SCHEMA_NOT_FOUND", f"schemaId {ref.schema_id} がありません")
        return row
    assert ref.schema_key is not None
    version = ref.schema_version or _latest_version(session, ref.schema_key)
    row = session.exec(
        select(JsonSchema).where(
            JsonSchema.schema_key == ref.schema_key, JsonSchema.schema_version == version
        )
    ).first()
    if row is None:
        raise ServiceError(
            404,
            "SCHEMA_NOT_FOUND",
            f"schemaKey {ref.schema_key} (version {version or '最新'}) がありません",
        )
    return row


def get_schema(session: Session, ref: SchemaRef) -> JsonSchemaOut:
    """schema_id、または schema_key (+ schema_version。省略時は最新版) でスキーマを取得する。"""
    return _schema_out(_find_schema(session, ref))


def get_schema_json(session: Session, ref: SchemaRef) -> dict[str, Any]:
    """スキーマ本体 (schema_json) だけを返す。OpenAPI からの外部参照 (URL) で使う。

    $id (urn:) を残すと、本体内の $ref (#/$defs/...) が urn を基準に解決され、外部参照として
    取り込めない。そのため $id を除いて返す (スキーマテーブルの内容は変えない)。
    """
    body = _find_schema(session, ref).schema_body
    return {k: v for k, v in body.items() if k != "$id"}


def register_schema(session: Session, data: JsonSchemaIn) -> JsonSchemaOut:
    """新しいスキーマ (版) を登録する。登録済みの行は更新できないため、変更は新しい版で行う。"""
    errors = check_schema_document(data.schema_body)
    expected_id = f"urn:das:schema:{data.schema_key}:{data.schema_version}"
    declared_id = data.schema_body.get("$id")
    if declared_id is not None and declared_id != expected_id:
        errors.append(
            custom_error(
                "/$id", "const", f"$id は {expected_id} にしてください (指定値: {declared_id})"
            )
        )
    if errors:
        raise SchemaValidationError(errors, target="schemaJson")

    row = JsonSchema(
        schema_key=data.schema_key,
        schema_version=data.schema_version,
        record_type=data.record_type,
        feature_domain=data.feature_domain,
        schema_body=data.schema_body,
    )
    session.add(row)
    _flush(session)
    session.commit()
    session.refresh(row)
    return _schema_out(row)


def _validate_content(
    session: Session,
    schema: JsonSchema,
    content: dict[str, Any],
    record_type: str,
    feature_domain: str | None,
) -> None:
    if schema.record_type != record_type or schema.feature_domain not in (None, feature_domain):
        raise ServiceError(
            409,
            "SCHEMA_MISMATCH",
            f"スキーマ {schema.schema_key} v{schema.schema_version} は "
            f"recordType={schema.record_type} / featureDomain={schema.feature_domain} 用です",
        )
    errors = validate_instance(schema.schema_body, content)
    if errors:
        raise SchemaValidationError(
            errors,
            target="contentJson",
            schema=schema,
            latest_version=_latest_version(session, schema.schema_key),
        )


def _add_revision(
    session: Session, record: ContentRecord, schema: JsonSchema, data: RevisionIn
) -> ContentRevision:
    previous = session.exec(
        select(ContentRevision)
        .where(ContentRevision.record_id == record.record_id)
        .order_by(ContentRevision.revision_no.desc())  # type: ignore[attr-defined]
        .limit(1)
    ).first()
    revision = ContentRevision(
        record_id=record.record_id,
        schema_id=schema.schema_id,
        revision_no=previous.revision_no + 1 if previous else 1,
        content_json=data.content_json,
        change_reason=data.change_reason,
    )
    session.add(revision)
    _flush(session)
    if previous:
        session.add(
            RevisionParent(
                revision_id=revision.revision_id,
                parent_revision_id=previous.revision_id,
                relationship="PREVIOUS",
            )
        )
        _flush(session)
    return revision


def create_record(session: Session, data: RecordIn) -> RecordWithRevisions:
    """レコードと最初のリビジョンを作成する。検証に通らなければ何も書き込まない。"""
    schema = _find_schema(session, data)
    _validate_content(session, schema, data.content_json, data.record_type, data.feature_domain)
    record = ContentRecord(
        origin_platform_id=data.origin_platform_id,
        origin_product_id=data.origin_product_id,
        record_type=data.record_type,
        feature_domain=data.feature_domain,
        logical_key=data.logical_key,
    )
    session.add(record)
    _flush(session)
    _add_revision(session, record, schema, data)
    session.commit()
    return get_record(session, record.record_id)


def add_revision(session: Session, record_id: uuid.UUID, data: RevisionIn) -> RevisionOut:
    """既存レコードに新しいリビジョンを追加する (既存リビジョンは更新できない)。"""
    # 同一レコードへの同時追加で revision_no が衝突しないよう、レコードの行をロックする
    record = session.exec(
        select(ContentRecord).where(ContentRecord.record_id == record_id).with_for_update()
    ).first()
    if record is None:
        raise ServiceError(404, "RECORD_NOT_FOUND", f"recordId {record_id} がありません")
    schema = _find_schema(session, data)
    _validate_content(session, schema, data.content_json, record.record_type, record.feature_domain)
    revision = _add_revision(session, record, schema, data)
    session.commit()
    session.refresh(revision)
    return RevisionOut.model_validate(revision)


def get_record(session: Session, record_id: uuid.UUID) -> RecordWithRevisions:
    record = session.get(ContentRecord, record_id)
    if record is None:
        raise ServiceError(404, "RECORD_NOT_FOUND", f"recordId {record_id} がありません")
    revisions = session.exec(
        select(ContentRevision)
        .where(ContentRevision.record_id == record_id)
        .order_by(ContentRevision.revision_no)
    ).all()
    return RecordWithRevisions(
        **RecordOut.model_validate(record).model_dump(),
        revisions=[RevisionOut.model_validate(r) for r in revisions],
    )
