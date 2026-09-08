"""
Phase 3B-4A 验收测试：heartmula /generate 的 JWT 身份保护（不触真实 GPU/推理）。

覆盖：
  - 无 JWT → 401，且 reserve_generation 不被调用
  - 有 Bearer(A) + X-User-ID(B) → reserve_generation 使用 A（忽略 X-User-ID）
"""
import pytest
from fastapi.testclient import TestClient

from main import app
from app.services import auth_identity, ai_limits
from app.routers import heartmula

client = TestClient(app)

A = "00000000-0000-4000-8000-0000000000aa"
B = "00000000-0000-4000-8000-0000000000bb"


@pytest.fixture(autouse=True)
def _jwt_stub(monkeypatch):
    def _resolve(auth):
        if isinstance(auth, str) and auth.startswith("Bearer "):
            return auth[len("Bearer "):] or None
        return None
    monkeypatch.setattr(auth_identity, "resolve_auth_user_id", _resolve)


class _FakeService:
    local_mode = True

    async def generate_music(self, req):
        return {
            "success": True,
            "audio_url": "https://cdn.example.com/x.wav",
            "duration": 12.0,
            "sample_rate": 48000,
            "channels": 2,
            "format": "wav",
            "task_id": "heartmula-test",
            "metadata": {},
        }


def test_heartmula_generate_no_jwt_401(monkeypatch):
    seen = {"reserve": []}
    monkeypatch.setattr(ai_limits, "reserve_generation",
                        lambda uid, d=None: seen["reserve"].append(uid) or {"success": True})
    monkeypatch.setattr(heartmula, "get_heartmula_service", lambda: _FakeService())
    r = client.post("/api/v1/heartmula/generate", json={"prompt": "a test song"})
    assert r.status_code == 401
    assert seen["reserve"] == []  # 未进入 reserve / GPU


def test_heartmula_generate_identity_from_jwt_not_xheader(monkeypatch):
    seen = {}
    monkeypatch.setattr(ai_limits, "reserve_generation",
                        lambda uid, d=None: seen.setdefault("uid", uid) and {"success": True})
    monkeypatch.setattr(ai_limits, "refund_generation",
                        lambda uid, d=None, reason="": None)
    monkeypatch.setattr(heartmula, "get_heartmula_service", lambda: _FakeService())
    r = client.post(
        "/api/v1/heartmula/generate",
        json={"prompt": "a test song"},
        headers={"Authorization": f"Bearer {A}", "X-User-ID": B},
    )
    assert r.status_code == 200, r.text
    assert seen["uid"] == A  # 用 JWT 身份 A，忽略 X-User-ID B