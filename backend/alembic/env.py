"""Alembic 迁移配置 - V1.1 公测

修改:
1. sqlalchemy.url → 从环境变量读取 Supabase URL
2. target_metadata → 导入所有模型
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

import os
import sys
from dotenv import load_dotenv

# ===== 加载环境变量 =====
load_dotenv()

# ===== 导入所有模型 (用于自动生成迁移) =====
# 现有模型
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.models.social import Base as SocialBase
from app.models.v1_core import Base as V1CoreBase

# 合并所有 Base
target_metadata = V1CoreBase.metadata

# ===== Alembic 配置 =====

config = context.config

# 从环境变量读取数据库 URL
db_url = os.getenv("SUPABASE_URL", "")
if db_url:
    # Supabase PostgreSQL 连接字符串格式:
    # postgresql://postgres:PASSWORD@HOST:PORT/postgres
    db_password = os.getenv("SUPABASE_SERVICE_KEY", "")
    db_host = db_url.replace("https://", "")
    config.set_main_option(
        "sqlalchemy.url",
        f"postgresql://postgres:{db_password}@{db_host}/postgres"
    )

# 日志配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    """离线模式迁移 (仅生成 SQL)"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式迁移 (实际执行)"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()