"""Phase 4.2（一次性充值制）— Credits 余额/充值/扣费/退款 场景测试。

对应产品裁定：docs/CREDITS_REFUND_RULES.md v1.0 + 2026-10-03 充值制授权。
场景编号对应实施指令 §23（A–K）。

覆盖策略：
- A/B/C（充值/重复充值/多档）：credits_service.add_credits（LS 履约的实际入账调用点）。
- D/E（重复 webhook/支付失败）：由 tests/test_lemon_squeezy_credit_pack.py 既有
  14+ 用例覆盖（duplicate delivery / 非 paid status IGNORED / 金额不符 REJECTED）；
  本文件补 LemonSqueezyPurchase.ls_order_id UNIQUE 的库级断言。
- F/G（余额不足/正常扣除）、H/I（退款/退款幂等）：credits_service 直测。
- J（并发扣除）：双线程同时扣 30，恰一成功，余额不为负。
- K（长期余额）：源级断言（credits 层无 expires/清零逻辑）+ 余额稳定。

全部临时 SQLite：不触真实 API/DB/支付。
"""
from __future__ import annotations

import inspect
import threading

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.services import credits_config, credits_service
from app.services.credits_service import (
    add_credits,
    consume_credits,
    refund_generation_credits,
    reserve_generation_credits,
)

USER = "payg-user"


@pytest.fixture()
def cdb(tmp_path, monkeypatch):
    """隔离 credits 存储（临时 SQLite），并建全部表。"""
    eng = create_engine(
        f"sqlite:///{tmp_path / 'payg.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=eng)
    monkeypatch.setattr(credits_service, "SessionLocal", sessionmaker(bind=eng))
    return eng


# ── 定价真值绑定（CREDIT_COSTS 与产品裁定 2026-10-03 一致）─────────────────

def test_credit_costs_match_product_decision():
    cc = credits_config.CREDIT_COSTS
    expected = {
        "standard_song": 30,
        "cover_song": 120,
        "stem_separation": 60,          # Stems V2
        "stem_separation_v3": 30,       # Stems V3
        "stem_separation_v1": 15,       # 预留（NOT_WIRED）
        "song_extend": 30,              # 预留（NOT_WIRED）
        "remix": 60,                    # 预留（NOT_WIRED）
        "song_identification": 10,      # 预留（NOT_WIRED）
        "song_analysis": 15,            # 预留（NOT_WIRED）
        "music_transcription": 40,      # 预留（NOT_WIRED）
    }
    for k, v in expected.items():
        assert cc[k]["credit_cost"] == v, f"{k} 应为 {v}"
        assert cc[k]["enabled"] is True


def test_cover_fail_closed_is_lifted():
    """Cover=120 → get_credit_cost 返回 120（503 cover_not_priced 解除）。"""
    assert credits_config.get_credit_cost("cover_song") == 120


def test_midi_stays_fail_closed():
    """MIDI 保持 0 = 未定价 → 端点 503 fail-closed 不变。"""
    assert credits_config.get_credit_cost("midi") is None


# ── A/B/C：充值（add_credits = LS 履约的实际入账调用点）────────────────────

def test_a_single_pack_purchase(cdb):
    add_credits(USER, 200, "purchase", reference_id="ls:order:o-pack200-1")
    assert credits_service.get_balance(USER) == 200


def test_b_repeat_purchase_same_pack(cdb):
    add_credits(USER, 200, "purchase", reference_id="ls:order:o-b1")
    add_credits(USER, 200, "purchase", reference_id="ls:order:o-b2")
    assert credits_service.get_balance(USER) == 400


def test_c_multi_tier_purchases(cdb):
    for ref, amount in (("ls:o-c1", 200), ("ls:o-c2", 500),
                        ("ls:o-c3", 1200), ("ls:o-c4", 2800)):
        add_credits(USER, amount, "purchase", reference_id=ref)
    assert credits_service.get_balance(USER) == 4700


# ── D 库级幂等：ls_order_id UNIQUE ────────────────────────────────────────

def test_d_ls_order_id_unique_constraint(cdb):
    """LemonSqueezyPurchase.ls_order_id 有 UNIQUE —— 同一 order 第二次插入必须 IntegrityError。"""
    from sqlalchemy.exc import IntegrityError

    from app.db.database import SessionLocal as _  # noqa: F401 确认模块可用
    from app.services import lemon_squeezy_service as lss
    LemonSqueezyPurchase = lss.LemonSqueezyPurchase
    sess = sessionmaker(bind=cdb)()
    sess.add(LemonSqueezyPurchase(ls_order_id="ord-dup-1", user_id=USER))
    sess.commit()
    sess.add(LemonSqueezyPurchase(ls_order_id="ord-dup-1", user_id=USER))
    try:
        sess.commit()
        raised = False
    except IntegrityError:
        sess.rollback()
        raised = True
    assert raised, "同 ls_order_id 第二次插入必须触发 UNIQUE IntegrityError"


# ── F/G：余额不足 / 正常扣除 ─────────────────────────────────────────────

def test_f_insufficient_balance_rejects_and_stays(cdb):
    add_credits(USER, 20, "purchase", reference_id="ls:o-f1")
    r = consume_credits(USER, 30, reference_id="task-f")
    assert r["success"] is False
    assert r["balance"] == 20          # 不扣成负数、不部分扣除


def test_g_normal_deduction(cdb):
    add_credits(USER, 100, "purchase", reference_id="ls:o-g1")
    r = consume_credits(USER, 30, reference_id="task-g")
    assert r["success"] is True and r["balance"] == 70


# ── H/I：失败退款 + 退款幂等 ─────────────────────────────────────────────

def test_h_failure_refund_restores_full_amount(cdb):
    add_credits(USER, 100, "purchase", reference_id="ls:o-h1")
    assert consume_credits(USER, 30, reference_id="task-h")["balance"] == 70
    r = refund_generation_credits(USER, "task-h")
    assert r["success"] is True
    assert credits_service.get_balance(USER) == 100


def test_i_refund_is_idempotent(cdb):
    add_credits(USER, 100, "purchase", reference_id="ls:o-i1")
    consume_credits(USER, 30, reference_id="task-i")
    r1 = refund_generation_credits(USER, "task-i")
    r2 = refund_generation_credits(USER, "task-i")
    r3 = refund_generation_credits(USER, "task-i")
    assert r1.get("already_refunded") is not True   # 第一次真实退款
    assert r2.get("already_refunded") is True       # 之后全部幂等跳过
    assert r3.get("already_refunded") is True
    assert credits_service.get_balance(USER) == 100  # 只退了一次


# ── J：并发扣除（原子性）────────────────────────────────────────────────

def test_j_concurrent_deduction_no_negative_balance(cdb):
    add_credits(USER, 30, "purchase", reference_id="ls:o-j")
    results = []
    barrier = threading.Barrier(2)

    def worker():
        barrier.wait()
        results.append(consume_credits(USER, 30, reference_id=f"task-{threading.get_ident()}"))

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start(); t2.start(); t1.join(); t2.join()

    ok = [r for r in results if r["success"]]
    assert len(ok) == 1, f"并发 30/30 只能恰一成功，实际 {results}"
    assert credits_service.get_balance(USER) == 0
    # 底层条件 UPDATE（WHERE balance >= :neg）保证永远不会出现负数
    src = inspect.getsource(credits_service)
    assert "balance >= :neg" in src or "balance >= :neg" in inspect.getsource(
        credits_service._apply
    )


# ── K：长期余额（无过期/无清零）──────────────────────────────────────────

def test_k_no_expiration_logic_in_credits_layer():
    """Credits 层不得存在 expires/expiry/月度清零逻辑（一次性充值制核心约束）。"""
    src_cs = inspect.getsource(credits_service)
    src_cc = inspect.getsource(credits_config)
    for banned in ("expires_at", "expiry", "monthly_reset", "rollover", "clear_expired"):
        assert banned not in src_cs, f"credits_service 不得包含 {banned}"
        assert banned not in src_cc, f"credits_config 不得包含 {banned}"


def test_k_balance_is_stable_over_time(cdb):
    add_credits(USER, 500, "purchase", reference_id="ls:o-k")
    before = credits_service.get_balance(USER)
    after = credits_service.get_balance(USER)   # 无任何时间触发的扣减路径
    assert before == after == 500
