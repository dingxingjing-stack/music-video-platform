"""P4-B2 Phase A-17 测试：Cover 恢复（TemPolor tempolor-latest，action=upload_cover）。

覆盖 A-17 授权 §三/§六/§八/§九：
- 契约：action="upload_cover" + upload_audio_url + model 锁定 tempolor-latest +
  callback_url 必填；歌词为空 → 不传 lyrics（供应商自动写词 +7 点，行为保留）；
- 禁令：Cover 不支持 instrumental（non_retryable）；tempolor-latest-cover 旧键不复用；
  Reference 保持下线（422 / chain ValueError）；
- Credits：cover_song 未定价 → /generate fail-closed 503 cover_not_priced（先于任务/Credits）；
  Reference 判定不受 cover 字段污染；
- 参考音频：_upload_cover_reference 解码/格式/大小校验 + R2 私有上传 + presigned URL；
  失败 → CoverReferenceError（上层统一 failed + 恰好一次退款）；
- 240s 门：cover 与其他操作共用 _enforce_duration_gate（链循环后统一执行，无旁路）。

全部 mock，零真实 API、零费用。
"""
from __future__ import annotations

import asyncio
import base64
import json
import zipfile
from io import BytesIO

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import ai_music
from app.routers.ai_music import (
    CoverReferenceError,
    GenerateRequest,
    _upload_cover_reference,
    determine_generation_operation,
)
from app.services.provider_registry import get_provider_registry
from app.services.tempolor_provider import TempolorProvider
from app.services.credits_config import get_credit_cost


USER = "a17-cover-user"
_WAV_HEAD = b"RIFF" + b"\x00" * 8
_VALID_WAV = _WAV_HEAD + b"\x00" * 4096  # magic bytes 合法（上传链路 mock，不做真实解码）


# ── 1) Operation 判定 ────────────────────────────────────────────────────

def test_operation_cover_with_reference():
    req = GenerateRequest(prompt="test prompt", reference_audio_b64="QUJD", cover=True)
    assert determine_generation_operation(req) == "cover"


def test_operation_reference_without_cover_flag():
    req = GenerateRequest(prompt="test prompt", reference_audio_b64="QUJD")
    assert determine_generation_operation(req) == "reference"


def test_operation_cover_without_reference_falls_through():
    req = GenerateRequest(prompt="test prompt", cover=True)
    assert determine_generation_operation(req) == "normal"


# ── 2) Provider 契约 ─────────────────────────────────────────────────────

def _provider_with_mock_http(monkeypatch, submit_handler):
    """把 TempolorProvider.generate 的 httpx.AsyncClient 换成 MockTransport。"""
    real_client = httpx.AsyncClient

    def factory(**kwargs):
        kwargs["transport"] = httpx.MockTransport(submit_handler)
        return real_client(**kwargs)

    monkeypatch.setattr("app.services.tempolor_provider.httpx.AsyncClient", factory)
    monkeypatch.setenv("TEMPOLOR_API_KEY", "sentinel-key-never-log")
    monkeypatch.setenv("TEMPOLOR_CALLBACK_URL", "https://melovar.example/api/v1/ai/tempolor/callback")
    monkeypatch.setattr("app.services.tempolor_provider.TEMPOLOR_POLL_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr("app.services.tempolor_provider.TEMPOLOR_CALLBACK_URL",
                        "https://melovar.example/api/v1/ai/tempolor/callback")


def _submit_ok_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/song/generate"):
        return httpx.Response(200, json={"status": 200000, "data": {"item_ids": ["cov1"]}})
    if request.url.path.endswith("/song/query"):
        return httpx.Response(200, json={
            "status": 200000,
            "data": {"songs": [{"item_id": "cov1", "status": "succeeded",
                                 "audio_url": "https://cdn.example/a.mp3", "duration": 250}]},
        })
    return httpx.Response(404)


def test_cover_payload_contract(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/song/generate"):
            captured["payload"] = json.loads(request.content)
        return _submit_ok_handler(request)

    _provider_with_mock_http(monkeypatch, handler)
    monkeypatch.setattr("app.services.tempolor_provider._download_audio",
                        lambda url, dest_dir=None: __import__("os").devnull)

    provider = TempolorProvider()
    result = asyncio.run(
        provider.generate({
            "prompt": "dreamy pop",
            "lyrics": "verse",
            "cover_reference_url": "https://r2.example/cover/t1/reference.mp3",
            "is_instrumental": False,
            "duration": 270,
        })
    )
    assert result["success"] is True
    p = captured["payload"]
    assert p["action"] == "upload_cover"
    assert p["upload_audio_url"] == "https://r2.example/cover/t1/reference.mp3"
    assert p["model"] == "tempolor-latest"
    assert p["callback_url"]  # 官方强制非空
    assert p["lyrics"] == "verse"
    assert "instrumental" not in p  # Cover 不支持纯音乐，不发送该字段


def test_cover_empty_lyrics_auto_lyric_preserved(monkeypatch):
    """歌词为空 → 不传 lyrics → 供应商自动调用 Lyric v1（+7 点，行为保留）。"""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/song/generate"):
            captured["payload"] = json.loads(request.content)
        return _submit_ok_handler(request)

    _provider_with_mock_http(monkeypatch, handler)
    monkeypatch.setattr("app.services.tempolor_provider._download_audio",
                        lambda url, dest_dir=None: __import__("os").devnull)

    provider = TempolorProvider()
    result = asyncio.run(
        provider.generate({
            "prompt": "dreamy pop",
            "lyrics": "",
            "cover_reference_url": "https://r2.example/cover/t1/reference.mp3",
        })
    )
    assert result["success"] is True
    assert "lyrics" not in captured["payload"]  # 不传 → 供应商自动写词
    assert "instrumental" not in captured["payload"]


def test_cover_rejects_instrumental(monkeypatch):
    monkeypatch.setenv("TEMPOLOR_API_KEY", "sentinel-key-never-log")
    monkeypatch.setattr("app.services.tempolor_provider.TEMPOLOR_CALLBACK_URL",
                        "https://melovar.example/api/v1/ai/tempolor/callback")
    provider = TempolorProvider()
    result = asyncio.run(
        provider.generate({
            "prompt": "bgm",
            "cover_reference_url": "https://r2.example/x.mp3",
            "is_instrumental": True,
        })
    )
    assert result["success"] is False
    assert result.get("non_retryable") is True
    assert "纯音乐" in result["error"] or "instrumental" in result["error"]


def test_non_cover_path_has_no_action_key(monkeypatch):
    """回归：普通生成不带 cover_reference_url → payload 无 action/upload_cover。"""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/song/generate"):
            captured["payload"] = json.loads(request.content)
        return _submit_ok_handler(request)

    _provider_with_mock_http(monkeypatch, handler)
    monkeypatch.setattr("app.services.tempolor_provider._download_audio",
                        lambda url, dest_dir=None: __import__("os").devnull)
    monkeypatch.setattr(
        "app.services.tempolor_provider.select_music_model",
        lambda **kw: type("S", (), {"model": type("M", (), {
            "id_confirmed": True, "api_model_id": "tempolor-latest", "key": "tempolor-latest",
        })(), "total_cost_cny": 0.3})(),
    )

    provider = TempolorProvider()
    result = asyncio.run(
        provider.generate({"prompt": "normal song", "lyrics": "", "duration": 270})
    )
    assert result["success"] is True
    assert "action" not in captured["payload"]
    assert "upload_cover" not in json.dumps(captured["payload"])


# ── 3) 链路注册 ──────────────────────────────────────────────────────────

def test_cover_chain_is_tempolor_only():
    chain = get_provider_registry().chain_for_operation("cover")
    assert [p.name for p in chain] == ["tempolor"]


def test_reference_chain_still_rejected():
    with pytest.raises(ValueError):
        get_provider_registry().chain_for_operation("reference")


# ── 4) 端点层：fail-closed 定价门 + Reference 422 ────────────────────────

@pytest.fixture()
def client(monkeypatch, tmp_path):
    from app.services import ai_limits, task_store
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db = str(tmp_path / "a17_cover.db")
    monkeypatch.setattr(task_store, "_DB_PATH", db)
    monkeypatch.setattr(ai_limits, "_DB_PATH", db)
    eng = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    from app.db.database import Base
    Base.metadata.create_all(bind=eng)

    app = FastAPI()
    app.include_router(ai_music.router)
    from app.services.auth_identity import get_verified_user_id
    app.dependency_overrides[get_verified_user_id] = lambda: USER
    return TestClient(app)


def test_generate_cover_unpriced_fail_closed(client):
    """cover_song 无定价（credit_cost=0）→ 503 cover_not_priced，先于任务创建。"""
    assert get_credit_cost("cover_song") is None
    resp = client.post("/api/v1/ai/generate", json={
        "prompt": "cover it",
        "cover": True,
        "reference_audio_b64": base64.b64encode(_VALID_WAV).decode(),
    })
    assert resp.status_code == 503
    assert resp.json()["detail"] == "cover_not_priced"


def test_generate_reference_still_422(client):
    resp = client.post("/api/v1/ai/generate", json={
        "prompt": "mimic this",
        "reference_audio_b64": base64.b64encode(_VALID_WAV).decode(),
    })
    assert resp.status_code == 422
    assert resp.json()["detail"] == "reference_cover_feature_discontinued"


# ── 5) 参考音频上传 helper ────────────────────────────────────────────────

def test_upload_cover_reference_rejects_garbage_base64():
    with pytest.raises(CoverReferenceError):
        asyncio.run(
            _upload_cover_reference("task-1", "!!!not-base64!!!")
        )


def test_upload_cover_reference_rejects_too_small():
    tiny = base64.b64encode(b"RIFF" + b"\x00" * 4).decode()
    with pytest.raises(CoverReferenceError):
        asyncio.run(
            _upload_cover_reference("task-1", tiny)
        )


def test_upload_cover_reference_rejects_wrong_format():
    payload = base64.b64encode(b"NOTAUDIO" * 1000).decode()
    with pytest.raises(CoverReferenceError):
        asyncio.run(
            _upload_cover_reference("task-1", payload)
        )


def test_upload_cover_reference_success(monkeypatch):
    uploaded = {}

    class _FakeUploader:
        async def upload_private(self, local_path, key):
            uploaded["key"] = key
            uploaded["local_path"] = local_path

        def get_presigned_download_url(self, key, expires_in=600):
            uploaded["presigned_key"] = key
            return f"https://r2.example/{key}?sig=abc"

    import app.services.cdn_uploader as cdn_mod
    monkeypatch.setattr(cdn_mod, "cdn_uploader", _FakeUploader())

    url = asyncio.run(
        _upload_cover_reference("task-cover-1", base64.b64encode(_VALID_WAV).decode())
    )
    assert uploaded["key"] == "cover/task-cover-1/reference.wav"
    assert uploaded["presigned_key"] == uploaded["key"]
    assert url.startswith("https://r2.example/cover/task-cover-1/reference.wav")


# ── 6) 240s 门覆盖 cover（共用唯一出口，无旁路）──────────────────────────

def test_cover_gate_shares_enforce_duration_gate():
    """cover 与 normal/lyric_to_music 走同一链循环 → 同一 _enforce_duration_gate。

    静态确认：_run_generation 中 cover_reference_url 分支不引入独立交付路径，
    交付仍必须经过 _enforce_duration_gate + _upload_and_finalize。
    """
    import inspect
    src = inspect.getsource(ai_music._run_generation)
    assert "_enforce_duration_gate(volume_result)" in src
    # HF 兜底仅 normal/lyric_to_music：cover 不进 HF（无绕过 240s 门的旁路）
    assert 'operation in ("normal", "lyric_to_music")' in src


# ── A-18.1 增补：240s 门实测语义 / 输入边界 / legacy 禁令 / 定价 reserve / 恰一次退款 ──

import asyncio as _asyncio


# 16/17) duration gate：实测时长语义（_measured_duration_sec 直注，不依赖 ffprobe）

@pytest.mark.parametrize("measured,ok", [(240.0, True), (239.9, False), (300.0, True), (600.0, True)])
def test_duration_gate_measured_duration(measured, ok):
    from app.routers.ai_music import DurationValidationError, _enforce_duration_gate
    if ok:
        got = _asyncio.run(_enforce_duration_gate({"_measured_duration_sec": measured}))
        assert got == measured  # 绝不截断
    else:
        with pytest.raises(DurationValidationError):
            _asyncio.run(_enforce_duration_gate({"_measured_duration_sec": measured}))


def test_duration_gate_no_deliverable_raises():
    from app.routers.ai_music import DurationValidationError, _enforce_duration_gate
    with pytest.raises(DurationValidationError):
        _asyncio.run(_enforce_duration_gate({"full_mp3": "Z:/nonexistent/x.mp3",
                                             "_local_path": "Z:/nonexistent/x.mp3"}))


# 4) >10MB 拒绝 / 5) MP3 (ID3) 接受

def test_upload_cover_reference_rejects_over_10mb():
    big = base64.b64encode(_WAV_HEAD + b"\x00" * (11 * 1024 * 1024)).decode()
    with pytest.raises(CoverReferenceError):
        _asyncio.run(_upload_cover_reference("task-big", big))


def test_upload_cover_reference_accepts_mp3_id3(monkeypatch):
    mp3 = b"ID3" + b"\x03\x00" + b"\x00" * 4096
    uploaded = {}

    class _FakeUploader:
        async def upload_private(self, local_path, key):
            uploaded["key"] = key

        def get_presigned_download_url(self, key, expires_in=600):
            return f"https://r2.example/{key}?sig=abc"

    import app.services.cdn_uploader as cdn_mod
    monkeypatch.setattr(cdn_mod, "cdn_uploader", _FakeUploader())
    url = _asyncio.run(_upload_cover_reference("task-mp3", base64.b64encode(mp3).decode()))
    assert uploaded["key"] == "cover/task-mp3/reference.mp3"


# 22/23) legacy 键禁令（registry + payload 字符串级）

def test_no_legacy_tempolor_latest_cover_registry_entry():
    from app.services.model_registry import MODELS
    assert "tempolor-latest-cover" not in MODELS
    assert "cover" not in {m.operation for m in MODELS.values()}  # registry 无 cover 条目=Cover 走 provider 常量


def test_cover_payload_never_contains_legacy_key(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/song/generate"):
            captured["raw"] = request.content.decode("utf-8", "replace")
        return _submit_ok_handler(request)

    _provider_with_mock_http(monkeypatch, handler)
    monkeypatch.setattr("app.services.tempolor_provider._download_audio",
                        lambda url, dest_dir=None: "C:/tmp/fake.mp3")
    provider = TempolorProvider()
    result = _asyncio.run(provider.generate({
        "prompt": "dreamy pop", "lyrics": "verse",
        "cover_reference_url": "https://r2.example/x.mp3",
    }))
    assert result["success"] is True
    assert "tempolor-latest-cover" not in captured["raw"]


# 2 全链路) cover_song 定价后 reserve 金额正确（fail-closed 解除的唯一路径 = 定价）

def test_cover_priced_reserve_uses_cover_song(client, monkeypatch):
    from app.services import credits_config as cc
    from app.services import credits_service as cs
    monkeypatch.setitem(cc.CREDIT_COSTS, "cover_song",
                        {**cc.CREDIT_COSTS["cover_song"], "credit_cost": 40})
    captured = {}

    def fake_reserve(user_key, task_id, credit_cost):
        captured["cost"] = credit_cost
        return {"success": True}

    monkeypatch.setattr(ai_music.credits_service, "reserve_generation_credits", fake_reserve)

    async def noop_timeout(*a, **kw):
        return None

    monkeypatch.setattr(ai_music, "_run_with_timeout", noop_timeout)

    resp = client.post("/api/v1/ai/generate", json={
        "prompt": "cover it please",
        "cover": True,
        "reference_audio_b64": base64.b64encode(_VALID_WAV).decode(),
    })
    assert resp.status_code == 200
    assert captured["cost"] == 40  # 定价后 reserve 精确按 cover_song 扣


# 18) chain 失败 → refund exactly once（cover 链，ENVIRONMENT=production 无 HF）

def test_cover_chain_failure_refunds_exactly_once(monkeypatch, tmp_path):
    from app.services import ai_limits, task_store
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db = str(tmp_path / "a181_refund.db")
    monkeypatch.setattr(task_store, "_DB_PATH", db)
    monkeypatch.setattr(ai_limits, "_DB_PATH", db)
    eng = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    from app.db.database import Base
    Base.metadata.create_all(bind=eng)

    monkeypatch.setenv("ENVIRONMENT", "production")  # HF 兜底生产关闭 → 链失败直达退款

    class FakeRegistry:
        class _P:
            name = "tempolor"

            async def generate(self, request):
                return {"success": False, "error": "supplier down"}

        def chain_for_operation(self, operation, song_language=None):
            assert operation == "cover"  # 只允许 cover 链进入本测试
            return [self._P()]

    monkeypatch.setattr(ai_music, "get_provider_registry", lambda: FakeRegistry())

    refund_calls = {"credits": 0, "quota": 0}
    monkeypatch.setattr(
        ai_music.credits_service, "refund_generation_credits",
        lambda *a, **kw: refund_calls.__setitem__("credits", refund_calls["credits"] + 1),
    )
    monkeypatch.setattr(
        ai_music, "refund_generation",
        lambda *a, **kw: refund_calls.__setitem__("quota", refund_calls["quota"] + 1),
    )

    task_id = "stems-not-" + "x" * 0 + "song-cover-t1"
    task_store.new_task(user_key="u1", task_id=task_id, generation_quota_weight=1)
    req = GenerateRequest(prompt="cover it please", cover=True,
                          reference_audio_b64=base64.b64encode(_VALID_WAV).decode())

    async def no_upload_reference(*a, **kw):
        return "https://r2.example/fake-ref.mp3"

    monkeypatch.setattr(ai_music, "_upload_cover_reference", no_upload_reference)

    _asyncio.run(ai_music._run_generation(task_id, req, "u1", 1))

    assert refund_calls["credits"] == 1  # exactly once
    assert refund_calls["quota"] == 1
    task = task_store.get(task_id)
    assert task["state"] == "failed"


# ── A-18.1 增补：240s 门实测语义 / 输入边界 / legacy 禁令 / 定价 reserve / 恰一次退款 ──

import asyncio as _asyncio


# 16/17) duration gate：实测时长语义（_measured_duration_sec 直注，不依赖 ffprobe）

@pytest.mark.parametrize("measured,ok", [(240.0, True), (239.9, False), (300.0, True), (600.0, True)])
def test_duration_gate_measured_duration(measured, ok):
    from app.routers.ai_music import DurationValidationError, _enforce_duration_gate
    if ok:
        got = _asyncio.run(_enforce_duration_gate({"_measured_duration_sec": measured}))
        assert got == measured  # 绝不截断
    else:
        with pytest.raises(DurationValidationError):
            _asyncio.run(_enforce_duration_gate({"_measured_duration_sec": measured}))


def test_duration_gate_no_deliverable_raises():
    from app.routers.ai_music import DurationValidationError, _enforce_duration_gate
    with pytest.raises(DurationValidationError):
        _asyncio.run(_enforce_duration_gate({"full_mp3": "Z:/nonexistent/x.mp3",
                                             "_local_path": "Z:/nonexistent/x.mp3"}))


# 4) >10MB 拒绝 / 5) MP3 (ID3) 接受

def test_upload_cover_reference_rejects_over_10mb():
    big = base64.b64encode(_WAV_HEAD + b"\x00" * (11 * 1024 * 1024)).decode()
    with pytest.raises(CoverReferenceError):
        _asyncio.run(_upload_cover_reference("task-big", big))


def test_upload_cover_reference_accepts_mp3_id3(monkeypatch):
    mp3 = b"ID3" + b"\x03\x00" + b"\x00" * 4096
    uploaded = {}

    class _FakeUploader:
        async def upload_private(self, local_path, key):
            uploaded["key"] = key

        def get_presigned_download_url(self, key, expires_in=600):
            return f"https://r2.example/{key}?sig=abc"

    import app.services.cdn_uploader as cdn_mod
    monkeypatch.setattr(cdn_mod, "cdn_uploader", _FakeUploader())
    url = _asyncio.run(_upload_cover_reference("task-mp3", base64.b64encode(mp3).decode()))
    assert uploaded["key"] == "cover/task-mp3/reference.mp3"


# 22/23) legacy 键禁令（registry + payload 字符串级）

def test_no_legacy_tempolor_latest_cover_registry_entry():
    from app.services.model_registry import MODELS
    assert "tempolor-latest-cover" not in MODELS
    assert "cover" not in {m.operation for m in MODELS.values()}  # registry 无 cover 条目=Cover 走 provider 常量


def test_cover_payload_never_contains_legacy_key(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/song/generate"):
            captured["raw"] = request.content.decode("utf-8", "replace")
        return _submit_ok_handler(request)

    _provider_with_mock_http(monkeypatch, handler)
    monkeypatch.setattr("app.services.tempolor_provider._download_audio",
                        lambda url, dest_dir=None: "C:/tmp/fake.mp3")
    provider = TempolorProvider()
    result = _asyncio.run(provider.generate({
        "prompt": "dreamy pop", "lyrics": "verse",
        "cover_reference_url": "https://r2.example/x.mp3",
    }))
    assert result["success"] is True
    assert "tempolor-latest-cover" not in captured["raw"]


# 2 全链路) cover_song 定价后 reserve 金额正确（fail-closed 解除的唯一路径 = 定价）

def test_cover_priced_reserve_uses_cover_song(client, monkeypatch):
    from app.services import credits_config as cc
    from app.services import credits_service as cs
    monkeypatch.setitem(cc.CREDIT_COSTS, "cover_song",
                        {**cc.CREDIT_COSTS["cover_song"], "credit_cost": 40})
    captured = {}

    def fake_reserve(user_key, task_id, credit_cost):
        captured["cost"] = credit_cost
        return {"success": True}

    monkeypatch.setattr(ai_music.credits_service, "reserve_generation_credits", fake_reserve)

    async def noop_timeout(*a, **kw):
        return None

    monkeypatch.setattr(ai_music, "_run_with_timeout", noop_timeout)

    resp = client.post("/api/v1/ai/generate", json={
        "prompt": "cover it please",
        "cover": True,
        "reference_audio_b64": base64.b64encode(_VALID_WAV).decode(),
    })
    assert resp.status_code == 200
    assert captured["cost"] == 40  # 定价后 reserve 精确按 cover_song 扣


# 18) chain 失败 → refund exactly once（cover 链，ENVIRONMENT=production 无 HF）

def test_cover_chain_failure_refunds_exactly_once(monkeypatch, tmp_path):
    from app.services import ai_limits, task_store
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db = str(tmp_path / "a181_refund.db")
    monkeypatch.setattr(task_store, "_DB_PATH", db)
    monkeypatch.setattr(ai_limits, "_DB_PATH", db)
    eng = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    from app.db.database import Base
    Base.metadata.create_all(bind=eng)

    monkeypatch.setenv("ENVIRONMENT", "production")  # HF 兜底生产关闭 → 链失败直达退款

    class FakeRegistry:
        class _P:
            name = "tempolor"

            async def generate(self, request):
                return {"success": False, "error": "supplier down"}

        def chain_for_operation(self, operation, song_language=None):
            assert operation == "cover"  # 只允许 cover 链进入本测试
            return [self._P()]

    monkeypatch.setattr(ai_music, "get_provider_registry", lambda: FakeRegistry())

    refund_calls = {"credits": 0, "quota": 0}
    monkeypatch.setattr(
        ai_music.credits_service, "refund_generation_credits",
        lambda *a, **kw: refund_calls.__setitem__("credits", refund_calls["credits"] + 1),
    )
    monkeypatch.setattr(
        ai_music, "refund_generation",
        lambda *a, **kw: refund_calls.__setitem__("quota", refund_calls["quota"] + 1),
    )

    task_id = "stems-not-" + "x" * 0 + "song-cover-t1"
    task_store.new_task(user_key="u1", task_id=task_id, generation_quota_weight=1)
    req = GenerateRequest(prompt="cover it please", cover=True,
                          reference_audio_b64=base64.b64encode(_VALID_WAV).decode())

    async def no_upload_reference(*a, **kw):
        return "https://r2.example/fake-ref.mp3"

    monkeypatch.setattr(ai_music, "_upload_cover_reference", no_upload_reference)

    _asyncio.run(ai_music._run_generation(task_id, req, "u1", 1))

    assert refund_calls["credits"] == 1  # exactly once
    assert refund_calls["quota"] == 1
    task = task_store.get(task_id)
    assert task["state"] == "failed"
