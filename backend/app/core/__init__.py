"""
应用配置模块
所有外部配置（HF Worker 地址、密钥、Supabase 配置）统一从此处获取。
"""

from dataclasses import dataclass
from typing import Optional

from app.core.secrets import get_secret


@dataclass(frozen=True)
class Settings:
    # Supabase
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: Optional[str]
    SUPABASE_SERVICE_ROLE_KEY: Optional[str]

    # HuggingFace Worker
    HF_WORKER_URL: str
    HF_WORKER_API_KEY: str


def get_settings() -> Settings:
    return Settings(
        SUPABASE_URL=get_secret("SUPABASE_URL", required=True),
        SUPABASE_ANON_KEY=get_secret("SUPABASE_ANON_KEY"),
        SUPABASE_SERVICE_ROLE_KEY=get_secret("SUPABASE_SERVICE_ROLE_KEY"),
        HF_WORKER_URL=get_secret("HF_WORKER_URL", required=True),
        HF_WORKER_API_KEY=get_secret("HF_WORKER_API_KEY", required=True),
    )
