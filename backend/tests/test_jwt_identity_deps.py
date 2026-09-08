"""
Phase 3B-1 安全验收测试：后端 JWT 身份统一（不联真实 Supabase / AI / GPU）。

核心验收（依赖层行为）：
  1) 无 Authorization → 401
  2) 仅 X-User-ID（无 Authorization）→ 401（不再信任 X-User-ID）
  3) 有效 Bearer → 以 verified id 作为身份（dev/test 下映射为 token 部分）

其余端点级 IDOR/ownership 已由：
  - tests/test_ai_limits.py（download/poll ownership）
  - tests/test_retry_stems_security.py（retry ownership）
  - tests/test_workflow_quota.py（workflow a/b/c/d quota + 身份）
  - tests/test_ai_music_flow.py（ai_tasks 全链路 + 跨用户隔离）
覆盖并已随本轮改为 Authorization Bearer 模型。
"""
from fastapi.testclient import TestClient

from main import app
from app.services import auth_identity

client = TestClient(app)

AUTH_UUID = "00000000-0000-4000-8000-0000000000aa"
ATTACKER = "00000000-0000-4000-8000-0000000000bb"


def _stub_resolve(monkeypatch):
    """dev/test 下把 Authorization: Bearer <token> 映射为 token 本身。"""
    def _resolve(auth):
        if isinstance(auth, str) and auth.startswith("Bearer "):
            return auth[len("Bearer "):]
        return None
    monkeypatch.setattr(auth_identity, "resolve_auth_user_id", _resolve)


def test_dependency_missing_auth_401():
    r = client.get("/api/v1/ai/limits")
    assert r.status_code == 401


def test_dependency_x_user_id_alone_401():
    # 仅带 X-User-ID，无 Authorization → 401（X-User-ID 不再决定身份）
    r = client.get("/api/v1/ai/limits", headers={"X-User-ID": ATTACKER})
    assert r.status_code == 401


def test_dependency_valid_bearer_returns_uuid(monkeypatch):
    _stub_resolve(monkeypatch)
    r = client.get("/api/v1/ai/limits", headers={"Authorization": f"Bearer {AUTH_UUID}"})
    assert r.status_code == 200
    assert r.json()["user_id"] == AUTH_UUID