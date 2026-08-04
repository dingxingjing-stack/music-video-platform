"""
歌词押韵 AI 路由

端点:
- POST /lyrics/analyze - 分析歌词押韵
- POST /lyrics/suggest - 生成押韵建议
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.services.lyrics_rhyme_ai import analyze_lyrics_rhyme, generate_rhyme_suggestion

router = APIRouter(prefix="/api/v1/lyrics", tags=["歌词押韵 AI"])


class LyricsAnalyzeRequest(BaseModel):
    lines: List[str]
    language: Optional[str] = "zh"


class LyricsSuggestRequest(BaseModel):
    previous_line: str
    language: Optional[str] = "zh"


@router.post("/analyze")
async def analyze_lyrics(request: LyricsAnalyzeRequest):
    """分析歌词押韵格式和得分"""
    result = analyze_lyrics_rhyme(request.lines)
    return {
        "success": True,
        "data": result
    }


@router.post("/suggest")
async def suggest_rhyme(request: LyricsSuggestRequest):
    """根据上一句生成押韵建议"""
    suggestion = generate_rhyme_suggestion(request.previous_line)
    return {
        "success": True,
        "suggestion": suggestion
    }