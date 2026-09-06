"""P0-1 — songs update 字段白名单 + publish ownership 安全测试。

验证：
  - owner 可修改允许字段（title/lyrics/style/duration_seconds/is_public/metadata）
  - owner 不能修改 user_id / status / play_count / created_at / id / updated_at
  - 未知字段被 422 拒绝（不允许绕过白名单）
  - 非 owner 修改他人 song → 403
  - publish 必须 ownership 校验（非 owner 不能 publish）
  - 未认证一律 401
"""
import os
import uuid
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# 强制走 Supabase 分支（不依赖真实 SUPABASE_URL，后续 monkeypatch 整个 supabase client）
os.environ.setdefault("SUPABASE_URL", "https://staging.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "anon-for-test")

from app.routers import songs as songs_mod


OWNER_UUID = "11111111-1111-4111-8111-111111111111"
OTHER_UUID = "22222222-2222-4222-8222-222222222222"
SONG_ID = str(uuid.uuid4())


class _Q:
    """记录 update 实际写入字段的 stub。"""
    def __init__(self, rec):
        self.rec = rec
        self._update_payload = None

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        return self

    def update(self, payload):
        self._update_payload = payload
        return self

    def delete(self):
        return self

    def execute(self):
        if self._update_payload is not None:
            self.rec["updates"].append(self._update_payload)
            self.rec["song"].update(self._update_payload)   # 实际应用写入，模拟 DB update
            return type("R", (), {"data": [dict(self.rec["song"])]})()
        # select 路径：返回 song
        return type("R", (), {"data": [self.rec["song"]]})()


class _FakeSB:
    def __init__(self, rec):
        self.rec = rec

    def table(self, name):
        assert name == "songs"
        return _Q(self.rec)


@pytest.fixture()
def rec():
    """每个测试独立数据：song 属于 OWNER_UUID。"""
    return {
        "updates": [],
        "song": {
            "id": SONG_ID,
            "user_id": OWNER_UUID,
            "title": "original",
            "lyrics": "orig lyrics",
            "style": "pop",
            "duration_seconds": 10,
            "is_public": False,
            "play_count": 0,
            "like_count": 0,
            "status": "ready",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "metadata": {},
        },
    }


@pytest.fixture(autouse=True)
def _patch(monkeypatch, rec):
    # 身份：把 Bearer 持有者解析为 OWNER_UUID 对应的 users.id
    monkeypatch.setattr(songs_mod, "resolve_auth_user_id", lambda auth: OWNER_UUID if auth else None)
    monkeypatch.setattr(songs_mod, "get_user", lambda uid: {
        "id": OWNER_UUID, "email": "owner@test", "supabase_user_id": OWNER_UUID, "credits": 100,
    } if uid == OWNER_UUID else None)
    monkeypatch.setattr(songs_mod, "log_activity", lambda **kw: None)  # 不外发
    # 注意：router 内部 `from app.services.supabase_service import supabase`，
    # 因此 patch songs 模块里 import 后的对象（直接替换模块全局的 supabase_service.supabase）
    fake = _FakeSB(rec)
    import app.services.supabase_service as sb_svc
    monkeypatch.setattr(sb_svc, "supabase", fake)


def _client():
    app = FastAPI()
    app.include_router(songs_mod.router)
    return TestClient(app)


# ── 允许字段：owner 可正常修改 ──────────────────────────────────────
def test_owner_can_update_allowed_fields(rec):
    c = _client()
    r = c.put(f"/api/v1/songs/{SONG_ID}", headers={"Authorization": "Bearer ok"},
              json={"title": "New Title", "style": "rock", "is_public": True,
                    "metadata": {"mood": "energetic"}})
    assert r.status_code == 200, r.text
    assert rec["song"]["title"] == "New Title"
    assert rec["song"]["style"] == "rock"
    assert rec["song"]["is_public"] is True
    assert rec["song"]["metadata"]["mood"] == "energetic"


# ── 受保护字段：全部被 422 拒绝且不写库 ──────────────────────────────
@pytest.mark.parametrize("field", ["user_id", "status", "play_count", "like_count",
                                   "created_at", "id", "updated_at"])
def test_owner_cannot_update_protected_fields(rec, field):
    c = _client()
    original = rec["song"][field]
    r = c.put(f"/api/v1/songs/{SONG_ID}", headers={"Authorization": "Bearer ok"},
              json={field: "HACKED", "title": "ok-update"})
    assert r.status_code == 422, r.text
    assert rec["song"][field] == original  # 未污染
    assert rec["updates"] == []            # 未写入任何 update


# ── 未知字段 → 422（不允许绕过白名单） ──────────────────────────────
def test_unknown_field_rejected(rec):
    c = _client()
    r = c.put(f"/api/v1/songs/{SONG_ID}", headers={"Authorization": "Bearer ok"},
              json={"some_unknown": "x", "another_bad": 1})
    assert r.status_code == 422
    assert rec["updates"] == []


# ── 非 owner 修改 → 403 ──────────────────────────────────────────────
def test_non_owner_cannot_update(rec, monkeypatch):
    monkeypatch.setattr(songs_mod, "resolve_auth_user_id", lambda auth: OTHER_UUID)
    monkeypatch.setattr(songs_mod, "get_user", lambda uid: {
        "id": OTHER_UUID, "email": "other@test"
    } if uid == OTHER_UUID else None)
    c = _client()
    r = c.put(f"/api/v1/songs/{SONG_ID}", headers={"Authorization": "Bearer ok"},
              json={"title": "hijack"})
    assert r.status_code == 403
    assert rec["song"]["title"] == "original"


# ── 未认证 → 401 ────────────────────────────────────────────────────
def test_no_auth_401(rec):
    c = _client()
    r = c.put(f"/api/v1/songs/{SONG_ID}", json={"title": "x"})
    assert r.status_code == 401


# ── publish：非 owner 不能发布他人歌曲 ───────────────────────────────
def test_non_owner_cannot_publish(rec, monkeypatch):
    monkeypatch.setattr(songs_mod, "resolve_auth_user_id", lambda auth: OTHER_UUID)
    monkeypatch.setattr(songs_mod, "get_user", lambda uid: {
        "id": OTHER_UUID
    } if uid == OTHER_UUID else None)
    c = _client()
    r = c.post(f"/api/v1/songs/{SONG_ID}/publish", headers={"Authorization": "Bearer ok"})
    assert r.status_code == 403
    assert rec["song"]["is_public"] is False  # 未被改动


# ── publish：owner 可正常发布 ───────────────────────────────────────
def test_owner_can_publish(rec):
    c = _client()
    r = c.post(f"/api/v1/songs/{SONG_ID}/publish", headers={"Authorization": "Bearer ok"})
    assert r.status_code == 200
    # 检查对白名单后写入的 is_public 生效
    assert rec["updates"][-1]["is_public"] is True
