"""Auth User Provisioning 测试（不联真实 Supabase / 不创建真实用户）。

目标：
  1) 新 Auth UUID 能创建 public.users
  2) id = Auth UUID
  3) supabase_user_id = Auth UUID
  4) 重复 ensure 不产生第二次写入
  5) provisioning 失败不影响已验证 JWT 的身份解析
  6) ensure_user 只触碰 users 表，不触碰 quota/task/songs

Trigger DDL 只做文本级守护：确认已准备 AFTER INSERT + SECURITY DEFINER +
固定 search_path + 幂等冲突处理；不连接真实数据库。
"""
from pathlib import Path

from app.services import auth_identity, supabase_service

AUTH_UUID = "00000000-0000-4000-8000-0000000000aa"
EMAIL = "provision-test@example.com"


class _FakeQuery:
    """模拟 PostgREST 链式调用，只覆盖 ensure_user 用到的行为。"""

    def __init__(self, client, table: str):
        self.client = client
        self.table = table
        self.filters = []
        self.op = "select"

    def select(self, *args, **kwargs):
        self.op = "select"
        return self

    def eq(self, col: str, val):
        self.filters.append((col, val))
        return self

    def upsert(self, data, on_conflict=None, ignore_duplicates=False):
        self.op = "upsert"
        self.client.upserts.append(
            {
                "table": self.table,
                "data": data,
                "on_conflict": on_conflict,
                "ignore_duplicates": ignore_duplicates,
            }
        )
        return self

    def execute(self):
        if self.op == "upsert":
            return type("R", (), {"data": [self.client.upserts[-1]["data"]]})()

        rows = self.client.rows
        for col, val in self.filters:
            rows = [row for row in rows if str(row.get(col)) == str(val)]
        return type("R", (), {"data": rows})()


class _FakeSupabase:
    """记录表访问与 upsert 行为的假 Supabase 客户端。"""

    def __init__(self):
        self.rows = []
        self.upserts = []
        self.tables_touched = []

    def table(self, name: str):
        self.tables_touched.append(name)
        return _FakeQuery(self, name)


def test_ensure_user_creates_users_with_auth_uuid(monkeypatch):
    fake = _FakeSupabase()
    monkeypatch.setattr(supabase_service, "supabase", fake)
    monkeypatch.setattr(supabase_service, "_SUPABASE_CONFIGURED", True)

    user = supabase_service.ensure_user(AUTH_UUID, EMAIL)

    assert user["id"] == AUTH_UUID
    assert user["supabase_user_id"] == AUTH_UUID
    assert user["email"] == EMAIL

    assert len(fake.upserts) == 1
    upsert = fake.upserts[0]
    assert upsert["table"] == "users"
    assert upsert["on_conflict"] == "supabase_user_id"
    assert upsert["ignore_duplicates"] is True
    assert upsert["data"]["id"] == AUTH_UUID
    assert upsert["data"]["supabase_user_id"] == AUTH_UUID


def test_repeat_ensure_user_is_idempotent(monkeypatch):
    fake = _FakeSupabase()
    monkeypatch.setattr(supabase_service, "supabase", fake)
    monkeypatch.setattr(supabase_service, "_SUPABASE_CONFIGURED", True)

    first = supabase_service.ensure_user(AUTH_UUID, EMAIL)
    # 模拟第一次 upsert 后数据库中已存在该 Auth UUID 对应行
    fake.rows.append(first)

    second = supabase_service.ensure_user(AUTH_UUID, EMAIL)

    assert second["id"] == AUTH_UUID
    assert second["supabase_user_id"] == AUTH_UUID
    assert second is first
    assert len(fake.upserts) == 1, "重复 ensure 不得产生第二次 upsert"


def test_ensure_user_touches_only_users_table(monkeypatch):
    fake = _FakeSupabase()
    monkeypatch.setattr(supabase_service, "supabase", fake)
    monkeypatch.setattr(supabase_service, "_SUPABASE_CONFIGURED", True)

    supabase_service.ensure_user(AUTH_UUID, EMAIL)

    assert set(fake.tables_touched) == {"users"}


def test_provisioning_failure_does_not_break_verified_jwt(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://staging.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")

    def _boom(supabase_user_id, email):
        raise Exception("provisioning unavailable")

    class _AuthOK:
        def get_user(self, token):
            user = type("U", (), {"id": AUTH_UUID, "email": EMAIL})()
            return type("R", (), {"user": user})()

    class _S:
        auth = _AuthOK()

    monkeypatch.setattr(supabase_service, "supabase", _S())
    monkeypatch.setattr(supabase_service, "ensure_user", _boom)

    uid = auth_identity.verify_bearer_jwt("valid-token")

    assert uid == AUTH_UUID
    assert auth_identity.is_uuid(uid)


def test_trigger_ddl_is_prepared_and_idempotent():
    sql_path = Path(__file__).parents[1] / "scripts" / "supabase_auth_user_trigger.sql"
    sql = sql_path.read_text(encoding="utf-8").lower()

    assert "create trigger on_auth_user_created" in sql
    assert "after insert on auth.users" in sql
    assert "for each row" in sql
    assert "execute function public.handle_new_auth_user()" in sql
    assert "security definer" in sql
    assert "set search_path = public" in sql
    assert "new.id::text" in sql
    assert "on conflict (supabase_user_id) do nothing" in sql
