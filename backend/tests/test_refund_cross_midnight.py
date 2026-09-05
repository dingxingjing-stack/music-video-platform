"""P0-4 Phase 5-C —— 跨午夜退款一致性修复验证。

独立确认 refund_generation 在跨日期/跨月份的「跨午夜」边界下，
generation_usage 与 beta_users 同步扣减，无部分退款。
"""
import os
import pytest

from app.services import ai_limits, task_store


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "midnight.db")
    monkeypatch.setattr(ai_limits, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(ai_limits, "_DB_PATH", db_path)
    monkeypatch.setattr(task_store, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(task_store, "_DB_PATH", db_path)
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")
    return db_path


def _read(user_id):
    sess = ai_limits._get_session()
    try:
        from sqlalchemy import text
        gen = sess.execute(
            text("SELECT date, daily_count, month_key, monthly_count FROM generation_usage WHERE user_id=:u"),
            {"u": user_id},
        ).fetchone()
        beta = sess.execute(
            text("SELECT daily_credits_used FROM beta_users WHERE user_id=:u"), {"u": user_id}
        ).fetchone()
        return gen, (beta[0] if beta else 0)
    finally:
        sess.close()


def test_refund_cross_midnight_is_consistent(isolated_db, monkeypatch):
    """reserve 在午夜前、refund 在午夜后，二者必须都正确扣减（不丢部分）。"""
    u = "u-cross"
    orig_today = ai_limits._today
    orig_month = ai_limits._month_key

    # 1) reserve 在「旧日期」
    monkeypatch.setattr(ai_limits, "_today", lambda: "2026-09-01")
    monkeypatch.setattr(ai_limits, "_month_key", lambda: "2026-09")
    assert ai_limits.reserve_generation(u, duration=60)["success"] is True
    gen1, beta1 = _read(u)
    assert gen1 == ("2026-09-01", 1, "2026-09", 1)
    assert beta1 == 1

    # 2) 跨日到「新日期」，执行退款
    monkeypatch.setattr(ai_limits, "_today", lambda: "2026-09-02")
    monkeypatch.setattr(ai_limits, "_month_key", lambda: "2026-09")
    res = ai_limits.refund_generation(u, duration=60, reason="provider_failed")
    assert res["success"] is True and res["refunded"] is True

    # 3) 修复后：generation 与 beta 都被扣回
    gen2, beta2 = _read(u)
    assert gen2[1] == 0, f"daily_count 应为 0，实际 {gen2[1]}"
    assert gen2[3] == 0, f"monthly_count 应为 0，实际 {gen2[3]}"
    assert beta2 == 0, f"beta daily_credits_used 应为 0，实际 {beta2}"


def test_refund_cross_month_is_consistent(isolated_db, monkeypatch):
    """reserve/退款跨月时同样一致性。"""
    u = "u-cross-month"
    monkeypatch.setattr(ai_limits, "_today", lambda: "2026-09-30")
    monkeypatch.setattr(ai_limits, "_month_key", lambda: "2026-09")
    assert ai_limits.reserve_generation(u, duration=180)["success"] is True  # weight=2
    gen1, beta1 = _read(u)
    assert gen1[3] == 2 and beta1 == 2  # monthly=2, credits=2

    # 跨到十月
    monkeypatch.setattr(ai_limits, "_today", lambda: "2026-10-01")
    monkeypatch.setattr(ai_limits, "_month_key", lambda: "2026-10")
    res = ai_limits.refund_generation(u, duration=180, reason="provider_failed")
    assert res["refunded"] is True

    gen2, beta2 = _read(u)
    assert gen2[1] == 0 and gen2[3] == 0, f"跨月 refund daily/monthly 应为 0，实际 {gen2}"
    assert beta2 == 0, f"beta 应为 0，实际 {beta2}"


def test_refund_repeat_cross_midnight_no_negative(isolated_db, monkeypatch):
    """跨午夜多轮 reserve+refund 后，永远不为负值。"""
    u = "u-cross-multi"
    monkeypatch.setattr(ai_limits, "_today", lambda: "2026-09-30")
    monkeypatch.setattr(ai_limits, "_month_key", lambda: "2026-09")
    assert ai_limits.reserve_generation(u, duration=60)["success"] is True

    # 跨日 refund 两次
    monkeypatch.setattr(ai_limits, "_today", lambda: "2026-10-01")
    monkeypatch.setattr(ai_limits, "_month_key", lambda: "2026-10")
    ai_limits.refund_generation(u, duration=60, reason="provider_failed")  # 第 1 次
    ai_limits.refund_generation(u, duration=60, reason="provider_failed")  # 第 2 次再退（幂等，不为负）

    gen2, beta2 = _read(u)
    assert gen2[1] >= 0 and gen2[3] >= 0 and beta2 >= 0, f"出现负值 gen={gen2} beta={beta2}"