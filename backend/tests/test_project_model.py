"""Phase 3-1 测试：Project SQLAlchemy model（临时 SQLite CRUD + 用户隔离 + schema 对齐）。"""

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.db.database import Base, Project


@pytest.fixture()
def sqlite_engine(tmp_path):
    """每个测试用独立 SQLite，避免污染 backend/data。"""
    db_path = str(tmp_path / "test_projects.db")
    eng = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(sqlite_engine):
    S = sessionmaker(bind=sqlite_engine)
    s = S()
    yield s
    s.close()


# ── 1. ORM 字段与 Production 对齐（schema drift 守护） ──
def test_project_columns_match_production():
    cols = {c.name: c for c in Project.__table__.columns}
    assert set(cols) == {"id", "user_id", "name", "created_at", "updated_at"}

    # id / user_id / name = text（Python String，text 语义）
    import sqlalchemy as sa
    assert isinstance(cols["id"].type, sa.String), "id 应为 text/String"
    assert isinstance(cols["user_id"].type, sa.String), "user_id 应为 text/String"
    assert isinstance(cols["name"].type, sa.String), "name 应为 text/String"

    # PK
    assert cols["id"].primary_key is True

    # nullable 约定
    assert cols["user_id"].nullable is False
    assert cols["name"].nullable is False


# ── 2. CRUD ──
def test_project_crud(session):
    p = Project(id="p-1", user_id="user-a", name="My Album")
    session.add(p)
    session.commit()

    got = session.query(Project).filter(Project.id == "p-1").one()
    assert got.name == "My Album"
    assert got.user_id == "user-a"

    # update
    got.name = "Renamed"
    session.commit()
    assert session.query(Project).filter(Project.id == "p-1").one().name == "Renamed"

    # delete
    session.delete(got)
    session.commit()
    assert session.query(Project).filter(Project.id == "p-1").count() == 0


# ── 3. user_id 隔离查询 ──
def test_project_user_isolation(session):
    session.add_all([
        Project(id="a-1", user_id="user-a", name="A1"),
        Project(id="a-2", user_id="user-a", name="A2"),
        Project(id="b-1", user_id="user-b", name="B1"),
    ])
    session.commit()

    a = [r.id for r in session.query(Project).filter(Project.user_id == "user-a").all()]
    b = [r.id for r in session.query(Project).filter(Project.user_id == "user-b").all()]
    assert sorted(a) == ["a-1", "a-2"]
    assert b == ["b-1"]

    # user-c 无 projects
    assert session.query(Project).filter(Project.user_id == "user-c").count() == 0


# ── 4. 幂等 create_all 不报错（重复建表安全） ──
def test_create_all_idempotent(sqlite_engine):
    Base.metadata.create_all(bind=sqlite_engine)  # 第二次调用应无异常