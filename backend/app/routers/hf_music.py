"""
HF 音乐生成路由 - V1.1 公测
复用 ai_music.py 80% 逻辑，仅修改服务调用为 HFMusicService

端点:
  POST /api/v1/ai/generate - 生成歌曲
  GET  /api/v1/ai/styles - 获取风格列表
  POST /api/v1/ai/generate-hf - HF 专属生成 (支持选择模型)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import os
from app.services.hf_music_service import HFMusicService, HFMusicGenerationRequest, HFModel

router = APIRouter(tags=["ai-music-hf"])
hf_service = HFMusicService()

# Mock 模式配置
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() == "true"
MOCK_AUDIO_URL = os.getenv("MOCK_HF_AUDIO_URL", "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3")


class GenerateRequest(BaseModel):
    """AI 生成请求 - 复用原结构"""
    prompt: str  # 音乐提示词
    style: str = "pop"  # 风格
    duration: Optional[int] = 30  # 时长（秒）
    lyrics: Optional[str] = None  # 歌词（可选）
    temperature: Optional[float] = 0.7  # 随机性


class GenerateResponse(BaseModel):
    """AI 生成响应 - 复用原结构"""
    success: bool
    audio_url: Optional[str] = None
    error: Optional[str] = None
    task_id: Optional[str] = None
    model: Optional[str] = None  # HF 模型名称


class HFGenerateRequest(GenerateRequest):
    """HF 专属生成请求 - 支持选择模型"""
    model: HFModel = HFModel.ACE_STEP


@router.post("/generate", response_model=GenerateResponse)
async def generate_music(request: GenerateRequest):
    """
    AI 生成音乐 (默认使用 ACE-Step)
    
    - **prompt**: 音乐描述（风格、情绪、节奏等）
    - **style**: 音乐风格（pop/rock/electronic/hip-hop/r&b/jazz/classical/ambient/cinematic/lo-fi）
    - **duration**: 时长（秒），默认 30 秒
    - **lyrics**: 歌词（可选，ACE-Step/YuE 支持）
    - **temperature**: 随机性（0.0-1.0），默认 0.7
    """
    # 验证提示词
    if not request.prompt or len(request.prompt.strip()) < 5:
        raise HTTPException(status_code=400, detail="提示词至少需要 5 个字符")
    
    # 构建 HF 请求
    hf_request = HFMusicGenerationRequest(
        lyrics=request.lyrics or request.prompt,
        model=HFModel.ACE_STEP,  # 默认使用 ACE-Step
        style=request.style,
        duration=request.duration,
        temperature=request.temperature
    )
    
    # Mock 模式：直接返回假数据
    if MOCK_MODE:
        return GenerateResponse(
            success=True,
            audio_url=MOCK_AUDIO_URL,
            error=None,
            task_id="mock_hf_task_12345",
            model="hf_ace_step"
        )
    
    # 调用 HF Service
    result = await hf_service.generate_song(hf_request)
    
    return GenerateResponse(
        success=result.success,
        audio_url=result.audio_url,
        error=result.error,
        task_id=result.task_id,
        model=result.model.value if result.model else None
    )


@router.post("/generate-hf", response_model=GenerateResponse)
async def generate_music_hf(request: HFGenerateRequest):
    """
    HF 专属生成 - 可选择模型
    
    - **model**: HF 模型 (hf_musicgen, hf_ace_step, hf_yue)
    - **prompt**: 音乐提示词
    - **style**: 音乐风格
    - **duration**: 时长（秒）
    - **lyrics**: 歌词（可选）
    - **temperature**: 随机性
    """
    # 验证提示词
    if not request.prompt or len(request.prompt.strip()) < 5:
        raise HTTPException(status_code=400, detail="提示词至少需要 5 个字符")
    
    # 构建 HF 请求
    hf_request = HFMusicGenerationRequest(
        lyrics=request.lyrics or request.prompt,
        model=request.model,
        style=request.style,
        duration=request.duration,
        temperature=request.temperature
    )
    
    # Mock 模式：直接返回假数据
    if MOCK_MODE:
        return GenerateResponse(
            success=True,
            audio_url=MOCK_AUDIO_URL,
            error=None,
            task_id=f"mock_hf_{request.model.value}_12345",
            model=request.model.value
        )
    
    # 调用 HF Service
    result = await hf_service.generate_song(hf_request)
    
    return GenerateResponse(
        success=result.success,
        audio_url=result.audio_url,
        error=result.error,
        task_id=result.task_id,
        model=result.model.value if result.model else None
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


@router.get("/models")
async def list_models():
    """获取可用的 HF 模型"""
    try:
        models = await hf_service.get_available_models()
        return {
            "models": [
                {
                    "id": model.value,
                    "name": model.value.replace("hf_", "").title(),
                    "available": True
                }
                for model in models
            ]
        }
    except Exception as e:
        # 返回静态列表（当 HF Space 不可达时）
        return {
            "models": [
                {"id": "hf_musicgen", "name": "MusicGen (Meta)", "available": True},
                {"id": "hf_ace_step", "name": "ACE-Step", "available": True},
                {"id": "hf_yue", "name": "YuE (Wed Strength)", "available": True}
            ]
        }


@router.get("/health")
async def check_health(model: HFModel = HFModel.ACE_STEP):
    """检查 HF Space 健康状态"""
    try:
        health = await hf_service.check_health(model)
        return {
            "success": True,
            "data": health
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))