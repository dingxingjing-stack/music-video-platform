"""P6-B-C3-1：continuation 中间态映射为既有活跃态（最小解 A）的契约测试。

最小解 A（唯一授权改动，位于 continuation_service.generate_long_music）：
    generating_continuation -> generating
    stitching               -> generating

不扩展 task_store / task_recovery 的 ACTIVE_STATES；映射后既有机制自动覆盖：
- task_store.is_user_busy（内联活跃态五元组）
- task_store.acquire_lock 的陈旧锁清理（同五元组）
- task_store.get 的惰性超时标记（同五元组）
- task_recovery.reconcile_stale_tasks / reconcile_orphans_after_restart
  与 finalize_stale_task 的失败 CAS + 单一退款出口

Case A：第二段续写阶段（progress=50）——活跃态成员 / busy / stale 可识别 / 不被当成闲置
Case B：拼接阶段（progress=80）——同上
Case C：stale continuation task -> 既有 reconcile -> failed + 既有退款一次 + 锁释放 + 幂等
Case D：正常 continuation 成功 -> completed（路由既有收尾），阶段状态全为活跃态
Case E：正常 continuation 失败 -> failed + 路由既有退款各一次，busy 正确释放

全部 provider / R2 / LLM / Credits 均为 fake 或注入替身；
YINCHAO_API_BASE_URL / TEMPOLOR_BASE_URL 指向 127.0.0.1:9。禁止任何真实外部调用。
"""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import app.services.ai_limits as ai_limits
import app.services.credits_service as credits_service
import app.services.continuation_service as cont_mod
from app.routers import ai_music
from app.services import task_recovery, task_store
from app.services.continuation_service import continuation_service

OLD_CONT_STATE = "generating_continuation"
OLD_STITCH_STATE = "stitching"


# ─────────────────────────────────────────────────────────────────────────────
# fixtures：独立 sqlite（Base 先建，避免旧 DDL 抢建 ai_tasks）+ 替身环境
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = str(tmp_path / "c31.db")
    monkeypatch.setattr(task_store, "_DB_PATH", db)
    monkeypatch.setattr(ai_limits, "_DB_PATH", db)
    eng = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    from app.db.database import Base

    Base.metadata.create_all(bind=eng)
    monkeypatch.setattr(credits_service, "SessionLocal", sessionmaker(bind=eng))
    monkeypatch.setenv("YINCHAO_API_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("TEMPOLOR_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.delenv("AI_GENERATION_PROVIDER", raising=False)
    return eng


@pytest.fixture()
def refunds(monkeypatch):
    """既有退款出口的记录器：任务恢复路径与路由路径分开记录。"""
    calls = SimpleNamespace(quota=[], credits=[], route_quota=[])
    monkeypatch.setattr(
        ai_limits, "refund_generation",
        lambda user_id, **kw: calls.quota.append({"user": user_id, **kw}) or {"refunded": True},
    )
    monkeypatch.setattr(
        credits_service, "refund_generation_credits",
        lambda user_id, task_id: calls.credits.append((user_id, task_id)) or {"success": True},
    )
    monkeypatch.setattr(
        ai_music, "refund_generation",
        lambda user_id, **kw: calls.route_quota.append({"user": user_id, **kw}) or {"refunded": True},
    )
    return calls


@pytest.fixture()
def state_log(monkeypatch):
    """记录所有带 state 的任务写入（真实写入仍照常发生）。"""
    log = []
    orig = task_store.update

    def spy(tid, **kw):
        if "state" in kw:
            log.append({"task_id": tid, "state": kw["state"], "progress": kw.get("progress")})
        return orig(tid, **kw)

    monkeypatch.setattr(task_store, "update", spy)
    return log


class FakeProvider:
    provider_type = "api"
    capabilities = ["text_to_music"]
    production = True
    max_duration = 300
    gpu = "none"

    def __init__(self, name, results=None, on_call=None):
        self.name = name
        self._results = list(results or [])
        self.requests = []
        self.on_call = on_call

    async def generate(self, request: dict) -> dict:
        self.requests.append(dict(request))
        if self.on_call is not None:
            self.on_call(request)
        if self._results:
            return self._results.pop(0)
        return {"success": False, "error": f"{self.name} 脚本已耗尽"}


def _ok(tmp_path, tag):
    p = tmp_path / f"{tag}.wav"
    p.write_bytes(b"RIFFfake")
    return {"success": True, "volume_files": {"full_wav": p.name, "_local_path": str(p),
                                              "_measured_duration_sec": 271.0}}


def _fail(error):
    return {"success": False, "error": error}


@pytest.fixture()
def stub_heavy_io(monkeypatch, tmp_path):
    """桩掉参考段分析/歌词续写/拼接/实测/R2；task_store 真实写入不桩。"""
    combined = tmp_path / "combined.wav"
    combined.write_bytes(b"RIFFfake")
    monkeypatch.setattr(
        cont_mod.continuation_service, "_prepare_continuation_context",
        AsyncMock(return_value=("cmViZA==", {"bpm": 120, "key": "C major"})),
    )
    monkeypatch.setattr(cont_mod.continuation_service, "_continue_lyrics", AsyncMock(return_value="ly2"))
    monkeypatch.setattr(
        cont_mod.continuation_service, "_stitch_with_crossfade", AsyncMock(return_value=str(combined))
    )
    monkeypatch.setattr(
        cont_mod.continuation_service, "_measure_final_duration", AsyncMock(return_value=271.0)
    )
    monkeypatch.setattr(cont_mod.continuation_service, "_upload_parts", AsyncMock(return_value={}))
    monkeypatch.setattr(
        cont_mod.continuation_service, "_upload_final",
        AsyncMock(return_value={"full_wav": "music/final.wav", "full_mp3": "music/final.mp3"}),
    )
    return SimpleNamespace(combined=combined)


def _snapshot(tid, user, phase):
    """拍下阶段瞬间的持久化状态 + 既有机制判定，含惰性 stale 识别演练。"""
    row = task_store.get(tid) or {}
    state = row.get("state")
    snap = {
        "phase": phase,
        "state": state,
        "progress": row.get("progress"),
        "busy": task_store.is_user_busy(user),
        "active": state in task_recovery.ACTIVE_STATES,
    }
    sess = task_store._get_session()
    try:
        sess.execute(text("BEGIN"))
        sess.execute(
            text("UPDATE ai_tasks SET updated_at = :old WHERE task_id = :tid"),
            {"old": time.time() - 700, "tid": tid},
        )
        sess.commit()
    finally:
        sess.close()
    stale_row = task_store.get(tid) or {}
    snap["stale_identified"] = stale_row.get("stale_timed_out") is True
    return snap


def _backdate(tid, seconds=700):
    sess = task_store._get_session()
    try:
        sess.execute(text("BEGIN"))
        sess.execute(
            text("UPDATE ai_tasks SET updated_at = :old WHERE task_id = :tid"),
            {"old": time.time() - seconds, "tid": tid},
        )
        sess.commit()
    finally:
        sess.close()


async def _run_long(tid, user, provider, **kw):
    params = dict(
        prompt="p", style="pop", duration=300, lyrics="ly",
        task_id=tid, user_key=user, provider_chain=[provider],
    )
    params.update(kw)
    return await continuation_service.generate_long_music(**params)


# ─────────────────────────────────────────────────────────────────────────────
# Case A：第二段续写阶段（写入 progress=50 的时刻）
# ─────────────────────────────────────────────────────────────────────────────
async def test_case_a_continuation_phase_is_active_busy_and_stale_identifiable(
    env, refunds, state_log, stub_heavy_io, tmp_path
):
    user = "u-c31a"
    tid = task_store.new_task(user_key=user, generation_quota_weight=2)
    assert task_store.acquire_lock(user, tid) is True

    snaps = []

    def on_call(req):
        phase = "continuation" if req.get("enable_audio2audio") else "first"
        snaps.append(_snapshot(tid, user, phase))

    p = FakeProvider(
        "yinchao", results=[_ok(tmp_path, "a1"), _ok(tmp_path, "a2")], on_call=on_call
    )
    result = await _run_long(tid, user, p)
    assert result["success"] is True

    cont = [s for s in snaps if s["phase"] == "continuation"]
    assert cont, "第二段（enable_audio2audio）调用时必须拍到快照"
    snap = cont[0]
    # 最小解 A：该阶段持久化的就是既有活跃态，而非旧中间态
    assert snap["state"] == "generating"
    assert snap["progress"] == 50
    assert snap["active"] is True
    assert snap["busy"] is True
    assert snap["stale_identified"] is True
    # 不会被当成闲置任务：同用户第二个任务抢锁必须失败
    assert task_store.acquire_lock(user, "task-intruder") is False

    states = [w["state"] for w in state_log]
    assert OLD_CONT_STATE not in states
    assert OLD_STITCH_STATE not in states
    # 全程每个阶段状态都在既有活跃集合内（恢复机制零扩展即可覆盖）
    assert all(w["state"] in task_recovery.ACTIVE_STATES or w["state"] == "completed"
               for w in state_log if w["task_id"] == tid)


# ─────────────────────────────────────────────────────────────────────────────
# Case B：拼接阶段（写入 progress=80 的时刻）
# ─────────────────────────────────────────────────────────────────────────────
async def test_case_b_stitching_phase_is_active_busy_and_stale_identifiable(
    env, refunds, state_log, stub_heavy_io, monkeypatch, tmp_path
):
    user = "u-c31b"
    tid = task_store.new_task(user_key=user, generation_quota_weight=2)
    assert task_store.acquire_lock(user, tid) is True

    snaps = []

    async def stitch(*args, **kwargs):
        snaps.append(_snapshot(tid, user, "stitching"))
        return str(stub_heavy_io.combined)

    monkeypatch.setattr(
        cont_mod.continuation_service, "_stitch_with_crossfade", AsyncMock(side_effect=stitch)
    )

    p = FakeProvider("yinchao", results=[_ok(tmp_path, "b1"), _ok(tmp_path, "b2")])
    result = await _run_long(tid, user, p)
    assert result["success"] is True

    assert len(snaps) == 1, "拼接调用时必须恰好拍到一次快照"
    snap = snaps[0]
    assert snap["state"] == "generating"
    assert snap["progress"] == 80
    assert snap["active"] is True
    assert snap["busy"] is True
    assert snap["stale_identified"] is True

    states = [w["state"] for w in state_log]
    assert OLD_STITCH_STATE not in states
    assert OLD_CONT_STATE not in states


# ─────────────────────────────────────────────────────────────────────────────
# Case C：stale continuation task -> 既有 reconcile -> failed + 既有退款出口
# ─────────────────────────────────────────────────────────────────────────────
async def test_case_c_stale_continuation_task_enters_existing_failed_refund_path(
    env, refunds, state_log, stub_heavy_io, tmp_path
):
    user = "u-c31c"
    tid = task_store.new_task(user_key=user, generation_quota_weight=2)
    assert task_store.acquire_lock(user, tid) is True

    p = FakeProvider(
        "yinchao",
        results=[_ok(tmp_path, "c1")] + [_fail("续写段 provider 挂了")] * 99,
    )
    with pytest.raises(RuntimeError, match="续写段生成失败"):
        await _run_long(tid, user, p)

    # 模拟进程在续写期间崩溃后的残留：活跃态未终态化 + 锁未释放
    row = task_store.get(tid)
    assert row["state"] == "generating"
    assert task_store.is_user_busy(user) is True
    assert task_store.acquire_lock(user, "task-intruder") is False

    _backdate(tid, seconds=700)
    assert task_recovery.reconcile_stale_tasks(now=time.time()) == 1

    row = task_store.get(tid)
    assert row["state"] == "failed"
    assert row.get("error")
    # 既有单一退款出口：日额度 + Credits 各一次，权重取建任务时持久化的 2
    assert len(refunds.quota) == 1
    assert refunds.quota[0]["task_id"] == tid
    assert refunds.quota[0]["weight"] == 2
    assert refunds.quota[0]["reason"] == "provider_failed"
    assert refunds.credits == [(user, tid)]
    # 锁已释放，用户不再被卡单
    assert task_store.is_user_busy(user) is False
    # 幂等：CAS 未命中 → 不再退款
    assert task_recovery.finalize_stale_task(tid, reason="again").get("finalized") is False
    assert len(refunds.quota) == 1
    assert len(refunds.credits) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 路由层替身：registry / Agnes / 成本日志 / CDN（真实 _run_generation + 真实 continuation）
# ─────────────────────────────────────────────────────────────────────────────
class FakeCdnUploader:
    async def upload_music_package(self, task_id, files_local):
        return {
            "full_wav": f"music/{task_id}/full.wav",
            "full_mp3": f"music/{task_id}/full.mp3",
            "vocals": f"music/{task_id}/vocals.wav",
            "drums": f"music/{task_id}/drums.wav",
            "bass": f"music/{task_id}/bass.wav",
            "other": f"music/{task_id}/other.wav",
        }

    def get_presigned_download_url(self, key, expires=600):
        return f"https://signed/{key}"


def _stub_route(monkeypatch, provider):
    reg = SimpleNamespace(
        fallback_chain=lambda: [provider],
        chain_for_operation=lambda operation, song_language=None: [provider],
        select=lambda name=None: provider,
        get=lambda name: provider,
    )
    monkeypatch.setattr(ai_music, "get_provider_registry", lambda: reg)
    monkeypatch.setattr(
        ai_music.agnes_service, "generate_song",
        AsyncMock(return_value=SimpleNamespace(optimized_prompt="prompt-x", generated_lyrics="la la")),
    )
    monkeypatch.setattr(ai_music, "_log_generation_cost", lambda *a, **k: None)
    monkeypatch.setattr(ai_music, "cdn_uploader", FakeCdnUploader())
    # 阶段 B：链失败后仅 normal/lyric_to_music 允许 HF 兜底——测试恒 None，避免真实外呼
    monkeypatch.setattr(ai_music, "_try_hf_ace_step_fallback", AsyncMock(return_value=None))


def _new_route_task(user, weight=2):
    tid = task_store.new_task(user_key=user, generation_quota_weight=weight)
    assert task_store.acquire_lock(user, tid) is True
    return tid


# ─────────────────────────────────────────────────────────────────────────────
# Case D：正常单次生成成功 -> completed（阶段 B 路由收尾，状态序列全为既有活跃态）
# ─────────────────────────────────────────────────────────────────────────────
async def test_case_d_normal_continuation_success_ends_completed(
    env, refunds, state_log, stub_heavy_io, monkeypatch, tmp_path
):
    user = "u-c31d"
    p = FakeProvider("yinchao", results=[_ok(tmp_path, "d1")])
    _stub_route(monkeypatch, p)
    tid = _new_route_task(user)

    req = ai_music.GenerateRequest(prompt="a song", style="pop", duration=270, type="song")
    await ai_music._run_generation(tid, req, user, 2)

    row = task_store.get(tid)
    assert row["state"] == "completed"
    assert row.get("progress") == 100
    assert task_store.is_user_busy(user) is False          # 路由 finally 释放锁
    assert refunds.route_quota == []                        # 成功不退款
    assert refunds.quota == []
    assert refunds.credits == []
    # 阶段 B 单次生成的进度序列：processing 10 → generating 40 → uploading 75 → completed 100
    cont_states = [w for w in state_log if w["task_id"] == tid]
    assert OLD_CONT_STATE not in [w["state"] for w in cont_states]
    assert OLD_STITCH_STATE not in [w["state"] for w in cont_states]
    assert any(w["state"] == "processing" and w["progress"] == 10 for w in cont_states)
    assert any(w["state"] == "generating" and w["progress"] == 40 for w in cont_states)
    assert any(w["state"] == "uploading" and w["progress"] == 75 for w in cont_states)
    assert any(w["state"] == "completed" and w["progress"] == 100 for w in cont_states)


# ─────────────────────────────────────────────────────────────────────────────
# Case E：正常生成失败 -> failed + 路由既有退款各一次
# ─────────────────────────────────────────────────────────────────────────────
async def test_case_e_normal_continuation_failure_ends_failed_with_single_refund(
    env, refunds, state_log, stub_heavy_io, monkeypatch, tmp_path
):
    user = "u-c31e"
    p = FakeProvider("yinchao", results=[_fail("provider 挂了")] * 10)
    _stub_route(monkeypatch, p)
    tid = _new_route_task(user)

    snaps = []

    def on_call(req):
        snaps.append(_snapshot(tid, user, "generation"))

    p.on_call = on_call

    req = ai_music.GenerateRequest(prompt="a song", style="pop", duration=270, type="song")
    await ai_music._run_generation(tid, req, user, 2)

    # 失败阶段快照：映射后的活跃态 + busy（在崩溃点之前拍到）
    assert snaps, "provider 调用时必须拍到快照"
    assert snaps[0]["state"] == "generating"
    assert snaps[0]["busy"] is True

    row = task_store.get(tid)
    assert row["state"] == "failed"
    assert row.get("error")
    assert task_store.is_user_busy(user) is False          # 路由 finally 释放锁
    # 路由既有退款：日额度一次（reason/weight 不变）+ Credits 一次；recovery 路径未介入
    assert len(refunds.route_quota) == 1
    assert refunds.route_quota[0]["task_id"] == tid
    assert refunds.route_quota[0]["weight"] == 2
    assert refunds.route_quota[0]["reason"] == "provider_failed"
    assert refunds.credits == [(user, tid)]
    assert refunds.quota == []

    states = [w["state"] for w in state_log if w["task_id"] == tid]
    assert OLD_CONT_STATE not in states
    assert OLD_STITCH_STATE not in states
    assert "completed" not in states
