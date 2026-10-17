"""REST / MCP の入出力モデル (JSONの形)。"""

import uuid
from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

RecordType = Literal["FEATURE", "ARTIFACT"]
FeatureDomain = Literal["HARDWARE", "BASIC_SOFTWARE", "APPLICATION"]


class JsonSchemaSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    schema_id: uuid.UUID
    schema_key: str
    schema_version: int
    record_type: RecordType
    feature_domain: FeatureDomain | None
    created_at: datetime


class JsonSchemaOut(JsonSchemaSummary):
    model_config = ConfigDict(populate_by_name=True)

    # BaseModel.schema_json と衝突するため、属性名は schema_body とし JSON上は schema_json とする
    schema_body: dict[str, Any] = Field(alias="schema_json")


class JsonSchemaIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_key: str = Field(min_length=1)
    schema_version: int = Field(ge=1)
    record_type: RecordType
    feature_domain: FeatureDomain | None = None
    schema_body: dict[str, Any] = Field(alias="schema_json")


class SchemaRef(BaseModel):
    """検証に使うスキーマの指定。schema_id か、schema_key (+ schema_version) のどちらか。

    schema_version を省略すると、schema_key の最新版を使う。
    """

    schema_id: uuid.UUID | None = None
    schema_key: str | None = None
    schema_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _exactly_one_selector(self) -> Self:
        if (self.schema_id is None) == (self.schema_key is None):
            raise ValueError("schema_id か schema_key のどちらか一方を指定してください")
        if self.schema_id is not None and self.schema_version is not None:
            raise ValueError("schema_id と schema_version は同時に指定できません")
        return self


class RevisionIn(SchemaRef):
    content_json: dict[str, Any]
    change_reason: str | None = None


class RecordIn(RevisionIn):
    """レコードと最初のリビジョンを作成する。"""

    record_type: RecordType
    feature_domain: FeatureDomain | None = None
    origin_platform_id: uuid.UUID | None = None
    origin_product_id: uuid.UUID | None = None
    logical_key: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_record(self) -> Self:
        if (self.record_type == "FEATURE") != (self.feature_domain is not None):
            raise ValueError("feature_domain は record_type が FEATURE のときだけ指定します")
        if self.origin_platform_id and self.origin_product_id:
            raise ValueError("origin_platform_id と origin_product_id は同時に指定できません")
        return self


class RecordUpdateIn(RecordIn):
    """レコードの属性を置き換え、新しいリビジョンを追加する。"""


class RevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    revision_id: uuid.UUID
    record_id: uuid.UUID
    schema_id: uuid.UUID
    revision_no: int
    content_json: dict[str, Any]
    change_reason: str | None
    created_at: datetime


class RecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    record_id: uuid.UUID
    origin_platform_id: uuid.UUID | None
    origin_product_id: uuid.UUID | None
    record_type: RecordType
    feature_domain: FeatureDomain | None
    logical_key: str
    created_at: datetime


class RecordWithRevisions(RecordOut):
    revisions: list[RevisionOut]
