"""
分轨导出路由 (Stems Export Router)

API 端点:
POST /api/v1/export/stems — 导出分轨
GET  /api/v1/export/stems/{track_id} — 获取分轨状态
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from app.services.stems_export_service import stems_service, StemTrack


router = APIRouter(prefix="/api/v1/export", tags=["分轨导出"])


class StemsRequest(BaseModel):
    """分轨导出请求"""
    audio_url: str
    track_id: Optional[str] = None


class StemsResponse(BaseModel):
    """分轨导出响应"""
    success: bool
    stems: List[StemTrack]
    original_url: Optional[str] = None
    duration: int = 0
    error: Optional[str] = None


@router.post("/stems", response_model=StemsResponse)
async def export_stems(request: StemsRequest):
    """
    导出分轨
    
    将完整音频分离为独立轨道:
    - 人声 (Vocals)
    - 鼓组 (Drums)
    - 贝斯 (Bass)
    - 其他 (Other)
    
    返回分轨音频 URL 列表，可在多轨编辑器中单独处理
    """
    result = await stems_service.export_stems(request.audio_url)
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    
    return result


@router.get("/stems/{track_id}")
async def get_stems_status(track_id: str):
    """
    获取分轨导出状态
    
    TODO: 实现异步任务队列后，返回导出进度
    """
    return {
        "status": "completed",
        "track_id": track_id,
        "message": "分轨已就绪",
    }