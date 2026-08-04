"""
PostgreSQL 数据库迁移与配置

目标:
- 从 SQLite/JSON 迁移到 PostgreSQL
- 提升查询性能 10x+
- 支持并发写入
- 完整事务支持

迁移步骤:
1. 安装 PostgreSQL
2. 创建数据库/用户
3. 安装 Python 驱动
4. 配置 SQLAlchemy ORM
5. 数据迁移脚本
6. 测试验证
"""

import os
from typing import Optional
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import asyncio

# ─── 数据库配置 ───────────────────────────────────────

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://hermes:hermes_password@localhost:5432/hermes_platform"
)

# 创建引擎
engine = create_engine(
    DATABASE_URL,
    pool_size=20,           # 连接池大小
    max_overflow=40,        # 最大溢出连接
    pool_recycle=3600,      # 连接回收时间 (秒)
    pool_pre_ping=True,     # 自动检测失效连接
    echo=False              # SQL 调试模式
)

# 会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 基类
Base = declarative_base()


# ─── 数据模型 ───────────────────────────────────────

class User(Base):
    """用户表"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    age = Column(Integer)
    is_premium = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    tracks = relationship("Track", back_populates="user", lazy="dynamic")
    projects = relationship("Project", back_populates="user", lazy="dynamic")


class Track(Base):
    """音频轨道表"""
    __tablename__ = "tracks"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    audio_url = Column(String(500), nullable=False)
    cdn_url = Column(String(500))  # CDN 加速 URL
    duration = Column(Float)  # 时长 (秒)
    tempo = Column(Float)  # BPM
    key_signature = Column(String(10))  # 调性
    style = Column(String(100))  # 风格
    lyrics = Column(Text)  # 歌词
    structure = Column(JSON)  # 歌曲结构
    metadata = Column(JSON)  # 其他元数据
    is_public = Column(Boolean, default=True)
    play_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # 关系
    user = relationship("User", back_populates="tracks")


class Project(Base):
    """音乐项目表 (多轨工程)"""
    __tablename__ = "projects"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    tracks = Column(JSON)  # 轨道配置
    settings = Column(JSON)  # 项目设置
    is_public = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    user = relationship("User", back_populates="projects")


class MVTemplate(Base):
    """MV 模板表"""
    __tablename__ = "mv_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    category = Column(String(50), index=True)  # 分类
    style = Column(String(50))  # 风格
    thumbnail_url = Column(String(500))
    preview_url = Column(String(500))
    config = Column(JSON)  # 模板配置
    duration = Column(Float)  # 时长
    is_premium = Column(Boolean, default=False)
    usage_count = Column(Integer, default=0)
    rating = Column(Float, default=0.0)  # 评分
    created_at = Column(DateTime, default=datetime.utcnow)


class VoiceProfile(Base):
    """声音档案表 (声音克隆)"""
    __tablename__ = "voice_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    audio_sample_url = Column(String(500), nullable=False)
    duration = Column(Float)  # 样本时长 (秒)
    features = Column(JSON)  # 声音特征向量
    model_path = Column(String(500))  # 训练模型路径
    is_public = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class CopyrightReport(Base):
    """版权检测报告表"""
    __tablename__ = "copyright_reports"
    
    id = Column(Integer, primary_key=True, index=True)
    track_id = Column(Integer, ForeignKey("tracks.id"), nullable=False, index=True)
    risk_level = Column(String(20))  # low/medium/high/critical
    similarity_score = Column(Float)  # 相似度
    matched_works = Column(JSON)  # 匹配作品
    report_data = Column(JSON)  # 完整报告
    created_at = Column(DateTime, default=datetime.utcnow)


class SocialPost(Base):
    """社区动态表"""
    __tablename__ = "social_posts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    track_id = Column(Integer, ForeignKey("tracks.id"))
    content = Column(Text)
    media_urls = Column(JSON)  # 媒体 URL 列表
    like_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    share_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class Collaboration(Base):
    """协作会话表"""
    __tablename__ = "collaborations"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    host_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(String(100), unique=True, index=True)
    participants = Column(JSON)  # 参与者列表
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime)


# ─── 数据库操作 ───────────────────────────────────────

def init_db():
    """初始化数据库 (创建所有表)"""
    print("[PostgreSQL] 正在创建数据表...")
    Base.metadata.create_all(bind=engine)
    print("[PostgreSQL] ✅ 数据表创建完成")


def get_db():
    """获取数据库会话 (依赖注入)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def init_db_async():
    """异步初始化数据库"""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    async_engine = create_async_engine(
        DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
        pool_size=20,
        max_overflow=40
    )
    
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    print("[PostgreSQL] ✅ 异步数据表创建完成")


# ─── 迁移脚本 ───────────────────────────────────────

def migrate_from_sqlite(sqlite_path: str, progress_callback=None):
    """
    从 SQLite 迁移到 PostgreSQL
    
    Args:
        sqlite_path: SQLite 数据库路径
        progress_callback: 进度回调函数
    """
    import sqlite3
    
    print(f"[迁移] 从 SQLite 迁移：{sqlite_path}")
    
    # 1. 连接 SQLite
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()
    
    # 2. 创建 PostgreSQL 会话
    db = SessionLocal()
    
    try:
        # 3. 迁移用户
        print("[迁移] 迁移用户表...")
        sqlite_cursor.execute("SELECT * FROM users")
        users = sqlite_cursor.fetchall()
        
        for user in users:
            db_user = User(
                id=user['id'],
                username=user['username'],
                email=user['email'],
                password_hash=user['password_hash'],
                age=user.get('age'),
                is_premium=user.get('is_premium', False),
                created_at=datetime.fromisoformat(user['created_at']) if user.get('created_at') else datetime.utcnow()
            )
            db.add(db_user)
        
        db.commit()
        if progress_callback:
            progress_callback("users", len(users))
        
        # 4. 迁移轨道
        print("[迁移] 迁移轨道表...")
        sqlite_cursor.execute("SELECT * FROM tracks")
        tracks = sqlite_cursor.fetchall()
        
        for track in tracks:
            db_track = Track(
                id=track['id'],
                user_id=track['user_id'],
                title=track['title'],
                audio_url=track['audio_url'],
                cdn_url=track.get('cdn_url'),
                duration=track.get('duration'),
                tempo=track.get('tempo'),
                key_signature=track.get('key_signature'),
                style=track.get('style'),
                lyrics=track.get('lyrics'),
                structure=track.get('structure'),
                metadata=track.get('metadata'),
                is_public=track.get('is_public', True),
                play_count=track.get('play_count', 0),
                like_count=track.get('like_count', 0),
                created_at=datetime.fromisoformat(track['created_at']) if track.get('created_at') else datetime.utcnow()
            )
            db.add(db_track)
        
        db.commit()
        if progress_callback:
            progress_callback("tracks", len(tracks))
        
        print(f"[迁移] ✅ 完成！迁移 {len(users)} 用户，{len(tracks)} 轨道")
        
    except Exception as e:
        db.rollback()
        print(f"[迁移] ❌ 失败：{e}")
        raise
    finally:
        db.close()
        sqlite_conn.close()


# ─── 性能优化 ───────────────────────────────────────

def create_indexes():
    """创建索引优化查询性能"""
    from sqlalchemy import text
    
    print("[优化] 创建索引...")
    
    with engine.connect() as conn:
        # 用户索引
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)"))
        
        # 轨道索引
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tracks_user_id ON tracks(user_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tracks_created_at ON tracks(created_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tracks_is_public ON tracks(is_public)"))
        
        # MV 模板索引
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_mv_templates_category ON mv_templates(category)"))
        
        # 声音档案索引
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_voice_profiles_user_id ON voice_profiles(user_id)"))
        
        # 社区动态索引
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_social_posts_user_id ON social_posts(user_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_social_posts_created_at ON social_posts(created_at)"))
        
        conn.commit()
    
    print("[优化] ✅ 索引创建完成")


def vacuum_analyze():
    """清理碎片并更新统计信息"""
    from sqlalchemy import text
    
    print("[优化] 执行 VACUUM ANALYZE...")
    
    with engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text("VACUUM ANALYZE"))
        conn.commit()
    
    print("[优化] ✅ VACUUM ANALYZE 完成")


# ─── 主入口 ───────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("🗄️  PostgreSQL 数据库初始化")
    print("=" * 60)
    
    # 1. 创建表
    init_db()
    
    # 2. 创建索引
    create_indexes()
    
    # 3. 优化
    vacuum_analyze()
    
    print("\n✅ PostgreSQL 数据库就绪！")
    print(f"连接字符串：{DATABASE_URL}")
    print(f"连接池：20 基础 + 40 溢出")