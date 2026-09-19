"""Phase 3-3 测试：Projects 最小 CRUD（JWT 隔离 + 所有权）。

覆盖：
  1. JWT 缺失 → 401
  2. 创建项目成功
  3. 当前用户只能看到自己的 projects
  4. 用户 A 不能读取用户 B 的 project → 404
  5. 用户 A 不能删除用户 B 的 project → 404
  6. 自己可以读取 / 删除
  7. 恶意传 body.user_id / 参数 user_id 不改变 JWT user_id
"""

import uuid
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
    """临时 SQLite + 覆盖 router 的 SessionLocal + 可切换的身份依赖。"""
    eng = create_engine(f"sqlite:///{tmp_path/'p.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    S = sessionmaker(bind=eng)
    monkeypatch.setattr(projects_mod, "SessionLocal", S)
    # Phase 3-7：delete_project 现会先 detach 关联 songs（supabase_service）。
    # 该测试未涉及关联 songs，直接桩空实现即可（不触碰真实 Supabase）。
    monkeypatch.setattr(projects_mod, "detach_songs_from_project", lambda pid, uid: True)

    app = FastAPI()
    app.include_router(projects_mod.router)
    client = TestClient(app)

    state = {"current": OWNER}
    def _override():
        return state["current"]
    app.dependency_overrides[get_verified_user_id] = _override

    # seeding helper（直接写库，模拟 DB 已存在的项目）
    def seed(pid, uid, name):
        with S() as s:
            s.add(Project(id=pid, user_id=uid, name=name))
            s.commit()

    ctx_obj = {"client": client, "S": S, "seed": seed, "set_user": lambda u: state.__setitem__("current", u)}
    return ctx_obj


# ── 1. JWT 缺失 → 401（用真实依赖，无 Authorization） ──
def test_no_jwt_401(monkeypatch):
    # 全新 app：不覆盖依赖，直接发无 Authorization 请求
    app = FastAPI()
    app.include_router(projects_mod.router)
    c = TestClient(app)
    r = c.get("/api/v1/projects")
    assert r.status_code == 401
    r2 = c.post("/api/v1/projects", json={"name": "n"})
    assert r2.status_code == 401


# ── 2. 创建项目成功 ──
def test_create_project(ctx):
    r = ctx["client"].post("/api/v1/projects", json={"name": "My Album"})
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["user_id"] == OWNER
    assert data["name"] == "My Album"
    assert data["id"]


# ── 7. 恶意 body.user_id 不改变 JWT user_id ──
def test_create_ignores_client_user_id(ctx):
    r = ctx["client"].post("/api/v1/projects", json={"name": "n", "user_id": OTHER})
    assert r.status_code == 201, r.text
    assert r.json()["user_id"] == OWNER, "必须用 JWT 身份，忽略客户端 user_id"


# ── 3. 当前用户只能看到自己的 projects ──
def test_list_only_own(ctx):
    ctx["seed"]("own-1", OWNER, "A1")
    ctx["seed"]("own-2", OWNER, "A2")
    ctx["seed"]("b-1", OTHER, "B1")
    r = ctx["client"].get("/api/v1/projects")
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()]
    assert set(ids) == {"own-1", "own-2"}, f"不应包含 B1: {ids}"


# ── 4. 用户 A 不能读取用户 B 的 project → 404 ──
def test_cannot_read_others(ctx):
    ctx["seed"]("b-1", OTHER, "B1")
    r = ctx["client"].get("/api/v1/projects/b-1")
    assert r.status_code == 404


# ── 6a. 自己可以读取 ──
def test_can_read_own(ctx):
    ctx["seed"]("own-1", OWNER, "A1")
    r = ctx["client"].get("/api/v1/projects/own-1")
    assert r.status_code == 200
    assert r.json()["user_id"] == OWNER


# ── 5. 用户 A 不能删除用户 B 的 project → 404 ──
def test_cannot_delete_others(ctx):
    ctx["seed"]("b-1", OTHER, "B1")
    r = ctx["client"].delete("/api/v1/projects/b-1")
    assert r.status_code == 404
    # 确认仍存在（未被删）
    with ctx["S"]() as s:
        assert s.query(Project).filter(Project.id == "b-1").count() == 1


# ── 6b. 自己可以删除 ──
def test_can_delete_own(ctx):
    ctx["seed"]("own-1", OWNER, "A1")
    r = ctx["client"].delete("/api/v1/projects/own-1")
    assert r.status_code == 204
    with ctx["S"]() as s:
        assert s.query(Project).filter(Project.id == "own-1").count() == 0


# ── 切换用户后隔离仍成立 ──
def test_switch_user_isolation(ctx):
    ctx["seed"]("a-1", OWNER, "A1")
    ctx["set_user"](OTHER)
    # OTHER 看不到 OWNER 的
    r1 = ctx["client"].get("/api/v1/projects/a-1")
    assert r1.status_code == 404
    # OTHER 创建后只能看到自己的
    ctx["client"].post("/api/v1/projects", json={"name": "Bproj"})
    r2 = ctx["client"].get("/api/v1/projects")
    assert all(p["user_id"] == OTHER for p in r2.json())