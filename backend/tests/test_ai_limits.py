"""测试：AI 生成额度/成本保护 + 授权下载（IDOR 防护/限流/审计）。"""

import tempfile

import pytest

from app.services import ai_limits, task_store
from app.routers import ai_music


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """每个测试使用独立 SQLite，避免污染 backend/data/beta.db。"""
    db_path = str(tmp_path / "test_beta.db")
    monkeypatch.setattr(ai_limits, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(ai_limits, "_DB_PATH", db_path)
    monkeypatch.setattr(task_store, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(task_store, "_DB_PATH", db_path)
    return db_path


def _task_for(user: str, task_id: str = "task-test-1") -> str:
    tid = task_store.new_task(user_key=user, task_id=task_id)
    prefix = f"music/{task_id}"
    task_store.update(tid, state="completed", progress=100, stems_state="ok", download={
        "full_mp3": f"{prefix}/full.mp3",
        "full_wav": f"{prefix}/full.wav",
        "vocals": f"{prefix}/vocals.wav",
        "drums": f"{prefix}/drums.wav",
        "bass": f"{prefix}/bass.wav",
        "other": f"{prefix}/other.wav",
    })
    return tid


def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(ai_music.router)
    return TestClient(app)


# ────────────────────────── 额度 / 成本保护 ──────────────────────────

def test_daily_limit_enforced(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 1)
    assert ai_limits.reserve_generation("u1")["success"] is True
    r2 = ai_limits.reserve_generation("u1")
    assert r2["success"] is False
    assert "今日" in r2["error"]
    ai_limits.refund_generation("u1")
    assert ai_limits.reserve_generation("u1")["success"] is True


def test_monthly_limit_enforced(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 2)
    for _ in range(2):
        assert ai_limits.reserve_generation("u2")["success"] is True
    assert ai_limits.reserve_generation("u2")["success"] is False


def test_global_daily_cost_guard(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 2)
    assert ai_limits.reserve_generation("u3")["success"] is True
    assert ai_limits.reserve_generation("u4")["success"] is True
    blocked = ai_limits.reserve_generation("u5")
    assert blocked["success"] is False
    assert "全平台" in blocked["error"]
    # 全局计数只增不减：失败退款不回退全局（防"失败→退款→重试"空转 GPU）
    ai_limits.refund_generation("u3")
    assert ai_limits.reserve_generation("u5")["success"] is False


def test_budget_hard_stop(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "1")
    assert ai_limits.reserve_generation("u6")["success"] is True
    blocked = ai_limits.reserve_generation("u7")
    assert blocked["success"] is False
    assert "预算" in blocked["error"]


def test_refund_never_below_zero(isolated_db):
    ai_limits.refund_generation("ghost")
    assert ai_limits.reserve_generation("ghost")["success"] is True


# ────────────────────────── 授权下载 / IDOR ──────────────────────────

def test_download_requires_matching_user(isolated_db, monkeypatch):
    monkeypatch.setattr(
        ai_music.cdn_uploader, "get_presigned_download_url",
        lambda key, expires_in=600: f"https://signed/{key}",
    )
    _task_for("userA", "task-idor-1")

    c = _client()
    # 用户 A 自己下载 → 200 + 预签名 URL
    r = c.get("/api/v1/ai/task/task-idor-1/download?file=full", headers={"X-User-ID": "userA"})
    assert r.status_code == 200, r.text
    assert "https://signed/music/task-idor-1/full.mp3" in r.json()["url"]

    # 用户 B 尝试下载用户 A 的 job → 403（IDOR 防护）
    r = c.get("/api/v1/ai/task/task-idor-1/download?file=full", headers={"X-User-ID": "userB"})
    assert r.status_code == 403

    # 未带 X-User-ID → 403
    r = c.get("/api/v1/ai/task/task-idor-1/download?file=full")
    assert r.status_code == 403

    # 不存在的 job → 404
    r = c.get("/api/v1/ai/task/task-none/download?file=full", headers={"X-User-ID": "userA"})
    assert r.status_code == 404


def test_download_full_wav_and_stems(isolated_db, monkeypatch):
    monkeypatch.setattr(
        ai_music.cdn_uploader, "get_presigned_download_url",
        lambda key, expires_in=600: f"https://signed/{key}",
    )
    _task_for("userA", "task-idor-2")
    c = _client()
    r = c.get("/api/v1/ai/task/task-idor-2/download?file=full&fmt=wav", headers={"X-User-ID": "userA"})
    assert r.status_code == 200 and "full.wav" in r.json()["url"]
    for stem in ("vocals", "drums", "bass", "other"):
        r = c.get(f"/api/v1/ai/task/task-idor-2/download?file={stem}", headers={"X-User-ID": "userA"})
        assert r.status_code == 200, f"{stem}: {r.text}"


def test_stem_download_blocked_when_stems_failed(isolated_db, monkeypatch):
    monkeypatch.setattr(
        ai_music.cdn_uploader, "get_presigned_download_url",
        lambda key, expires_in=600: f"https://signed/{key}",
    )
    tid = task_store.new_task(user_key="userA", task_id="task-stemfail")
    task_store.update(tid, state="completed_with_stems_failed", progress=100, stems_state="failed",
                      download={"full_mp3": "music/x/full.mp3"})
    c = _client()
    r = c.get("/api/v1/ai/task/task-stemfail/download?file=vocals", headers={"X-User-ID": "userA"})
    assert r.status_code == 409
    r = c.get("/api/v1/ai/task/task-stemfail/download?file=full", headers={"X-User-ID": "userA"})
    assert r.status_code == 200


def test_download_rate_limit(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "DOWNLOAD_RATE_LIMIT", 2)
    monkeypatch.setattr(
        ai_music.cdn_uploader, "get_presigned_download_url",
        lambda key, expires_in=600: f"https://signed/{key}",
    )
    _task_for("userR", "task-rate")
    c = _client()
    assert c.get("/api/v1/ai/task/task-rate/download", headers={"X-User-ID": "userR"}).status_code == 200
    assert c.get("/api/v1/ai/task/task-rate/download", headers={"X-User-ID": "userR"}).status_code == 200
    assert c.get("/api/v1/ai/task/task-rate/download", headers={"X-User-ID": "userR"}).status_code == 429


def test_task_poll_ownership(isolated_db, monkeypatch):
    monkeypatch.setattr(
        ai_music.cdn_uploader, "get_presigned_download_url",
        lambda key, expires_in=600: f"https://signed/{key}",
    )
    _task_for("userA", "task-poll")
    c = _client()
    assert c.get("/api/v1/ai/task/task-poll", headers={"X-User-ID": "userA"}).status_code == 200
    assert c.get("/api/v1/ai/task/task-poll", headers={"X-User-ID": "userB"}).status_code == 403
    # 不带头仍兼容（公测安全限制）
    assert c.get("/api/v1/ai/task/task-poll").status_code == 200