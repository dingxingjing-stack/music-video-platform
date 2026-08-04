"""
智能抠图 API

端点:
- POST /bg/remove - 单张抠图
- POST /bg/batch - 批量抠图
- GET /bg/quota - 配额查询
- GET /bg/pricing - 价格方案
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
import tempfile
import os

from app.services.bg_removal import bg_removal_service, remove_background, batch_remove_background

router = APIRouter(prefix="/api/v1/bg", tags=["智能抠图"])


class BGRemovalResponse(BaseModel):
    """抠图响应"""
    success: bool
    output_url: Optional[str] = None
    credits_charged: int = 0
    credits_remaining: int = 0
    error: Optional[str] = None


class BatchBGRemovalResponse(BaseModel):
    """批量抠图响应"""
    success: bool
    results: List[dict] = []
    total_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    total_credits: int = 0


@router.post("/remove", response_model=BGRemovalResponse)
async def remove_bg_endpoint(
    image: UploadFile = File(..., description="要抠图的图片"),
    bg_color: Optional[str] = Form(None, description="背景颜色"),
    bg_image_url: Optional[str] = Form(None, description="背景图片 URL"),
    size: str = Form("auto", description="输出尺寸 (auto/preview/full)"),
    format: str = Form("png", description="输出格式 (png/jpg)"),
    type: str = Form("auto", description="抠图类型 (auto/person/product/car/graphics)")
):
    """
    智能抠图 - 移除图片背景
    
    支持:
    - Remove.bg API (精准，需 API 密钥)
    - 本地 rembg (免费，质量较好)
    
    费用:
    - Remove.bg: 1 credit/张 (约¥1.4)
    - 本地方案：免费
    """
    # 验证文件类型
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="请上传图片文件")
    
    # 保存到临时文件
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(image.filename or "image.png")[1]) as tmp:
        tmp.write(await image.read())
        tmp_path = tmp.name
    
    try:
        # 调用抠图服务
        result = await remove_background(
            tmp_path,
            bg_color=bg_color,
            bg_image=bg_image_url,
            size=size,
            format=format,
            type=type
        )
        
        if result["success"]:
            # 生成 CDN URL (如果配置了 CDN)
            output_url = result["output_path"]
            # TODO: 上传到 CDN
            
            return BGRemovalResponse(
                success=True,
                output_url=output_url,
                credits_charged=result["credits_charged"],
                credits_remaining=result["credits_remaining"],
                error=None
            )
        else:
            return BGRemovalResponse(
                success=False,
                output_url=None,
                credits_charged=0,
                credits_remaining=0,
                error=result["error"]
            )
    
    finally:
        # 清理临时文件
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/batch", response_model=BatchBGRemovalResponse)
async def remove_bg_batch_endpoint(
    images: List[UploadFile] = File(..., description="图片列表"),
    size: str = Form("auto", description="输出尺寸"),
    format: str = Form("png", description="输出格式"),
):
    """
    批量抠图
    
    最多支持 50 张图片同时处理
    """
    if len(images) > 50:
        raise HTTPException(status_code=400, detail="最多支持 50 张图片")
    
    # 保存所有临时文件
    temp_files = []
    for img in images:
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(img.filename or "image.png")[1]) as tmp:
            tmp.write(await img.read())
            temp_files.append(tmp.name)
    
    try:
        # 批量处理
        results = await batch_remove_background(temp_files, max_concurrent=5)
        
        success_count = sum(1 for r in results if r["success"])
        failed_count = len(results) - success_count
        total_credits = sum(r.get("credits_charged", 0) for r in results)
        
        return BatchBGRemovalResponse(
            success=True,
            results=results,
            total_count=len(results),
            success_count=success_count,
            failed_count=failed_count,
            total_credits=total_credits
        )
    
    finally:
        # 清理临时文件
        for tmp_path in temp_files:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


@router.get("/quota")
async def get_quota():
    """查询抠图配额"""
    quota_info = bg_removal_service.get_quota_info()
    return {
        "success": True,
        "quota": quota_info
    }


@router.get("/pricing")
async def get_pricing():
    """查询抠图价格"""
    pricing_info = bg_removal_service.get_pricing_info()
    return {
        "success": True,
        "pricing": pricing_info
    }