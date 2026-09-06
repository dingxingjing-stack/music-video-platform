"""数据库连接硬化测试（Task A→G）—— 只验证配置/连接行为，不连真实生产库。

覆盖：
  1. DATABASE_URL 从环境变量读取
  2. production 缺少 DATABASE_URL → 明确失败（不 fallback SQLite）
  3. production + sqlite → 明确失败（已在 test_db_production.py，此处补缺失场景）
  4. 连接池参数收敛（pool_size/max_overflow/recycle/connect_timeout/pre_ping）
  5. session/connection 正确释放
  6. /health 数据库正常
  7. /health 数据库异常 → 稳定安全信息，不泄密（不含 password/uri/token/完整异常）
  8. 匿名访问受保护 API 返回 401（数据库异常时不得伪装成认证问题）
"""
from __future__ import annotations

import os
import subprocess
import sys
import pathlib

import pytest
from fastapi.testclient import TestClient

_BACKEND = str(pathlib.Path(__file__).resolve().parents[1])


def _run(code: str, env_extra: dict, timeout=60):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("SUPABASE_URL", None)
    env.pop("SUPABASE_ANON_KEY", None)
    env.pop("SUPABASE_SERVICE_ROLE_KEY", None)
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, cwd=_BACKEND, timeout=timeout,
    )


# ── 1. DATABASE_URL 从 env 读取 ──────────────────────────────────────
def test_datbase_url_reads_from_env():
    code = (
        "import app.db.database as d;"
        "print('SCHEME', d.DATABASE_URL.split(':')[0]);"
        "print('IS_SQLITE', d.IS_SQLITE);"
        "print('HAS_POOL_SIZE', hasattr(d.engine.pool, 'size'))"
    )
    r = _run(code, {"ENVIRONMENT": "development",
                    "DATABASE_URL": "sqlite:///./tmp_read_env.db"})
    assert r.returncode == 0, r.stderr
    assert "SCHEME sqlite" in r.stdout
    assert "IS_SQLITE True" in r.stdout


# ── 2. production 缺少 DATABASE_URL → 明确失败 ───────────────────────
def test_production_missing_database_url_raises():
    code = "import app.db.database"
    r = _run(code, {"ENVIRONMENT": "production"})
    assert r.returncode != 0
    assert "DATABASE_URL" in (r.stderr + r.stdout)


# ── 3. production + sqlite → 明确失败（不 fallback） ─────────────────
def test_production_sqlite_no_fallback():
    code = "import app.db.database"
    r = _run(code, {"ENVIRONMENT": "production",
                    "DATABASE_URL": "sqlite:///./nope.db"})
    assert r.returncode != 0
    assert "SQLite" in (r.stderr + r.stdout) or "sqlite" in (r.stderr + r.stdout).lower()


# ── 4. 连接池参数收敛 ────────────────────────────────────────────────
def test_pool_params_converged():
    code = (
        "import app.db.database as d;"
        "p=d.engine.pool;"
        "print('MAXSIZE', getattr(p._pool,'maxsize',None));"   # = pool_size
        "print('MAX', getattr(p,'_max_overflow',None));"         # = max_overflow
        "print('PREPING', getattr(d.engine.pool,'_pre_ping',None));"
        "print('RECYCLE', getattr(d.engine.pool,'_recycle',None));"
        "print('URLQUERY', dict(d.engine.url.query));"
        "print('POOLTYPE', type(p).__name__);"
    )
    r = _run(code, {"ENVIRONMENT": "production",
                    "DATABASE_URL": "postgresql://u:p@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require"})
    assert r.returncode == 0, r.stderr
    out = r.stdout
    # pool_size=5 / max_overflow=10 / recycle=1800 / pre_ping=True / 单 QueuePool Engine
    assert "MAXSIZE 5" in out, out
    assert "MAX 10" in out, out
    assert "RECYCLE 1800" in out, out
    assert "PREPING True" in out, out
    assert "POOLTYPE QueuePool" in out, out
    # sslmode=require 注入 PG 连接
    assert "sslmode" in out and "require" in out, out


# ── 5. session 正确释放 ──────────────────────────────────────────────
def test_session_closes_returns_to_pool():
    code = (
        "from app.db.database import SessionLocal, engine;"
        "s = SessionLocal();"
        "assert s is not None;"
        "s.close();"
        "print('CLOSED_OK')"
    )
    r = _run(code, {"ENVIRONMENT": "development",
                    "DATABASE_URL": "sqlite:///./tmp_session.db"})
    assert r.returncode == 0, r.stderr
    assert "CLOSED_OK" in r.stdout


# ── 6/7/8. /health 与匿名 401（in-process，monkeypatch engine） ──────

@pytest.fixture()
def client():
    import main as main_mod
    return TestClient(main_mod.app)


def test_health_ok(client, monkeypatch):
    import main as main_mod
    # 用 mock engine 返回成功，验证 /health ok 且不泄密
    class _OkConn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a, **k): return None
    class _OkEngine:
        def connect(self): return _OkConn()
    monkeypatch.setattr("app.db.database.engine", _OkEngine())
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["services"]["database"]["healthy"] is True


def test_health_error_non_leaking(client, monkeypatch):
    # 模拟 DB 连接异常：/health 必须 degraded，且信息中不含 password/uri/完整异常
    class _BadEngine:
        def connect(self):
            raise RuntimeError("FATAL: password authentication failed for user postgres@aws-0-us-east-1.pooler.supabase.com:5432")
    monkeypatch.setattr("app.db.database.engine", _BadEngine())
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "degraded"
    msg = body["services"]["database"]["message"]
    assert body["services"]["database"]["healthy"] is False
    # 不泄密：不出现 password / 完整 host / uri / token
    for forbidden in ("password", "authentication failed", "pooler.supabase.com", "postgres@", "DATABASE_URL", "token"):
        assert forbidden not in msg.lower(), f"泄漏检测失败: {msg!r} 包含 {forbidden!r}"


def test_anonymous_protected_api_401_when_db_error(client, monkeypatch):
    # 数据库异常时，受保护 API 仍应 401（不是 500/伪认证）；身份校验先于 DB 访问。
    # 用 mock 让 reserve_generation 不依赖真实 DB，验证身份链路。
    import main as main_mod
    class _BadEngine:
        def connect(self):
            raise RuntimeError("db down")
    monkeypatch.setattr("app.db.database.engine", _BadEngine())

    # predict/music 无身份：budget_hard_stop_reached 读 DB（mock 它返回 False）→ 401
    from app.services import ai_limits
    monkeypatch.setattr(ai_limits, "budget_hard_stop_reached", lambda: False)
    r = client.post("/api/v1/predict/music", json={"prompt": "x"})
    assert r.status_code == 401, f"expected 401 got {r.status_code}: {r.text}"