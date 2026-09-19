"""Phase 2B-2 测试：ai_tasks 统一走 SQLAlchemy（task_store.count_user_tasks）。

覆盖：
  1. count 正常
  2. 用户隔离（user-a 只数 user-a）
  3. 空任务 → 0
  4. stats endpoint 的 total_tasks 来自 task_store（不再 PostgREST ai_tasks）
"""

import pytest

from app.services import task_store


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_tasks.db")
    monkeypatch.setattr(task_store, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(task_store, "_DB_PATH", db_path)
    return db_path


def test_count_empty_returns_zero(isolated_db):
    assert task_store.count_user_tasks("user-a") == 0


def test_count_normal(isolated_db):
    for i in range(3):
        task_store.new_task(user_key="user-a", task_id=f"a-{i}")
    assert task_store.count_user_tasks("user-a") == 3


def test_count_user_isolation(isolated_db):
    task_store.new_task(user_key="user-a", task_id="a-1")
    task_store.new_task(user_key="user-a", task_id="a-2")
    task_store.new_task(user_key="user-b", task_id="b-1")
    assert task_store.count_user_tasks("user-a") == 2
    assert task_store.count_user_tasks("user-b") == 1
    assert task_store.count_user_tasks("user-c") == 0


def test_count_none_returns_zero(isolated_db):
    assert task_store.count_user_tasks(None) == 0
    assert task_store.count_user_tasks("") == 0


def test_get_user_stats_uses_task_store(monkeypatch, isolated_db):
    """get_user_stats 的 total_tasks 来自 task_store.count_user_tasks（SQLAlchemy）。"""
    import asyncio
    from app.routers import auth
    import app.services.supabase_service as supabase_service

    # 桩 get_user（假用户，避免真实用户表）
    monkeypatch.setattr(
        auth, "get_user",
        lambda uid: {"id": uid, "email": "x@x.com", "credits": 10,
                     "subscription_tier": "free"},
    )

    # 桩 supabase（模块级符号）：只允许 songs；若触碰 ai_tasks 则断言失败
    accessed = []

    class _Resp:
        count = 5

    class _FakeSongs:
        def select(self, *a, **k):
            return self
        def eq(self, *a, **k):
            return self
        def execute(self):
            return _Resp()

    class _FakeTable:
        def __call__(self, name):
            accessed.append(name)
            assert name != "ai_tasks", "get_user_stats 不得再通过 supabase 读 ai_tasks"
            return _FakeSongs()

    class _FakeSupabase:
        def __init__(self):
            self.table = _FakeTable()

    monkeypatch.setattr(supabase_service, "supabase", _FakeSupabase())

    # 记录 count_user_tasks 被调用
    monkeypatch.setattr(task_store, "count_user_tasks",
                        lambda uk: 2)

    result = asyncio.run(auth.get_user_stats("user-x"))

    assert result["total_tasks"] == 2          # 来自 task_store.count_user_tasks
    assert result["total_songs"] == 5          # songs 仍走 supabase
    assert result["user_id"] == "user-x"
    assert "ai_tasks" not in accessed          # 确认未经 supabase 读 ai_tasks