"""声音参考样本 API — 上传/授权确认/查询/删除/预签名下载。

安全约束：
  - 所有端点强制 X-User-ID 鉴权
  - 上传必须 agree_authorized=True，否则 422
  - reference 读取/删除/下载仅限本人（跨用户返回 404，不泄露存在性）
  - 下载返回 10 分钟 presigned URL，不使用公开 URL
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile

from app.services import voice_reference_service as vrs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/voice-reference", tags=["voice-clone"])

MAX_UPLOAD_BYTES = vrs.MAX_REF_BYTES


def _user_id(x_user_id: Optional[str] = Header(None, alias="X-User-ID")) -> str:
    if not x_user_id:
        raise HTTPException(422, "X-User-ID header required")
    return x_user_id


@router.post("/upload")
async def upload_reference(
    user_id: str = Depends(_user_id),
    file: UploadFile = File(..., description="声音参考样本（WAV/MP3/M4A/OGG/FLAC，10~60s）"),
    agree_authorized: bool = File(False, description="授权确认：我拥有该声音使用权或已获授权"),
):
    """上传声音参考样本。必须勾选授权确认，否则拒绝。"""
    if not agree_authorized:
        raise HTTPException(422, "必须确认你拥有该声音的使用权或已获得声音本人授权")

    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(422, f"参考音频超过大小限制（{MAX_UPLOAD_BYTES // (1024 * 1024)}MB）")
    if not data:
        raise HTTPException(422, "参考音频为空，请重新上传")

    try:
        ref = await vrs.create_voice_reference(user_id, data, agree_authorized=agree_authorized)
    except vrs.VoiceReferenceError as exc:
        raise HTTPException(422, str(exc))

    return {
        "success": True,
        "reference_id": ref.reference_id,
        "duration": round(ref.duration, 1),
        "format": ref.format,
        "message": "声音样本已就绪",
    }


@router.get("/list")
async def list_references(user_id: str = Depends(_user_id)):
    """列出当前用户的声音参考样本。"""
    return {"success": True, "references": vrs.list_references(user_id)}


@router.get("/{reference_id}")
async def get_reference(reference_id: str, user_id: str = Depends(_user_id)):
    """查询单个参考样本（仅限本人）。"""
    ref = vrs.get_reference(user_id, reference_id)
    if not ref:
        raise HTTPException(404, "Reference not found")
    return {
        "success": True,
        "reference_id": ref.reference_id,
        "duration": round(ref.duration, 1),
        "format": ref.format,
        "status": ref.status,
        "created_at": ref.created_at,
        "agree_authorized": ref.agree_authorized,
        "prompt_language": ref.prompt_language,
        "detected_language": ref.detected_language,
    }


@router.get("/{reference_id}/download")
async def download_reference(reference_id: str, user_id: str = Depends(_user_id)):
    """下载参考样本（10 分钟 presigned URL，仅限本人）。"""
    url = vrs.get_reference_presigned_url(user_id, reference_id)
    if not url:
        raise HTTPException(404, "Reference not found or unavailable")
    return {"success": True, "url": url, "expires_at": 600}


@router.delete("/{reference_id}")
async def delete_reference(reference_id: str, user_id: str = Depends(_user_id)):
    """删除参考样本（仅限本人）。"""
    ok = await vrs.delete_reference(user_id, reference_id)
    if not ok:
        raise HTTPException(404, "Reference not found")
    return {"success": True, "message": "参考样本已删除"}