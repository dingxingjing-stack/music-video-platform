"""公开分享（PLG 病毒飞轮的承接点）—— 凭签名链接读取作品，无需登录。

为什么用「签名令牌」而不是数据库字段：
  项目**没有 Alembic**，新增列需要手工 DDL、且 create_all 建不出已有表的新列。
  分享令牌改为对 task_id 做 HMAC 签名：验证签名即放行，不落库、不改表结构。
  （如需「撤销分享/设置有效期」，届时再引入 share 表，属独立工程。）

安全边界（重要）：
  - 只返回标题、时长、音频预签名 URL —— **绝不返回 email / user_key 等 PII**；
  - 签名不匹配或任务不存在一律 404（不泄露任务是否存在）；
  - 创建分享链接需登录且必须是作品所有者（防越权生成他人分享链）；
  - SHARE_LINK_SECRET 未配置时 fail-closed（503），绝不退化成不签名。

路由：
  POST /api/v1/share/task/{task_id}        登录 + 所有者 → 生成分享令牌
  GET  /api/v1/share/{token}               公开 → 返回作品（不含 PII）
"""

from __future__ import annotations

import hmac
import hashlib
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.services.auth_identity import get_verified_user_id
from app.services import task_store

router = APIRouter(prefix="/api/v1/share", tags=["share"])

# 预签名音频有效期（秒）：与既有 download 端点同口径
AUDIO_URL_EXPIRES_IN = 600


def _secret() -> str:
    """分享签名密钥；未配置则 fail-closed（调用方返回 503）。"""
    return (os.getenv("SHARE_LINK_SECRET") or "").strip()


def _sign(task_id: str) -> str:
    return hmac.new(
        _secret().encode(), task_id.encode(), hashlib.sha256
    ).hexdigest()[:32]


def make_token(task_id: str) -> str:
    """生成分享令牌：`<task_id>.<hmac>`（确定性，可重复生成同一链接）。"""
    return f"{task_id}.{_sign(task_id)}"


def parse_token(token: str) -> Optional[str]:
    """校验分享令牌，返回 task_id；签名不匹配/格式错误返回 None。"""
    if not token or "." not in token:
        return None
    task_id, _, sig = token.rpartition(".")
    if not task_id or not sig:
        return None
    expected = _sign(task_id)
    if not hmac.compare_digest(sig, expected):
        return None
    return task_id


@router.post("/task/{task_id}")
async def create_share_link(task_id: str, user_id: str = Depends(get_verified_user_id)):
    """为本人作品生成分享令牌（需登录 + 所有者校验）。"""
    secret = _secret()
    if not secret:
        raise HTTPException(status_code=503, detail="share_not_configured")

    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 越权防护：只能分享自己的作品
    if (task.get("user_key") or "") != user_id:
        raise HTTPException(status_code=403, detail="无权分享该任务")

    if task.get("state") not in ("completed", "completed_with_stems_failed"):
        raise HTTPException(status_code=409, detail="任务尚未完成")

    return {"token": make_token(task_id), "task_id": task_id}


@router.get("/{token}")
async def get_shared_work(token: str):
    """公开读取分享作品（无需登录）。只返回展示所需字段，不含任何 PII。"""
    secret = _secret()
    if not secret:
        raise HTTPException(status_code=503, detail="share_not_configured")

    task_id = parse_token(token)
    if not task_id:
        # 不泄露任务是否存在
        raise HTTPException(status_code=404, detail="分享内容不存在或链接无效")

    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="分享内容不存在或链接无效")

    if task.get("state") not in ("completed", "completed_with_stems_failed"):
        raise HTTPException(status_code=409, detail="该作品尚未生成完成")

    manifest = task.get("download") or {}
    key = manifest.get("full_mp3") or manifest.get("full_wav")
    audio_url = None
    if key:
        try:
            from app.services.cdn_uploader import cdn_uploader

            audio_url = cdn_uploader.get_presigned_download_url(
                key, expires_in=AUDIO_URL_EXPIRES_IN
            )
        except Exception:  # noqa: BLE001
            audio_url = None

    if not audio_url:
        raise HTTPException(status_code=404, detail="音频不可用")

    return {
        "task_id": task_id,
        "title": task.get("title") or "",
        "duration": task.get("duration"),
        "audio_url": audio_url,
        "expires_in": AUDIO_URL_EXPIRES_IN,
        # 明示品牌，供分享页展示「这是 AI 生成的」——飞轮的钩子
        "brand": "Melovar",
    }
