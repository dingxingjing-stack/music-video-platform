"""
音质测试 API

端点:
- POST /api/v1/audio/enhance-prompt - 测试 Prompt 增强效果
- POST /api/v1/audio/compare - A/B 测试不同生成策略
- GET /api/v1/audio/quality-stats - 音质统计
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
from app.services.prompt_enhancer import prompt_enhancer
import random

router = APIRouter(prefix="/api/v1/audio", tags=["audio-quality"])


class PromptEnhanceRequest(BaseModel):
    user_prompt: str
    style: str = "pop"
    template: str = "professional"


class PromptEnhanceResponse(BaseModel):
    original: str
    enhanced: str
    improvements: List[str]


class ABTestRequest(BaseModel):
    user_prompt: str
    style: str
    num_variants: int = 4


class ABTestResponse(BaseModel):
    variants: List[Dict[str, str]]
    recommendation: str


@router.post("/enhance-prompt", response_model=PromptEnhanceResponse)
async def test_prompt_enhancement(request: PromptEnhanceRequest):
    """
    测试 Prompt 增强效果
    
    输入用户原始 prompt，返回增强版本
    """
    enhanced = prompt_enhancer.enhance(
        user_prompt=request.user_prompt,
        style=request.style,
        template=request.template,
        production_quality=True
    )
    
    improvements = [
        "✅ 添加了专业制作质量标签",
        "✅ 细化了风格描述",
        "✅ 增加了情绪标签",
        "✅ 添加了参考曲目类型"
    ]
    
    return PromptEnhanceResponse(
        original=request.user_prompt,
        enhanced=enhanced,
        improvements=improvements
    )


@router.post("/compare", response_model=ABTestResponse)
async def ab_test_generation(request: ABTestRequest):
    """
    A/B 测试 - 生成多个变体用于对比
    """
    variants = []
    templates = ["detailed", "professional", "scene_based"]
    
    for i in range(request.num_variants):
        template = templates[i % len(templates)]
        enhanced = prompt_enhancer.enhance(
            user_prompt=request.user_prompt,
            style=request.style,
            template=template,
            production_quality=True
        )
        variants.append({
            "id": f"variant_{i+1}",
            "prompt": enhanced,
            "template": template,
            "strategy": [
                "detailed" if template == "detailed" else 
                "professional" if template == "professional" else "scene-based"
            ][0]
        })
    
    return ABTestResponse(
        variants=variants,
        recommendation="建议使用 variant_2 (professional 模板) - 通常音质最佳"
    )


@router.get("/quality-stats")
async def get_quality_statistics():
    """获取音质优化统计信息"""
    # 模拟统计 (实际应从数据库读取)
    return {
        "total_generations": 156,
        "enhanced_generations": 142,
        "enhancement_rate": 0.91,
        "avg_quality_score": 8.3,
        "quality_improvement": "+1.8 vs 无增强",
        "favorite_templates": {
            "professional": 89,
            "detailed": 34,
            "scene_based": 19
        },
        "favorite_styles": {
            "pop": 45,
            "electronic": 38,
            "hiphop": 29,
            "ambient": 21,
            "rock": 17
        }
    }


@router.get("/prompt-templates")
async def get_prompt_templates():
    """获取所有可用的 Prompt 模板"""
    from app.services.prompt_enhancer import (
        STYLE_TAGS, MOOD_TAGS, PRODUCTION_TAGS, INSTRUMENT_TAGS
    )
    
    return {
        "styles": list(STYLE_TAGS.keys()),
        "style_descriptions": {
            style: tags["enhanced"][:2]
            for style, tags in STYLE_TAGS.items()
        },
        "moods": MOOD_TAGS[:8],  # 前 8 个
        "production_tags": PRODUCTION_TAGS,
        "instrument_categories": list(INSTRUMENT_TAGS.keys()),
        "usage_guide": """
        使用建议:
        1. 选择与歌曲匹配的风格 (style)
        2. 添加 1-2 个情绪标签 (mood)
        3. 指定具体的乐器 (instruments)
        4. 启用制作质量标签 (production_quality=True)
        5. 选择 professional 模板获得最佳效果
        """
    }