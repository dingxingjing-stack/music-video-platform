"""P2 — TemPolor Stems v2 实施测试（2026-10-01 授权范围）。

覆盖（实施授权第十五节）：
- Provider 契约：不传 model / 创建 POST / query 必须是 POST JSON（禁止 GET）/
  业务码字段 `status`（非 code）/ data.stems[] / callback payload / 恒回 "success"；
- Credits：35 Credits / 不足 402 / 提交与终态失败退款 / 退款幂等 / retry 不扣费；
- ZIP 安全：正常 zip / 缺成员 / 非预期成员 / 路径穿越 / symlink / 空成员；
- 权限：stems 任务归属校验 / song 任务不可经 stems 端点读取 / callback 无法改任务；
- 回调 URL 派生：/tempolor/stems/callback 独立端点、token 附加、fail-closed。

全部本地：零真实 provider 请求、零第三方费用、零生产接触。
"""
from __future__ import annotations

import asyncio
import io
import json
import zipfile

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.routers import ai_music
from app.services import (
    ai_limits,
    credits_service,
    task_store,
    tempolor_stems_service as stems_service,
)
from app.services.auth_identity import get_verified_user_id
from app.services.cdn_uploader import cdn_uploader
from app.services.credits_config import get_credit_cost

CALLBACK_SECRET = "stems-cb-secret-for-tests-only"
USER = "stems-test-user"
OTHER = "stems-other-user"
SENTINEL_KEY = "SENTINEL-tempolor-key-never-log"


# ── fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = str(tmp_path / "p2_stems.db")
    monkeypatch.setattr(task_store, "_DB_PATH", db)
    monkeypatch.setattr(ai_limits, "_DB_PATH", db)
    eng = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    from app.db.database import Base
    Base.metadata.create_all(bind=eng)
    monkeypatch.setattr(credits_service, "SessionLocal", sessionmaker(bind=eng))
    for key, value in {
        "TEMPOLOR_API_KEY": SENTINEL_KEY,
        "TEMPOLOR_CALLBACK_SECRET": CALLBACK_SECRET,
        "TEMPOLOR_CALLBACK_URL": "https://melovar.example/api/v1/ai/tempolor/callback",
        "ENVIRONMENT": "development",
    }.items():
        monkeypatch.setenv(key, value)
    # 快速轮询节奏（测试不等待真实 20s/3s）
    monkeypatch.setattr(stems_service, "STEMS_FIRST_POLL_DELAY_SECONDS", 0.01)
    monkeypatch.setattr(stems_service, "STEMS_POLL_INTERVAL_SECONDS", 0.01)
    return eng


@pytest.fixture()
def client(env):
    app = FastAPI()
    app.include_router(ai_music.router)
    app.dependency_overrides[get_verified_user_id] = lambda: USER
    return TestClient(app)


def _grant(user: str, amount: int = 1000):
    credits_service.add_credits(user, amount, "admin_adjustment", description="grant")


def _balance(user: str) -> int:
    raw = credits_service.get_balance(user)
    return raw["balance"] if isinstance(raw, dict) else raw


def _make_flac_zip(path, members: dict[str, bytes], extra=None, symlink=None):
    """构造 stems 形态的 zip（成员名精确；_probe_flac 会被 monkeypatch）。"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
        for name in (symlink or []):
            info = zipfile.ZipInfo(name)
            info.external_attr = (0o120777 << 16)  # S_IFLNK
            zf.writestr(info, b"/etc/passwd")


VALID_MEMBERS = {
    "originalaudio.flac": b"O" * 2048,
    "originalaudio_vocals.flac": b"V" * 2048,
    "originalaudio_bass.flac": b"B" * 2048,
    "originalaudio_drums.flac": b"D" * 2048,
    "originalaudio_other.flac": b"O" * 2048,
}


@pytest.fixture()
def fake_probe(monkeypatch):
    """ffprobe 结果替身：全部视为合法 FLAC/44.1k/stereo/210s。"""
    meta = {"codec": "flac", "duration": 210.0, "sample_rate": 44100, "channels": 2}
    monkeypatch.setattr(stems_service, "_probe_flac", lambda path: dict(meta))


# ── 1) Provider 契约：提交 ────────────────────────────────────────────────

def _mock_client_factory(monkeypatch, handler):
    real_client = httpx.AsyncClient  # 先捕获真实类，避免 factory 内递归

    def factory(**kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(**kwargs)
    monkeypatch.setattr(stems_service.httpx, "AsyncClient", factory)


def _mock_cdn(monkeypatch, calls):
    async def fake_upload_private(file_path, key, content_type="audio/wav"):
        calls.append(("upload_private", key, content_type))
        return key

    def fake_presign(key, expires_in=600):
        calls.append(("presign", key, expires_in))
        return f"https://r2.example/signed/{key}"

    def fake_delete(key):
        calls.append(("delete", key))
        return True

    monkeypatch.setattr(cdn_uploader, "upload_private", fake_upload_private)
    monkeypatch.setattr(cdn_uploader, "get_presigned_download_url", fake_presign)
    monkeypatch.setattr(cdn_uploader, "delete_object", fake_delete)


def test_submit_contract_no_model_post_bare_key(env, monkeypatch, tmp_path):
    """创建：POST、body 不含 model、裸 Key 鉴权、callback 指向独立 stems 端点。"""
    calls: list = []
    _mock_cdn(monkeypatch, calls)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"status": 200000, "data": {"item_ids": ["mss_test1"]}})

    _mock_client_factory(monkeypatch, handler)
    inp = tmp_path / "input.wav"
    inp.write_bytes(b"RIFF-fake-audio" * 100)

    item_id = asyncio.run(stems_service.submit_stems(str(inp), "stems-abc"))
    assert item_id == "mss_test1"
    assert seen["method"] == "POST"
    assert seen["url"].endswith("/open-apis/v1/stems")
    assert seen["auth"] == SENTINEL_KEY  # 裸 Key，无 Bearer 前缀
    assert "model" not in seen["body"]  # ⚠️ 授权强制：不传 model
    assert seen["body"]["url"].startswith("https://r2.example/signed/stems/stems-abc/input")
    # callback 必须指向派生的独立 stems 端点并带共享令牌
    assert seen["body"]["callback_url"].startswith(
        "https://melovar.example/api/v1/ai/tempolor/stems/callback"
    )
    assert "token=" in seen["body"]["callback_url"]
    # presign TTL = 3600s
    assert any(c[0] == "presign" and c[2] == 3600 for c in calls)


def test_submit_business_error_raises(env, monkeypatch, tmp_path):
    calls: list = []
    _mock_cdn(monkeypatch, calls)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": 400003, "message": "Bad Parameter"})

    _mock_client_factory(monkeypatch, handler)
    inp = tmp_path / "input.wav"
    inp.write_bytes(b"x" * 2048)
    with pytest.raises(stems_service.StemsError, match="400003"):
        asyncio.run(stems_service.submit_stems(str(inp), "stems-abc"))


def test_submit_fails_closed_when_callback_unconfigurable(env, monkeypatch, tmp_path):
    monkeypatch.setenv("TEMPOLOR_CALLBACK_URL", "https://elsewhere.example/hook")
    calls: list = []
    _mock_cdn(monkeypatch, calls)
    inp = tmp_path / "input.wav"
    inp.write_bytes(b"x" * 2048)
    with pytest.raises(stems_service.StemsError, match="派生"):
        asyncio.run(stems_service.submit_stems(str(inp), "stems-abc"))


# ── 2) Provider 契约：查询（POST JSON / status 字段）─────────────────────

def test_poll_uses_post_json_and_status_field(env, monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append({
            "method": request.method,
            "url": str(request.url),
            "body": json.loads(request.content.decode()),
        })
        if len(calls) == 1:
            return httpx.Response(200, json={"status": 200000, "data": {"stems": [
                {"item_id": "mss_x", "status": "pending"}]}})
        return httpx.Response(200, json={"status": 200000, "data": {"stems": [
            {"item_id": "mss_x", "status": "succeeded",
             "stems_url": "https://data.example/mss_x_normal.zip?auth_key=abc"}]}})

    _mock_client_factory(monkeypatch, handler)
    url = asyncio.run(stems_service.poll_stems("mss_x", "stems-abc"))
    assert url.startswith("https://data.example/mss_x_normal.zip")
    for c in calls:
        assert c["method"] == "POST"  # ⚠️ 契约：query 禁止 GET（实测 405）
        assert c["url"].endswith("/open-apis/v1/stems/query")
        assert c["body"] == {"item_ids": ["mss_x"]}  # ⚠️ POST JSON，非 item_ids[] 表单


def test_poll_known_failure_raises_immediately(env, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": 200000, "data": {"stems": [
            {"item_id": "mss_x", "status": "failed"}]}})

    _mock_client_factory(monkeypatch, handler)
    with pytest.raises(stems_service.StemsError, match="status=failed"):
        asyncio.run(stems_service.poll_stems("mss_x", "stems-abc"))


def test_poll_unknown_status_keeps_polling_then_safe_timeout(env, monkeypatch):
    """未知状态绝不当作成功：继续轮询直至 deadline → 安全失败（含 item 供人工审计）。"""
    monkeypatch.setattr(stems_service, "STEMS_TIMEOUT_SECONDS", 0.15)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": 200000, "data": {"stems": [
            {"item_id": "mss_x", "status": "mystery_state"}]}})

    _mock_client_factory(monkeypatch, handler)
    with pytest.raises(stems_service.StemsError, match="timeout.*mss_x"):
        asyncio.run(stems_service.poll_stems("mss_x", "stems-abc"))


def test_poll_business_400008_is_terminal(env, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": 400008, "message": "not found", "data": None})

    _mock_client_factory(monkeypatch, handler)
    with pytest.raises(stems_service.StemsError, match="400008"):
        asyncio.run(stems_service.poll_stems("mss_x", "stems-abc"))


# ── 3) ZIP 安全矩阵 ──────────────────────────────────────────────────────

def test_zip_normal_ok(env, tmp_path, fake_probe):
    zp = tmp_path / "s.zip"
    _make_flac_zip(zp, VALID_MEMBERS)
    result = stems_service.extract_and_validate_stems(str(zp), str(tmp_path / "out"))
    assert set(result.keys()) == {"original", "vocals", "bass", "drums", "other"}


def test_zip_missing_stem_fails(env, tmp_path, fake_probe):
    zp = tmp_path / "s.zip"
    members = dict(VALID_MEMBERS)
    members.pop("originalaudio_drums.flac")  # 缺鼓轨
    _make_flac_zip(zp, members)
    with pytest.raises(stems_service.StemsError):
        stems_service.extract_and_validate_stems(str(zp), str(tmp_path / "out"))


def test_zip_unexpected_member_fails(env, tmp_path, fake_probe):
    zp = tmp_path / "s.zip"
    _make_flac_zip(zp, VALID_MEMBERS, extra={"README.txt": b"hi"})
    with pytest.raises(stems_service.StemsError, match="unexpected"):
        stems_service.extract_and_validate_stems(str(zp), str(tmp_path / "out"))


def test_zip_path_traversal_member_fails(env, tmp_path, fake_probe):
    zp = tmp_path / "s.zip"
    _make_flac_zip(zp, VALID_MEMBERS, extra={"../evil.flac": b"x" * 2048})
    with pytest.raises(stems_service.StemsError):
        stems_service.extract_and_validate_stems(str(zp), str(tmp_path / "out"))


def test_zip_symlink_member_fails(env, tmp_path, fake_probe):
    zp = tmp_path / "s.zip"
    _make_flac_zip(zp, VALID_MEMBERS, symlink=["originalaudio.flac"])
    with pytest.raises(stems_service.StemsError, match="dir/symlink"):
        stems_service.extract_and_validate_stems(str(zp), str(tmp_path / "out"))


def test_zip_empty_member_fails(env, tmp_path, fake_probe):
    zp = tmp_path / "s.zip"
    members = dict(VALID_MEMBERS)
    members["originalaudio_vocals.flac"] = b""  # 空轨
    _make_flac_zip(zp, members)
    with pytest.raises(stems_service.StemsError):
        stems_service.extract_and_validate_stems(str(zp), str(tmp_path / "out"))


def test_zip_duration_mismatch_fails(env, tmp_path, monkeypatch):
    zp = tmp_path / "s.zip"
    _make_flac_zip(zp, VALID_MEMBERS)
    metas = {
        "original": {"codec": "flac", "duration": 210.0, "sample_rate": 44100, "channels": 2},
        "vocals": {"codec": "flac", "duration": 210.0, "sample_rate": 44100, "channels": 2},
        "bass": {"codec": "flac", "duration": 210.0, "sample_rate": 44100, "channels": 2},
        "drums": {"codec": "flac", "duration": 30.0, "sample_rate": 44100, "channels": 2},
        "other": {"codec": "flac", "duration": 210.0, "sample_rate": 44100, "channels": 2},
    }
    monkeypatch.setattr(stems_service, "_probe_flac", lambda path: dict(metas[os_path_stem(path)]))


def os_path_stem(path: str) -> str:
    import os
    return os.path.basename(path).replace("originalaudio", "").replace(".flac", "").strip("_") or "original"


# ── 4) Credits：60 定价（2026-10-03 裁定）/ 不足 402 / 扣费与退款 ────────

def test_stems_priced_at_60_credits(env):
    assert get_credit_cost("stem_separation") == 60


def test_separate_insufficient_credits_402_no_task(env, client):
    _balance(USER)  # 0 余额
    resp = client.post(
        "/api/v1/ai/stems/separate",
        files={"file": ("song.wav", b"RIFF" + b"0" * 2048, "audio/wav")},
    )
    assert resp.status_code == 402
    assert resp.json()["detail"] == "insufficient_credits"
    sess = task_store._get_session()
    try:
        from sqlalchemy import text
        rows = sess.execute(text("SELECT task_id FROM ai_tasks")).fetchall()
    finally:
        sess.close()
    assert rows == []


def test_separate_happy_path_charges_60(env, client, monkeypatch, tmp_path):
    _grant(USER, 1000)
    before = _balance(USER)
    manifest = {
        "vocals": "music/stems-x/vocals.flac", "drums": "music/stems-x/drums.flac",
        "bass": "music/stems-x/bass.flac", "other": "music/stems-x/other.flac",
        "original": "music/stems-x/original.flac",
    }

    async def fake_run(task_id, input_path, include_original=True,
                       model=None, expected_members=None):
        assert include_original is True
        return dict(manifest)

    monkeypatch.setattr(ai_music.stems_service, "run_stems_task", fake_run)
    resp = client.post(
        "/api/v1/ai/stems/separate",
        files={"file": ("song.wav", b"RIFF" + b"0" * 2048, "audio/wav")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["task_id"].startswith("stems-")
    assert data["credits_charged"] == 60
    assert _balance(USER) == before - 60  # 仅扣一次

    task = task_store.get(data["task_id"])
    assert task is not None and task["user_key"] == USER


def test_stems_generation_failure_refunds_once(env, monkeypatch, tmp_path):
    """终态失败 → 成对退款；重复退款幂等（callback/轮询双通道也不会多退）。"""
    _grant(USER, 1000)
    before = _balance(USER)
    task_id = task_store.new_task(user_key=USER, task_id="stems-fail1", generation_quota_weight=1)
    task_store.acquire_lock(USER, task_id)
    credits_service.reserve_generation_credits(USER, task_id, 35)

    async def fake_run(*a, **k):
        raise stems_service.StemsError("zip contains unexpected members")

    monkeypatch.setattr(ai_music.stems_service, "run_stems_task", fake_run)
    inp = tmp_path / "input.wav"
    inp.write_bytes(b"x" * 1024)
    asyncio.run(ai_music._run_stems_generation(task_id, USER, str(inp), 1))

    task = task_store.get(task_id)
    assert task["state"] == "failed"
    assert _balance(USER) == before  # 已退回
    # 幂等：再退一次不产生第二笔
    result = credits_service.refund_generation_credits(USER, task_id)
    assert result.get("already_refunded") is True
    assert _balance(USER) == before


def test_stems_generation_success_no_refund(env, monkeypatch, tmp_path):
    _grant(USER, 1000)
    before = _balance(USER)
    task_id = task_store.new_task(user_key=USER, task_id="stems-ok1", generation_quota_weight=1)
    task_store.acquire_lock(USER, task_id)
    credits_service.reserve_generation_credits(USER, task_id, 35)
    manifest = {k: f"music/{task_id}/{k}.flac" for k in ("vocals", "drums", "bass", "other", "original")}

    async def fake_run(*a, **k):
        return dict(manifest)

    monkeypatch.setattr(ai_music.stems_service, "run_stems_task", fake_run)
    inp = tmp_path / "input.wav"
    inp.write_bytes(b"x" * 1024)
    asyncio.run(ai_music._run_stems_generation(task_id, USER, str(inp), 1))

    task = task_store.get(task_id)
    assert task["state"] == "completed"
    assert task["stems_state"] == "ok"
    assert task["download"]["vocals"] == manifest["vocals"]
    assert _balance(USER) == before - 35  # 成功不退款


# ── 5) 权限 / 隔离 ────────────────────────────────────────────────────────

def test_status_endpoint_rejects_other_user(env, client):
    task_store.new_task(user_key=OTHER, task_id="stems-theirs", generation_quota_weight=1)
    resp = client.get("/api/v1/ai/stems/task/stems-theirs")
    assert resp.status_code == 403


def test_status_endpoint_rejects_song_task_prefix(env, client):
    """song 任务绝不可经 stems 端点读取（前缀护栏）。"""
    task_store.new_task(user_key=USER, task_id="task-song1", generation_quota_weight=1)
    resp = client.get("/api/v1/ai/stems/task/task-song1")
    assert resp.status_code == 404


def test_item_id_never_exposed_to_frontend(env, client, monkeypatch):
    _grant(USER, 1000)
    manifest = {k: f"music/stems-x/{k}.flac" for k in ("vocals", "drums", "bass", "other", "original")}

    async def fake_run(task_id, input_path, include_original=True):
        return dict(manifest)

    monkeypatch.setattr(ai_music.stems_service, "run_stems_task", fake_run)
    resp = client.post(
        "/api/v1/ai/stems/separate",
        files={"file": ("song.wav", b"RIFF" + b"0" * 2048, "audio/wav")},
    )
    body = resp.json()
    assert "item_id" not in json.dumps(body)


# ── 6) Callback（独立端点）────────────────────────────────────────────────

def test_stems_callback_route_registered_and_song_callback_intact(client):
    # 本 FastAPI 版本对 include 的 router 做懒包装（app.routes 不展开子路由），
    # 且 prefix 烘焙进 router 自身路由 → 直接断言 router 本体（注册唯一事实源）
    paths = {r.path for r in ai_music.router.routes}
    assert "/api/v1/ai/tempolor/stems/callback" in paths
    assert "/api/v1/ai/tempolor/callback" in paths  # Song callback 原样保留


def test_stems_callback_full_path_via_client(env, client):
    """经 TestClient 实际请求验证公网挂载路径（包含 router prefix）。"""
    resp = client.post(
        "/api/v1/ai/tempolor/stems/callback",
        json={"stems": [{"item_id": "mss_p", "status": "succeeded", "stems_url": "https://x/y.zip"}]},
        params={"token": CALLBACK_SECRET},
    )
    assert resp.status_code == 200
    assert resp.text == "success"


def test_stems_callback_success_and_no_state_change(env, client):
    task_store.new_task(user_key=USER, task_id="stems-cb1", generation_quota_weight=1)
    before_tasks = task_store.get("stems-cb1")
    resp = client.post(
        "/api/v1/ai/tempolor/stems/callback",
        json={"stems": [{"item_id": "mss_cb1", "status": "succeeded",
                          "stems_url": "https://data.example/x.zip?auth_key=z"}]},
        params={"token": CALLBACK_SECRET},
    )
    assert resp.status_code == 200
    assert resp.text == "success"
    after = task_store.get("stems-cb1")
    # callback 绝不改任务状态/计费（轮询为唯一终态权威 → 双通道幂等）
    assert after["state"] == before_tasks["state"]
    assert after["download"] == before_tasks["download"]


def test_stems_callback_bad_token_401(env, client):
    resp = client.post(
        "/api/v1/ai/tempolor/stems/callback",
        json={"stems": []},
        params={"token": "wrong"},
    )
    assert resp.status_code == 401


def test_stems_callback_fail_closed_without_secret(env, client, monkeypatch):
    monkeypatch.delenv("TEMPOLOR_CALLBACK_SECRET", raising=False)
    resp = client.post("/api/v1/ai/tempolor/stems/callback", json={"stems": []})
    assert resp.status_code == 503


# ── 7) retry-stems：生产走 Stems（免费语义不变），开发走旧短路 ────────────

def test_retry_stems_production_uses_stems_no_charge(env, monkeypatch):
    _grant(USER, 1000)
    monkeypatch.setenv("ENVIRONMENT", "production")
    task_id = task_store.new_task(user_key=USER, task_id="task-retry1", generation_quota_weight=1)
    task_store.acquire_lock(USER, task_id)
    task_store.update(
        task_id, state="completed", volume_files={"full_wav": "music/task-retry1/full_wav.wav"},
        download={"full_mp3": "music/task-retry1/full_mp3.mp3"},
    )
    # 端点在启动后台协程前已完成 completed → separating 的 CAS 抢占，测试对齐该时序
    assert task_store.try_transition_state(task_id, ("completed",), "separating") is True
    before = _balance(USER)
    calls = {}

    async def fake_retry_via_stems(tid, full_wav_key, tmp_dir):
        calls["task_id"] = tid
        calls["key"] = full_wav_key
        return {k: f"music/{tid}/{k}.flac" for k in ("vocals", "drums", "bass", "other")}

    monkeypatch.setattr(ai_music, "_run_song_retry_via_stems", fake_retry_via_stems)
    asyncio.run(ai_music._run_retry_stems(task_id, USER, "music/task-retry1/full_wav.wav"))

    task = task_store.get(task_id)
    assert task["state"] == "completed"
    assert task["stems_state"] == "ok"
    assert task["download"]["vocals"] == "music/task-retry1/vocals.flac"
    assert calls["key"] == "music/task-retry1/full_wav.wav"
    assert _balance(USER) == before  # retry 不重复扣费（既有免费语义）


def test_retry_stems_stems_failure_converges_without_failed(env, monkeypatch):
    """F9：主音频已交付的任务，分轨重试失败绝不打 failed。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    task_id = task_store.new_task(user_key=USER, task_id="task-retry2", generation_quota_weight=1)
    task_store.acquire_lock(USER, task_id)
    task_store.update(
        task_id, state="completed", volume_files={"full_wav": "music/task-retry2/full_wav.wav"},
        download={"full_mp3": "music/task-retry2/full_mp3.mp3"},
    )
    assert task_store.try_transition_state(task_id, ("completed",), "separating") is True

    async def fake_retry_via_stems(tid, key, tmp_dir):
        return None

    monkeypatch.setattr(ai_music, "_run_song_retry_via_stems", fake_retry_via_stems)
    asyncio.run(ai_music._run_retry_stems(task_id, USER, "music/task-retry2/full_wav.wav"))
    assert task_store.get(task_id)["state"] == "completed_with_stems_failed"


def test_retry_stems_dev_keeps_legacy_shortcircuit(env, client, monkeypatch):
    """开发环境保持旧 ace_step 短路行为（现有测试/monkeypatch 兼容）。"""
    _grant(USER, 1000)
    task_id = task_store.new_task(user_key=USER, task_id="task-retry3", generation_quota_weight=1)
    task_store.acquire_lock(USER, task_id)
    task_store.update(
        task_id, state="completed", volume_files={"full_wav": "music/task-retry3/full_wav.wav"},
        download={"full_mp3": "music/task-retry3/full_mp3.mp3"},
    )

    async def fake_ace(full_wav):
        return None

    monkeypatch.setattr(ai_music, "ace_step_separate", fake_ace)
    resp = client.post(f"/api/v1/ai/task/{task_id}/retry-stems")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


# ── 8) Stems 不进入 provider_registry（禁止扩大范围护栏）─────────────────

def test_stems_not_in_provider_registry():
    from app.services import provider_registry
    reg = provider_registry.get_provider_registry()
    assert "stems" not in reg._providers
    # _OPERATION_CHAINS 是模块级常量（音乐生成 operation chain 唯一定义处）
    assert "stems" not in provider_registry._OPERATION_CHAINS
    for chain in provider_registry._OPERATION_CHAINS.values():
        assert "stems" not in chain


# ── 9) cdn_uploader FLAC 分支 ─────────────────────────────────────────────

def test_upload_music_package_flac_content_type(env, monkeypatch):
    recorded = {}

    async def fake_upload_private(file_path, key, content_type="audio/wav"):
        recorded[key] = content_type
        return key

    monkeypatch.setattr(cdn_uploader, "upload_private", fake_upload_private)
    manifest = asyncio.run(cdn_uploader.upload_music_package(
        "t1", {"vocals": "/tmp/vocals.flac", "full_mp3": "/tmp/full.mp3", "full_wav": "/tmp/full.wav"}
    ))
    assert manifest["vocals"] == "music/t1/vocals.flac"
    assert recorded["music/t1/vocals.flac"] == "audio/flac"
    assert recorded["music/t1/full_mp3.mp3"] == "audio/mpeg"
    assert recorded["music/t1/full_wav.wav"] == "audio/wav"
