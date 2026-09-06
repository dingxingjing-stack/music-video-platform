"""Supabase PostgreSQL 兼容修复测试（本阶段：auth/feedback/get_user/log_activity）。

覆盖：
  - Bearer JWT 不再被当作用户 ID（必须经 Supabase Auth 验证）
  - get_user 的 UUID 安全：非 UUID 输入不触发 users.id 查询
  - create_feedback 写入 user_id/content/text（对齐真实 NOT NULL 约束）
  - log_activity 在 activity_logs 缺失时安全 no-op
  - ai_limits 的 ON CONFLICT(user_id/date) 与真实约束一致（文本级守护 + SQLite 功能验证）
"""
import re

import pytest

from app.services import auth_identity, supabase_service


# ── 假 Supabase 客户端：记录查询/插入行为 ──────────────────────────
class _FakeQuery:
    def __init__(self, table, recorder):
        self.table = table
        self.recorder = recorder
        self._filters = []

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def insert(self, data):
        self.recorder["inserts"].append({"table": self.table, "data": data})
        return self

    def execute(self):
        # users.id 命中：仅当有过滤到 id 且为已知 uuid
        self.recorder["queries"].append({"table": self.table, "filters": list(self._filters)})
        known = self.recorder.get("known", {})
        for col, val in self._filters:
            if (self.table, col, val) in known:
                return type("R", (), {"data": [known[(self.table, col, val)]]})()
        # insert 返回记录本身
        if self.recorder["inserts"]:
            last = self.recorder["inserts"][-1]
            return type("R", (), {"data": [last["data"]]})()
        return type("R", (), {"data": []})()


class _FakeSupabase:
    def __init__(self):
        self.recorder = {"queries": [], "inserts": [], "known": {}}

    def table(self, name):
        return _FakeQuery(name, self.recorder)


UUID_OK = "123e4567-e89b-42d3-a456-426614174000"
JWT_LIKE = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjNlNDU2Ny1lODliLTQyZDMtYTQ1Ni00MjY2MTQxNzQwMDAifQ.fake"


# ── Auth：Bearer JWT 不再被直接用作用户 ID ───────────────────────────
def test_bearer_jwt_not_treated_as_user_id(monkeypatch):
    """配置了 Supabase 时，非法/伪造 JWT → None（不直接当 user id）。"""
    monkeypatch.setenv("SUPABASE_URL", "https://staging.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")

    class _FailingAuth:
        def get_user(self, jwt):
            raise Exception("invalid jwt")

    class _S:
        auth = _FailingAuth()

    monkeypatch.setattr(supabase_service, "supabase", _S())
    assert auth_identity.resolve_auth_user_id(f"Bearer {JWT_LIKE}") is None


def test_valid_jwt_yields_uuid(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://staging.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")

    class _AuthOK:
        def get_user(self, jwt):
            return type("R", (), {"user": type("U", (), {"id": UUID_OK})()})()

    class _S:
        auth = _AuthOK()

    monkeypatch.setattr(supabase_service, "supabase", _S())
    uid = auth_identity.resolve_auth_user_id(f"Bearer {JWT_LIKE}")
    assert uid == UUID_OK
    assert auth_identity.is_uuid(uid)


def test_dev_fallback_when_no_supabase(monkeypatch):
    """未配置 Supabase（本地/测试）：保留旧语义，token 即用户标识。"""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    assert auth_identity.resolve_auth_user_id("Bearer dev-user-1") == "dev-user-1"


def test_non_bearer_header_rejected(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://staging.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    assert auth_identity.extract_bearer_token(None) is None
    assert auth_identity.extract_bearer_token("") is None


# ── get_user：UUID 安全 ─────────────────────────────────────────────
def test_get_user_non_uuid_skips_id_query(monkeypatch):
    """非 UUID（如 JWT 字符串）绝不能触发 users.id 的 uuid 比较查询。"""
    fake = _FakeSupabase()
    monkeypatch.setattr(supabase_service, "supabase", fake)
    monkeypatch.setattr(supabase_service, "_SUPABASE_CONFIGURED", True)

    supabase_service.get_user(JWT_LIKE)
    id_queries = [q for q in fake.recorder["queries"]
                  if q["table"] == "users" and any(f[0] == "id" for f in q["filters"])]
    assert id_queries == [], "非 UUID 输入不得查询 users.id"
    supa_queries = [q for q in fake.recorder["queries"]
                    if q["table"] == "users" and any(f[0] == "supabase_user_id" for f in q["filters"])]
    assert supa_queries, "非 UUID 输入应直接查 supabase_user_id"


def test_get_user_uuid_queries_id_first(monkeypatch):
    fake = _FakeSupabase()
    fake.recorder["known"][("users", "id", UUID_OK)] = {"id": UUID_OK, "email": "a@b.c"}
    monkeypatch.setattr(supabase_service, "supabase", fake)

    user = supabase_service.get_user(UUID_OK)
    assert user["id"] == UUID_OK
    first = fake.recorder["queries"][0]
    assert first["filters"][0] == ("id", UUID_OK)


# ── Feedback：写入字段与真实 schema 对齐 ────────────────────────────
def test_creat_feedback_writes_required_fields(monkeypatch):
    fake = _FakeSupabase()
    monkeypatch.setattr(supabase_service, "supabase", fake)
    supabase_service.create_feedback("张三", "很好用", UUID_OK)
    ins = fake.recorder["inserts"][0]
    assert ins["table"] == "feedback"
    assert ins["data"]["user_id"] == UUID_OK
    assert ins["data"]["content"] == "很好用"
    assert ins["data"]["text"] == "很好用"
    assert ins["data"]["name"] == "张三"


# ── log_activity：activity_logs 缺失时不炸主流程 ────────────────────
def test_log_activity_noop_when_table_missing(monkeypatch, caplog):
    class _Boom:
        def table(self, name):
            raise Exception("relation activity_logs does not exist")

    monkeypatch.setattr(supabase_service, "supabase", _Boom())
    import logging
    with caplog.at_level(logging.DEBUG):
        assert supabase_service.log_activity(UUID_OK, "USER_REGISTERED") is None
    # 不抛异常即通过；且不创建表（不可能，因为只调用了 insert）


# ── ai_limits ON CONFLICT 与真实约束的一致性守护（文本级） ──────────
def test_upsert_conflict_targets_match_real_schema():
    src = open("app/services/ai_limits.py", encoding="utf-8").read()
    assert "ON CONFLICT(user_id)" in src, "beta_users / generation_usage 依赖 ON CONFLICT(user_id)"
    assert "ON CONFLICT(date)" in src, "global_usage 依赖 ON CONFLICT(date)"
    # 守护：task_store.update(ai_tasks) 不得写入不存在的列 prompt_text / prompt_language
    vct = open("app/services/voice_clone_task.py", encoding="utf-8").read()
    for m in re.finditer(r"task_store\.update\([^)]*\)", vct, re.S):
        assert "prompt_text" not in m.group(0) and "prompt_language" not in m.group(0), \
            f"task_store.update 写入了 ai_tasks 不存在的列: {m.group(0)[:120]}"


def test_upsert_paths_functional_on_sqlite(tmp_path, monkeypatch):
    """SQLite 功能级验证：reserve 一次后行被创建（UPSERT 路径可用）。"""
    from app.services import ai_limits
    monkeypatch.setattr(ai_limits, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(ai_limits, "_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 10)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")
    r = ai_limits.reserve_generation("u-compat-1")
    assert r["success"] is True
    r2 = ai_limits.reserve_generation("u-compat-1")  # 再次 upsert，同一 user（ON CONFLICT 命中）
    assert r2["success"] is True
