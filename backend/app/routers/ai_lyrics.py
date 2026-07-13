"""
AI 作词 API 路由
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from app.services.lyric_service import lyric_service, LyricRequest

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
        raise HTTPException(status_code=500, detail=response.message)
    
    return response


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