"""P1-1 修复验证：predict / tts_run 身份只能来自 Authorization Bearer JWT（verified auth.users.id）。

P5-B.7 起 predict/* 已整体退休为 410 Gone（端点退休守卫见 tests/test_e2e_integration.py），
本文件保留仍在线的 /api/v1/tts/run 身份用例。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import main as main_mod
from app.services import ai_limits, auth_identity


@pytest.fixture(autouse=True)
def _jwt_stub(monkeypatch):
    """Phase 3B：predict/tts_run 身份改为 Authorization Bearer JWT。测试环境打桩 resolve。"""
    def _resolve(auth):
        if isinstance(auth, str) and auth.startswith("Bearer "):
            return auth[len("Bearer "):] or None
        return None
    monkeypatch.setattr(auth_identity, "resolve_auth_user_id", _resolve)


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    # 禁止真实 GPU：reserve 记录、budget=False、factory.create 返回假服务
    calls = {"reserve": [], "create": []}

    # 让 tts_run 进入非 mock 分支（测试真实 quota 身份逻辑）
    monkeypatch.setattr(main_mod, "TTS_BACKEND_MODE", "real")

    monkeypatch.setattr(ai_limits, "budget_hard_stop_reached", lambda: False)

    def _reserve(user_id, duration=None):
        calls["reserve"].append(user_id)
        return {"success": True}

    monkeypatch.setattr(ai_limits, "reserve_generation", _reserve)

    class _DummySvc:
        async def predict(self, req):
            from app.services.inference import PredictResult, TaskStatus
            return PredictResult(task_id=req.task_id, status=TaskStatus.COMPLETED,
                                 progress=100, message="ok", metadata={})

    def _create(canonical, broadcast=None):
        calls["create"].append(canonical)
        return _DummySvc()

    monkeypatch.setattr(main_mod.factory, "create", _create)

    # tts_run real 分支会构造 GPTSovitsService + 后台 run_tts_and_save → 全部禁用，避免真实网络/GPU
    class _DummyGpt:
        def __init__(self, **kw):
            pass

    async def _noop_tts_save(*a, **k):
        return None

    monkeypatch.setattr(main_mod, "GPTSovitsService", _DummyGpt)
    monkeypatch.setattr(main_mod, "run_tts_and_save", _noop_tts_save)

    return calls


@pytest.fixture()
def client():
    return TestClient(main_mod.app)




def test_tts_no_x_user_id_401(client, _patch):
    r = client.post("/api/v1/tts/run", json={"text": "hi", "reference_audio": "AAAA"})
    assert r.status_code == 401
    assert _patch["reserve"] == []




def test_tts_header_identity_used_not_body(client, _patch):
    r = client.post("/api/v1/tts/run",
                    json={"text": "hi", "reference_audio": "AAAA", "user_id": "attacker"},
                    headers={"Authorization": "Bearer legit-user"})
    assert r.status_code == 200, r.text
    assert _patch["reserve"] == ["legit-user"]








def test_tts_blank_header_401(client, _patch):
    r = client.post("/api/v1/tts/run", json={"text": "hi", "reference_audio": "AAAA"},
                    headers={"Authorization": "Bearer "})
    assert r.status_code == 401