"""
声音克隆 API 路由
"""

from fastapi import APIRouter, HTTPException
from typing import List
from ..services.voice_clone_service import (
    voice_clone_service,
    VoiceSample,
    VoiceCloneRequest,
    VoiceCloneResponse,
)

router = APIRouter(
    prefix="/voice",
    tags=["声音克隆"],
)


@router.get("/voices", response_model=List[VoiceSample])
async def list_voices():
    """获取声音列表"""
    return voice_clone_service.list_voices()


@router.post("/upload", response_model=VoiceSample)
async def upload_voice(audio_url: str, name: str = None):
    """上传声音样本"""
    if not audio_url:
        raise HTTPException(status_code=400, detail="audio_url 必填")
    
    return voice_clone_service.upload_voice(audio_url, name)


@router.post("/clone", response_model=VoiceCloneResponse)
async def clone_voice(request: VoiceCloneRequest):
    """
    声音克隆合成
    
    - **voice_id**: 声音 ID (从 /api/v1/voice/voices 获取)
    - **text**: 合成文本 (最多 1000 字符)
    - **speed**: 速度 (0.5-2.0)
    - **pitch_shift**: 音高偏移 (-12 到 +12)
    """
    if not request.text or len(request.text) > 1000:
        raise HTTPException(status_code=400, detail="文本长度必须在 1-1000 字符之间")
    
    return await voice_clone_service.clone_voice(request)


@router.get("/presets", response_model=List[VoiceSample])
async def get_presets():
    """获取预设声音列表"""
    return voice_clone_service.presets