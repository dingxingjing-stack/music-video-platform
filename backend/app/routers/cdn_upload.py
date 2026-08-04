"""
CDN 上传 API

端点:
- POST /cdn/upload - 上传文件到 CDN
- POST /cdn/presigned-url - 获取预签名上传 URL (前端直传)
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict

from app.services.cdn_uploader import cdn_uploader, upload_to_cdn

router = APIRouter(prefix="/api/v1/cdn", tags=["CDN 上传"])


class UploadResponse(BaseModel):
    """上传响应"""
    success: bool
    cdn_url: str
    file_key: str
    provider: str
    file_size: Optional[int] = None
    error: Optional[str] = None


class PresignedUrlResponse(BaseModel):
    """预签名 URL 响应"""
    success: bool
    upload_url: Optional[str]
    file_key: str
    cdn_url: Optional[str]
    provider: str
    expires_in: int = 900
    error: Optional[str] = None


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(..., description="要上传的文件"),
    file_type: str = Form(..., description="文件类型：audio/video/image")
):
    """
    上传文件到 CDN
    
    支持:
    - Cloudflare R2 (推荐)
    - AWS S3
    - 本地存储 (回退)
    
    费用估算:
    - Cloudflare R2: 免费 10GB/月，超出后 $0.015/GB
    - AWS S3: $0.023/GB/月
    """
    try:
        # 1. 验证文件类型
        allowed_types = {
            "audio": ["audio/wav", "audio/mp3", "audio/flac", "audio/aac", "audio/ogg"],
            "video": ["video/mp4", "video/webm", "video/avi", "video/mov"],
            "image": ["image/png", "image/jpeg", "image/webp", "image/gif"],
        }
        
        if file_type not in allowed_types:
            return UploadResponse(
                success=False,
                cdn_url="",
                file_key="",
                provider="unknown",
                error=f"不支持的文件类型：{file_type}"
            )
        
        # 2. 检查 MIME 类型
        if file.content_type not in allowed_types[file_type]:
            # 宽松模式：允许上传
            print(f"⚠️ MIME 类型不匹配：{file.content_type} (期望：{allowed_types[file_type]})")
        
        # 3. 保存到临时文件
        import tempfile
        import os
        
        temp_fd, temp_path = tempfile.mkstemp(suffix=os.path.splitext(file.filename or "file")[1])
        os.close(temp_fd)
        
        # 读取文件内容
        content = await file.read()
        with open(temp_path, 'wb') as f:
            f.write(content)
        
        file_size = len(content)
        
        # 4. 上传到 CDN
        cdn_url = await upload_to_cdn(temp_path, file_type)
        
        # 5. 清理临时文件
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        # 6. 提取 file_key
        file_key = cdn_url.split('/')[-1]
        provider = cdn_uploader.provider.value
        
        return UploadResponse(
            success=True,
            cdn_url=cdn_url,
            file_key=file_key,
            provider=provider,
            file_size=file_size,
            error=None
        )
    
    except Exception as e:
        return UploadResponse(
            success=False,
            cdn_url="",
            file_key="",
            provider="unknown",
            error=str(e)
        )


@router.post("/presigned-url", response_model=PresignedUrlResponse)
async def get_presigned_url(
    file_type: str = Form(..., description="文件类型：audio/video/image"),
    file_ext: str = Form(..., description="文件扩展名：.wav/.mp4/.png")
):
    """
    获取预签名上传 URL
    
    用于前端直传文件到 CDN，避免通过后端中转
    
    流程:
    1. 前端调用此接口获取 upload_url
    2. 前端 PUT 文件到 upload_url
    3. CDN 返回 cdn_url
    """
    try:
        result = cdn_uploader.get_upload_url(file_type, file_ext)
        
        if result["upload_url"] is None:
            # 本地存储模式
            return PresignedUrlResponse(
                success=False,
                upload_url=None,
                file_key=result["file_key"],
                cdn_url=None,
                provider="local",
                error="本地存储不支持预签名 URL，请直接调用 /upload 接口"
            )
        
        return PresignedUrlResponse(
            success=True,
            upload_url=result["upload_url"],
            file_key=result["file_key"],
            cdn_url=result.get("cdn_url"),
            provider=result["provider"],
            expires_in=900,  # 15 分钟
            error=None
        )
    
    except Exception as e:
        return PresignedUrlResponse(
            success=False,
            upload_url=None,
            file_key="",
            cdn_url=None,
            provider="unknown",
            expires_in=900,
            error=str(e)
        )


@router.get("/info")
async def get_cdn_info():
    """
    获取 CDN 配置信息
    """
    provider = cdn_uploader.provider
    config = {
        "provider": provider.value,
        "base_url": cdn_uploader.base_url,
        "bucket": cdn_uploader.bucket,
        "features": {
            "presigned_urls": provider != cdn_uploader.provider.LOCAL,
            "auto_compress": True,
            "cache_control": True,
        }
    }
    
    # 费用估算
    if provider == cdn_uploader.provider.R2:
        config["pricing"] = {
            "free_tier": "10GB/月",
            "overage": "$0.015/GB",
            "egress": "免费"
        }
    elif provider == cdn_uploader.provider.S3:
        config["pricing"] = {
            "storage": "$0.023/GB/月",
            "requests": "$0.0004/1000 请求",
            "egress": "$0.09/GB (前 10TB)"
        }
    else:
        config["pricing"] = {
            "storage": "本地磁盘",
            "requests": "免费",
            "egress": "免费"
        }
    
    return {
        "success": True,
        "config": config
    }