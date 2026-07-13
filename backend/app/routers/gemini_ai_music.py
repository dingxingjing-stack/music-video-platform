"""
AI 音乐生成路由（Gemini 临时方案 - 开发阶段）
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.services.gemini_music_service import gemini_service, GeminiSongRequest

router = APIRouter()


class GenerateRequest(BaseModel):
    """音乐生成请求"""
    prompt: str
    style: str
    duration: Optional[int] = 180
    type: Optional[str] = "song"
    # Phase 1 新增
    vocal_type: Optional[str] = "auto"  # auto/male/female/instrumental
    weirdness: Optional[float] = 0.5  # 0-1 风格偏离度
    style_strength: Optional[float] = 0.7  # 0-1 风格强度
    structure: Optional[str] = None  # 歌曲结构 JSON
    lyrics: Optional[str] = None  # 自定义歌词


class GenerateResponse(BaseModel):
    """音乐生成响应"""
    success: bool
    audio_url: Optional[str]
    optimized_prompt: Optional[str]
    style_suggestions: Optional[list]
    error: Optional[str]
    task_id: Optional[str]
    generated_lyrics: Optional[str] = None


@router.post("/generate", response_model=GenerateResponse)
async def generate_music(request: GenerateRequest):
    """
    生成音乐（Gemini 临时方案）
    
    - **prompt**: 音乐提示词（至少 5 个字符）
    - **style**: 音乐风格（pop/rock/electronic/hip-hop/r&b/jazz/classical/ambient/cinematic/lo-fi）
    - **duration**: 时长（秒），默认 180
    - **type**: 类型（song/music/bgm），默认 song
    
    开发阶段：使用 Mock 音频 + Gemini 提示词优化
    生产阶段：切换回 Mureka API 或 NVIDIA NVAPI
    """
    if len(request.prompt) < 5:
        raise HTTPException(status_code=400, detail="提示词至少需要 5 个字符")
    
    valid_styles = ["pop", "rock", "electronic", "hip-hop", "r&b", "jazz", "classical", "ambient", "cinematic", "lo-fi"]
    if request.style not in valid_styles:
        raise HTTPException(status_code=400, detail=f"不支持的风格：{request.style}。可选：{', '.join(valid_styles)}")
    
    # 调用 Gemini 服务
    song_request = GeminiSongRequest(
        prompt=request.prompt,
        style=request.style,
        duration=request.duration,
        type=request.type,
        vocal_type=request.vocal_type,
        weirdness=request.weirdness,
        style_strength=request.style_strength,
        structure=request.structure,
        lyrics=request.lyrics
    )
    
    response = await gemini_service.generate_song(song_request)
    
    if not response.success:
        raise HTTPException(status_code=500, detail=response.error)
    
    return response


@router.get("/styles", response_model=list)
async def get_styles():
    """获取支持的音乐风格"""
    return await gemini_service.get_styles()