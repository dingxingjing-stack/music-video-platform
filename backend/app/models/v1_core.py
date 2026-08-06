"""
V1.1 核心业务数据表 (10 张)
日期：2026-07-14
策略：直接复用现有 User/Message，新增歌曲/任务/资源相关表
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum, Float, Boolean, Index
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum
import datetime

# ==================== 枚举定义 ====================

class TaskStatus(str, PyEnum):
    """AI 生成任务状态"""
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    RUNNING = "running"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"

class CopyrightRiskLevel(str, PyEnum):
    """版权风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class AssetType(str, PyEnum):
    """媒体资源类型"""
    AUDIO = "audio"
    COVER = "cover"
    LYRICS = "lyrics"
    VIDEO = "video"

# ==================== 核心业务表 ====================

class Song(Base):
    """
    歌曲主表
    存储歌词、曲风、语种、情绪等元数据
    """
    __tablename__ = "songs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(255), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    lyrics = Column(Text)  # 完整歌词 (带段落结构)
    style_prompt = Column(Text, nullable=False)  # 曲风描述
    language = Column(String(50), default="zh")
    mood = Column(String(50))  # Happy, Sad, Energetic...
    tempo = Column(String(20))  # Slow, Medium, Fast
    duration = Column(Integer, default=30)  # 秒
    is_public = Column(Boolean, default=True)
    play_count = Column(Integer, default=0)
    share_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # 关联
    user = relationship("User", back_populates="songs")
    tasks = relationship("Task", back_populates="song", cascade="all, delete-orphan")
    media = relationship("MediaAsset", back_populates="song", cascade="all, delete-orphan")
    copyright_records = relationship("CopyrightRecord", back_populates="song", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_songs_user_created', 'user_id', 'created_at'),
        Index('idx_songs_public_created', 'is_public', 'created_at'),
    )


class Task(Base):
    """
    AI 生成任务表
    跟踪歌曲生成的完整生命周期
    """
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    song_id = Column(Integer, ForeignKey("songs.id"), nullable=False, index=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, index=True)
    model_provider = Column(String(50), nullable=False)  # "hf_musicgen", "hf_ace_step", "hf_yue"
    model_version = Column(String(20))  # "v1.0", "large", "small"
    progress = Column(Integer, default=0)  # 0-100
    hf_task_id = Column(String(255))  # HF Space 返回的任务 ID
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    prompt_text = Column(Text)  # 原始提示词
    temperature = Column(Float, default=0.7)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    
    # 关联
    song = relationship("Song", back_populates="tasks")
    
    __table_args__ = (
        Index('idx_tasks_status_created', 'status', 'created_at'),
    )


class MediaAsset(Base):
    """
    统一媒体资源表
    存储音频/封面/歌词文件的 R2 索引
    """
    __tablename__ = "media_assets"
    
    id = Column(Integer, primary_key=True, index=True)
    song_id = Column(Integer, ForeignKey("songs.id"), nullable=False, index=True)
    asset_type = Column(Enum(AssetType), nullable=False, index=True)
    storage_provider = Column(String(20), default="r2")  # "r2", "local"
    r2_bucket = Column(String(255))
    r2_key = Column(String(500))  # R2 object key
    public_url = Column(String(1000))  # CDN 公开 URL
    size_bytes = Column(Integer)
    duration_seconds = Column(Integer)  # 音频时长
    mime_type = Column(String(50))  # "audio/mpeg", "image/jpeg"
    checksum_md5 = Column(String(32))  # 文件校验
    is_processed = Column(Boolean, default=False)  # 是否完成处理
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    
    # 关联
    song = relationship("Song", back_populates="media")
    
    __table_args__ = (
        Index('idx_media_song_type', 'song_id', 'asset_type'),
    )


class CopyrightRecord(Base):
    """
    版权全链路溯源记录
    记录每次生成的版权检测结果
    """
    __tablename__ = "copyright_records"
    
    id = Column(Integer, primary_key=True, index=True)
    song_id = Column(Integer, ForeignKey("songs.id"), nullable=False, index=True)
    risk_level = Column(Enum(CopyrightRiskLevel), nullable=False, index=True)
    fingerprint_hash = Column(String(64))  # 音频指纹
    matched_works = Column(Text)  # JSON: 匹配到的相似作品
    similar_segments = Column(Text)  # JSON: 相似片段详情
    is_cleared = Column(Boolean, default=False)  # 是否通过审核
    reviewer_id = Column(String(255))  # 审核员 ID
    review_notes = Column(Text)
    checked_at = Column(DateTime, default=datetime.datetime.utcnow)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    
    # 关联
    song = relationship("Song", back_populates="copyright_records")
    
    __table_args__ = (
        Index('idx_copyright_song_risk', 'song_id', 'risk_level'),
    )


class QuotaLog(Base):
    """
    用户每日额度消耗日志
    用于限流和配额管理
    """
    __tablename__ = "quota_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(255), ForeignKey("users.id"), nullable=False, index=True)
    action_type = Column(String(50), nullable=False)  # "generate_song", "export_stem", "voice_clone"
    quota_consumed = Column(Integer, default=1)  # 消耗配额数
    cost_credits = Column(Integer, default=0)  # 消耗积分
    task_id = Column(Integer, ForeignKey("tasks.id"))
    ip_address = Column(String(45))  # IPv6
    user_agent = Column(String(500))
    status = Column(String(20), default="success")  # "success", "failed", "rate_limited"
    created_date = Column(DateTime, index=True)  # 按日期分区
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # 关联
    user = relationship("User")
    task = relationship("Task")
    
    __table_args__ = (
        Index('idx_quota_user_date', 'user_id', 'created_date'),
    )


class AuditLog(Base):
    """
    全局操作审计日志
    记录所有关键操作
    """
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(255), ForeignKey("users.id"), index=True)
    action = Column(String(100), nullable=False)  # "user.login", "song.create", "song.delete"
    resource_type = Column(String(50))  # "song", "user", "task"
    resource_id = Column(Integer)
    old_value = Column(Text)  # JSON: 旧值
    new_value = Column(Text)  # JSON: 新值
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    status = Column(String(20), default="success")  # "success", "failed"
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    
    # 关联
    user = relationship("User")
    
    __table_args__ = (
        Index('idx_audit_user_action', 'user_id', 'action'),
        Index('idx_audit_resource', 'resource_type', 'resource_id'),
    )


class ProviderLog(Base):
    """
    AI 模型调用耗时、成功率日志
    用于监控 Provider 健康状态
    """
    __tablename__ = "provider_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    provider_name = Column(String(50), nullable=False, index=True)  # "hf_musicgen", "gemini"
    endpoint = Column(String(255), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id"))
    request_payload = Column(Text)  # JSON: 请求体
    response_status = Column(Integer)  # HTTP status
    response_time_ms = Column(Integer)  # 响应时间 (毫秒)
    is_success = Column(Boolean, default=False, index=True)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    cost_credits = Column(Integer, default=0)  # 调用成本
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    
    # 关联
    task = relationship("Task")
    
    __table_args__ = (
        Index('idx_provider_name_time', 'provider_name', 'created_at'),
        Index('idx_provider_success', 'provider_name', 'is_success'),
    )


class PromptLibrary(Base):
    """
    用户收藏提示词库
    仅存数据，不做推荐算法
    """
    __tablename__ = "prompt_library"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(255), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    prompt_text = Column(Text, nullable=False)
    style_tags = Column(Text)  # JSON: ["Pop", "Sad", "Piano"]
    usage_count = Column(Integer, default=0)
    is_favorite = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # 关联
    user = relationship("User")
    
    __table_args__ = (
        Index('idx_prompt_user_favorite', 'user_id', 'is_favorite'),
    )


class Project(Base):
    """
    用户作品分组
    用于组织和管理多首歌曲
    """
    __tablename__ = "projects"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(255), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    cover_image_url = Column(String(1000))
    song_count = Column(Integer, default=0)
    is_public = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # 关联
    user = relationship("User")
    songs = relationship("Song", secondary="project_songs", back_populates="projects")
    
    __table_args__ = (
        Index('idx_project_user', 'user_id', 'created_at'),
    )


# ==================== 关联表 ====================

class ProjectSong(Base):
    """
    项目 - 歌曲关联表 (多对多)
    """
    __tablename__ = "project_songs"
    
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    song_id = Column(Integer, ForeignKey("songs.id"), nullable=False, index=True)
    added_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    __table_args__ = (
        Index('idx_project_song_unique', 'project_id', 'song_id', unique=True),
    )


# ==================== 用户模型扩展 ====================
# 注意：User 模型已在 social.py 中定义，这里仅添加扩展字段
# 实际使用时需要在 social.py 的 User 模型中添加以下 back_populates:
# 
# class User(Base):
#     ...
#     songs = relationship("Song", back_populates="user")
#     prompts = relationship("PromptLibrary", back_populates="user")
#     projects = relationship("Project", back_populates="user")