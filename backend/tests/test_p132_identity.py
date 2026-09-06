"""P1-1 修复验证：predict / tts_run 身份只能来自 X-User-ID。

验证：
  1. 无 X-User-ID → 401
  2. 有 X-User-ID + body 提供其他 user_id → 使用 header 身份（body 不参与）
  3. 攻击者改 body.user_id → 不能获得新 quota（身份仍以 header 为准）
  4. client.host 改变 → 不改变 quota identity
  5. 合法请求仍能进入 reserve_generation（用记录 stub 验证收到的 user_id）
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import main as main_mod
from app.services import ai_limits


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


# ── 1. 无 X-User-ID → 401 ──────────────────────────────────────────
def test_predict_no_x_user_id_401(client, _patch):
    r = client.post("/api/v1/predict/tts", json={"text": "hi"})
    assert r.status_code == 401
    assert _patch["reserve"] == []  # 未扣额度


def test_tts_no_x_user_id_401(client, _patch):
    r = client.post("/api/v1/tts/run", json={"text": "hi", "reference_audio": "AAAA"})
    assert r.status_code == 401
    assert _patch["reserve"] == []


# ── 2. header 优先于 body.user_id ──────────────────────────────────
def test_predict_header_identity_used_not_body(client, _patch):
    r = client.post("/api/v1/predict/tts",
                    json={"text": "hi", "user_id": "attacker"},
                    headers={"X-User-ID": "legit-user"})
    assert r.status_code == 200, r.text
    assert _patch["reserve"] == ["legit-user"], "必须用 header 身份，而非 body.user_id"


def test_tts_header_identity_used_not_body(client, _patch):
    r = client.post("/api/v1/tts/run",
                    json={"text": "hi", "reference_audio": "AAAA", "user_id": "attacker"},
                    headers={"X-User-ID": "legit-user"})
    assert r.status_code == 200, r.text
    assert _patch["reserve"] == ["legit-user"]


# ── 3. 攻击者改 body.user_id 不能重置额度 ───────────────────────────
def test_predict_body_user_id_cannot_reset_quota(client, _patch):
    # 同一 header 身份，连续两次请求，body.user_id 每次不同
    r1 = client.post("/api/v1/predict/tts", json={"text": "hi", "user_id": "fake-1"},
                     headers={"X-User-ID": "victim"})
    r2 = client.post("/api/v1/predict/tts", json={"text": "hi", "user_id": "fake-2"},
                     headers={"X-User-ID": "victim"})
    assert r1.status_code == 200 and r2.status_code == 200
    # 两次 reserve 用的都是 header 身份，而不是 body 里不断变化的值
    assert _patch["reserve"] == ["victim", "victim"]


# ── 4. client.host 不改变身份（不同测试进程 host 相同，重点验证来源非 host） ──
def test_predict_identity_not_from_client_host(client, _patch):
    # 无 X-User-ID 时，即便 client 有 IP，也必须 401（不 fallback 到 host）
    r = client.post("/api/v1/predict/tts", json={"text": "hi"})
    assert r.status_code == 401
    assert _patch["reserve"] == []


# ── 5. 合法请求进入 reserve_generation ─────────────────────────────
def test_predict_legal_reaches_reserve(client, _patch):
    r = client.post("/api/v1/predict/tts", json={"text": "hi"},
                    headers={"X-User-ID": "ok-user"})
    assert r.status_code == 200
    assert _patch["reserve"] == ["ok-user"]
    assert _patch["create"] == ["tts"]  # 正常走到 factory.create


def test_tts_blank_header_401(client, _patch):
    r = client.post("/api/v1/tts/run", json={"text": "hi", "reference_audio": "AAAA"},
                    headers={"X-User-ID": "   "})
    assert r.status_code == 401