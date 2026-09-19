"""Phase 3-2C 测试：songs.project_id 最小接入。

覆盖：
  1. project_id=None 时 create_song 不注入 project_id（旧行为兼容）
  2. project_id="xxx" 正确进入 payload
  3. SongResponse 正确返回 project_id（None 与 有值）
"""

import pytest

from app.routers.songs import SongResponse, SongCreate


# ── 3. SongResponse.project_id 序列化 ──
def test_song_response_project_id_none():
    r = SongResponse(
        id="s1", user_id="u1", title="t", status="pending",
        is_public=False, play_count=0, like_count=0, metadata={},
        created_at="2026-01-01T00:00:00+00:00", updated_at="2026-01-01T00:00:00+00:00",
    )
    assert r.project_id is None
    d = r.model_dump()
    assert "project_id" in d and d["project_id"] is None


def test_song_response_project_id_set():
    r = SongResponse(
        id="s2", user_id="u1", title="t", status="pending",
        is_public=False, play_count=0, like_count=0, metadata={},
        created_at="2026-01-01T00:00:00+00:00", updated_at="2026-01-01T00:00:00+00:00",
        project_id="p-9",
    )
    assert r.project_id == "p-9"
    assert r.model_dump()["project_id"] == "p-9"


# ── 1/2. create_song 的 project_id 处理（mock supabase，不碰真实网络/DB） ──
def test_create_song_project_id_none(monkeypatch):
    import app.services.supabase_service as svc_module

    captured = {}

    class _FakeResp:
        data = [{"id": "s1", "user_id": "u1", "title": "t"}]

    class _FakeQuery:
        def insert(self, payload):
            captured["payload"] = payload
            return self
        def execute(self):
            return _FakeResp()

    class _FakeTable:
        def __call__(self, name):
            captured["table"] = name
            return _FakeQuery()

    class _FakeSupabase:
        table = _FakeTable()

    monkeypatch.setattr(svc_module, "supabase", _FakeSupabase())

    r = svc_module.create_song("u1", {"title": "t"}, project_id=None)
    assert captured["payload"].get("title") == "t"
    assert "project_id" not in captured["payload"], "project_id=None 不应写入 payload"


def test_create_song_project_id_set(monkeypatch):
    import app.services.supabase_service as svc_module

    captured = {}

    class _FakeResp:
        data = [{"id": "s1", "user_id": "u1", "title": "t", "project_id": "p-9"}]

    class _FakeQuery:
        def insert(self, payload):
            captured["payload"] = payload
            return self
        def execute(self):
            return _FakeResp()

    class _FakeTable:
        def __call__(self, name):
            return _FakeQuery()

    class _FakeSupabase:
        table = _FakeTable()

    monkeypatch.setattr(svc_module, "supabase", _FakeSupabase())

    r = svc_module.create_song("u1", {"title": "t"}, project_id="p-9")
    assert captured["payload"]["project_id"] == "p-9", "project_id 应写入 payload"


# ── SongCreate.project_id 默认 None ──
def test_song_create_project_id_default():
    sc = SongCreate(title="t")
    assert sc.project_id is None
    sc2 = SongCreate(title="t", project_id="p-1")
    assert sc2.project_id == "p-1"