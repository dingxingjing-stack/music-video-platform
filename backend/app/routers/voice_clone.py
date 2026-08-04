"""
声音克隆 API 路由 v2 — 合规版
- /voices         → 分组返回（官方 + 用户私有）
- /upload         → 上传校验 + 月度配额
- /clone          → TTS 合成（含 pitch/speed）
- /clone-quota    → 查询用户本月配额
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from ..services.voice_clone_service import (
    voice_clone_service,
    VoiceSample,
    VoiceCloneRequest,
    VoiceCloneResponse,
    QuotaInfo,
)

router = APIRouter(prefix="/voice", tags=["声音克隆"])

@router.get("/voices", response_model=List[VoiceSample])
async def list_voices(user_id: str = Query("anonymous", description="用户 ID")):
    return voice_clone_service.list_voices(user_id)

@router.get("/clone-quota", response_model=QuotaInfo)
async def clone_quota(user_id: str = Query("anonymous", description="用户 ID")):
    return voice_clone_service.get_quota(user_id)

@router.post("/upload", response_model=VoiceSample)
async def upload_voice(
    audio_url: str = Query(..., description="音频 URL"),
    name: Optional[str] = Query(None, description="音色名称"),
    user_id: str = Query("anonymous", description="用户 ID"),
):
    if not audio_url:
        raise HTTPException(400, "audio_url 必填")
    try:
        return voice_clone_service.upload_voice(audio_url, name, user_id)
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.post("/clone", response_model=VoiceCloneResponse)
async def clone_voice(request: VoiceCloneRequest):
    if not request.text or len(request.text) > 1000:
        raise HTTPException(400, "文本长度必须在 1-1000 字符之间")
    return await voice_clone_service.clone_voice(request)

@router.get("/presets", response_model=List[VoiceSample])
async def get_presets():
    return voice_clone_service.presets
