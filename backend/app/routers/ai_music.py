"""
AI 音乐生成路由
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.services.mureka_service import mureka_service, MurekaSongRequest
from app.services.agnes_music_service import agnes_service, AgnesSongRequest

router = APIRouter(prefix="/api/v1/ai", tags=["ai-music"])


class GenerateRequest(BaseModel):
    """AI 生成请求"""
    prompt: str  # 音乐提示词
    style: str = "pop"  # 风格
    duration: Optional[int] = None  # 时长（秒）
    type: str = "song"  # song/music/bgm


class GenerateResponse(BaseModel):
    """AI 生成响应"""
    success: bool
    audio_url: Optional[str] = None
    error: Optional[str] = None
    task_id: Optional[str] = None
    ai_provider: Optional[str] = None   # "agnes" / "gemini" / "mureka"
    agnes_debug: Optional[str] = None    # 调试 Agnes 调用详情


@router.post("/generate", response_model=GenerateResponse)
async def generate_music(request: GenerateRequest):
    """
    AI 生成音乐（Agnes 主力 + Gemini 备用 + Mureka 音频）
    
    - **prompt**: 音乐提示词（风格、情绪、节奏等）
    - **style**: 音乐风格（pop/rock/electronic/hip-hop/r&b/jazz/classical/ambient/cinematic/lo-fi）
    - **duration**: 时长（秒），可选
    - **type**: 生成类型（song=带人声，music=纯音乐，bgm=背景音乐）
    """
    # 验证提示词
    if not request.prompt or len(request.prompt.strip()) < 5:
        raise HTTPException(status_code=400, detail="提示词至少需要 5 个字符")
    
    # 1. 使用 Agnes 优化提示词 + 生成歌词（主力）
    agnes_request = AgnesSongRequest(
        prompt=request.prompt,
        style=request.style,
        duration=request.duration or 180,
        type=request.type,
    )
    
    agnes_result = await agnes_service.generate_song(agnes_request)
    
    # 记录 AI 提供者 + 调试信息
    ai_provider = "agnes" if agnes_result.optimized_prompt and agnes_result.optimized_prompt != request.prompt else "gemini"
    agnes_debug = f"success={agnes_result.success}, opt_changed={'yes' if agnes_result.optimized_prompt != request.prompt else 'no'}, error={agnes_result.error}, key_set={bool(agnes_service.API_KEY)}"
    
    # 2. 使用优化后的提示词调用 Mureka 生成音频
    final_prompt = agnes_result.optimized_prompt or request.prompt
    if agnes_result.generated_lyrics:
        final_prompt = agnes_result.generated_lyrics
    
    mureka_request = MurekaSongRequest(
        lyrics=final_prompt,
        style=request.style,
        duration=request.duration,
    )
    
    mureka_result = await mureka_service.generate_song(mureka_request)
    
    return GenerateResponse(
        success=mureka_result.success,
        audio_url=mureka_result.audio_url,
        error=mureka_result.error,
        task_id=mureka_result.task_id,
        ai_provider=ai_provider,
        agnes_debug=agnes_debug,
    )


@router.get("/styles")
async def list_styles():
    """获取支持的音乐风格"""
    return {
        "styles": [
            {"value": "pop", "label": "流行", "description": "主流流行音乐"},
            {"value": "rock", "label": "摇滚", "description": "摇滚乐"},
            {"value": "electronic", "label": "电子", "description": "电子音乐"},
            {"value": "hip-hop", "label": "嘻哈", "description": "嘻哈/说唱"},
            {"value": "r&b", "label": "R&B", "description": "节奏布鲁斯"},
            {"value": "jazz", "label": "爵士", "description": "爵士乐"},
            {"value": "classical", "label": "古典", "description": "古典音乐"},
            {"value": "ambient", "label": "氛围", "description": "氛围音乐"},
            {"value": "cinematic", "label": "电影配乐", "description": "电影原声"},
            {"value": "lo-fi", "label": "Lo-Fi", "description": "低保真音乐"},
        ]
    }