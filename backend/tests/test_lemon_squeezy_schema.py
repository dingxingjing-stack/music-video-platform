"""P2-2：Lemon Squeezy 4 张台账表的 schema 测试。

只测结构，不测任何业务逻辑（本阶段没有任何代码读写这些表）。

锁住六件事：
  A/B 四张表由项目现有的 init_db() 建出，且 init_db() 连跑两次幂等；
  C   四个唯一约束是**数据库级**的 —— 用真实重复插入触发 IntegrityError，
      而不是验证"应用层先查后插"（并发重投会双双通过应用层检查）；
  D/E 四张表都有 test_mode 与 created_at/updated_at；
  F   membership 表**没有** interval（LS payload 不提供可靠真值，存了就是第二个真值源）；
  G   没有 lemonsqueezy_checkouts（本阶段明确不建）；
  H   Paddle / Credits / 会员既有表仍在、结构未被改动（含 database.py 是纯追加的 git 证据）。

全程用 tmp_path 里的临时 SQLite，绝不碰开发库 music_platform.db。
"""

from __future__ import annotations

import subprocess

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable

from app.db import database
from app.db.database import (
    Base,
    LemonSqueezyMembership,
    LemonSqueezyMembershipGrant,
    LemonSqueezyPurchase,
    LemonSqueezyWebhookDelivery,
)

LS_TABLES = [
    "lemonsqueezy_webhook_deliveries",
    "lemonsqueezy_purchases",
    "lemonsqueezy_memberships",
    "lemonsqueezy_membership_grants",
]

# 本阶段必须"只存在、不被改"的既有商业表
PREEXISTING_TABLES = [
    "user_credits",
    "credits_transactions",
    "credit_pack_purchases",
    "user_memberships",
    "paddle_customers",
    "paddle_subscriptions",
]

TIMESTAMP_COLS = {"created_at", "updated_at"}


@pytest.fixture()
def ls_engine(monkeypatch, tmp_path):
    """把 database.engine 指到临时库，再用项目自己的 init_db() 建表（连建两次）。"""
    eng = create_engine(f"sqlite:///{tmp_path / 'ls.schema.db'}",
                        connect_args={"check_same_thread": False})
    monkeypatch.setattr(database, "engine", eng)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=eng))
    database.init_db()          # 第一次：建表
    database.init_db()          # 第二次：必须幂等、不报错
    yield eng
    eng.dispose()


@pytest.fixture()
def session(ls_engine):
    maker = sessionmaker(bind=ls_engine)
    sess = maker()
    yield sess
    sess.close()


def _columns(engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


def _assert_db_rejects(session, model, first: dict, second: dict) -> None:
    """插入两条冲突行：第二条必须由**数据库**抛 IntegrityError。"""
    session.add(model(**first))
    session.flush()
    session.commit()
    try:
        session.add(model(**second))
        session.flush()
        raise AssertionError(f"{model.__tablename__} 没有拒绝重复值 —— UNIQUE 未落到数据库")
    except IntegrityError:
        session.rollback()


# ── A. 表存在 ───────────────────────────────────────────────────────────
def test_all_four_lemonsqueezy_tables_exist(ls_engine):
    names = set(inspect(ls_engine).get_table_names())
    for table in LS_TABLES:
        assert table in names


def test_models_are_registered_on_shared_metadata():
    """四张表挂在项目同一个 Base.metadata 上 ⇒ 由同一个 init_db() 建，无第二套机制。"""
    for table in LS_TABLES:
        assert table in Base.metadata.tables


# ── B. 重复 init_db（fixture 已连跑两次，这里再补一次显式断言）────────────
def test_init_db_is_idempotent_and_keeps_tables(ls_engine):
    database.init_db()
    names = set(inspect(ls_engine).get_table_names())
    assert set(LS_TABLES) <= names
    assert set(PREEXISTING_TABLES) <= names


# ── C. 四个数据库级 UNIQUE ──────────────────────────────────────────────
def test_delivery_ls_event_id_is_db_unique(session):
    base = dict(ls_event_id="a2d4dd6c-f570-4089-8255-e6babb691ffe",
                event_name="order_created", object_type="orders", object_id="9569465",
                test_mode=True)
    dup = dict(base, ls_event_id=base["ls_event_id"], object_id="9999999")
    _assert_db_rejects(session, LemonSqueezyWebhookDelivery, base, dup)


def test_purchase_ls_order_id_is_db_unique(session):
    base = dict(ls_order_id="9569465", user_id="u-pack-1", test_mode=True,
                variant_id="2167238", total_cents=499, currency="USD")
    _assert_db_rejects(session, LemonSqueezyPurchase, base, dict(base, user_id="u-pack-2"))


def test_membership_ls_subscription_id_is_db_unique(session):
    base = dict(ls_subscription_id="2556628", user_id="u-sub-1", test_mode=True,
                variant_id="2167193", status="active")
    _assert_db_rejects(session, LemonSqueezyMembership, base, dict(base, user_id="u-sub-2"))


def test_membership_grant_composite_key_is_db_unique(session):
    """同一 (subscription, invoice) 拒绝；同一 subscription 的不同 invoice 必须放行。"""
    base = dict(ls_subscription_id="2556628", ls_invoice_id="8554443",
                user_id="u-sub-1", test_mode=True, billing_reason="initial",
                amount_cents=499, currency="USD")
    _assert_db_rejects(session, LemonSqueezyMembershipGrant, base,
                       dict(base, user_id="u-other", billing_reason="renewal"))

    # 反向：换个 invoice id 就不能被挡住（否则续费永远发不出权益）。
    # 上一行 base（invoice 8554443）此刻仍在表里。
    session.add(LemonSqueezyMembershipGrant(**dict(base, ls_invoice_id="8554444",
                                                   billing_reason="renewal")))
    session.flush()
    session.commit()
    rows = session.query(LemonSqueezyMembershipGrant).filter_by(
        ls_subscription_id="2556628").all()
    assert len(rows) == 2


def test_composite_unique_constraint_is_in_ddl(ls_engine):
    ddl = str(CreateTable(LemonSqueezyMembershipGrant.__table__).compile(ls_engine)).upper()
    assert "UNIQUE" in ddl
    assert "LS_SUBSCRIPTION_ID" in ddl and "LS_INVOICE_ID" in ddl


# ── D. test_mode ────────────────────────────────────────────────────────
@pytest.mark.parametrize("table", LS_TABLES)
def test_test_mode_column_present(ls_engine, table):
    cols = _columns(ls_engine, table)
    assert "test_mode" in cols


def test_test_mode_defaults_to_false_and_distinguishes_test_from_live(session):
    """同一张表里要能明确区分 Test 与 Live，而不是靠分库/分表名。"""
    session.add(LemonSqueezyPurchase(ls_order_id="7000001", user_id="u-a"))       # 默认 False
    session.add(LemonSqueezyPurchase(ls_order_id="7000002", user_id="u-b", test_mode=True))
    session.commit()
    live = session.query(LemonSqueezyPurchase).filter_by(ls_order_id="7000001").one()
    test = session.query(LemonSqueezyPurchase).filter_by(ls_order_id="7000002").one()
    assert live.test_mode is False and test.test_mode is True


# ── E. timestamps ───────────────────────────────────────────────────────
@pytest.mark.parametrize("table", LS_TABLES)
def test_timestamp_columns_present(ls_engine, table):
    assert TIMESTAMP_COLS <= _columns(ls_engine, table)


def test_timestamps_are_populated_on_insert(session):
    session.add(LemonSqueezyWebhookDelivery(ls_event_id="evt-ts-1", event_name="order_created",
                                            object_type="orders"))
    session.commit()
    row = session.query(LemonSqueezyWebhookDelivery).filter_by(ls_event_id="evt-ts-1").one()
    assert row.created_at is not None and row.updated_at is not None


# ── F. 没有 interval ────────────────────────────────────────────────────
def test_membership_table_has_no_interval_column(ls_engine):
    """实测 LS payload 不提供 interval ⇒ 表里也不该有这一列（避免第二个真值源）。"""
    cols = _columns(ls_engine, "lemonsqueezy_memberships")
    assert "interval" not in cols
    assert "credits_per_month" not in cols


def test_no_ls_table_stores_credit_amounts_or_plan_ids(ls_engine):
    """档位/积分真值只在 credits_config；表里不得出现 plan_id / pack_id / credits。"""
    for table in LS_TABLES:
        cols = _columns(ls_engine, table)
        assert not {"plan_id", "pack_id", "credits"} & cols, table


# ── G. 不建 checkout 表 ─────────────────────────────────────────────────
def test_checkouts_table_is_not_created(ls_engine):
    assert "lemonsqueezy_checkouts" not in inspect(ls_engine).get_table_names()


# ── H. 既有 schema 未被破坏 ─────────────────────────────────────────────
@pytest.mark.parametrize("table", PREEXISTING_TABLES)
def test_preexisting_tables_still_exist(ls_engine, table):
    assert table in inspect(ls_engine).get_table_names()


def test_paddle_and_membership_key_columns_unchanged(ls_engine):
    """关键列名逐个点名：改名/删列会在这里断掉，而不是在生产 webhook 上。"""
    assert "paddle_transaction_id" in _columns(ls_engine, "credit_pack_purchases")
    assert "paddle_event_id" in _columns(ls_engine, "credit_pack_purchases")
    assert "paddle_price_id" in _columns(ls_engine, "credit_pack_purchases")
    assert "paddle_subscription_id" in _columns(ls_engine, "user_memberships")
    assert "last_granted_period_start" in _columns(ls_engine, "user_memberships")
    assert "interval" in _columns(ls_engine, "user_memberships")   # Paddle 侧照旧保留
    assert "paddle_customer_id" in _columns(ls_engine, "paddle_customers")
    assert "balance" in _columns(ls_engine, "user_credits")


def test_no_foreign_keys_on_lemonsqueezy_tables(ls_engine):
    for table in LS_TABLES:
        assert inspect(ls_engine).get_foreign_keys(table) == []


def test_database_py_change_is_append_only():
    """git 证据：本阶段对 database.py 只允许"追加模型 + 改一行 import"。

    任何对既有列/表的删改都会以"被删除行"的形式出现在 diff 里，这里逐行检查。
    """
    proc = subprocess.run(["git", "diff", "--unified=0", "--", "app/db/database.py"],
                          cwd=str(__import__("pathlib").Path(database.__file__).parents[2]),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        pytest.skip("git 不可用，无法做 append-only 检查")
    removed = [ln[1:].strip() for ln in proc.stdout.splitlines()
               if ln.startswith("-") and not ln.startswith("---")]
    unexpected = [ln for ln in removed if ln and "import" not in ln]
    assert not unexpected, f"database.py 出现非 import 的删除行：{unexpected}"
