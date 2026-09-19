"""Phase 3-4 测试：Project ↔ Song 绑定（JWT 隔离 + 所有权 + 幂等）。

端点：POST /api/v1/projects/{project_id}/songs/{song_id}
- project/song 都必须属于当前 JWT 用户，否则 404
- 绑定成功返回 project_id；重复绑定幂等；可重新绑定到自己另一 project
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
    eng = create_engine(f"sqlite:///{tmp_path/'p.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    S = sessionmaker(bind=eng)
    monkeypatch.setattr(projects_mod, "SessionLocal", S)

    # 内存歌曲仓库（模拟 supabase_service 的 select *）
    songs = {}

    def _get_song_by_id(song_id):
        return dict(songs[song_id]) if song_id in songs else None

    def _update_song(song_id, updates):
        if song_id not in songs:
            return None
        songs[song_id] = {**songs[song_id], **updates}
        return dict(songs[song_id])

    monkeypatch.setattr(projects_mod, "get_song_by_id", _get_song_by_id)
    monkeypatch.setattr(projects_mod, "update_song", _update_song)

    app = FastAPI()
    app.include_router(projects_mod.router)
    client = TestClient(app)
    state = {"current": OWNER}
    app.dependency_overrides[get_verified_user_id] = lambda: state["current"]

    def seed_project(pid, uid):
        with S() as s:
            s.add(Project(id=pid, user_id=uid, name="n"))
            s.commit()

    def seed_song(sid, uid, project_id=None):
        songs[sid] = {"id": sid, "user_id": uid, "title": "t",
                      "project_id": project_id, "status": "pending", "updated_at": None}

    return {
        "client": client, "songs": songs,
        "seed_project": seed_project, "seed_song": seed_song,
        "set_user": lambda u: state.__setitem__("current", u),
    }


def bind(ctx, pid, sid):
    return ctx["client"].post(f"/api/v1/projects/{pid}/songs/{sid}")


# 1. JWT 缺失 → 401
def test_no_jwt_401():
    app = FastAPI()
    app.include_router(projects_mod.router)
    c = TestClient(app)
    r = c.post("/api/v1/projects/p1/songs/s1")
    assert r.status_code == 401


# 2. 自己的 Project + 自己的 Song → 成功
def test_bind_own_project_own_song(ctx):
    ctx["seed_project"]("p1", OWNER)
    ctx["seed_song"]("s1", OWNER)
    r = bind(ctx, "p1", "s1")
    assert r.status_code == 200, r.text
    assert r.json()["project_id"] == "p1"
    assert ctx["songs"]["s1"]["project_id"] == "p1"


# 3. Project 属于其他用户 → 404
def test_project_other_user_404(ctx):
    ctx["seed_project"]("p1", OTHER)
    ctx["seed_song"]("s1", OWNER)
    assert bind(ctx, "p1", "s1").status_code == 404


# 4. Song 属于其他用户 → 404
def test_song_other_user_404(ctx):
    ctx["seed_project"]("p1", OWNER)
    ctx["seed_song"]("s1", OTHER)
    assert bind(ctx, "p1", "s1").status_code == 404


# 5. 都不属于当前用户 → 404（任一先命中即可，这里 project 先 404）
def test_both_not_own_404(ctx):
    ctx["seed_project"]("p1", OTHER)
    ctx["seed_song"]("s1", OTHER)
    assert bind(ctx, "p1", "s1").status_code == 404


# 6. 重复绑定幂等
def test_rebind_idempotent(ctx):
    ctx["seed_project"]("p1", OWNER)
    ctx["seed_song"]("s1", OWNER, project_id="p1")
    r1 = bind(ctx, "p1", "s1")
    r2 = bind(ctx, "p1", "s1")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert ctx["songs"]["s1"]["project_id"] == "p1"
    # 无重复记录：单标量列，仍只有一条 song，project_id 保持 p1


# 7. 绑定后 project_id 正确（且可重新绑定到自己另一 project）
def test_rebind_to_another_own_project(ctx):
    ctx["seed_project"]("p1", OWNER)
    ctx["seed_project"]("p2", OWNER)
    ctx["seed_song"]("s1", OWNER, project_id="p1")
    r = bind(ctx, "p2", "s1")
    assert r.status_code == 200
    assert r.json()["project_id"] == "p2"
    assert ctx["songs"]["s1"]["project_id"] == "p2"


# 8. 不存在的 song → 404（不泄露）
def test_song_not_found_404(ctx):
    ctx["seed_project"]("p1", OWNER)
    assert bind(ctx, "p1", "missing-song").status_code == 404