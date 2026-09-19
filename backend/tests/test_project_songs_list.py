"""Phase 3-5 测试：Project → Songs 只读查询。

GET /api/v1/projects/{project_id}/songs
- JWT 必需；project 必须属于当前用户；songs 必须同时 project_id+user_id 匹配。
"""

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

    # stub songs 查询（可控返回值）
    state = {"songs": []}
    monkeypatch.setattr(projects_mod, "get_songs_by_project", lambda pid, uid: list(state["songs"]))

    app = FastAPI()
    app.include_router(projects_mod.router)
    client = TestClient(app)
    cur = {"u": OWNER}
    app.dependency_overrides[get_verified_user_id] = lambda: cur["u"]

    def seed_project(pid, uid):
        with S() as s:
            s.add(Project(id=pid, user_id=uid, name="n"))
            s.commit()

    return {"client": client, "seed_project": seed_project, "state": state,
            "set_user": lambda u: cur.__setitem__("u", u)}


def _song(sid, **kw):
    d = {"id": sid, "user_id": OWNER, "title": "t", "status": "pending",
         "is_public": False, "play_count": 0, "like_count": 0, "metadata": {},
         "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00"}
    d.update(kw)
    return d


# 1. JWT 缺失 → 401
def test_no_jwt_401():
    app = FastAPI()
    app.include_router(projects_mod.router)
    c = TestClient(app)
    assert c.get("/api/v1/projects/p1/songs").status_code == 401


# 2. 自己 Project → 200
def test_own_project_200(ctx):
    ctx["seed_project"]("p1", OWNER)
    ctx["state"]["songs"] = [_song("s1", project_id="p1")]
    r = ctx["client"].get("/api/v1/projects/p1/songs")
    assert r.status_code == 200
    assert len(r.json()) == 1


# 3. 空 Project → []
def test_empty_project(ctx):
    ctx["seed_project"]("p1", OWNER)
    ctx["state"]["songs"] = []
    r = ctx["client"].get("/api/v1/projects/p1/songs")
    assert r.status_code == 200
    assert r.json() == []


# 4. 他人 Project → 404
def test_other_project_404(ctx):
    ctx["seed_project"]("p1", OTHER)
    ctx["state"]["songs"] = [_song("s1", project_id="p1")]
    r = ctx["client"].get("/api/v1/projects/p1/songs")
    assert r.status_code == 404


# 5. 结果列表 project_id 返回正确
def test_response_includes_project_id(ctx):
    ctx["seed_project"]("p1", OWNER)
    ctx["state"]["songs"] = [_song("s1", project_id="p1")]
    r = ctx["client"].get("/api/v1/projects/p1/songs")
    assert r.json()[0]["project_id"] == "p1"


# ── 双归属过滤（supabase_service.get_songs_by_project 必须 .eq 两次） ──
def test_get_songs_by_project_filters_both(monkeypatch):
    import app.services.supabase_service as svc_module

    rec = {"eqs": []}

    class _FakeQuery:
        def select(self, *a, **k):
            return self
        def eq(self, col, val):
            rec["eqs"].append((col, val))
            return self
        def order(self, *a, **k):
            rec["order"] = a
            return self
        def limit(self, *a, **k):
            return self
        def offset(self, *a, **k):
            return self
        def execute(self):
            return type("R", (), {"data": []})()

    class _FakeTable:
        def __call__(self, name):
            rec["table"] = name
            return _FakeQuery()

    class _FakeSupabase:
        table = _FakeTable()

    monkeypatch.setattr(svc_module, "supabase", _FakeSupabase())

    svc_module.get_songs_by_project("p1", "user-a")
    eqs = dict(rec["eqs"])
    assert eqs.get("project_id") == "p1"
    assert eqs.get("user_id") == "user-a", "必须同时过滤 user_id（防跨用户泄露）"