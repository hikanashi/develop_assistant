"""データベース論理設計 (design/database/er-design.md) に対応するテーブル定義。

CHECK制約・部分一意インデックス・不変性トリガーなどモデルで表現しきれない
定義はマイグレーションに記述する。
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

# 制約名を固定し、マイグレーションの差分を安定させる
SQLModel.metadata.naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}


def uuid_pk(**kwargs: Any) -> Any:
    return Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
        **kwargs,
    )


def timestamp(*, nullable: bool = False, **kwargs: Any) -> Any:
    column_kwargs: dict[str, Any] = {"nullable": nullable}
    if not nullable:
        column_kwargs["server_default"] = func.now()
    return Field(sa_type=DateTime(timezone=True), sa_column_kwargs=column_kwargs, **kwargs)


class Customer(SQLModel, table=True):
    __tablename__ = "customer"

    customer_id: uuid.UUID = uuid_pk()
    name: str
    created_at: datetime = timestamp(default_factory=lambda: datetime.now().astimezone())


class Platform(SQLModel, table=True):
    __tablename__ = "platform"

    platform_id: uuid.UUID = uuid_pk()
    name: str
    created_at: datetime = timestamp(default_factory=lambda: datetime.now().astimezone())


class PlatformVersion(SQLModel, table=True):
    """released_at が NULL の間は編集中、設定後は変更・削除不可 (トリガーで保護)。"""

    __tablename__ = "platform_version"
    __table_args__ = (
        UniqueConstraint("platform_id", "version_label", name="uq_platform_version_label"),
    )

    platform_version_id: uuid.UUID = uuid_pk()
    platform_id: uuid.UUID = Field(foreign_key="platform.platform_id")
    version_label: str
    released_at: datetime | None = timestamp(nullable=True, default=None)


class Product(SQLModel, table=True):
    """base_platform_version_id は必須で、作成後は変更不可 (トリガーで保護)。"""

    __tablename__ = "product"
    __table_args__ = (
        Index("ix_product_customer_id", "customer_id"),
        Index("ix_product_base_platform_version_id", "base_platform_version_id"),
    )

    product_id: uuid.UUID = uuid_pk()
    customer_id: uuid.UUID = Field(foreign_key="customer.customer_id")
    base_platform_version_id: uuid.UUID = Field(foreign_key="platform_version.platform_version_id")
    name: str
    created_at: datetime = timestamp(default_factory=lambda: datetime.now().astimezone())


class ProductVersion(SQLModel, table=True):
    """released_at が NULL の間は編集中、設定後は変更・削除不可 (トリガーで保護)。"""

    __tablename__ = "product_version"
    __table_args__ = (
        UniqueConstraint("product_id", "version_label", name="uq_product_version_label"),
    )

    product_version_id: uuid.UUID = uuid_pk()
    product_id: uuid.UUID = Field(foreign_key="product.product_id")
    version_label: str
    released_at: datetime | None = timestamp(nullable=True, default=None)


class ContentRecord(SQLModel, table=True):
    __tablename__ = "content_record"
    __table_args__ = (
        CheckConstraint("record_type IN ('FEATURE', 'ARTIFACT')", name="record_type"),
        CheckConstraint(
            "feature_domain IS NULL OR feature_domain IN "
            "('HARDWARE', 'BASIC_SOFTWARE', 'APPLICATION')",
            name="feature_domain_values",
        ),
        # FEATURE のときだけ feature_domain を持つ
        CheckConstraint(
            "(record_type = 'FEATURE') = (feature_domain IS NOT NULL)",
            name="feature_domain_required",
        ),
        # 作成元はプラットフォームか製品のどちらか一方、または共通(両方NULL)
        CheckConstraint(
            "origin_platform_id IS NULL OR origin_product_id IS NULL",
            name="single_origin",
        ),
        # 論理キーは共有スコープ(作成元)内で一意
        Index(
            "uq_content_record_platform_logical_key",
            "origin_platform_id",
            "logical_key",
            unique=True,
            postgresql_where=text("origin_platform_id IS NOT NULL"),
        ),
        Index(
            "uq_content_record_product_logical_key",
            "origin_product_id",
            "logical_key",
            unique=True,
            postgresql_where=text("origin_product_id IS NOT NULL"),
        ),
        Index(
            "uq_content_record_common_logical_key",
            "logical_key",
            unique=True,
            postgresql_where=text("origin_platform_id IS NULL AND origin_product_id IS NULL"),
        ),
    )

    record_id: uuid.UUID = uuid_pk()
    origin_platform_id: uuid.UUID | None = Field(default=None, foreign_key="platform.platform_id")
    origin_product_id: uuid.UUID | None = Field(default=None, foreign_key="product.product_id")
    record_type: str
    feature_domain: str | None = None
    logical_key: str
    created_at: datetime = timestamp(default_factory=lambda: datetime.now().astimezone())


class JsonSchema(SQLModel, table=True):
    """不変のバージョン付きJSON Schema定義 (更新・削除不可、トリガーで保護)。"""

    __tablename__ = "json_schema"
    __table_args__ = (
        UniqueConstraint("schema_key", "schema_version", name="uq_json_schema_key_version"),
        CheckConstraint("schema_version >= 1", name="schema_version"),
        CheckConstraint("record_type IN ('FEATURE', 'ARTIFACT')", name="record_type"),
        CheckConstraint(
            "feature_domain IS NULL OR feature_domain IN "
            "('HARDWARE', 'BASIC_SOFTWARE', 'APPLICATION')",
            name="feature_domain_values",
        ),
    )

    schema_id: uuid.UUID = uuid_pk()
    schema_key: str
    schema_version: int
    record_type: str
    feature_domain: str | None = None
    # 属性名が SQLModel.schema_json と衝突するため、DBの列名のみ schema_json とする
    schema_body: dict[str, Any] = Field(sa_column=Column("schema_json", JSONB, nullable=False))
    created_at: datetime = timestamp(default_factory=lambda: datetime.now().astimezone())


class PlatformSchemaBinding(SQLModel, table=True):
    __tablename__ = "platform_schema_binding"
    __table_args__ = (Index("ix_platform_schema_binding_schema_id", "schema_id"),)

    platform_id: uuid.UUID = Field(foreign_key="platform.platform_id", primary_key=True)
    schema_id: uuid.UUID = Field(foreign_key="json_schema.schema_id", primary_key=True)


class ContentRevision(SQLModel, table=True):
    """レコードの不変リビジョン (更新・削除不可、トリガーで保護)。"""

    __tablename__ = "content_revision"
    __table_args__ = (
        UniqueConstraint("record_id", "revision_no", name="uq_content_revision_record_no"),
        # バージョン内容テーブルの複合外部キーの参照先
        UniqueConstraint("revision_id", "record_id", name="uq_content_revision_id_record"),
        CheckConstraint("revision_no >= 1", name="revision_no"),
        Index("ix_content_revision_schema_id", "schema_id"),
    )

    revision_id: uuid.UUID = uuid_pk()
    record_id: uuid.UUID = Field(foreign_key="content_record.record_id")
    schema_id: uuid.UUID = Field(foreign_key="json_schema.schema_id")
    revision_no: int
    content_json: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    change_reason: str | None = None
    created_at: datetime = timestamp(default_factory=lambda: datetime.now().astimezone())


class RevisionParent(SQLModel, table=True):
    __tablename__ = "revision_parent"
    __table_args__ = (
        CheckConstraint(
            "relationship IN ('PREVIOUS', 'DERIVED_FROM', 'MERGED_FROM')",
            name="relationship",
        ),
        CheckConstraint("revision_id <> parent_revision_id", name="not_self"),
        Index("ix_revision_parent_parent_revision_id", "parent_revision_id"),
    )

    revision_id: uuid.UUID = Field(foreign_key="content_revision.revision_id", primary_key=True)
    parent_revision_id: uuid.UUID = Field(
        foreign_key="content_revision.revision_id", primary_key=True
    )
    relationship: str
    ordinal: int = 0


class PlatformVersionContent(SQLModel, table=True):
    """プラットフォームバージョンが採用するリビジョンのスナップショット。"""

    __tablename__ = "platform_version_content"
    __table_args__ = (
        # 採用リビジョンが record_id のレコードに属することを保証する
        ForeignKeyConstraint(
            ["revision_id", "record_id"],
            ["content_revision.revision_id", "content_revision.record_id"],
            name="fk_platform_version_content_revision",
        ),
        Index("ix_platform_version_content_revision", "revision_id", "record_id"),
    )

    platform_version_id: uuid.UUID = Field(
        foreign_key="platform_version.platform_version_id", primary_key=True
    )
    record_id: uuid.UUID = Field(foreign_key="content_record.record_id", primary_key=True)
    revision_id: uuid.UUID


class ProductVersionContent(SQLModel, table=True):
    """製品バージョンが採用するリビジョンの完全な構成マニフェスト。"""

    __tablename__ = "product_version_content"
    __table_args__ = (
        ForeignKeyConstraint(
            ["revision_id", "record_id"],
            ["content_revision.revision_id", "content_revision.record_id"],
            name="fk_product_version_content_revision",
        ),
        Index("ix_product_version_content_revision", "revision_id", "record_id"),
    )

    product_version_id: uuid.UUID = Field(
        foreign_key="product_version.product_version_id", primary_key=True
    )
    record_id: uuid.UUID = Field(foreign_key="content_record.record_id", primary_key=True)
    revision_id: uuid.UUID
