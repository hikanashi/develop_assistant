"""Protect immutable published records from update and deletion."""

from alembic import op

revision = "0002_immutable_records"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

TABLES = ("PLATFORM_VERSION", "PRODUCT_VERSION", "CONTENT_REVISION", "JSON_SCHEMA")


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION prevent_immutable_record_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'Rows in % are immutable', TG_TABLE_NAME
                USING ERRCODE = '23000';
        END;
        $$
        """
    )
    for table in TABLES:
        op.execute(
            f'CREATE TRIGGER "trg_{table.lower()}_immutable" '
            f'BEFORE UPDATE OR DELETE ON "{table}" '
            "FOR EACH ROW EXECUTE FUNCTION prevent_immutable_record_mutation()"
        )
    op.execute(
        """
        CREATE FUNCTION prevent_product_baseline_change()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.base_platform_version_id IS DISTINCT FROM OLD.base_platform_version_id THEN
                RAISE EXCEPTION 'A product baseline cannot be changed'
                    USING ERRCODE = '23000';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_product_baseline_immutable
        BEFORE UPDATE OF base_platform_version_id ON "PRODUCT"
        FOR EACH ROW EXECUTE FUNCTION prevent_product_baseline_change()
        """
    )


def downgrade() -> None:
    op.execute('DROP TRIGGER IF EXISTS trg_product_baseline_immutable ON "PRODUCT"')
    op.execute("DROP FUNCTION IF EXISTS prevent_product_baseline_change()")
    for table in TABLES:
        op.execute(f'DROP TRIGGER IF EXISTS "trg_{table.lower()}_immutable" ON "{table}"')
    op.execute("DROP FUNCTION IF EXISTS prevent_immutable_record_mutation()")
