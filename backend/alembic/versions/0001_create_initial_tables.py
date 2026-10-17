"""create initial tables

design/database/er-design.md のテーブルと、整合性ルール8 (不変性) のトリガーを作成する。

Revision ID: 0001
Revises:
Create Date: 2026-10-17 08:14:13.273827
"""

import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# 整合性ルール8: 公開済みのバージョン、リビジョン、JSON Schema定義は更新・削除しない。
# 製品の基準プラットフォームバージョンは作成後に変更しない。
IMMUTABILITY_SQL = [
    """
    CREATE FUNCTION das_forbid_modify() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION '% is immutable', TG_TABLE_NAME
            USING ERRCODE = 'integrity_constraint_violation';
    END $$
    """,
    """
    CREATE TRIGGER trg_content_revision_immutable
        BEFORE UPDATE OR DELETE ON content_revision
        FOR EACH ROW EXECUTE FUNCTION das_forbid_modify()
    """,
    """
    CREATE TRIGGER trg_json_schema_immutable
        BEFORE UPDATE OR DELETE ON json_schema
        FOR EACH ROW EXECUTE FUNCTION das_forbid_modify()
    """,
    """
    CREATE FUNCTION das_forbid_released_modify() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF OLD.released_at IS NOT NULL THEN
            RAISE EXCEPTION 'released % cannot be modified', TG_TABLE_NAME
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END $$
    """,
    """
    CREATE TRIGGER trg_platform_version_released
        BEFORE UPDATE OR DELETE ON platform_version
        FOR EACH ROW EXECUTE FUNCTION das_forbid_released_modify()
    """,
    """
    CREATE TRIGGER trg_product_version_released
        BEFORE UPDATE OR DELETE ON product_version
        FOR EACH ROW EXECUTE FUNCTION das_forbid_released_modify()
    """,
    """
    CREATE FUNCTION das_forbid_base_platform_change() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.base_platform_version_id IS DISTINCT FROM OLD.base_platform_version_id THEN
            RAISE EXCEPTION 'product.base_platform_version_id cannot be changed'
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
        RETURN NEW;
    END $$
    """,
    """
    CREATE TRIGGER trg_product_base_platform_version
        BEFORE UPDATE ON product
        FOR EACH ROW EXECUTE FUNCTION das_forbid_base_platform_change()
    """,
    """
    CREATE FUNCTION das_forbid_released_platform_content_modify() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM platform_version
            WHERE platform_version_id = OLD.platform_version_id AND released_at IS NOT NULL
        ) THEN
            RAISE EXCEPTION 'content of a released platform_version cannot be modified'
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END $$
    """,
    """
    CREATE TRIGGER trg_platform_version_content_released
        BEFORE UPDATE OR DELETE ON platform_version_content
        FOR EACH ROW EXECUTE FUNCTION das_forbid_released_platform_content_modify()
    """,
    """
    CREATE FUNCTION das_forbid_released_product_content_modify() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM product_version
            WHERE product_version_id = OLD.product_version_id AND released_at IS NOT NULL
        ) THEN
            RAISE EXCEPTION 'content of a released product_version cannot be modified'
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END $$
    """,
    """
    CREATE TRIGGER trg_product_version_content_released
        BEFORE UPDATE OR DELETE ON product_version_content
        FOR EACH ROW EXECUTE FUNCTION das_forbid_released_product_content_modify()
    """,
]


def upgrade() -> None:
    op.create_table(
        "customer",
        sa.Column(
            "customer_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("customer_id", name=op.f("pk_customer")),
    )
    op.create_table(
        "json_schema",
        sa.Column(
            "schema_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("schema_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("record_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("feature_domain", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("schema_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "feature_domain IS NULL OR feature_domain IN ('HARDWARE', 'BASIC_SOFTWARE', 'APPLICATION')",
            name=op.f("ck_json_schema_feature_domain_values"),
        ),
        sa.CheckConstraint(
            "record_type IN ('FEATURE', 'ARTIFACT')", name=op.f("ck_json_schema_record_type")
        ),
        sa.CheckConstraint("schema_version >= 1", name=op.f("ck_json_schema_schema_version")),
        sa.PrimaryKeyConstraint("schema_id", name=op.f("pk_json_schema")),
        sa.UniqueConstraint("schema_key", "schema_version", name="uq_json_schema_key_version"),
    )
    op.create_table(
        "platform",
        sa.Column(
            "platform_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("platform_id", name=op.f("pk_platform")),
    )
    op.create_table(
        "platform_schema_binding",
        sa.Column("platform_id", sa.Uuid(), nullable=False),
        sa.Column("schema_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["platform_id"],
            ["platform.platform_id"],
            name=op.f("fk_platform_schema_binding_platform_id"),
        ),
        sa.ForeignKeyConstraint(
            ["schema_id"],
            ["json_schema.schema_id"],
            name=op.f("fk_platform_schema_binding_schema_id"),
        ),
        sa.PrimaryKeyConstraint(
            "platform_id", "schema_id", name=op.f("pk_platform_schema_binding")
        ),
    )
    op.create_index(
        "ix_platform_schema_binding_schema_id",
        "platform_schema_binding",
        ["schema_id"],
        unique=False,
    )
    op.create_table(
        "platform_version",
        sa.Column(
            "platform_version_id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("platform_id", sa.Uuid(), nullable=False),
        sa.Column("version_label", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["platform_id"], ["platform.platform_id"], name=op.f("fk_platform_version_platform_id")
        ),
        sa.PrimaryKeyConstraint("platform_version_id", name=op.f("pk_platform_version")),
        sa.UniqueConstraint("platform_id", "version_label", name="uq_platform_version_label"),
    )
    op.create_table(
        "product",
        sa.Column(
            "product_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("base_platform_version_id", sa.Uuid(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["base_platform_version_id"],
            ["platform_version.platform_version_id"],
            name=op.f("fk_product_base_platform_version_id"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customer.customer_id"], name=op.f("fk_product_customer_id")
        ),
        sa.PrimaryKeyConstraint("product_id", name=op.f("pk_product")),
    )
    op.create_index(
        "ix_product_base_platform_version_id", "product", ["base_platform_version_id"], unique=False
    )
    op.create_index("ix_product_customer_id", "product", ["customer_id"], unique=False)
    op.create_table(
        "content_record",
        sa.Column(
            "record_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("origin_platform_id", sa.Uuid(), nullable=True),
        sa.Column("origin_product_id", sa.Uuid(), nullable=True),
        sa.Column("record_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("feature_domain", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("logical_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(record_type = 'FEATURE') = (feature_domain IS NOT NULL)",
            name=op.f("ck_content_record_feature_domain_required"),
        ),
        sa.CheckConstraint(
            "feature_domain IS NULL OR feature_domain IN ('HARDWARE', 'BASIC_SOFTWARE', 'APPLICATION')",
            name=op.f("ck_content_record_feature_domain_values"),
        ),
        sa.CheckConstraint(
            "record_type IN ('FEATURE', 'ARTIFACT')", name=op.f("ck_content_record_record_type")
        ),
        sa.CheckConstraint(
            "origin_platform_id IS NULL OR origin_product_id IS NULL",
            name=op.f("ck_content_record_single_origin"),
        ),
        sa.ForeignKeyConstraint(
            ["origin_platform_id"],
            ["platform.platform_id"],
            name=op.f("fk_content_record_origin_platform_id"),
        ),
        sa.ForeignKeyConstraint(
            ["origin_product_id"],
            ["product.product_id"],
            name=op.f("fk_content_record_origin_product_id"),
        ),
        sa.PrimaryKeyConstraint("record_id", name=op.f("pk_content_record")),
    )
    op.create_index(
        "uq_content_record_common_logical_key",
        "content_record",
        ["logical_key"],
        unique=True,
        postgresql_where=sa.text("origin_platform_id IS NULL AND origin_product_id IS NULL"),
    )
    op.create_index(
        "uq_content_record_platform_logical_key",
        "content_record",
        ["origin_platform_id", "logical_key"],
        unique=True,
        postgresql_where=sa.text("origin_platform_id IS NOT NULL"),
    )
    op.create_index(
        "uq_content_record_product_logical_key",
        "content_record",
        ["origin_product_id", "logical_key"],
        unique=True,
        postgresql_where=sa.text("origin_product_id IS NOT NULL"),
    )
    op.create_table(
        "product_version",
        sa.Column(
            "product_version_id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("version_label", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["product_id"], ["product.product_id"], name=op.f("fk_product_version_product_id")
        ),
        sa.PrimaryKeyConstraint("product_version_id", name=op.f("pk_product_version")),
        sa.UniqueConstraint("product_id", "version_label", name="uq_product_version_label"),
    )
    op.create_table(
        "content_revision",
        sa.Column(
            "revision_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("schema_id", sa.Uuid(), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("content_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("change_reason", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("revision_no >= 1", name=op.f("ck_content_revision_revision_no")),
        sa.ForeignKeyConstraint(
            ["record_id"], ["content_record.record_id"], name=op.f("fk_content_revision_record_id")
        ),
        sa.ForeignKeyConstraint(
            ["schema_id"], ["json_schema.schema_id"], name=op.f("fk_content_revision_schema_id")
        ),
        sa.PrimaryKeyConstraint("revision_id", name=op.f("pk_content_revision")),
        sa.UniqueConstraint("record_id", "revision_no", name="uq_content_revision_record_no"),
        sa.UniqueConstraint("revision_id", "record_id", name="uq_content_revision_id_record"),
    )
    op.create_index(
        "ix_content_revision_schema_id", "content_revision", ["schema_id"], unique=False
    )
    op.create_table(
        "platform_version_content",
        sa.Column("platform_version_id", sa.Uuid(), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["platform_version_id"],
            ["platform_version.platform_version_id"],
            name=op.f("fk_platform_version_content_platform_version_id"),
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["content_record.record_id"],
            name=op.f("fk_platform_version_content_record_id"),
        ),
        sa.ForeignKeyConstraint(
            ["revision_id", "record_id"],
            ["content_revision.revision_id", "content_revision.record_id"],
            name="fk_platform_version_content_revision",
        ),
        sa.PrimaryKeyConstraint(
            "platform_version_id", "record_id", name=op.f("pk_platform_version_content")
        ),
    )
    op.create_index(
        "ix_platform_version_content_revision",
        "platform_version_content",
        ["revision_id", "record_id"],
        unique=False,
    )
    op.create_table(
        "product_version_content",
        sa.Column("product_version_id", sa.Uuid(), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_version_id"],
            ["product_version.product_version_id"],
            name=op.f("fk_product_version_content_product_version_id"),
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["content_record.record_id"],
            name=op.f("fk_product_version_content_record_id"),
        ),
        sa.ForeignKeyConstraint(
            ["revision_id", "record_id"],
            ["content_revision.revision_id", "content_revision.record_id"],
            name="fk_product_version_content_revision",
        ),
        sa.PrimaryKeyConstraint(
            "product_version_id", "record_id", name=op.f("pk_product_version_content")
        ),
    )
    op.create_index(
        "ix_product_version_content_revision",
        "product_version_content",
        ["revision_id", "record_id"],
        unique=False,
    )
    op.create_table(
        "revision_parent",
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("parent_revision_id", sa.Uuid(), nullable=False),
        sa.Column("relationship", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "relationship IN ('PREVIOUS', 'DERIVED_FROM', 'MERGED_FROM')",
            name=op.f("ck_revision_parent_relationship"),
        ),
        sa.CheckConstraint(
            "revision_id <> parent_revision_id", name=op.f("ck_revision_parent_not_self")
        ),
        sa.ForeignKeyConstraint(
            ["parent_revision_id"],
            ["content_revision.revision_id"],
            name=op.f("fk_revision_parent_parent_revision_id"),
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["content_revision.revision_id"],
            name=op.f("fk_revision_parent_revision_id"),
        ),
        sa.PrimaryKeyConstraint(
            "revision_id", "parent_revision_id", name=op.f("pk_revision_parent")
        ),
    )
    op.create_index(
        "ix_revision_parent_parent_revision_id",
        "revision_parent",
        ["parent_revision_id"],
        unique=False,
    )

    for statement in IMMUTABILITY_SQL:
        op.execute(statement)


def downgrade() -> None:
    op.drop_index("ix_revision_parent_parent_revision_id", table_name="revision_parent")
    op.drop_table("revision_parent")
    op.drop_index("ix_product_version_content_revision", table_name="product_version_content")
    op.drop_table("product_version_content")
    op.drop_index("ix_platform_version_content_revision", table_name="platform_version_content")
    op.drop_table("platform_version_content")
    op.drop_index("ix_content_revision_schema_id", table_name="content_revision")
    op.drop_table("content_revision")
    op.drop_table("product_version")
    op.drop_index(
        "uq_content_record_product_logical_key",
        table_name="content_record",
        postgresql_where=sa.text("origin_product_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_content_record_platform_logical_key",
        table_name="content_record",
        postgresql_where=sa.text("origin_platform_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_content_record_common_logical_key",
        table_name="content_record",
        postgresql_where=sa.text("origin_platform_id IS NULL AND origin_product_id IS NULL"),
    )
    op.drop_table("content_record")
    op.drop_index("ix_product_customer_id", table_name="product")
    op.drop_index("ix_product_base_platform_version_id", table_name="product")
    op.drop_table("product")
    op.drop_table("platform_version")
    op.drop_index("ix_platform_schema_binding_schema_id", table_name="platform_schema_binding")
    op.drop_table("platform_schema_binding")
    op.drop_table("platform")
    op.drop_table("json_schema")
    op.drop_table("customer")
    for function in (
        "das_forbid_modify",
        "das_forbid_released_modify",
        "das_forbid_base_platform_change",
        "das_forbid_released_platform_content_modify",
        "das_forbid_released_product_content_modify",
    ):
        op.execute(f"DROP FUNCTION {function}()")
