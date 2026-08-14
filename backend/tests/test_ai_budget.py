"""B4 测试：Modal GPU 每日预算硬停线（服务端真实硬限制，非前端提示）。

覆盖：
  1. 未达到预算 → 可以创建任务
  2. 达到预算 → 阻止新任务（明确限额错误）
  3. 阻止时不会启动 GPU（不调用 ace_step_generate）
  4. 重复请求不会绕过预算
  5. 并发不会绕过预算（条件自增原子性）
  6. retry-stems（Demucs GPU）不会绕过预算
  7. 服务重启后预算状态不丢失（SQLite 持久化）
"""

import concurrent.futures

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import ai_music
from app.services import ai_limits, task_store


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """独立 SQLite + 清空进程内任务/锁，避免跨测试污染。"""
    db_path = str(tmp_path / "budget.db")
    monkeypatch.setattr(ai_limits, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(ai_limits, "_DB_PATH", db_path)
    monkeypatch.setattr(task_store, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(task_store, "_DB_PATH", db_path)
    monkeypatch.setattr(ai_music, "HF_FALLBACK_ENABLED", False)
    return db_path


@pytest.fixture()
def disable_bg(monkeypatch):
    """端点后台任务替换为 no-op，避免测试驱动与后台重复执行。"""

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(ai_music, "_run_with_timeout", _noop)


@pytest.fixture()
def fake_modal(monkeypatch):
    """记录 GPU 调用（generate=ACE-Step, separate=Demucs），默认不真正运行。"""
    calls = {"generate": [], "separate": []}

    async def _generate(prompt=None, lyrics=None, duration=None):
        calls["generate"].append(duration)
        return {"full_wav": "song_full.wav"}

    async def _separate(full_wav):
        calls["separate"].append(full_wav)
        return {"vocals": "v.wav", "drums": "d.wav", "bass": "b.wav", "other": "o.wav"}

    monkeypatch.setattr(ai_music, "ace_step_generate", _generate)
    monkeypatch.setattr(ai_music, "ace_step_separate", _separate)
    return calls


def _client():
    app = FastAPI()
    app.include_router(ai_music.router)
    return TestClient(app)


def _no_user_limits(monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 1000)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 1000)


# ────────────────────────── 预算硬停线 ──────────────────────────

def test_under_budget_can_create_task(isolated_db, fake_modal, disable_bg, monkeypatch):
    """1: 未达到预算 → 可创建任务（reserve 成功，任务入队）。"""
    _no_user_limits(monkeypatch)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "5")
    r = ai_limits.reserve_generation("u1")
    assert r["success"] is True
    assert r["budget_daily_used"] == 1 and r["budget_daily_limit"] == 5

    c = _client()
    rr = c.post("/api/v1/ai/generate", json={"prompt": "a song"}, headers={"X-User-ID": "u2"})
    assert rr.status_code == 200 and rr.json()["success"] is True
    # 任务已创建，通过 is_user_busy 验证
    assert task_store.is_user_busy("u2") is True


def test_at_budget_blocks_new_task(isolated_db, monkeypatch):
    """2: 达到预算 → 阻止新任务，返回明确限额错误。"""
    _no_user_limits(monkeypatch)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "1")
    assert ai_limits.reserve_generation("u1")["success"] is True
    r = ai_limits.reserve_generation("u2")
    assert r["success"] is False
    assert "预算" in r["error"]


def test_blocked_does_not_start_gpu(isolated_db, fake_modal, disable_bg, monkeypatch):
    """3: 预算用尽被拒时不会启动 GPU（不调用 ace_step_generate，不创建任务）。"""
    _no_user_limits(monkeypatch)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "1")
    assert ai_limits.reserve_generation("u1")["success"] is True  # 预算用尽

    c = _client()
    r = c.post("/api/v1/ai/generate", json={"prompt": "a song"}, headers={"X-User-ID": "u2"})
    assert r.status_code == 429  # 预算硬停线：GPU 启动前 429
    assert r.json()["success"] is False
    assert "预算" in r.json()["error"]
    assert fake_modal["generate"] == []  # 未启动 ACE-Step GPU
    # 任务未创建，is_user_busy 应为 False
    assert task_store.is_user_busy("u2") is False


def test_repeat_requests_cannot_bypass_budget(isolated_db, monkeypatch):
    """4: 预算用尽后连续重复请求均被拒绝。"""
    _no_user_limits(monkeypatch)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "1")
    assert ai_limits.reserve_generation("u1")["success"] is True
    for i in range(5):
        assert ai_limits.reserve_generation(f"u{i + 2}")["success"] is False


def test_concurrency_cannot_bypass_budget(isolated_db, monkeypatch):
    """5: 并发请求无法越过预算（条件自增原子性，恰好只成功 budget 次）。"""
    _no_user_limits(monkeypatch)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "3")

    def _call(i):
        return ai_limits.reserve_generation(f"conc-{i}")["success"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        results = list(ex.map(_call, range(40)))
    assert sum(results) == 3
    assert ai_limits.budget_hard_stop_reached() is True


def test_retry_stems_gated_by_budget(isolated_db, fake_modal, disable_bg, monkeypatch):
    """6: 预算用尽后 retry-stems（Demucs GPU）被 429 拒绝，不启动 Demucs。"""
    _no_user_limits(monkeypatch)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "1")
    assert ai_limits.reserve_generation("u1")["success"] is True  # 预算用尽

    tid = task_store.new_task(user_key="uA", task_id="budget-retry")
    task_store.update(
        tid, state="completed_with_stems_failed", progress=100, stems_state="failed",
        volume_files={"full_wav": "song_full.wav"},
        download={"full_mp3": "music/budget-retry/full.mp3"},
    )
    c = _client()
    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"X-User-ID": "uA"})
    assert r.status_code == 429
    assert "预算" in r.json()["detail"]
    assert fake_modal["separate"] == []  # 未启动 Demucs GPU


def test_budget_state_persists_across_restart(isolated_db, monkeypatch):
    """7: 预算状态持久化在 SQLite；服务重启后依旧硬性拒绝。"""
    _no_user_limits(monkeypatch)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "1")
    assert ai_limits.reserve_generation("u1")["success"] is True
    assert ai_limits.budget_hard_stop_reached() is True

    # 模拟服务重启：重新打开连接 + 重跑建表（数据在 SQLite 文件，不丢失）
    conn = ai_limits._get_conn()
    try:
        ai_limits._init_db(conn)
        g = conn.execute(
            "SELECT count FROM global_usage WHERE date=?", (ai_limits._today(),)
        ).fetchone()
        assert g and g["count"] == 1
    finally:
        conn.close()

    assert ai_limits.reserve_generation("u2")["success"] is False
    assert "预算" in ai_limits.reserve_generation("u3")["error"]


def test_budget_status_exposes_used_and_limit(isolated_db, monkeypatch):
    """额外：/limits 返回预算使用与限额（供前端/运营查看，真实服务端数据）。"""
    _no_user_limits(monkeypatch)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "4")
    ai_limits.reserve_generation("u1")
    import asyncio

    st = asyncio.run(ai_limits.generation_usage_status("u1"))
    assert st["budget_daily_limit"] == 4
    assert st["budget_daily_used"] == 1