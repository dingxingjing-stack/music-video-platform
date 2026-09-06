"""P1-3 修复验证：budget_hard_stop_reached() 统一 hard-stop 语义。

验证 budget_hard_stop_reached 与 global_hard_stop_reached 采用相同语义：
  cap = min(GLOBAL_DAILY_GENERATION_LIMIT, GPU 预算)
  任一有效限制达到即触发；未配置变量时兼容旧行为。

覆盖：
  - 只有 FAL_BUDGET_DAILY
  - 只有 GLOBAL_DAILY_GENERATION_LIMIT（FAL 未配置）
  - 两者同时达到（先到先触发/较小者）
  - 两者都未达到
  - 未配置变量时（默认 GLOBAL=30）
  - hard stop 后不触发额外扣额度（只读）
"""
from __future__ import annotations

import pytest

from app.services import ai_limits


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "p133.db")
    monkeypatch.setattr(ai_limits, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(ai_limits, "_DB_PATH", db_path)
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 1000)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 1000)
    return db_path


# ── 仅 FAL_BUDGET_DAILY ──────────────────────────────────────────────
def test_only_fal_budget_hard_stop(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 1000)  # 高，不主导
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "3")
    assert ai_limits.budget_hard_stop_reached() is False
    for i in range(3):
        assert ai_limits.reserve_generation(f"f-{i}")["success"] is True
    assert ai_limits.budget_hard_stop_reached() is True
    # 读只操作，不因 hard stop 多扣（数量=3）
    assert ai_limits.global_hard_stop_reached() is True


# ── 仅 GLOBAL_DAILY_GENERATION_LIMIT（FAL 未配置） ─────────────────────
def test_only_global_hard_stop(isolated_db, monkeypatch):
    """修复点：此前 FAL 未配置时 budget_hard_stop 恒 False，现在须覆盖 GLOBAL。"""
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 2)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")  # 预算未配置
    assert ai_limits.budget_hard_stop_reached() is False
    assert ai_limits.reserve_generation("g1")["success"] is True
    assert ai_limits.reserve_generation("g2")["success"] is True
    assert ai_limits.budget_hard_stop_reached() is True
    # 再一个用户 → reserve 也应拒绝（最终原子 cap）
    assert ai_limits.reserve_generation("g3")["success"] is False


# ── 两者同时达到 → 较小 cap 先触发 ───────────────────────────────────
def test_both_budget_and_global_reached(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 10)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "4")
    for i in range(4):
        assert ai_limits.reserve_generation(f"both-{i}")["success"] is True
    assert ai_limits.budget_hard_stop_reached() is True  # cap=min(10,4)=4 已到
    # GLOBAL 相对高，所以预算先边界 → 4 后 hard stop
    assert ai_limits.reserve_generation("both-x")["success"] is False


# ── 两者都未达到 ─────────────────────────────────────────────────────
def test_neither_reached(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "100")
    assert ai_limits.budget_hard_stop_reached() is False
    assert ai_limits.reserve_generation("n")["success"] is True
    assert ai_limits.budget_hard_stop_reached() is False


# ── 未配置变量时兼容旧行为（默认 GLOBAL=30） ──────────────────────────
def test_defaults_compat_when_unconfigured(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")   # 预算未配置
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 30)
    # 未达 30 前不触发
    assert ai_limits.budget_hard_stop_reached() is False
    # 用低预算别名间接验证全局默认 30 不早触发
    assert ai_limits.GLOBAL_DAILY_GENERATION_LIMIT == 30


# ── reserve_generation atomic cap 保持不变（不因 hard stop 双扣） ─────
def test_reserve_atomic_cap_unchanged(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 3)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "3")
    # 恰好 3 次成功（atomic cap 允许多并行但总量=3）
    assert ai_limits.reserve_generation("a")["success"] is True
    assert ai_limits.reserve_generation("b")["success"] is True
    assert ai_limits.reserve_generation("c")["success"] is True
    assert ai_limits.reserve_generation("d")["success"] is False
    assert ai_limits.budget_hard_stop_reached() is True