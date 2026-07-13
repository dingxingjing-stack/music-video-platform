"""Add V1.1 core tables (10 张业务表)

创建表:
- songs (歌曲主表)
- tasks (AI 生成任务)
- media_assets (媒体资源)
- copyright_records (版权记录)
- quota_logs (配额日志)
- audit_logs (审计日志)
- provider_logs (Provider 调用日志)
- prompt_library (提示词库)
- projects (作品分组)
- project_songs (项目 - 歌曲关联表)

修订日期：2026-07-14
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime


# Revision identifiers
revision = 'v1_1_initial'
down_revision = None  # 初始迁移
branch_labels = None
depends_on = None


def upgrade() -> None:
    """升级：创建所有 V1.1 表"""
    
    # ===== 1. songs 歌曲主表 =====
    op.create_table('songs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('lyrics', sa.Text()),
        sa.Column('style_prompt', sa.Text(), nullable=False),
        sa.Column('language', sa.String(50), default='zh'),
        sa.Column('mood', sa.String(50)),
        sa.Column('tempo', sa.String(20)),
        sa.Column('duration', sa.Integer(), default=30),
        sa.Column('is_public', sa.Boolean(), default=True),
        sa.Column('play_count', sa.Integer(), default=0),
        sa.Column('share_count', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(), default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime(), default=datetime.utcnow, onupdate=datetime.utcnow),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_songs_user_id', 'songs', ['user_id'])
    op.create_index('idx_songs_created_at', 'songs', ['created_at'])
    op.create_index('idx_songs_user_created', 'songs', ['user_id', 'created_at'])
    op.create_index('idx_songs_public_created', 'songs', ['is_public', 'created_at'])
    
    # ===== 2. tasks AI 生成任务表 =====
    op.create_table('tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('song_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), default='pending'),
        sa.Column('model_provider', sa.String(50), nullable=False),
        sa.Column('model_version', sa.String(20)),
        sa.Column('progress', sa.Integer(), default=0),
        sa.Column('hf_task_id', sa.String(255)),
        sa.Column('error_message', sa.Text()),
        sa.Column('retry_count', sa.Integer(), default=0),
        sa.Column('max_retries', sa.Integer(), default=3),
        sa.Column('prompt_text', sa.Text()),
        sa.Column('temperature', sa.Float(), default=0.7),
        sa.Column('started_at', sa.DateTime()),
        sa.Column('completed_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), default=datetime.utcnow),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_tasks_song_id', 'tasks', ['song_id'])
    op.create_index('idx_tasks_status', 'tasks', ['status'])
    op.create_index('idx_tasks_status_created', 'tasks', ['status', 'created_at'])
    
    # ===== 3. media_assets 媒体资源表 =====
    op.create_table('media_assets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('song_id', sa.Integer(), nullable=False),
        sa.Column('asset_type', sa.String(20), nullable=False),
        sa.Column('storage_provider', sa.String(20), default='r2'),
        sa.Column('r2_bucket', sa.String(255)),
        sa.Column('r2_key', sa.String(500)),
        sa.Column('public_url', sa.String(1000)),
        sa.Column('size_bytes', sa.Integer()),
        sa.Column('duration_seconds', sa.Integer()),
        sa.Column('mime_type', sa.String(50)),
        sa.Column('checksum_md5', sa.String(32)),
        sa.Column('is_processed', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(), default=datetime.utcnow),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_media_song_id', 'media_assets', ['song_id'])
    op.create_index('idx_media_asset_type', 'media_assets', ['asset_type'])
    op.create_index('idx_media_song_type', 'media_assets', ['song_id', 'asset_type'])
    
    # ===== 4. copyright_records 版权记录表 =====
    op.create_table('copyright_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('song_id', sa.Integer(), nullable=False),
        sa.Column('risk_level', sa.String(20), nullable=False),
        sa.Column('fingerprint_hash', sa.String(64)),
        sa.Column('matched_works', sa.Text()),
        sa.Column('similar_segments', sa.Text()),
        sa.Column('is_cleared', sa.Boolean(), default=False),
        sa.Column('reviewer_id', sa.String(255)),
        sa.Column('review_notes', sa.Text()),
        sa.Column('checked_at', sa.DateTime(), default=datetime.utcnow),
        sa.Column('created_at', sa.DateTime(), default=datetime.utcnow),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_copyright_song_id', 'copyright_records', ['song_id'])
    op.create_index('idx_copyright_risk_level', 'copyright_records', ['risk_level'])
    op.create_index('idx_copyright_song_risk', 'copyright_records', ['song_id', 'risk_level'])
    
    # ===== 5. quota_logs 配额日志表 =====
    op.create_table('quota_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('action_type', sa.String(50), nullable=False),
        sa.Column('quota_consumed', sa.Integer(), default=1),
        sa.Column('cost_credits', sa.Integer(), default=0),
        sa.Column('task_id', sa.Integer()),
        sa.Column('ip_address', sa.String(45)),
        sa.Column('user_agent', sa.String(500)),
        sa.Column('status', sa.String(20), default='success'),
        sa.Column('created_date', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), default=datetime.utcnow),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_quota_user_id', 'quota_logs', ['user_id'])
    op.create_index('idx_quota_created_date', 'quota_logs', ['created_date'])
    op.create_index('idx_quota_user_date', 'quota_logs', ['user_id', 'created_date'])
    
    # ===== 6. audit_logs 审计日志表 =====
    op.create_table('audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(255)),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('resource_type', sa.String(50)),
        sa.Column('resource_id', sa.Integer()),
        sa.Column('old_value', sa.Text()),
        sa.Column('new_value', sa.Text()),
        sa.Column('ip_address', sa.String(45)),
        sa.Column('user_agent', sa.String(500)),
        sa.Column('status', sa.String(20), default='success'),
        sa.Column('error_message', sa.Text()),
        sa.Column('created_at', sa.DateTime(), default=datetime.utcnow),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_audit_user_id', 'audit_logs', ['user_id'])
    op.create_index('idx_audit_action', 'audit_logs', ['action'])
    op.create_index('idx_audit_user_action', 'audit_logs', ['user_id', 'action'])
    op.create_index('idx_audit_resource', 'audit_logs', ['resource_type', 'resource_id'])
    
    # ===== 7. provider_logs Provider 调用日志 =====
    op.create_table('provider_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider_name', sa.String(50), nullable=False),
        sa.Column('endpoint', sa.String(255), nullable=False),
        sa.Column('task_id', sa.Integer()),
        sa.Column('request_payload', sa.Text()),
        sa.Column('response_status', sa.Integer()),
        sa.Column('response_time_ms', sa.Integer()),
        sa.Column('is_success', sa.Boolean(), default=False),
        sa.Column('error_message', sa.Text()),
        sa.Column('retry_count', sa.Integer(), default=0),
        sa.Column('cost_credits', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(), default=datetime.utcnow),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_provider_name', 'provider_logs', ['provider_name'])
    op.create_index('idx_provider_created_at', 'provider_logs', ['created_at'])
    op.create_index('idx_provider_name_time', 'provider_logs', ['provider_name', 'created_at'])
    op.create_index('idx_provider_success', 'provider_logs', ['provider_name', 'is_success'])
    
    # ===== 8. prompt_library 提示词库 =====
    op.create_table('prompt_library',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('prompt_text', sa.Text(), nullable=False),
        sa.Column('style_tags', sa.Text()),
        sa.Column('usage_count', sa.Integer(), default=0),
        sa.Column('is_favorite', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(), default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime(), default=datetime.utcnow, onupdate=datetime.utcnow),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_prompt_user_id', 'prompt_library', ['user_id'])
    op.create_index('idx_prompt_user_favorite', 'prompt_library', ['user_id', 'is_favorite'])
    
    # ===== 9. projects 作品分组 =====
    op.create_table('projects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('cover_image_url', sa.String(1000)),
        sa.Column('song_count', sa.Integer(), default=0),
        sa.Column('is_public', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(), default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime(), default=datetime.utcnow, onupdate=datetime.utcnow),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_project_user_id', 'projects', ['user_id'])
    op.create_index('idx_project_user_created', 'projects', ['user_id', 'created_at'])
    
    # ===== 10. project_songs 项目 - 歌曲关联表 =====
    op.create_table('project_songs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('song_id', sa.Integer(), nullable=False),
        sa.Column('added_at', sa.DateTime(), default=datetime.utcnow),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_project_song_project_id', 'project_songs', ['project_id'])
    op.create_index('idx_project_song_song_id', 'project_songs', ['song_id'])
    op.create_index('idx_project_song_unique', 'project_songs', ['project_id', 'song_id'], unique=True)
    
    # ===== 外键约束 =====
    op.create_foreign_key('fk_tasks_song', 'tasks', 'songs', ['song_id'], ['id'])
    op.create_foreign_key('fk_media_song', 'media_assets', 'songs', ['song_id'], ['id'])
    op.create_foreign_key('fk_copyright_song', 'copyright_records', 'songs', ['song_id'], ['id'])
    op.create_foreign_key('fk_prompt_user', 'prompt_library', 'users', ['user_id'], ['id'])
    op.create_foreign_key('fk_project_user', 'projects', 'users', ['user_id'], ['id'])
    op.create_foreign_key('fk_project_song_project', 'project_songs', 'projects', ['project_id'], ['id'])
    op.create_foreign_key('fk_project_song_song', 'project_songs', 'songs', ['song_id'], ['id'])


def downgrade() -> None:
    """降级：删除所有 V1.1 表"""
    # 先删除关联表
    op.drop_table('project_songs')
    
    # 删除有外键的表
    op.drop_table('projects')
    op.drop_table('prompt_library')
    op.drop_table('provider_logs')
    op.drop_table('audit_logs')
    op.drop_table('quota_logs')
    op.drop_table('copyright_records')
    op.drop_table('media_assets')
    op.drop_table('tasks')
    op.drop_table('songs')