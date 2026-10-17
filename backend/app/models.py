from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

JSON_DOCUMENT = JSONB().with_variant(JSON(), "sqlite")


class Customer(SQLModel, table=True):
    __tablename__ = "CUSTOMER"

    customer_id: str = Field(sa_column=Column(Uuid(as_uuid=False), primary_key=True))
    name: str = Field(sa_column=Column(String, nullable=False))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    )


class Platform(SQLModel, table=True):
    __tablename__ = "PLATFORM"

    platform_id: str = Field(sa_column=Column(Uuid(as_uuid=False), primary_key=True))
    name: str = Field(sa_column=Column(String, nullable=False))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    )


class PlatformVersion(SQLModel, table=True):
    __tablename__ = "PLATFORM_VERSION"

    platform_version_id: str = Field(sa_column=Column(Uuid(as_uuid=False), primary_key=True))
    platform_id: str = Field(
        sa_column=Column(Uuid(as_uuid=False), ForeignKey("PLATFORM.platform_id"), nullable=False)
    )
    version_label: str = Field(sa_column=Column(String, nullable=False))
    released_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    )


class Product(SQLModel, table=True):
    __tablename__ = "PRODUCT"

    product_id: str = Field(sa_column=Column(Uuid(as_uuid=False), primary_key=True))
    customer_id: str = Field(
        sa_column=Column(Uuid(as_uuid=False), ForeignKey("CUSTOMER.customer_id"), nullable=False)
    )
    base_platform_version_id: str = Field(
        sa_column=Column(
            Uuid(as_uuid=False),
            ForeignKey("PLATFORM_VERSION.platform_version_id"),
            nullable=False,
        )
    )
    name: str = Field(sa_column=Column(String, nullable=False))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    )


class ProductVersion(SQLModel, table=True):
    __tablename__ = "PRODUCT_VERSION"

    product_version_id: str = Field(sa_column=Column(Uuid(as_uuid=False), primary_key=True))
    product_id: str = Field(
        sa_column=Column(Uuid(as_uuid=False), ForeignKey("PRODUCT.product_id"), nullable=False)
    )
    version_label: str = Field(sa_column=Column(String, nullable=False))
    released_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    )


class ContentRecord(SQLModel, table=True):
    __tablename__ = "CONTENT_RECORD"
    __table_args__ = (
        CheckConstraint(
            "NOT (origin_platform_id IS NOT NULL AND origin_product_id IS NOT NULL)",
            name="ck_content_record_single_origin",
        ),
        CheckConstraint(
            "(record_type = 'FEATURE' AND feature_domain IS NOT NULL) OR "
            "(record_type = 'ARTIFACT' AND feature_domain IS NULL)",
            name="ck_content_record_type_domain",
        ),
        CheckConstraint(
            "record_type IN ('FEATURE', 'ARTIFACT')",
            name="ck_content_record_record_type",
        ),
        CheckConstraint(
            "feature_domain IS NULL OR feature_domain IN "
            "('HARDWARE', 'BASIC_SOFTWARE', 'APPLICATION')",
            name="ck_content_record_feature_domain",
        ),
        Index(
            "uq_content_record_shared_logical_key",
            "logical_key",
            unique=True,
            postgresql_where=text("origin_platform_id IS NULL AND origin_product_id IS NULL"),
            sqlite_where=text("origin_platform_id IS NULL AND origin_product_id IS NULL"),
        ),
        Index(
            "uq_content_record_platform_logical_key",
            "origin_platform_id",
            "logical_key",
            unique=True,
            postgresql_where=text("origin_platform_id IS NOT NULL"),
            sqlite_where=text("origin_platform_id IS NOT NULL"),
        ),
        Index(
            "uq_content_record_product_logical_key",
            "origin_product_id",
            "logical_key",
            unique=True,
            postgresql_where=text("origin_product_id IS NOT NULL"),
            sqlite_where=text("origin_product_id IS NOT NULL"),
        ),
    )

    record_id: str = Field(sa_column=Column(Uuid(as_uuid=False), primary_key=True))
    origin_platform_id: str | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=False), ForeignKey("PLATFORM.platform_id"), nullable=True),
    )
    origin_product_id: str | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=False), ForeignKey("PRODUCT.product_id"), nullable=True),
    )
    record_type: str = Field(sa_column=Column(String, nullable=False))
    feature_domain: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    logical_key: str = Field(sa_column=Column(String, nullable=False))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    )


class JsonSchema(SQLModel, table=True):
    __tablename__ = "JSON_SCHEMA"
    __table_args__ = (
        CheckConstraint("schema_version > 0", name="ck_json_schema_positive_version"),
        CheckConstraint(
            "record_type IN ('FEATURE', 'ARTIFACT')",
            name="ck_json_schema_record_type",
        ),
        UniqueConstraint("schema_key", "schema_version", name="uq_json_schema_key_version"),
    )

    schema_id: str = Field(sa_column=Column(Uuid(as_uuid=False), primary_key=True))
    schema_key: str = Field(sa_column=Column(String, nullable=False))
    schema_version: int = Field(sa_column=Column(Integer, nullable=False))
    record_type: str = Field(sa_column=Column(String, nullable=False))
    feature_domain: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    schema_json_value: dict[str, Any] = Field(
        sa_column=Column("schema_json", JSON_DOCUMENT, nullable=False)
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    )


class ContentRevision(SQLModel, table=True):
    __tablename__ = "CONTENT_REVISION"
    __table_args__ = (
        UniqueConstraint("record_id", "revision_no", name="uq_content_revision_number"),
        UniqueConstraint("revision_id", "record_id", name="uq_content_revision_id_record"),
        CheckConstraint("revision_no > 0", name="ck_content_revision_positive_number"),
    )

    revision_id: str = Field(sa_column=Column(Uuid(as_uuid=False), primary_key=True))
    record_id: str = Field(
        sa_column=Column(
            Uuid(as_uuid=False), ForeignKey("CONTENT_RECORD.record_id"), nullable=False
        )
    )
    schema_id: str = Field(
        sa_column=Column(Uuid(as_uuid=False), ForeignKey("JSON_SCHEMA.schema_id"), nullable=False)
    )
    revision_no: int = Field(sa_column=Column(Integer, nullable=False))
    content_json: Any = Field(sa_column=Column(JSON_DOCUMENT, nullable=False))
    change_reason: str = Field(sa_column=Column(String, nullable=False))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    )


class RevisionParent(SQLModel, table=True):
    __tablename__ = "REVISION_PARENT"
    __table_args__ = (
        CheckConstraint(
            "relationship IN ('PREVIOUS', 'DERIVED_FROM', 'MERGED_FROM')",
            name="ck_revision_parent_relationship",
        ),
        CheckConstraint("ordinal > 0", name="ck_revision_parent_positive_ordinal"),
    )

    revision_id: str = Field(
        sa_column=Column(
            Uuid(as_uuid=False),
            ForeignKey("CONTENT_REVISION.revision_id"),
            primary_key=True,
        )
    )
    parent_revision_id: str = Field(
        sa_column=Column(
            Uuid(as_uuid=False),
            ForeignKey("CONTENT_REVISION.revision_id"),
            primary_key=True,
        )
    )
    relationship: str = Field(sa_column=Column(String, nullable=False))
    ordinal: int = Field(sa_column=Column(Integer, nullable=False))


class PlatformSchemaBinding(SQLModel, table=True):
    __tablename__ = "PLATFORM_SCHEMA_BINDING"

    platform_id: str = Field(
        sa_column=Column(Uuid(as_uuid=False), ForeignKey("PLATFORM.platform_id"), primary_key=True)
    )
    schema_id: str = Field(
        sa_column=Column(Uuid(as_uuid=False), ForeignKey("JSON_SCHEMA.schema_id"), primary_key=True)
    )


class PlatformVersionContent(SQLModel, table=True):
    __tablename__ = "PLATFORM_VERSION_CONTENT"
    __table_args__ = (
        ForeignKeyConstraint(
            ["revision_id", "record_id"],
            ["CONTENT_REVISION.revision_id", "CONTENT_REVISION.record_id"],
            name="fk_platform_version_content_revision_record",
        ),
    )

    platform_version_id: str = Field(
        sa_column=Column(
            Uuid(as_uuid=False),
            ForeignKey("PLATFORM_VERSION.platform_version_id"),
            primary_key=True,
        )
    )
    record_id: str = Field(sa_column=Column(Uuid(as_uuid=False), primary_key=True))
    revision_id: str = Field(sa_column=Column(Uuid(as_uuid=False), nullable=False))


class ProductVersionContent(SQLModel, table=True):
    __tablename__ = "PRODUCT_VERSION_CONTENT"
    __table_args__ = (
        ForeignKeyConstraint(
            ["revision_id", "record_id"],
            ["CONTENT_REVISION.revision_id", "CONTENT_REVISION.record_id"],
            name="fk_product_version_content_revision_record",
        ),
    )

    product_version_id: str = Field(
        sa_column=Column(
            Uuid(as_uuid=False),
            ForeignKey("PRODUCT_VERSION.product_version_id"),
            primary_key=True,
        )
    )
    record_id: str = Field(sa_column=Column(Uuid(as_uuid=False), primary_key=True))
    revision_id: str = Field(sa_column=Column(Uuid(as_uuid=False), nullable=False))


TABLE_MODELS = {
    model.__tablename__: model
    for model in (
        Customer,
        Platform,
        PlatformVersion,
        Product,
        ProductVersion,
        ContentRecord,
        JsonSchema,
        ContentRevision,
        RevisionParent,
        PlatformSchemaBinding,
        PlatformVersionContent,
        ProductVersionContent,
    )
}

SEED_INSERT_ORDER = (
    "CUSTOMER",
    "PLATFORM",
    "PLATFORM_VERSION",
    "PRODUCT",
    "PRODUCT_VERSION",
    "CONTENT_RECORD",
    "JSON_SCHEMA",
    "CONTENT_REVISION",
    "REVISION_PARENT",
    "PLATFORM_SCHEMA_BINDING",
    "PLATFORM_VERSION_CONTENT",
    "PRODUCT_VERSION_CONTENT",
)
