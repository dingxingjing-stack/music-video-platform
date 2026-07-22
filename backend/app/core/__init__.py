"""应用配置模块 — 统一读取 Supabase / Modal / HF 等外部配置"""
from dataclasses import dataclass
from typing import Optional
from app.core.secrets import get_secret


@dataclass(frozen=True)
class Settings:
    # Supabase
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: Optional[str]
    SUPABASE_SERVICE_ROLE_KEY: Optional[str]

    # Modal Worker (主推理)
    MODAL_WORKER_URL: str
    MODAL_WORKER_API_KEY: str

    # HF Worker (兼容旧版本, 可选)
    HF_WORKER_URL: Optional[str]
    HF_WORKER_API_KEY: Optional[str]


def get_settings() -> Settings:
    return Settings(
        SUPABASE_URL=get_secret("SUPABASE_URL", required=True),
        SUPABASE_ANON_KEY=get_secret("SUPABASE_ANON_KEY"),
        SUPABASE_SERVICE_ROLE_KEY=get_secret("SUPABASE_SERVICE_ROLE_KEY"),
        MODAL_WORKER_URL=get_secret("MODAL_WORKER_URL", required=True),
        MODAL_WORKER_API_KEY=get_secret("MODAL_WORKER_API_KEY", required=True),
        HF_WORKER_URL=get_secret("HF_WORKER_URL"),
        HF_WORKER_API_KEY=get_secret("HF_WORKER_API_KEY"),
    )
