"""初期マイグレーションの制約・トリガーの検証 (全てロールバックされる)。"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.config import DATABASE_URL


@pytest.fixture
def conn():
    engine = create_engine(DATABASE_URL)
    try:
        connection = engine.connect()
    except OperationalError:
        pytest.skip("PostgreSQL に接続できません")
    with connection.begin() as tx:
        if not connection.execute(text("select to_regclass('content_revision')")).scalar():
            pytest.skip("マイグレーション未適用")
        yield connection
        tx.rollback()
    connection.close()


def one(conn, sql, **params):
    return conn.execute(text(sql), params).scalar_one()


def make_fixture(conn):
    ids = {}
    ids["platform"] = one(conn, "insert into platform (name) values ('p') returning platform_id")
    ids["pv"] = one(
        conn,
        "insert into platform_version (platform_id, version_label) values (:p, '1.0') "
        "returning platform_version_id",
        p=ids["platform"],
    )
    ids["customer"] = one(conn, "insert into customer (name) values ('c') returning customer_id")
    ids["product"] = one(
        conn,
        "insert into product (customer_id, base_platform_version_id, name) "
        "values (:c, :pv, 'prod') returning product_id",
        c=ids["customer"],
        pv=ids["pv"],
    )
    ids["schema"] = one(
        conn,
        "insert into json_schema (schema_key, schema_version, record_type, schema_json) "
        "values ('test.schema', 1, 'ARTIFACT', '{}') returning schema_id",
    )
    ids["record"] = one(
        conn,
        "insert into content_record (record_type, logical_key) values ('ARTIFACT', 'k1') "
        "returning record_id",
    )
    ids["revision"] = one(
        conn,
        "insert into content_revision (record_id, schema_id, revision_no, content_json) "
        "values (:r, :s, 1, '{\"a\": 1}') returning revision_id",
        r=ids["record"],
        s=ids["schema"],
    )
    return ids


def rejected(conn, sql, error=IntegrityError, **params):
    with pytest.raises(error), conn.begin_nested():
        conn.execute(text(sql), params)


def test_content_record_rules(conn):
    ids = make_fixture(conn)
    # FEATURE は feature_domain 必須、それ以外は NULL
    rejected(conn, "insert into content_record (record_type, logical_key) values ('FEATURE', 'f')")
    rejected(
        conn,
        "insert into content_record (record_type, feature_domain, logical_key) "
        "values ('ARTIFACT', 'HARDWARE', 'a')",
    )
    rejected(
        conn,
        "insert into content_record (record_type, feature_domain, logical_key) "
        "values ('FEATURE', 'OTHER', 'f')",
    )
    # 作成元は一方のみ
    rejected(
        conn,
        "insert into content_record (origin_platform_id, origin_product_id, record_type, logical_key) "
        "values (:p, :pr, 'ARTIFACT', 'x')",
        p=ids["platform"],
        pr=ids["product"],
    )
    # 論理キーはスコープ内で一意 (共通スコープ / プラットフォームスコープ)
    rejected(
        conn, "insert into content_record (record_type, logical_key) values ('ARTIFACT', 'k1')"
    )
    conn.execute(
        text(
            "insert into content_record (origin_platform_id, record_type, logical_key) "
            "values (:p, 'ARTIFACT', 'k1')"
        ),
        {"p": ids["platform"]},
    )
    rejected(
        conn,
        "insert into content_record (origin_platform_id, record_type, logical_key) "
        "values (:p, 'ARTIFACT', 'k1')",
        p=ids["platform"],
    )


def test_revision_rules(conn):
    ids = make_fixture(conn)
    rejected(
        conn,
        "insert into content_revision (record_id, schema_id, revision_no, content_json) "
        "values (:r, :s, 1, '{}')",
        r=ids["record"],
        s=ids["schema"],
    )
    for sql in (
        "update content_revision set change_reason = 'x'",
        "delete from content_revision",
        "update json_schema set schema_json = '{\"x\": 1}'",
        "delete from json_schema",
    ):
        rejected(conn, sql)


def test_version_content_requires_matching_record(conn):
    ids = make_fixture(conn)
    other = one(
        conn,
        "insert into content_record (record_type, logical_key) values ('ARTIFACT', 'k2') "
        "returning record_id",
    )
    insert = (
        "insert into platform_version_content (platform_version_id, record_id, revision_id) "
        "values (:pv, :rec, :rev)"
    )
    rejected(conn, insert, pv=ids["pv"], rec=other, rev=ids["revision"])
    conn.execute(text(insert), {"pv": ids["pv"], "rec": ids["record"], "rev": ids["revision"]})
    # 1バージョンにつき同一レコードの採用リビジョンは1つ
    rejected(conn, insert, pv=ids["pv"], rec=ids["record"], rev=ids["revision"])


def test_product_base_platform_version_is_fixed(conn):
    ids = make_fixture(conn)
    new_pv = one(
        conn,
        "insert into platform_version (platform_id, version_label) values (:p, '2.0') "
        "returning platform_version_id",
        p=ids["platform"],
    )
    rejected(
        conn,
        "update product set base_platform_version_id = :pv where product_id = :p",
        pv=new_pv,
        p=ids["product"],
    )
    conn.execute(
        text("update product set name = 'renamed' where product_id = :p"), {"p": ids["product"]}
    )


def test_released_versions_are_immutable(conn):
    ids = make_fixture(conn)
    pvc = (
        "insert into product_version_content (product_version_id, record_id, revision_id) "
        "values (:v, :rec, :rev)"
    )
    version = one(
        conn,
        "insert into product_version (product_id, version_label) values (:p, '0.1') "
        "returning product_version_id",
        p=ids["product"],
    )
    conn.execute(text(pvc), {"v": version, "rec": ids["record"], "rev": ids["revision"]})
    # 編集中は変更・削除できる
    conn.execute(
        text("delete from product_version_content where product_version_id = :v"), {"v": version}
    )
    conn.execute(text(pvc), {"v": version, "rec": ids["record"], "rev": ids["revision"]})

    conn.execute(
        text("update product_version set released_at = now() where product_version_id = :v"),
        {"v": version},
    )
    rejected(conn, "delete from product_version_content where product_version_id = :v", v=version)
    rejected(
        conn,
        "update product_version set version_label = 'x' where product_version_id = :v",
        v=version,
    )
    rejected(conn, "delete from product_version where product_version_id = :v", v=version)

    conn.execute(
        text("update platform_version set released_at = now() where platform_version_id = :v"),
        {"v": ids["pv"]},
    )
    rejected(conn, "delete from platform_version where platform_version_id = :v", v=ids["pv"])


def test_revision_parent_rules(conn):
    ids = make_fixture(conn)
    rejected(
        conn,
        "insert into revision_parent (revision_id, parent_revision_id, relationship, ordinal) "
        "values (:r, :r, 'PREVIOUS', 0)",
        r=ids["revision"],
    )
    parent = one(
        conn,
        "insert into content_revision (record_id, schema_id, revision_no, content_json) "
        "values (:r, :s, 2, '{}') returning revision_id",
        r=ids["record"],
        s=ids["schema"],
    )
    conn.execute(
        text(
            "insert into revision_parent (revision_id, parent_revision_id, relationship, ordinal) "
            "values (:r, :p, 'PREVIOUS', 0)"
        ),
        {"r": parent, "p": ids["revision"]},
    )
    rejected(
        conn,
        "insert into revision_parent (revision_id, parent_revision_id, relationship, ordinal) "
        "values (:r, :p, 'UNKNOWN', 0)",
        r=ids["revision"],
        p=parent,
    )
