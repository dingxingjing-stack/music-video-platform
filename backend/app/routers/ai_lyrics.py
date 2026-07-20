"""
AI 作词 API 路由
"""

import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from typing import Optional, List
from app.services.lyric_service import lyric_service, LyricRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/lyrics", tags=["lyrics"])


class GenerateLyricRequest(BaseModel):
    """歌词生成请求"""
    theme: str
    style: Optional[str] = "pop"
    language: Optional[str] = "zh"
    mood: Optional[str] = "happy"
    structure: Optional[str] = "verse-chorus-verse-chorus-bridge-chorus"
    custom_lyrics: Optional[str] = None
    rhyme_scheme: Optional[str] = "AABB"


class GenerateLyricResponse(BaseModel):
    """歌词生成响应"""
    success: bool
    lyrics: str
    structure: str
    rhyme_analysis: Optional[str] = None
    message: str


@router.get("/styles", response_model=List[dict])
async def get_lyric_styles():
    """获取可用歌词风格列表"""
    return lyric_service.get_available_styles()


@router.get("/moods", response_model=List[str])
async def get_lyric_moods():
    """获取可用情绪列表"""
    return lyric_service.get_available_moods()


@router.post("/generate", response_model=GenerateLyricResponse)
async def generate_lyrics(request: GenerateLyricRequest):
    """生成歌词"""
    try:
        lyric_request = LyricRequest(
            theme=request.theme,
            style=request.style,
            language=request.language,
            mood=request.mood,
            structure=request.structure,
            custom_lyrics=request.custom_lyrics,
            rhyme_scheme=request.rhyme_scheme
        )
        
        response = await lyric_service.generate_lyrics(lyric_request)
        
        if not response.success:
            # 服务层失败，返回 200 + 友好提示（不抛 500）
            logger.warning("Lyric generation failed: %s", response.message)
            return GenerateLyricResponse(
                success=False,
                lyrics="（生成失败，请稍后重试）",
                structure="",
                rhyme_analysis=None,
                message=f"生成服务暂时不可用: {response.message}"
            )
        
        return response
    except Exception as e:
        logger.exception("Lyric generation exception")
        # 任何异常都包装成 200 返回，前端不崩
        return GenerateLyricResponse(
            success=False,
            lyrics="（生成失败，请稍后重试）",
            structure="",
            rhyme_analysis=None,
            message=f"服务异常: {str(e)}"
        )


@router.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    """捕获 Pydantic 422，返回 200 + 友好提示"""
    logger.warning("Validation error in %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=200,
        content={
            "success": False,
            "lyrics": "（请求参数错误）",
            "structure": "",
            "rhyme_analysis": None,
            "message": f"参数格式错误: {exc.errors()[0]['msg'] if exc.errors() else '请检查输入'}"
        }
    )


@router.post("/continue", response_model=GenerateLyricResponse)
async def continue_lyrics(
    existing_lyrics: str,
    style: Optional[str] = "pop"
):
    """续写歌词"""
    response = await lyric_service.continue_lyrics(existing_lyrics, style)
    
    if not response.success:
        raise HTTPException(status_code=500, detail=response.message)
    
    return response


@router.get("/analyze")
async def analyze_lyrics(lyrics: str):
    """分析歌词结构和押韵"""
    structure = lyric_service._parse_structure(lyrics)
    rhyme_analysis = lyric_service._analyze_rhyme(lyrics, "zh")
    
    return {
        "structure": structure,
        "rhyme_analysis": rhyme_analysis
    }