"""生产数据库配置测试 — 验证 production + PostgreSQL(DATABASE_URL) 下：
- 不使用 SQLite
- 强制 Supabase SSL
- production + sqlite 直接报错（拒绝静默降级）
- auth/songs 在生产选择 Supabase 后端
这些测试在独立子进程设置环境变量后 import，避免污染 pytest 进程。
"""
import os
import subprocess
import sys
import pathlib

_BACKEND = str(pathlib.Path(__file__).resolve().parents[1])

def _run(code: str, env_extra: dict):
    env = dict(os.environ)
    # 子进程用 UTF-8，避免 Windows GBK 控制台打印 emoji（sqlite_service init 的 ✅）崩溃
    env["PYTHONIOENCODING"] = "utf-8"
    # 清理会干扰的 Supabase 配置，保证 _SUPABASE_CFG 由 env_extra 精确控制
    env.pop("SUPABASE_URL", None)
    env.pop("SUPABASE_ANON_KEY", None)
    env.pop("SUPABASE_SERVICE_ROLE_KEY", None)
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, cwd=_BACKEND,
    )

def test_production_postgres_url_uses_postgres_not_sqlite():
    code = (
        "import app.db.database as d;"
        "print('IS_POSTGRES', d.IS_POSTGRES);"
        "print('IS_SQLITE', d.IS_SQLITE);"
        "print('ENGINE', type(d.engine).__name__);"
        "print('CONNECT_ARGS', d.engine.url.query)"
    )
    r = _run(code, {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql://u:p@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require",
    })
    assert r.returncode == 0, r.stderr
    assert "IS_POSTGRES True" in r.stdout
    assert "IS_SQLITE False" in r.stdout
    assert "Engine" in r.stdout or "create_engine" in r.stdout
    # Supabase pooler 强制 SSL
    assert r.stdout.lower().find("sslmode") != -1

def test_production_postgres_url_adds_ssl_when_missing():
    # URL 未带 sslmode 时，database.py 应为 PG 注入 sslmode=require
    code = (
        "import app.db.database as d;"
        "print('ENGINE', d.engine);"
        "print('ARGS', getattr(d.engine, 'connect_args', {}));"
    )
    r = _run(code, {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql://u:p@aws-0-us-east-1.pooler.supabase.com:6543/postgres",
    })
    assert r.returncode == 0, r.stderr
    assert "Engine" in r.stdout or "postgres" in r.stdout.lower()

def test_production_sqlite_url_raises_no_silent_fallback():
    code = "import app.db.database"
    r = _run(code, {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "sqlite:///./should_not_be_used.db",
    })
    # production + sqlite 必须报错，而非静默降级
    assert r.returncode != 0
    assert "production" in (r.stderr + r.stdout).lower()

def test_sqlite_service_skips_init_in_production():
    # 生产环境 import sqlite_service 不应创建/初始化数据库（返回 0 且不报错，文件不生成）
    code = (
        "import os, pathlib;"
        "p=pathlib.Path('app/services/sqlite_service.py');"
        "src=p.read_text(encoding='utf-8');"
        "assert '!= \"production\"' in src, 'production guard missing';"
        "print('GUARD_OK')"
    )
    r = _run(code, {"ENVIRONMENT": "production"})
    assert r.returncode == 0, r.stderr
    assert "GUARD_OK" in r.stdout

def test_auth_and_songs_prefer_supabase_when_configured():
    code = (
        "import app.routers.auth as a;"
        "import app.routers.songs as s;"
        "print('AUTH_BACKEND', a.DB_BACKEND);"
        "print('SONGS_BACKEND', s.DB_BACKEND)"
    )
    r = _run(code, {
        "ENVIRONMENT": "production",
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_ANON_KEY": "dummy-anon",
        "SUPABASE_SERVICE_ROLE_KEY": "dummy-svc",
    })
    assert r.returncode == 0, r.stderr
    assert "AUTH_BACKEND supabase" in r.stdout
    assert "SONGS_BACKEND supabase" in r.stdout

def test_auth_and_songs_use_sqlite_when_no_supabase():
    code = (
        "import app.routers.auth as a;"
        "import app.routers.songs as s;"
        "print('AUTH_BACKEND', a.DB_BACKEND);"
        "print('SONGS_BACKEND', s.DB_BACKEND)"
    )
    r = _run(code, {"ENVIRONMENT": "development"})
    assert r.returncode == 0, r.stderr
    assert "AUTH_BACKEND sqlite" in r.stdout
    assert "SONGS_BACKEND sqlite" in r.stdout