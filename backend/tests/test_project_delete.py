"""Phase 3-7 测试：Project delete 关联关系加固（保留 Song，project_id 置 NULL）。"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base, Project
from app.routers import projects as projects_mod
from app.services.auth_identity import get_verified_user_id


OWNER = "aaaa1111-1111-4111-8111-111111111111"
OTHER = "bbbb2222-2222-4222-8222-222222222222"


@pytest.fixture()
def ctx(monkeypatch, tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path/'p.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    S = sessionmaker(bind=eng)
    monkeypatch.setattr(projects_mod, "SessionLocal", S)

    # 内存歌曲仓库：detach 会真正清空匹配行的 project_id
    songs = {}

    def _detach(pid, uid):
        for s in songs.values():
            if s["project_id"] == pid and s["user_id"] == uid:
                s["project_id"] = None
        return True

    monkeypatch.setattr(projects_mod, "detach_songs_from_project", _detach)

    app = FastAPI()
    app.include_router(projects_mod.router)
    client = TestClient(app)
    cur = {"u": OWNER}
    app.dependency_overrides[get_verified_user_id] = lambda: cur["u"]

    def seed_project(pid, uid):
        with S() as s:
            s.add(Project(id=pid, user_id=uid, name="n"))
            s.commit()

    def seed_song(sid, uid, title="t", project_id=None, extra=None):
        base = {"id": sid, "user_id": uid, "title": title, "project_id": project_id, "status": "pending"}
        if extra: base.update(extra)
        songs[sid] = base

    def project_exists(pid):
        with S() as s:
            return s.query(Project).filter(Project.id == pid).count() == 1

    return {
        "client": client, "songs": songs, "S": S,
        "seed_project": seed_project, "seed_song": seed_song,
        "project_exists": project_exists,
        "set_user": lambda u: cur.__setitem__("u", u),
    }


# 1. JWT 缺失 → 401
def test_no_jwt_401():
    app = FastAPI()
    app.include_router(projects_mod.router)
    c = TestClient(app)
    assert c.delete("/api/v1/projects/p1").status_code == 401


# 2. 删除自己的空 Project → 204
def test_delete_own_empty_204(ctx):
    ctx["seed_project"]("p1", OWNER)
    assert ctx["client"].delete("/api/v1/projects/p1").status_code == 204


# 3. 删除后 Project 不存在
def test_project_gone_after_delete(ctx):
    ctx["seed_project"]("p1", OWNER)
    ctx["client"].delete("/api/v1/projects/p1")
    assert ctx["project_exists"]("p1") is False


# 4/5/6. 删除后关联 Songs 仍存在 + project_id=NULL + 其他字段不变
def test_songs_detached_not_deleted(ctx):
    ctx["seed_project"]("p1", OWNER)
    ctx["seed_song"]("s1", OWNER, title="Keep Me", project_id="p1", extra={"status": "completed", "custom": "x"})
    ctx["client"].delete("/api/v1/projects/p1")

    assert "s1" in ctx["songs"], "Song 必须保留"
    assert ctx["songs"]["s1"]["project_id"] is None, "project_id 应为 NULL"
    assert ctx["songs"]["s1"]["title"] == "Keep Me", "其他字段不变"
    assert ctx["songs"]["s1"]["status"] == "completed"
    assert ctx["songs"]["s1"]["custom"] == "x"


# 7. 删除他人 project → 404
def test_delete_other_404(ctx):
    ctx["seed_project"]("p1", OTHER)
    ctx["seed_song"]("s1", OTHER, project_id="p1")
    r = ctx["client"].delete("/api/v1/projects/p1")
    assert r.status_code == 404
    # 他人 project 与 song 均未动
    assert ctx["project_exists"]("p1") is True
    assert ctx["songs"]["s1"]["project_id"] == "p1"


# 9. 不属于该 project 的当前用户 Song 不受影响（project_id != p1 不动）
def test_unrelated_current_user_song_unaffected(ctx):
    ctx["seed_project"]("p1", OWNER)
    ctx["seed_song"]("keep_p2", OWNER, project_id="p2")  # 属于另一 project
    ctx["client"].delete("/api/v1/projects/p1")
    assert ctx["songs"]["keep_p2"]["project_id"] == "p2"


# 8. 他人 project 删除报 404 后，保持全部不变
def test_other_unchanged(ctx):
    ctx["seed_project"]("p1", OTHER)
    ctx["seed_song"]("s1", OTHER, project_id="p1")
    before = dict(ctx["songs"]["s1"])
    r = ctx["client"].delete("/api/v1/projects/p1")
    assert r.status_code == 404
    assert ctx["songs"]["s1"] == before


# 10. 删除不存在 project → 404
def test_delete_nonexistent_404(ctx):
    assert ctx["client"].delete("/api/v1/projects/ghost").status_code == 404


# ── detach 过滤链（supabase_service.detach_songs_from_project 必须双重 .eq） ──
def test_detach_filters_both(monkeypatch):
    import app.services.supabase_service as svc_module

    rec = {"update": None, "eqs": []}

    class _FakeQuery:
        def update(self, payload):
            rec["update"] = payload
            return self
        def eq(self, col, val):
            rec["eqs"].append((col, val))
            return self
        def execute(self):
            return None

    class _FakeTable:
        def __call__(self, name):
            rec["table"] = name
            return _FakeQuery()

    class _FakeSupabase:
        table = _FakeTable()

    monkeypatch.setattr(svc_module, "supabase", _FakeSupabase())

    svc_module.detach_songs_from_project("p1", "user-a")
    assert rec["update"] == {"project_id": None}
    eqs = dict(rec["eqs"])
    assert eqs.get("project_id") == "p1"
    assert eqs.get("user_id") == "user-a", "必须同时按 user_id 过滤，防改他人 Song"