"""
RunwayML AI 特效路由

端点:
- POST /ai/video - 图生视频
- POST /ai/inpaint - AI 扩图
- GET /ai/status/:task_id - 查询状态
- GET /ai/pricing - 价格查询
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from app.services.runway_ml import runway_service

router = APIRouter(prefix="/api/v1/ai-effects", tags=["AI 特效"])


class VideoGenRequest(BaseModel):
    image_url: str
    prompt: Optional[str] = ""
    motion_score: int = 5
    duration: int = 4
    aspect_ratio: str = "16:9"


class InpaintRequest(BaseModel):
    image_url: str
    mask_url: str
    prompt: str
    negative_prompt: Optional[str] = ""
    strength: float = 0.75


@router.post("/video")
async def generate_video(request: VideoGenRequest):
    """图生视频 (AI 动画)"""
    result = await runway_service.generate_image_to_video(
        image_url=request.image_url,
        prompt=request.prompt,
        motion_score=request.motion_score,
        duration=request.duration,
        aspect_ratio=request.aspect_ratio
    )
    
    if result["status"] == "failed":
        raise HTTPException(status_code=400, detail=result["error"])
    
    return {
        "success": True,
        "task_id": result["task_id"],
        "status": result["status"],
        "poll_url": result.get("poll_url")
    }


@router.post("/inpaint")
async def inpaint_image(request: InpaintRequest):
    """AI 扩图/修复"""
    result = await runway_service.inpaint_image(
        image_url=request.image_url,
        mask_url=request.mask_url,
        prompt=request.prompt,
        negative_prompt=request.negative_prompt,
        strength=request.strength
    )
    
    if result["status"] == "failed":
        raise HTTPException(status_code=400, detail=result["error"])
    
    return {
        "success": True,
        "task_id": result["task_id"],
        "status": result["status"]
    }


@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """查询任务状态"""
    result = await runway_service.get_task_status(task_id)
    return {
        "success": True,
        "data": result
    }


@router.get("/pricing")
async def get_pricing():
    """查询价格"""
    pricing = runway_service.get_pricing()
    return {
        "success": True,
        "pricing": pricing
    }