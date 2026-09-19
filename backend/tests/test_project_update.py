"""Phase 3-6 测试：Project name 更新（PATCH）。

- JWT 必需；只能更新自己的 project；只更新 name；忽略恶意 user_id；updated_at 刷新。
"""

import datetime
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

    app = FastAPI()
    app.include_router(projects_mod.router)
    client = TestClient(app)
    cur = {"u": OWNER}
    app.dependency_overrides[get_verified_user_id] = lambda: cur["u"]

    old = datetime.datetime(2020, 1, 1, 0, 0, 0)

    def seed_project(pid, uid, name="old", updated_at=old):
        with S() as s:
            s.add(Project(id=pid, user_id=uid, name=name,
                          created_at=old, updated_at=updated_at))
            s.commit()

    def get_updated_at(pid):
        with S() as s:
            return s.query(Project).filter(Project.id == pid).one().updated_at

    return {"client": client, "seed_project": seed_project, "get_updated_at": get_updated_at,
            "set_user": lambda u: cur.__setitem__("u", u), "OLD": old}


# 1. JWT 缺失 → 401
def test_no_jwt_401():
    app = FastAPI()
    app.include_router(projects_mod.router)
    c = TestClient(app)
    assert c.patch("/api/v1/projects/p1", json={"name": "x"}).status_code == 401


# 2/3. 自己的 project 更新成功 + name 确实更新
def test_update_own(ctx):
    ctx["seed_project"]("p1", OWNER, name="old")
    r = ctx["client"].patch("/api/v1/projects/p1", json={"name": "New Name"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "New Name"
    assert r.json()["id"] == "p1"


# 4. 恶意 body.user_id 不能改变所有者
def test_malicious_user_id_ignored(ctx):
    ctx["seed_project"]("p1", OWNER, name="old")
    r = ctx["client"].patch("/api/v1/projects/p1", json={"name": "x", "user_id": OTHER})
    assert r.status_code == 200
    assert r.json()["user_id"] == OWNER, "必须忽略 body 中的 user_id，保持 JWT 所有者"


# 5. 更新他人 project → 404
def test_update_other_404(ctx):
    ctx["seed_project"]("p1", OTHER)
    assert ctx["client"].patch("/api/v1/projects/p1", json={"name": "x"}).status_code == 404


# 6. 更新不存在 project → 404
def test_update_nonexistent_404(ctx):
    assert ctx["client"].patch("/api/v1/projects/ghost", json={"name": "x"}).status_code == 404


# 7. updated_at 正常更新
def test_updated_at_refreshes(ctx):
    ctx["seed_project"]("p1", OWNER, name="old", updated_at=ctx["OLD"])
    r = ctx["client"].patch("/api/v1/projects/p1", json={"name": "new"})
    assert r.status_code == 200
    new_ua = ctx["get_updated_at"]("p1")
    assert new_ua != ctx["OLD"], "updated_at 应已刷新"


# 8. name 为空/超长被 422 拒绝（仅 name 可改）
def test_name_validation(ctx):
    ctx["seed_project"]("p1", OWNER)
    assert ctx["client"].patch("/api/v1/projects/p1", json={"name": ""}).status_code == 422
    long_name = "x" * 256
    assert ctx["client"].patch("/api/v1/projects/p1", json={"name": long_name}).status_code == 422