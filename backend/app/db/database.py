"""
统一数据库入口 — Step 2 SQLite → Supabase PostgreSQL

设计：
- 唯一入口 DATABASE_URL（环境变量），生产为 postgresql://...（Supabase），开发/测试为 sqlite://...
- ENVIRONMENT=production 时若 DATABASE_URL 仍为 sqlite 则直接 RuntimeError，拒绝静默降级
- 连接池参数复用 DB_POOL_SIZE / DB_MAX_OVERFLOW / DB_POOL_RECYCLE（PostgreSQL 生效，SQLite 忽略）
- 提供 SQLAlchemy Base / engine / SessionLocal / init_db / get_db
- 所有业务表（ai_limits / task_store / beta_service / 原 postgres User/Track 等）通过 Base 统一建表
- 生产不执行 DROP，create_all 幂等（IF NOT EXISTS）

注意：psycopg2-binary 需在 requirements 中；本地无 PG 时自动回退 SQLite，不影响测试。
"""

from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Float, Text, Boolean, DateTime, ForeignKey, JSON
from datetime import datetime

# ── 环境判定 ────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./music_platform.db")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
IS_POSTGRES = DATABASE_URL.startswith("postgresql")
IS_SQLITE = DATABASE_URL.startswith("sqlite")

# 生产强制 PG
if ENVIRONMENT == "production" and not IS_POSTGRES:
    raise RuntimeError(
        f"[database] ENVIRONMENT=production 但 DATABASE_URL 非 PostgreSQL（当前 {DATABASE_URL!r}），"
        "拒绝静默创建 SQLite。生产必须配置 Supabase PostgreSQL 的 DATABASE_URL。"
    )

# ── 引擎创建 ────────────────────────────────────────
def _build_engine():
    url = DATABASE_URL
    # 连接池参数（仅 PG 生效）
    pool_size = int(os.getenv("DB_POOL_SIZE", "20"))
    max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "40"))
    pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "3600"))

    if IS_POSTGRES:
        # Supabase 要求 SSL，URL 中应含 ?sslmode=require（由运维配置）
        # SQLAlchemy 2.0 默认 psycopg2
        return create_engine(
            url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=pool_recycle,
            pool_pre_ping=True,
            echo=False,
        )
    # SQLite
    # check_same_thread=False 供多线程测试；WAL 由上层处理
    return create_engine(
        url,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
        echo=False,
    )

engine = _build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ── 模型定义（与原 sqlite schema 对齐，兼容 PG）─────────
# ai_limits 三张表
class GenerationUsage(Base):
    __tablename__ = "generation_usage"
    user_id = Column(String(255), primary_key=True)
    date = Column(String(20), nullable=False)
    daily_count = Column(Integer, nullable=False, default=0)
    month_key = Column(String(20), nullable=False)
    monthly_count = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class GlobalUsage(Base):
    __tablename__ = "global_usage"
    date = Column(String(20), primary_key=True)
    count = Column(Integer, nullable=False, default=0)

class DownloadLog(Base):
    __tablename__ = "download_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, index=True)
    job_id = Column(String(255), nullable=False)
    file_type = Column(String(100), nullable=False)
    ip_address = Column(String(100), default="")
    # 使用 Float 时间戳（兼容 SQLite 旧 TEXT + PG DateTime 混乱，统一为数值比较）
    created_at = Column(Float, default=lambda: __import__("time").time(), index=True)

# task_store 三张表
class AiTask(Base):
    __tablename__ = "ai_tasks"
    task_id = Column(String(100), primary_key=True)
    user_key = Column(String(255), nullable=False, index=True)
    state = Column(String(30), default="pending", index=True)
    progress = Column(Integer, default=0)
    audio_url = Column(Text)
    video_url = Column(Text)
    ai_provider = Column(String(100))
    error = Column(Text)
    download = Column(JSON)  # 对应原 TEXT JSON 字符串
    volume_files = Column(JSON)
    stems_state = Column(String(20))
    stems = Column(JSON)
    retries = Column(Integer, default=0)
    stem_retries = Column(Integer, default=0)
    created_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)

class TaskLock(Base):
    __tablename__ = "task_locks"
    user_key = Column(String(255), primary_key=True)
    task_id = Column(String(100), nullable=False)
    updated_at = Column(Float, nullable=False)

class GenerationCostLog(Base):
    __tablename__ = "generation_cost_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(100), nullable=False, index=True)
    user_key = Column(String(255))
    provider = Column(String(100))
    gpu = Column(String(100))
    result = Column(String(30))
    container_duration_ms = Column(Integer, default=0)
    model_load_ms = Column(Integer)
    generation_ms = Column(Integer)
    cold_warm = Column(String(20))
    container_id = Column(String(100))
    retries = Column(Integer, default=0)
    estimated_cost_usd = Column(Float, default=0.0)
    created_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)

# beta_service 三张表
class BetaUser(Base):
    __tablename__ = "beta_users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), unique=True, nullable=False, index=True)
    is_gray = Column(Integer, default=0)
    daily_credits_used = Column(Integer, default=0)
    daily_credits_limit = Column(Integer, default=10)
    total_generations = Column(Integer, default=0)
    activity_score = Column(Integer, default=0)
    gray_unlocked_at = Column(String(100))
    created_at = Column(String(50), default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(String(50), default=lambda: datetime.utcnow().isoformat())

class BetaGrayApplication(Base):
    __tablename__ = "beta_gray_applications"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, index=True)
    reason = Column(Text, nullable=False)
    contact = Column(String(255), default="")
    feature_key = Column(String(255), default="")
    status = Column(String(30), default="pending")
    created_at = Column(String(50), default=lambda: datetime.utcnow().isoformat())

class BetaBugReport(Base):
    __tablename__ = "beta_bug_reports"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False)
    report_type = Column(String(50), default="bug")
    description = Column(Text, nullable=False)
    status = Column(String(30), default="open")
    created_at = Column(String(50), default=lambda: datetime.utcnow().isoformat())

# ── 工具 ────────────────────────────────────────────
def init_db() -> None:
    """幂等建表（不 DROP，生产安全）。"""
    Base.metadata.create_all(bind=engine)

def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def is_postgres() -> bool:
    return IS_POSTGRES

def get_engine():
    return engine
