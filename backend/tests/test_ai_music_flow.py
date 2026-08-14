"""端点级流程测试：提交 -> 轮询 -> 完成/失败 -> 下载 / 重试分轨 全链路。

覆盖公测验收项：
  1. POST /generate 立即返回 task_id（异步协议）
  2. GET /task 轮询到终态（completed/failed）
  3. completed 返回完整歌曲预签名 URL
  4. completed 返回 vocals/drums/bass/other 四轨预签名
  5. 用户 A/B 隔离（poll/download IDOR 403）
  6. 每日额度真实进入生产调用链（POST 前置原子预留）
  7. 并发锁：同时仅 1 个任务（busy 拒绝重复 POST）
  8. 重复 POST 不绕过（同一用户忙碌拒绝）
  9. retry-stems 成功 + 次数上限（MAX_AUTO_RETRIES）
  10. 分轨失败时完整歌曲仍可下载，分轨返回 409
  11. 全平台每日限额阻断新任务（成本保护）
  13. 下载返回 600s 短期预签名 URL（非永久 URL）
  15. 时长上限在管线内钳制（MAX_AUDIO_DURATION_SECONDS）

注：TestClient 下 asyncio.create_task 的后台任务会在请求间继续执行。
为避免「端点后台任务」与测试手动驱动的管线双重执行（配额/计数不一致），
流程类用例通过 disable_bg 将端点后台任务替换为 no-op，仅由测试驱动同一
生产管线函数（_run_with_timeout / _run_retry_stems）；其余走真实 HTTP 端点。
"""

import asyncio
import os
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import ai_limits, task_store
from app.routers import ai_music

VOLUME_OK = {
    "full_wav": "song_full.wav",
    "full_mp3": "song_full.mp3",
    "vocals": "vocals.wav",
    "drums": "drums.wav",
    "bass": "bass.wav",
    "other": "other.wav",
}


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """独立 SQLite + 关闭 HF 兜底 + 清空进程内任务/锁（避免跨测试污染）。"""
    db_path = str(tmp_path / "flow.db")
    monkeypatch.setattr(ai_limits, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(ai_limits, "_DB_PATH", db_path)
    monkeypatch.setattr(task_store, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(task_store, "_DB_PATH", db_path)
    monkeypatch.setattr(ai_music, "HF_FALLBACK_ENABLED", False)
    return db_path


@pytest.fixture()
def disable_bg(monkeypatch):
    """把端点后台任务替换为 no-op，返回真实管线函数供测试手动驱动。"""
    real = ai_music._run_with_timeout

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(ai_music, "_run_with_timeout", _noop)
    return real


@pytest.fixture()
def fake_modal(monkeypatch):
    """模拟 Modal GPU 端：ACE-Step 生成 + Demucs 分轨 + 文件取回 + R2 上传/预签名。"""
    calls = {"generate": [], "separate": [], "download": []}

    async def _generate(prompt=None, lyrics=None, duration=None):
        calls["generate"].append({"prompt": prompt, "lyrics": lyrics, "duration": duration})
        return dict(VOLUME_OK)

    async def _download(name, local_dir):
        calls["download"].append(name)
        p = os.path.join(local_dir, name)
        with open(p, "w") as f:
            f.write("fake-audio")
        return p

    async def _separate(full_wav):
        calls["separate"].append(full_wav)
        return {"vocals": "vocals.wav", "drums": "drums.wav", "bass": "bass.wav", "other": "other.wav"}

    async def _upload(task_id, files_local):
        out = {}
        for k in files_local:
            ext = "mp3" if k == "full_mp3" else "wav"
            out[k] = f"music/{task_id}/{k}.{ext}"
        return out

    def _presign(key, expires_in=600):
        return f"https://signed/{key}"

    monkeypatch.setattr(ai_music, "ace_step_generate", _generate)
    monkeypatch.setattr(ai_music, "ace_step_download", _download)
    monkeypatch.setattr(ai_music, "ace_step_separate", _separate)
    monkeypatch.setattr(ai_music.cdn_uploader, "upload_music_package", _upload)
    monkeypatch.setattr(ai_music.cdn_uploader, "get_presigned_download_url", _presign)
    return calls


def _client():
    app = FastAPI()
    app.include_router(ai_music.router)
    return TestClient(app)


def _run_pipeline(run, task_id, user="uA", prompt="a summer pop song", duration=180):
    req = ai_music.GenerateRequest(prompt=prompt, style="pop", duration=duration, type="song")
    asyncio.run(run(task_id, req, user))


def _wait_terminal(c, task_id, headers, tries=60):
    for _ in range(tries):
        r = c.get(f"/api/v1/ai/task/{task_id}", headers=headers)
        if r.status_code == 200:
            st = r.json()["state"]
            if st in ("completed", "failed", "cancelled"):
                return r.json()
        time.sleep(0.02)
    raise AssertionError("任务未进入终态")


def _wait_store(task_id, states, tries=60):
    for _ in range(tries):
        st = (task_store.get(task_id) or {}).get("state")
        if st in states:
            return
        time.sleep(0.02)
    raise AssertionError(f"后台任务未收敛到 {states}")


# ────────────────────────── 完整链路 ──────────────────────────

def test_full_flow_completed(isolated_db, fake_modal, disable_bg):
    """1/2/3/4/6/13: 提交返回 task_id；额度在 GPU 前原子预留；完成返回完整歌+四轨预签名；下载为短期预签名。"""
    c = _client()
    r = c.post("/api/v1/ai/generate", json={"prompt": "a summer pop song"}, headers={"X-User-ID": "uA"})
    assert r.status_code == 200
    d = r.json()
    assert d["success"] is True and d["task_id"] and d["status_url"]
    tid = d["task_id"]

    # 额度在管线（GPU）运行前已原子预留 —— 生产调用链验证（P1）
    assert ai_limits.reserve_generation("uA")["success"] is False

    _run_pipeline(disable_bg, tid)
    poll = _wait_terminal(c, tid, {"X-User-ID": "uA"})
    assert poll["state"] == "completed"
    assert poll["stems_state"] == "ok"
    assert poll["audio_url"].startswith("https://signed/")
    assert set(poll["stems"]) == {"vocals", "drums", "bass", "other"}

    # 下载为 600s 预签名，非永久公开 URL
    rdl = c.get(f"/api/v1/ai/task/{tid}/download?file=full", headers={"X-User-ID": "uA"})
    assert rdl.status_code == 200
    assert rdl.json()["expires_in"] == 600
    assert rdl.json()["url"].startswith("https://signed/")

    # 成功不退款 → 当日额度仍被占用
    r2 = c.post("/api/v1/ai/generate", json={"prompt": "another song"}, headers={"X-User-ID": "uA"})
    assert r2.json()["success"] is False


def test_busy_lock_blocks_duplicate(isolated_db, fake_modal, disable_bg):
    """7/8: 同时仅 1 个任务；重复 POST 在锁释放前被拒绝。"""
    c = _client()
    r = c.post("/api/v1/ai/generate", json={"prompt": "a summer pop song"}, headers={"X-User-ID": "uB"})
    tid = r.json()["task_id"]
    assert task_store.is_user_busy("uB") is True

    r2 = c.post("/api/v1/ai/generate", json={"prompt": "another song"}, headers={"X-User-ID": "uB"})
    assert r2.json()["success"] is False
    assert "正在进行" in r2.json()["error"]

    # 释放锁 + 回退额度后可再次提交
    task_store.release_lock_for_task(tid)
    ai_limits.refund_generation("uB")
    r3 = c.post("/api/v1/ai/generate", json={"prompt": "another song"}, headers={"X-User-ID": "uB"})
    assert r3.json()["success"] is True


def test_global_limit_blocks_new_tasks(isolated_db, fake_modal, disable_bg, monkeypatch):
    """11: 全平台每日限额阻断新任务（成本保护，30 -> 1）。"""
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 1)
    c = _client()
    r = c.post("/api/v1/ai/generate", json={"prompt": "song A"}, headers={"X-User-ID": "uA"})
    assert r.json()["success"] is True
    r2 = c.post("/api/v1/ai/generate", json={"prompt": "song B"}, headers={"X-User-ID": "uB"})
    assert r2.json()["success"] is False
    assert "全平台" in r2.json()["error"]


def test_duration_clamped(isolated_db, fake_modal, disable_bg, monkeypatch):
    """15: 请求时长超过上限时在管线内钳制到 MAX_AUDIO_DURATION_SECONDS。"""
    monkeypatch.setattr(ai_music, "MAX_AUDIO_DURATION_SECONDS", 60)
    c = _client()
    r = c.post("/api/v1/ai/generate", json={"prompt": "a song", "duration": 180}, headers={"X-User-ID": "uA"})
    tid = r.json()["task_id"]
    _run_pipeline(disable_bg, tid, duration=180)
    assert fake_modal["generate"][0]["duration"] == 60


def test_auto_retry_on_generate_failure(isolated_db, fake_modal, disable_bg, monkeypatch):
    """MAX_AUTO_RETRIES=1：首次失败自动重试，第二次成功则完成。"""
    monkeypatch.setattr(ai_music, "MAX_AUTO_RETRIES", 1)
    calls = []

    async def flaky_generate(prompt=None, lyrics=None, duration=None):
        calls.append(duration)
        if len(calls) == 1:
            return None
        return dict(VOLUME_OK)

    monkeypatch.setattr(ai_music, "ace_step_generate", flaky_generate)
    c = _client()
    r = c.post("/api/v1/ai/generate", json={"prompt": "a song"}, headers={"X-User-ID": "uA"})
    tid = r.json()["task_id"]
    _run_pipeline(disable_bg, tid)
    poll = _wait_terminal(c, tid, {"X-User-ID": "uA"})
    assert poll["state"] == "completed"
    assert len(calls) == 2  # 1 次初试 + 1 次自动重试


def test_failed_flow_refunds_and_marks_failed(isolated_db, fake_modal, disable_bg, monkeypatch):
    """生成彻底失败 → 任务 failed + 额度回退（可再次提交）。"""
    monkeypatch.setattr(ai_music, "MAX_AUTO_RETRIES", 1)

    async def never(prompt=None, lyrics=None, duration=None):
        return None

    monkeypatch.setattr(ai_music, "ace_step_generate", never)
    c = _client()
    r = c.post("/api/v1/ai/generate", json={"prompt": "a song"}, headers={"X-User-ID": "uA"})
    tid = r.json()["task_id"]
    _run_pipeline(disable_bg, tid)
    poll = _wait_terminal(c, tid, {"X-User-ID": "uA"})
    assert poll["state"] == "failed"
    # 退款生效 → 再次提交成功
    r2 = c.post("/api/v1/ai/generate", json={"prompt": "another"}, headers={"X-User-ID": "uA"})
    assert r2.json()["success"] is True


# ────────────────────────── 分轨重试 / 隔离 ──────────────────────────

def test_retry_stems_limit(isolated_db, fake_modal, disable_bg, monkeypatch):
    """9/10: 分轨失败时完整歌曲仍可下载（分轨 409）；重试达 MAX_AUTO_RETRIES 上限被拒（429）。"""
    async def _fail_separate(full_wav):
        return None

    monkeypatch.setattr(ai_music, "ace_step_separate", _fail_separate)
    c = _client()
    tid = task_store.new_task(user_key="uA", task_id="retry-limit")
    task_store.update(tid, state="completed_with_stems_failed", progress=100, stems_state="failed",
                      volume_files={"full_wav": "song_full.wav"},
                      download={"full_mp3": "music/retry-limit/full.mp3"})

    # 分轨失败但完整歌曲仍可下载（409 vs 200）
    assert c.get(f"/api/v1/ai/task/{tid}/download?file=vocals", headers={"X-User-ID": "uA"}).status_code == 409
    assert c.get(f"/api/v1/ai/task/{tid}/download?file=full", headers={"X-User-ID": "uA"}).status_code == 200

    # 第一次重试成功受理（计数 +1）
    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"X-User-ID": "uA"})
    assert r.status_code == 200, r.text
    assert task_store.get(tid)["stem_retries"] == 1

    # 等后台失败重试收敛（回到 completed_with_stems_failed）
    _wait_store(tid, {"completed_with_stems_failed"})

    # 达 MAX_AUTO_RETRIES=1 → 第二次被拒（429）
    r2 = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"X-User-ID": "uA"})
    assert r2.status_code == 429, r2.text


def test_retry_stems_success(isolated_db, fake_modal, disable_bg):
    """9: retry-stems 成功 → 状态回 completed、四轨可用、分轨可下载。"""
    c = _client()
    tid = task_store.new_task(user_key="uA", task_id="retry-ok")
    task_store.update(tid, state="completed_with_stems_failed", progress=100, stems_state="failed",
                      volume_files={"full_wav": "song_full.wav"},
                      download={"full_mp3": "music/retry-ok/full.mp3"})

    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"X-User-ID": "uA"})
    assert r.status_code == 200, r.text

    _wait_store(tid, {"completed"})
    poll = c.get(f"/api/v1/ai/task/{tid}", headers={"X-User-ID": "uA"}).json()
    assert poll["state"] == "completed"
    assert poll["stems_state"] == "ok"
    assert c.get(f"/api/v1/ai/task/{tid}/download?file=vocals", headers={"X-User-ID": "uA"}).status_code == 200


def test_cross_user_isolation_flow(isolated_db, fake_modal, disable_bg):
    """5: 用户 B 无法读取 / 下载用户 A 的任务（IDOR 防护贯穿 poll 与 download）。"""
    c = _client()
    r = c.post("/api/v1/ai/generate", json={"prompt": "song A"}, headers={"X-User-ID": "uA"})
    tid = r.json()["task_id"]
    _run_pipeline(disable_bg, tid)
    poll = _wait_terminal(c, tid, {"X-User-ID": "uA"})
    assert poll["state"] == "completed"
    assert c.get(f"/api/v1/ai/task/{tid}", headers={"X-User-ID": "uB"}).status_code == 403
    assert c.get(f"/api/v1/ai/task/{tid}/download?file=full", headers={"X-User-ID": "uB"}).status_code == 403