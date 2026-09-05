"""P0-4 统一额度预留 —— 原子性 / 并发 / 退款 / 灰度权益 测试。

验证单一权威路径 reserve_generation 在**一个数据库事务**内覆盖：
  1. beta_users 每日 credits（权威限额来源 = beta_users.daily_credits_limit）
  2. generation_usage 每日生成数
  3. generation_usage 每月生成数
  4. global_usage 全平台硬停

并发正确性依赖数据库语义（原子条件更新 + PG 行级锁），不依赖 threading.Lock。
"""
import concurrent.futures
import asyncio

import pytest

from app.services import ai_limits, task_store
from app.services import beta_service


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """每个测试独立 SQLite，避免污染 backend/data/beta.db。"""
    db_path = str(tmp_path / "unified.db")
    monkeypatch.setattr(ai_limits, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(ai_limits, "_DB_PATH", db_path)
    monkeypatch.setattr(task_store, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(task_store, "_DB_PATH", db_path)
    monkeypatch.setattr(beta_service, "DB_DIR", str(tmp_path))
    monkeypatch.setattr(beta_service, "DB_PATH", db_path)
    return db_path


def _wide_user_limits(monkeypatch):
    """放开单用户日/月与全局，专注测试 beta_users 每日 credits（10）/ 灰度（30）。"""
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 1000)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 1000)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 1000)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")


def _beta_used(user_id: str) -> int:
    sess = ai_limits._get_session()
    try:
        from sqlalchemy import text
        row = sess.execute(text("SELECT daily_credits_used FROM beta_users WHERE user_id=:u"), {"u": user_id}).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    finally:
        sess.close()


def _beta_limit(user_id: str) -> int:
    sess = ai_limits._get_session()
    try:
        from sqlalchemy import text
        row = sess.execute(text("SELECT daily_credits_limit FROM beta_users WHERE user_id=:u"), {"u": user_id}).fetchone()
        return int(row[0]) if row and row[0] is not None else ai_limits.DAILY_LIMIT_NORMAL
    finally:
        sess.close()


def _global_count() -> int:
    sess = ai_limits._get_session()
    try:
        from sqlalchemy import text
        row = sess.execute(text("SELECT count FROM global_usage WHERE date=:d"), {"d": ai_limits._today()}).fetchone()
        return int(row[0]) if row else 0
    finally:
        sess.close()


def _gen_usage(user_id: str) -> dict:
    sess = ai_limits._get_session()
    try:
        from sqlalchemy import text
        row = sess.execute(text(
            "SELECT daily_count, monthly_count FROM generation_usage WHERE user_id=:u"
        ), {"u": user_id}).fetchone()
        return {"daily": int(row[0]) if row and row[0] else 0,
                "monthly": int(row[1]) if row and row[1] else 0}
    finally:
        sess.close()


# ───────────────────────────── 统一额度：limit=10 ─────────────────────────────
def test_limit_10_first_10_succeed_11th_fails(isolated_db, monkeypatch):
    """beta_users 每日 credits=10：前 10 次成功，第 11 次失败。"""
    _wide_user_limits(monkeypatch)
    u = "u-lim10"
    for _ in range(10):
        assert ai_limits.reserve_generation(u)["success"] is True
    r11 = ai_limits.reserve_generation(u)
    assert r11["success"] is False
    assert "今日" in r11["error"]
    # 11 次失败后无任何残留：beta 恒为 10、日/月|全局计数不变
    assert _beta_used(u) == 10
    assert _gen_usage(u) == {"daily": 10, "monthly": 10}
    assert _global_count() == 10


# ─────────────────────────── 跨端点共享额度 ───────────────────────────
def test_cross_endpoint_shared_quota(isolated_db, monkeypatch):
    """不同端点（generate / workflow / heartmula）都走 reserve_generation → 共享同一额度。"""
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 2)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")
    u = "u-shared"

    # /generate 入口预留
    assert ai_limits.reserve_generation(u, duration=60)["success"] is True
    # workflow 入口（real 模式）预留
    assert ai_limits.reserve_generation(u, duration=60)["success"] is True
    # heartmula 入口预留 —— 日生成数已到 2 上限
    r = ai_limits.reserve_generation(u, duration=60)
    assert r["success"] is False
    assert "今日生成额度已用完" in r["error"]
    # 三入口共享同一 generation_usage 日计数
    assert _gen_usage(u)["daily"] == 2


# ─────────────────────────── Beta 权益反映 ───────────────────────────
def test_beta_entitlement_reflected_in_return(isolated_db, monkeypatch):
    """reserve_generation 成功返回反映 beta 权益：credits_used / limit / is_gray。"""
    _wide_user_limits(monkeypatch)
    r = ai_limits.reserve_generation("u-entl", duration=240)  # >120s → weight=2
    assert r["success"] is True
    assert r["weight"] == 2
    assert r["beta_credits_used"] == 2
    assert r["beta_credits_limit"] == ai_limits.DAILY_LIMIT_NORMAL
    assert r["is_gray"] is False


def test_gray_entitlement_higher_credits(isolated_db, monkeypatch):
    """灰度用户 daily_credits_limit=30 可同样成功；权威限额来自数据库行，非硬编码 10。"""
    _wide_user_limits(monkeypatch)
    u = "u-gray"
    # 模拟灰度用户：limit=30, is_gray=1
    sess = ai_limits._get_session()
    try:
        from sqlalchemy import text
        sess.execute(text(
            "INSERT INTO beta_users (user_id, is_gray, daily_credits_used, daily_credits_limit) "
            "VALUES (:u, 1, 0, 30)"
        ), {"u": u})
        sess.commit()
    finally:
        sess.close()
    assert _beta_limit(u) == 30
    assert _beta_used(u) == 0
    # 灰度可连续消耗远超普通 10 的额度
    for _ in range(20):
        r = ai_limits.reserve_generation(u)
        assert r["success"] is True
    assert _beta_used(u) == 20
    assert _beta_limit(u) == 30


# ─────────────────────────── 并发（DB 语义，非 threading.Lock）──────────────────────────
def test_concurrent_20_with_global_limit_10(isolated_db, monkeypatch):
    """20 个不同用户并发、全局 limit 10 → 恰好 10 成功 / 10 失败（原子条件自增）。"""
    _wide_user_limits(monkeypatch)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 10)

    def _call(i):
        return ai_limits.reserve_generation(f"conc-global-{i}")["success"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        results = list(ex.map(_call, range(20)))
    assert sum(results) == 10
    assert _global_count() == 10


def test_concurrent_per_user_beta_limit_10_exact(isolated_db, monkeypatch):
    """同一用户、beta credits=10、20 线程并发 → 恰好 10 成功 / 10 失败（单条条件 UPDATE 原子）。"""
    _wide_user_limits(monkeypatch)
    u = "u-conc"
    # 预置 beta 行 limit=10
    sess = ai_limits._get_session()
    try:
        from sqlalchemy import text
        sess.execute(text(
            "INSERT INTO beta_users (user_id, is_gray, daily_credits_used, daily_credits_limit, activity_score, total_generations) "
            "VALUES (:u, 0, 0, 10, 0, 0)"
        ), {"u": u})
        sess.commit()
    finally:
        sess.close()

    def _call(_i):
        return ai_limits.reserve_generation(u)["success"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        results = list(ex.map(_call, range(20)))
    assert sum(results) == 10
    assert _beta_used(u) == 10
    assert _gen_usage(u)["daily"] == 10


def test_concurrent_beta_never_exceeds_limit(isolated_db, monkeypatch):
    """极端并发下与 beta_service.consume_credit 共享同表，daily_credits_used 永不超过 limit。"""
    _wide_user_limits(monkeypatch)
    u = "u-conc2"
    sess = ai_limits._get_session()
    try:
        from sqlalchemy import text
        sess.execute(text(
            "INSERT INTO beta_users (user_id, is_gray, daily_credits_used, daily_credits_limit, activity_score, total_generations) "
            "VALUES (:u, 0, 0, 5, 0, 0)"
        ), {"u": u})
        sess.commit()
    finally:
        sess.close()

    def _call(_i):
        return ai_limits.reserve_generation(u)["success"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(_call, range(15)))
    assert sum(results) == 5
    assert _beta_used(u) <= 5


# ─────────────────────────── 事务回滚：无部分消费残留 ───────────────────────────
def test_reserve_rollback_no_partial_state_on_commit_failure(isolated_db, monkeypatch):
    """在完成三次扣减后强制 commit 抛错 → 数据库事务整体回滚，无部分消费残留。

    模拟”持久化失败“（provider 已成功但数据库写失败）后，beta/generation/global
    三者必须全部保持未消费，绝不能只回滚其中一两个。
    """
    _wide_user_limits(monkeypatch)
    u = "u-rollback"

    # 拦截 _get_session 返回的 Session：让 commit 抛异常，模拟中途/提交时失败
    orig_get_session = ai_limits._get_session

    def _patched():
        s = orig_get_session()
        orig_commit = s.commit
        def _commit(*a, **k):
            _raise = RuntimeError("simulated db persistence failure at commit")
            try:
                s.rollback()
            except Exception:
                pass
            raise _raise
        s.commit = _commit
        return s

    monkeypatch.setattr(ai_limits, "_get_session", _patched)

    r = ai_limits.reserve_generation(u)
    assert r["success"] is False
    # 仅恢复 _get_session（勿用 undo()，否则会连 fixture 的隔离 DB 路径一起还原）
    monkeypatch.setattr(ai_limits, "_get_session", orig_get_session)

    # 无部分消费残留：beta 未扣、日/月未加、全局未加
    assert _beta_used(u) == 0
    assert _gen_usage(u) == {"daily": 0, "monthly": 0}
    assert _global_count() == 0
    # 后续正常可继续预留
    assert ai_limits.reserve_generation(u)["success"] is True


def test_reserve_failure_at_global_cap_rolls_back_user(isolated_db, monkeypatch):
    """全局硬停已满、某用户被拒 → 该用户 beta/generation 均无部分消费（整事务回滚）。"""
    _wide_user_limits(monkeypatch)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 1)
    # 用户 A 占用唯一全局额度
    assert ai_limits.reserve_generation("u-a")["success"] is True

    # 用户 B 达到全局上限 -> 整体回滚，B 不得有任何部分消费
    r = ai_limits.reserve_generation("u-b")
    assert r["success"] is False
    assert _beta_used("u-b") == 0
    assert _gen_usage("u-b") == {"daily": 0, "monthly": 0}
    assert _global_count() == 1  # 仍由 A 单独占用


# ─────────────────────────── 退款语义 ───────────────────────────
def test_refund_provider_explicit_fail(isolated_db, monkeypatch):
    """provider 明确失败 → 回滚用户 beta + generation 额度。"""
    _wide_user_limits(monkeypatch)
    u = "u-refund-pf"
    assert ai_limits.reserve_generation(u)["success"] is True
    assert _beta_used(u) == 1
    res = ai_limits.refund_generation(u, reason="provider_failed")
    assert res["success"] is True and res["refunded"] is True
    assert _beta_used(u) == 0
    assert _gen_usage(u) == {"daily": 0, "monthly": 0}


def test_refund_request_not_sent(isolated_db, monkeypatch):
    """provider 请求确定未发送 → 回滚用户预留。"""
    _wide_user_limits(monkeypatch)
    u = "u-refund-rns"
    assert ai_limits.reserve_generation(u, duration=60)["success"] is True
    res = ai_limits.refund_generation(u, duration=60, reason="request_not_sent")
    assert res["success"] is True and res["refunded"] is True
    assert _beta_used(u) == 0
    assert _gen_usage(u) == {"daily": 0, "monthly": 0}
    # global_usage 永不退款（成本保护硬停）
    assert _global_count() == 1


def test_refund_timeout_unknown_no_refund(isolated_db, monkeypatch):
    """超时/未知结果 → 请求可能已发送 → **不退款**，防免费生成漏洞。"""
    _wide_user_limits(monkeypatch)
    u = "u-refund-unk"
    assert ai_limits.reserve_generation(u)["success"] is True
    res = ai_limits.refund_generation(u, reason="timeout_unknown")
    assert res["success"] is False and res["refunded"] is False
    assert _beta_used(u) == 1  # 未退回
    assert _gen_usage(u)["daily"] == 1


def test_refund_persistence_failure_no_refund(isolated_db, monkeypatch):
    """provider 成功但后续持久化失败 → 可能已产生真实成本 → **不退款**。"""
    _wide_user_limits(monkeypatch)
    u = "u-refund-persist"
    assert ai_limits.reserve_generation(u)["success"] is True
    res = ai_limits.refund_generation(u, reason="persistence_failed")
    assert res["success"] is False and res["refunded"] is False
    assert _beta_used(u) == 1
    assert _gen_usage(u)["daily"] == 1


def test_refund_provider_failed_does_not_touch_global(isolated_db, monkeypatch):
    """退款永远不退还 global_usage —— 成本保护只增不减。"""
    _wide_user_limits(monkeypatch)
    u = "u-refund-global"
    assert ai_limits.reserve_generation(u)["success"] is True
    before = _global_count()
    assert before == 1
    ai_limits.refund_generation(u, reason="provider_failed")
    after = _global_count()
    assert after == before  # 保持不变


# ─────────────────────────── 无前端二次计费 ───────────────────────────
def test_generation_requires_no_frontend_consume_credit(isolated_db, monkeypatch):
    """单个真实生成只走 reserve_generation；不要求前端额外调用 consume-credit。"""
    _wide_user_limits(monkeypatch)
    u = "u-frontend"

    # 一次真实生成 = 一次 reserve_generation（/ai/generate、workflow、heartmula 均如此）
    r = ai_limits.reserve_generation(u, duration=60)
    assert r["success"] is True
    # 若前端再去 /beta/consume-credit 会重复扣 beta credits —— 这正是要避免的二次计费。
    # 断言：一次生成只产生一次 beta 扣减（1 credit），没有隐式二次扣减。
    assert _beta_used(u) == 1
    assert r["beta_credits_used"] == 1


def test_consume_credit_is_isolated_beta_action_not_generation_path(isolated_db, monkeypatch):
    """/beta/consume-credit 是独立 beta 手动动作，不会单独构成生成账单路径。"""
    _wide_user_limits(monkeypatch)
    u = "u-isolated"

    # consume_credit 手动花 1 credit
    result = asyncio.run(beta_service.consume_credit(u, amount=1))
    assert result["success"] is True
    assert _beta_used(u) == 1
    # 但它没有产生 generation_usage / global_usage（不构成生成预留）
    assert _gen_usage(u) == {"daily": 0, "monthly": 0}
    assert _global_count() == 0


# ─────────────────────────── 时长权重 ───────────────────────────
def test_duration_weight_consumes_appropriate_credits(isolated_db, monkeypatch):
    """>120s 作品 weight=2：一次消耗 2 credits，且在 beta + generation 均体现。"""
    _wide_user_limits(monkeypatch)
    u = "u-weight"
    assert ai_limits.get_duration_weight(180) == 2
    r = ai_limits.reserve_generation(u, duration=180)
    assert r["success"] is True and r["weight"] == 2
    assert _beta_used(u) == 2
    assert _gen_usage(u) == {"daily": 2, "monthly": 2}
    # global_usage 按“生成次数”计、非按权重计：一次生成 → +1（成本保护硬停以生成事件为粒度）
    assert _global_count() == 1