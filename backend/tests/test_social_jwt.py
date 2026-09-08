"""
Phase 3B-3 Social JWT 身份迁移测试（不联真实 Supabase Auth / 不落盘真实 social.db）。

覆盖：
  - 写端点无 JWT → 401
  - 写端点有 JWT → user_id = verified auth id（非 X-User-ID）
  - X-User-ID 伪造 → 不改变身份
  - GET /stats、/feed 匿名可访问；有 JWT 时个性化用 verified id
  - follow/unfollow 的 body.user_id 仍是目标用户 ID，当前身份来自 JWT
"""
import pytest
from fastapi.testclient import TestClient

from main import app
from app.services import auth_identity
from app.models.social import social_storage

client = TestClient(app)

AUTH_UUID = "00000000-0000-4000-8000-0000000000aa"
TARGET_USER = "00000000-0000-4000-8000-0000000000bb"


@pytest.fixture(autouse=True)
def _jwt_stub(monkeypatch):
    def _resolve(auth):
        if isinstance(auth, str) and auth.startswith("Bearer "):
            return auth[len("Bearer "):]
        return None
    monkeypatch.setattr(auth_identity, "resolve_auth_user_id", _resolve)


def _capture(method_name):
    captured = {}

    def _fn(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return True  # add_like/remove_* 均接受，避免真实库写入

    return captured, _fn


def test_write_no_jwt_401(monkeypatch):
    for ep in ("like", "unlike", "favorite", "unfavorite", "follow", "unfollow"):
        r = client.post(f"/api/v1/social/{ep}", json={"work_id": "w1", "user_id": TARGET_USER})
        assert r.status_code == 401, (ep, r.text)


def test_write_jwt_uses_verified_id(monkeypatch):
    captured, fn = _capture("add_like")
    monkeypatch.setattr(social_storage, "add_like", fn)
    r = client.post(
        "/api/v1/social/like",
        json={"work_id": "w1"},
        headers={"Authorization": f"Bearer {AUTH_UUID}", "X-User-ID": TARGET_USER},
    )
    assert r.status_code == 200, r.text
    # 身份必须是 JWT 的 AUTH_UUID，而非 X-User-ID 的 TARGET_USER
    assert captured["args"][0] == AUTH_UUID
    assert captured["args"][1] == "w1"


def test_follow_body_target_and_jwt_identity(monkeypatch):
    captured, fn = _capture("add_follow")
    monkeypatch.setattr(social_storage, "add_follow", fn)
    monkeypatch.setattr(social_storage, "get_follower_count", lambda x: 0)
    r = client.post(
        "/api/v1/social/follow",
        json={"user_id": TARGET_USER},
        headers={"Authorization": f"Bearer {AUTH_UUID}"},
    )
    assert r.status_code == 200, r.text
    # add_follow(user_id=当前JWT, target_user_id=body.user_id)
    assert captured["args"][0] == AUTH_UUID        # 当前用户 = JWT
    assert captured["args"][1] == TARGET_USER       # 目标用户 = body.user_id


def test_stats_anon_ok(monkeypatch):
    monkeypatch.setattr(social_storage, "get_work_stats",
                        lambda wid: type("W", (), {"likes": 1, "favorites": 2, "plays": 3})())
    monkeypatch.setattr(social_storage, "is_liked", lambda u, w: False)
    monkeypatch.setattr(social_storage, "is_favorited", lambda u, w: False)
    r = client.get("/api/v1/social/stats/w1")
    assert r.status_code == 200
    assert r.json()["is_liked"] is False
    assert r.json()["is_favorited"] is False


def test_stats_jwt_personalized(monkeypatch):
    monkeypatch.setattr(social_storage, "get_work_stats",
                        lambda wid: type("W", (), {"likes": 1, "favorites": 2, "plays": 3})())
    seen = {}
    monkeypatch.setattr(social_storage, "is_liked", lambda u, w: seen.setdefault("liked_by", u) == u)
    monkeypatch.setattr(social_storage, "is_favorited", lambda u, w: False)
    r = client.get("/api/v1/social/stats/w1", headers={"Authorization": f"Bearer {AUTH_UUID}"})
    assert r.status_code == 200
    assert seen["liked_by"] == AUTH_UUID


def test_feed_anon_ok(monkeypatch):
    monkeypatch.setattr(social_storage, "get_user_feed", lambda uid, limit: [])
    r = client.get("/api/v1/social/feed")
    assert r.status_code == 200


def test_feed_jwt_personalized(monkeypatch):
    seen = {}
    monkeypatch.setattr(social_storage, "get_user_feed",
                        lambda uid, limit: seen.setdefault("uid", uid) or [])
    r = client.get("/api/v1/social/feed", headers={"Authorization": f"Bearer {AUTH_UUID}"})
    assert r.status_code == 200
    assert seen["uid"] == AUTH_UUID