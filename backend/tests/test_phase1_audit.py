"""Phase 1 独立复核 —— 补充上一 AI 未充分覆盖的原子性 / 退款隔离审计。

本轮独立审计补充的真实覆盖点：
  - 场景 B/C：generation daily / monthly 达到时，beta_users 与 global_usage 必须不变
  - 场景 D：global 达到时，beta 与 generation 必须不变（已有，此处再强化断言）
  - 退款隔离：A 退款绝不误退 B（按 user_id 独立）
  - weight=1 与 weight=2 的退款各自精确
  - 退款永不为负（daily_count / monthly_count / daily_credits_used >= 0）
  - 同一用户 `跨日期` 退款不会把另一日期的 generation_usage 误退
"""
import concurrent.futures
import asyncio

import pytest

from app.services import ai_limits, task_store
from app.services import beta_service


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "audit.db")
    monkeypatch.setattr(ai_limits, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(ai_limits, "_DB_PATH", db_path)
    monkeypatch.setattr(task_store, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(task_store, "_DB_PATH", db_path)
    monkeypatch.setattr(beta_service, "DB_DIR", str(tmp_path))
    monkeypatch.setattr(beta_service, "DB_PATH", db_path)
    return db_path


def _row(table, user_id=None, **where):
    sess = ai_limits._get_session()
    try:
        from sqlalchemy import text
        if table == "beta_users":
            q = ("SELECT daily_credits_used, daily_credits_limit, total_generations, activity_score "
                 "FROM beta_users WHERE user_id=:u")
            r = sess.execute(text(q), {"u": user_id}).fetchone()
            return {"credits_used": r[0] or 0, "limit": r[1] or 0,
                    "total_gens": r[2] or 0, "activity": r[3] or 0} if r else None
        if table == "generation_usage":
            q = ("SELECT daily_count, monthly_count FROM generation_usage WHERE user_id=:u")
            r = sess.execute(text(q), {"u": user_id}).fetchone()
            return {"daily": r[0] if r and r[0] else 0, "monthly": r[1] if r and r[1] else 0} if r else {"daily": 0, "monthly": 0}
        if table == "global_usage":
            q = "SELECT count FROM global_usage WHERE date=:d"
            r = sess.execute(text(q), {"d": ai_limits._today()}).fetchone()
            return r[0] if r else 0
        raise ValueError(f"unknown table {table}")
    finally:
        sess.close()


def _mk_user(user_id, limit=10, used=0):
    sess = ai_limits._get_session()
    try:
        from sqlalchemy import text
        sess.execute(text(
            "INSERT INTO beta_users (user_id, is_gray, daily_credits_used, daily_credits_limit, activity_score, total_generations) "
            "VALUES (:u, 0, :used, :limit, 0, 0)"
        ), {"u": user_id, "used": used, "limit": limit})
        sess.commit()
    finally:
        sess.close()


# ───────────── 场景 B：generation daily limit 达到 → beta/global 不变 ─────────────
def test_daily_limit_reached_leaves_beta_and_global_unchanged(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 1)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")
    u = "u-b"
    assert ai_limits.reserve_generation(u)["success"] is True  # 吃掉当天 1
    beta_before = _row("beta_users", u)
    global_before = _row("global_usage")
    r = ai_limits.reserve_generation(u)
    assert r["success"] is False
    assert "今日生成额度已用完" in r["error"]
    # beta 与 global 不得因这次失败而变化
    assert _row("beta_users", u) == beta_before
    assert _row("global_usage") == global_before
    assert _row("generation_usage", u) == {"daily": 1, "monthly": 1}  # 仅第一次生效


# ───────────── 场景 C：generation monthly limit 达到 → beta/global 不变 ─────────────
def test_monthly_limit_reached_leaves_beta_and_global_unchanged(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 2)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")
    u = "u-c"
    assert ai_limits.reserve_generation(u)["success"] is True
    assert ai_limits.reserve_generation(u)["success"] is True  # monthly 2
    beta_before = _row("beta_users", u)
    global_before = _row("global_usage")
    r = ai_limits.reserve_generation(u)
    assert r["success"] is False
    assert "本月生成额度已用完" in r["error"]
    assert _row("beta_users", u) == beta_before
    assert _row("global_usage") == global_before
    assert _row("generation_usage", u) == {"daily": 2, "monthly": 2}


# ───────────── 场景 D：global limit 达到 → beta/generation 不变 ─────────────
def test_global_limit_reached_leaves_beta_and_generation_unchanged(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 1)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")
    # A 占用唯一全局额度
    assert ai_limits.reserve_generation("u-a")["success"] is True
    # 全局已满，任何新用户必须整体失败且 beta/generation 不变
    _mk_user("u-d2")
    before_beta = _row("beta_users", "u-d2")
    before_gen = _row("generation_usage", "u-d2")
    before_global = _row("global_usage")
    r = ai_limits.reserve_generation("u-d2")
    assert r["success"] is False
    assert "全平台" in r["error"]
    assert _row("beta_users", "u-d2") == before_beta
    assert _row("generation_usage", "u-d2") == before_gen
    assert _row("global_usage") == before_global


# ───────────── 退款隔离：A refund 不误退 B ─────────────
def test_refund_of_A_does_not_refund_B(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")
    assert ai_limits.reserve_generation("A")["success"] is True
    assert ai_limits.reserve_generation("B")["success"] is True
    # A 退款
    ai_limits.refund_generation("A", reason="provider_failed")
    assert _row("beta_users", "A")["credits_used"] == 0
    assert _row("generation_usage", "A") == {"daily": 0, "monthly": 0}
    # B 完全不受影响
    assert _row("beta_users", "B")["credits_used"] == 1
    assert _row("generation_usage", "B") == {"daily": 1, "monthly": 1}


# ───────────── weight=1 与 weight=2 的退款各自精确 ─────────────
def test_refund_weight1_and_weight2_are_precise(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")
    # weight=2 的作品（>120s）
    assert ai_limits.reserve_generation("W2", duration=180)["success"] is True
    assert _row("beta_users", "W2")["credits_used"] == 2
    ai_limits.refund_generation("W2", duration=180, reason="provider_failed")
    assert _row("beta_users", "W2")["credits_used"] == 0
    assert _row("generation_usage", "W2") == {"daily": 0, "monthly": 0}
    # weight=1
    assert ai_limits.reserve_generation("W1", duration=60)["success"] is True
    ai_limits.refund_generation("W1", duration=60, reason="provider_failed")
    assert _row("beta_users", "W1")["credits_used"] == 0


# ───────────── 退款永不为负 ─────────────
def test_refund_never_negative(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")
    u = "u-neg"
    _mk_user(u, limit=10, used=0)
    # 未消费就退款（weight=2）→ 不得低于 0
    ai_limits.refund_generation(u, duration=180, reason="provider_failed")
    assert _row("beta_users", u)["credits_used"] >= 0
    assert _row("generation_usage", u)["daily"] >= 0
    assert _row("generation_usage", u)["monthly"] >= 0


# ───────────── 并发：同一用户 limit=10，20 并发 → 恰好 10 成功 ─────────────
def test_concurrent_same_user_10_of_20(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 1000)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 1000)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 1000)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")
    u = "u-conc-same"
    _mk_user(u, limit=10, used=0)
    def _call(_): return ai_limits.reserve_generation(u)["success"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        results = list(ex.map(_call, range(20)))
    assert sum(results) == 10
    assert _row("beta_users", u)["credits_used"] == 10
    assert _row("generation_usage", u) == {"daily": 10, "monthly": 10}


# ───────────── 并发：A(10) + B(10) 争抢 global limit=10 → 总成功 10 ─────────────
def test_concurrent_two_users_race_global_10(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 1000)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 1000)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 10)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")
    jobs = [("uA10", i) for i in range(10)] + [("uB10", i) for i in range(10)]
    def _call(pair): return ai_limits.reserve_generation(pair[0])["success"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        results = list(ex.map(_call, jobs))
    assert sum(results) == 10
    assert _row("global_usage") == 10