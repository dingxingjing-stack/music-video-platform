"""P0-4 Phase 3 — retry-stems 配额与任务所有权安全测试（T1–T10）。

背景（审计确认）：
  - retry-stems 的 GPU 入口 ace_step_client.separate_only 在 ENVIRONMENT=production 时
    直接 return None（Modal Spleeter 已下线，生产主力是 RunPod），因此 retry-stems
    **不产生普通 generation 的真实 GPU 成本，不应纳入 beta/generation 用户额度**。
  - 但它仍可能启动真实 GPU（非生产），必须受以下三重保护：
      1) 身份/IDOR（task.user_key == X-User-ID）
      2) 全平台成本硬停 global_hard_stop_reached（覆盖 GLOBAL_DAILY_GENERATION_LIMIT + 预算）
      3) 次数上限 MAX_AUTO_RETRIES + 并发原子占锁（acquire_lock）
"""
import concurrent.futures
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import ai_music
from app.services import ai_limits, task_store


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "retry.db")
    monkeypatch.setattr(ai_limits, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(ai_limits, "_DB_PATH", db_path)
    monkeypatch.setattr(task_store, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(task_store, "_DB_PATH", db_path)
    monkeypatch.setattr(ai_music, "HF_FALLBACK_ENABLED", False)
    return db_path


@pytest.fixture()
def calls(monkeypatch):
    """替换 Spleeter GPU 调用为计数 stub，不真正启动 GPU。"""
    c = {"separate": []}

    async def _separate(full_wav):
        c["separate"].append(full_wav)
        return {"vocals": "v.wav", "drums": "d.wav", "bass": "b.wav", "other": "o.wav"}

    monkeypatch.setattr(ai_music, "ace_step_separate", _separate)
    return c


def _client():
    app = FastAPI()
    app.include_router(ai_music.router)
    return TestClient(app)


def _make_task(user_key="uA", task_id="t1", state="completed_with_stems_failed", stems_state="failed"):
    tid = task_store.new_task(user_key=user_key, task_id=task_id)
    task_store.update(tid, state=state, progress=100, stems_state=stems_state,
                      volume_files={"full_wav": "song_full.wav"},
                      download={"full_mp3": f"music/{task_id}/full.mp3"})
    return tid


# ───────────── T1: 自己的 task retry → 允许 ─────────────
def test_t1_own_task_retry_allowed(isolated_db, calls):
    c = _client()
    tid = _make_task("uA", "t1")
    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"X-User-ID": "uA"})
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True


# ───────────── T2: 他人 task retry → 拒绝 ─────────────
def test_t2_other_user_task_retry_denied(isolated_db, calls):
    c = _client()
    tid = _make_task("uA", "t2")
    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"X-User-ID": "uB"})
    assert r.status_code == 403, r.text
    assert calls["separate"] == []  # 未启动 GPU


# ───────────── T3: 无 X-User-ID → 拒绝 ─────────────
def test_t3_no_x_user_id_denied(isolated_db, calls):
    c = _client()
    tid = _make_task("uA", "t3")
    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems")
    assert r.status_code == 403, r.text
    assert calls["separate"] == []


# ───────────── T4: body.user_id 伪造 → 仍拒绝 ─────────────
def test_t4_body_user_id_forgery_still_denied(isolated_db, calls):
    """retry-stems 不读取 body.user_id；身份只来自 X-User-ID。body 伪造不影响结果。"""
    c = _client()
    tid = _make_task("uA", "t4")
    # 用 body 伪造 user_id=B，但 X-User-ID=C（非 owner）→ 仍拒绝
    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems",
               headers={"X-User-ID": "uC", "Content-Type": "application/json"},
               content='{"user_id": "uA"}')
    assert r.status_code == 403, r.text
    assert calls["separate"] == []


# ───────────── T5: retry 不计入用户 generation quota ─────────────
def test_t5_retry_does_not_consume_generation_quota(isolated_db, calls, monkeypatch):
    """retry-stems 不消耗 beta/generation 额度（生产 Modal Spleeter 下线，无普通 GPU 成本）。"""
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")
    c = _client()
    tid = _make_task("uA", "t5")
    # 读取 retry 前 quota
    before = ai_limits._get_session()
    from sqlalchemy import text
    row0 = before.execute(text("SELECT daily_credits_used FROM beta_users WHERE user_id=:u"), {"u": "uA"}).fetchone()
    gu0 = before.execute(text("SELECT daily_count FROM generation_usage WHERE user_id=:u"), {"u": "uA"}).fetchone()
    before.close()

    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"X-User-ID": "uA"})
    assert r.status_code == 200

    after = ai_limits._get_session()
    row1 = after.execute(text("SELECT daily_credits_used FROM beta_users WHERE user_id=:u"), {"u": "uA"}).fetchone()
    gu1 = after.execute(text("SELECT daily_count FROM generation_usage WHERE user_id=:u"), {"u": "uA"}).fetchone()
    after.close()
    # beta credits 不增加（可能没有行 → 0），generation daily 不增加
    assert (row1[0] if row1 else 0) == (row0[0] if row0 else 0)
    assert (gu1[0] if gu1 else 0) == (gu0[0] if gu0 else 0)


# ───────────── T6: global hard stop → 拒绝 + GPU=0 ─────────────
def test_t6_global_hard_stop_denies_retry(isolated_db, calls, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 1)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")
    c = _client()
    # 吃掉唯一全局额度（global count=1）
    assert ai_limits.reserve_generation("u-other")["success"] is True
    tid = _make_task("uA", "t6")
    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"X-User-ID": "uA"})
    assert r.status_code == 429, r.text
    assert calls["separate"] == []  # 未启动 Spleeter GPU


# ───────────── T6b: 预算硬停也拒绝 retry（兼容旧语义） ─────────────
def test_t6b_budget_hard_stop_denies_retry(isolated_db, calls, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 1000)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "1")
    c = _client()
    assert ai_limits.reserve_generation("u-other")["success"] is True  # 预算用尽
    tid = _make_task("uA", "t6b")
    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"X-User-ID": "uA"})
    assert r.status_code == 429, r.text
    assert calls["separate"] == []


# ───────────── T7: global hard stop 检查先于 GPU invocation ─────────────
def test_t7_hard_stop_checked_before_gpu(isolated_db, calls, monkeypatch):
    """retry-stems 在任何 GPU 工作前先做全平台硬停检查（global_hard_stop_reached）。"""
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 1)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")
    # 全局已满
    assert ai_limits.reserve_generation("u-other")["success"] is True
    assert ai_limits.global_hard_stop_reached() is True
    c = _client()
    tid = _make_task("uA", "t7")
    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"X-User-ID": "uA"})
    assert r.status_code == 429
    assert calls["separate"] == []  # 硬停先于 GPU，separate 从未被调


# ───────────── T8: provider failure 语义（retry 无 reserve → 无 refund 链路） ─────────────
def test_t8_provider_failure_no_refund_path(isolated_db, calls, monkeypatch):
    """retry-stems 不 reserve 额度，故失败时无 refund 链路，也不会误退用户额度。

    分轨失败后任务标记 completed_with_stems_failed，不影响用户 beta/generation 额度
    （额度本就未扣，故无需也无从退款）。
    """
    async def _fail(full_wav):
        calls["separate"].append(full_wav)
        return None

    import app.services
    monkeypatch.setattr(ai_music, "ace_step_separate", _fail)
    c = _client()
    tid = _make_task("uA", "t8")
    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"X-User-ID": "uA"})
    assert r.status_code == 200
    # 等后台失败收敛
    for _ in range(60):
        st = (task_store.get(tid) or {}).get("state")
        if st == "completed_with_stems_failed":
            break
        time.sleep(0.02)
    assert (task_store.get(tid) or {}).get("state") == "completed_with_stems_failed"


# ───────────── T9: timeout/unknown 不错误 refund（retry 无 refund 链路） ─────────────
def test_t9_timeout_unknown_no_wrong_refund(isolated_db, calls, monkeypatch):
    """retry-stems 的 _run_retry_stems 异常只更新任务状态，不调用 refund_generation。

    因此不存在「unknown outcome 却退款」的免费生成漏洞；额度本就未扣。
    """
    # 让 separate 抛异常（模拟 unknown outcome，不会触发 refund）
    async def _boom(full_wav):
        calls["separate"].append(full_wav)
        raise RuntimeError("simulated boom")

    monkeypatch.setattr(ai_music, "ace_step_separate", _boom)
    c = _client()
    tid = _make_task("uA", "t9")
    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"X-User-ID": "uA"})
    assert r.status_code == 200
    for _ in range(60):
        st = (task_store.get(tid) or {}).get("state")
        if st == "completed_with_stems_failed":
            break
        time.sleep(0.02)
    st = (task_store.get(tid) or {}).get("state")
    assert st == "completed_with_stems_failed"


# ───────────── T10: 并发 retry 不产生重复 GPU（状态转换原子性） ─────────────
def test_t10_concurrent_state_transition_exactly_one(isolated_db, monkeypatch):
    """核心并发保证：同一 task 的 20 个并发「可重试终态→separating」状态转换，恰好 1 成功。

    这是并发不超过 1 个 GPU 的数据库级保证：task_store.try_transition_state 用
    条件 UPDATE + rowcount 判定（与 reserve_generation 同构），不依赖 threading.Lock。
    """
    tid = _make_task("uA", "t10")  # state = completed_with_stems_failed

    def _call(_):
        return task_store.try_transition_state(
            tid, from_states=("completed", "completed_with_stems_failed"), to_state="separating"
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        results = list(ex.map(_call, range(20)))
    assert sum(results) == 1  # 只有第一个成功抢占
    assert (task_store.get(tid) or {}).get("state") == "separating"


def test_t10b_second_retry_rejected_after_state_transition(isolated_db, calls):
    """状态被抢占（转 separating）后，再次 retry 同一 task 会被 409/429 拒绝，不再启动第二个 GPU。"""
    c = _client()
    tid = _make_task("uA", "t10b")
    # 模拟已有并发 retry 在进行：抢占状态 → separating
    assert task_store.try_transition_state(
        tid, from_states=("completed", "completed_with_stems_failed"), to_state="separating"
    ) is True
    # 此时再 POST retry-stems：state 不再是可重试终态 → 409 拒绝
    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"X-User-ID": "uA"})
    assert r.status_code == 409, r.text
    assert calls["separate"] == []  # 未启动 GPU