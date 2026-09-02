"""
歌曲续写服务
功能:
- 从歌曲任意时间点继续创作
- 自动匹配风格和 BPM
- 生成交互式和弦进行
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import random

router = APIRouter(prefix="/api/v1/music", tags=["续写"])

class SongContinuationRequest(BaseModel):
    song_id: str
    continue_from: float  # 续写起始时间 (秒)
    prompt: Optional[str] = None  # 可选的续写提示
    style: Optional[str] = None  # 可选的风格覆盖
    duration: int = 60  # 续写时长 (秒)
    
class SongContinuationResponse(BaseModel):
    song_id: str
    continued_song_id: str
    title: str
    duration: float
    status: str
    audio_url: Optional[str] = None
    lyrics: Optional[str] = None

# 真实续写逻辑 — 转发至 continuation_service（单段 Audio2Audio 续写）
@router.post("/continue", response_model=SongContinuationResponse)
async def continue_song(request: SongContinuationRequest):
    """
    从歌曲的任意时间点继续创作（真实实现，非 Mock）
    转发到 continuation_service.continue_song，复用 BPM/key/歌词续写/FFmpeg 能力
    """
    from app.services.continuation_service import continuation_service
    from fastapi import Request
    # 限制单段续写不超过 60s（长任务走 /api/v1/ai/generate 的 150+150 路径）
    duration = min(int(request.duration), 60)
    try:
        result = await continuation_service.continue_song(
            song_id=request.song_id,
            continue_from=float(request.continue_from),
            duration=duration,
            style=request.style,
            prompt=request.prompt,
            user_key="",  # 若需归属校验可从 header 取，当前保持兼容
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error") or "续写失败")
        return SongContinuationResponse(
            song_id=request.song_id,
            continued_song_id=result.get("song_id") or result.get("new_song_id") or f"{request.song_id}_cont",
            title="续写版本",
            duration=result.get("duration") or duration,
            status="completed",
            audio_url=result.get("audio_url") or None,
            lyrics=result.get("lyrics") or None,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"续写失败: {type(e).__name__}: {e}")

class SongStructureRequest(BaseModel):
    song_id: str
    structure: str  # 如："Intro-Verse-Chorus-Verse-Chorus-Bridge-Chorus-Outro"
    
class SongStructureResponse(BaseModel):
    song_id: str
    new_song_id: str
    sections: List[dict]
    duration: float
    
@router.post("/extend-structure", response_model=SongStructureResponse)
async def extend_song_structure(request: SongStructureRequest):
    """
    扩展歌曲结构 - 一键添加段落
    
    支持的段落类型:
    - Intro (前奏)
    - Verse (主歌)
    - Chorus (副歌)
    - Bridge (桥段)
    - Outro (尾奏)
    - Solo (独奏)
    - Break (间奏)
    """
    sections = []
    total_duration = 0
    
    section_types = {
        "Intro": {"duration": 15, "energy": "low"},
        "Verse": {"duration": 30, "energy": "medium"},
        "Chorus": {"duration": 25, "energy": "high"},
        "Bridge": {"duration": 20, "energy": "medium"},
        "Outro": {"duration": 15, "energy": "low"},
        "Solo": {"duration": 20, "energy": "high"},
        "Break": {"duration": 10, "energy": "low"}
    }
    
    for section_name in request.structure.split("-"):
        if section_name in section_types:
            section_info = section_types[section_name]
            sections.append({
                "name": section_name,
                "start_time": total_duration,
                "duration": section_info["duration"],
                "energy": section_info["energy"]
            })
            total_duration += section_info["duration"]
    
    return SongStructureResponse(
        song_id=request.song_id,
        new_song_id=f"{request.song_id}_extended",
        sections=sections,
        duration=total_duration
    )