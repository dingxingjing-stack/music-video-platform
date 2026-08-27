"""
R2 统一配置 — Step 3 单一真相源

正式商用唯一命名：
- CLOUDFLARE_R2_ACCOUNT_ID
- CLOUDFLARE_R2_ACCESS_KEY
- CLOUDFLARE_R2_SECRET_KEY
- CDN_BUCKET（主） 兼容 R2_BUCKET_NAME（旧，deprecated）
- CDN_BASE_URL（自定义域，如 https://cdn.yourdomain.com）

所有业务代码应通过本模块读取，避免分散 os.getenv 导致双桶名不一致
"""

from __future__ import annotations

import os

def get_r2_account_id() -> str:
    return (os.getenv("CLOUDFLARE_R2_ACCOUNT_ID") or "").strip()

def get_r2_access_key() -> str:
    return (os.getenv("CLOUDFLARE_R2_ACCESS_KEY") or "").strip()

def get_r2_secret_key() -> str:
    return (os.getenv("CLOUDFLARE_R2_SECRET_KEY") or "").strip()

def get_r2_bucket() -> str:
    # 主键 CDN_BUCKET，兼容旧 R2_BUCKET_NAME
    v = (os.getenv("CDN_BUCKET") or "").strip()
    if v:
        return v
    legacy = (os.getenv("R2_BUCKET_NAME") or "").strip()
    if legacy:
        # 保留静默兼容，避免生产因变量名差异突断
        return legacy
    # 本地/测试默认值（与 workers/wrangler.cdn.toml 一致）
    return "music-audio-storage"

def get_cdn_base_url() -> str:
    return (os.getenv("CDN_BASE_URL") or "").rstrip("/")

def is_r2_configured() -> bool:
    return bool(get_r2_account_id() and get_r2_access_key() and get_r2_secret_key() and get_r2_bucket())

def is_r2_bucket_alias_used() -> bool:
    return not (os.getenv("CDN_BUCKET") or "").strip() and bool((os.getenv("R2_BUCKET_NAME") or "").strip())

def validate_production() -> None:
    """ENVIRONMENT=production 时若 R2 未配置则报错（Koyeb 无状态，不允许静默本地）"""
    env = (os.getenv("ENVIRONMENT") or "development").lower()
    if env == "production" and not is_r2_configured():
        raise RuntimeError("[r2_config] ENVIRONMENT=production 但 R2 未完整配置（需 CLOUDFLARE_R2_* + CDN_BUCKET）")
