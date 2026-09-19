"""Credits 服务单元测试 —— 临时 SQLite，全 mock，不碰真实 Supabase/余额。"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.services import credits_service


@pytest.fixture(autouse=True)
def _temp_db(monkeypatch, tmp_path):
    """把 credits_service.SessionLocal 指向临时 SQLite，并建表。"""
    eng = create_engine(f"sqlite:///{tmp_path/'credits_test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    Session = sessionmaker(bind=eng)
    monkeypatch.setattr(credits_service, "SessionLocal", Session)
    yield


def test_welcome_bonus_once():
    u = "u1"
    r1 = credits_service.claim_welcome_bonus(u)
    assert r1["success"] is True and r1["balance"] == 50
    r2 = credits_service.claim_welcome_bonus(u)
    assert r2["success"] is False and r2["already_claimed"] is True
    assert credits_service.get_balance(u) == 50


def test_email_bonus_once():
    u = "u2"
    assert credits_service.claim_email_verification_bonus(u)["success"] is True
    assert credits_service.claim_email_verification_bonus(u)["already_claimed"] is True
    assert credits_service.get_balance(u) == 25


def test_first_song_bonus_once():
    u = "u3"
    assert credits_service.claim_first_song_bonus(u)["success"] is True
    assert credits_service.claim_first_song_bonus(u)["already_claimed"] is True
    assert credits_service.get_balance(u) == 25


def test_consume_and_refund():
    u = "u4"
    credits_service.claim_welcome_bonus(u)  # 50
    r = credits_service.consume_credits(u, 30, reference_id="task-1")
    assert r["success"] is True and r["balance"] == 20
    rr = credits_service.refund_credits(u, 30, reference_id="task-1")
    assert rr["success"] is True and rr["balance"] == 50


def test_insufficient_balance_rejected():
    u = "u5"
    credits_service.claim_email_verification_bonus(u)  # 25
    r = credits_service.consume_credits(u, 30)
    assert r["success"] is False and "余额不足" in r["error"]
    assert credits_service.get_balance(u) == 25


def test_no_negative_balance_after_failed_consume():
    u = "u6"
    credits_service.claim_email_verification_bonus(u)  # 25
    for _ in range(3):
        credits_service.consume_credits(u, 20)  # 每次 20，第三次会失败
    assert credits_service.get_balance(u) >= 0  # 永不负数（要么扣成 0 后失败）


def test_add_credits_and_ledger():
    u = "u7"
    credits_service.add_credits(u, 100, "welcome_bonus")
    assert credits_service.get_balance(u) == 100


def test_summary():
    u = "u8"
    credits_service.claim_welcome_bonus(u)
    s = credits_service.get_credit_summary(u)
    assert s["balance"] == 50 and s["welcome_bonus_claimed"] is True
    assert s["email_verification_bonus_claimed"] is False