"""
一键发布路由 (One-Click Publish Router)

API 端点:
- GET /api/v1/publish/platforms - 获取可用平台列表
- POST /api/v1/publish/auth/{platform} - 获取平台授权 URL
- POST /api/v1/publish/callback/{platform} - OAuth 回调处理
- POST /api/v1/publish/upload - 上传视频到多个平台
- GET /api/v1/publish/status/{task_id} - 查询发布状态
"""

from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

router = APIRouter(prefix="/api/v1/publish", tags=["一键发布"])


# ============ Data Models ============

class PlatformInfo(BaseModel):
    id: str
    name: str
    icon: str
    color: str
    oauth_required: bool
    supported_formats: List[str]
    max_duration: int  # seconds
    max_file_size: int  # MB
    description: str


class PublishRequest(BaseModel):
    video_url: str = Field(..., description="视频文件 URL 或路径")
    platforms: List[str] = Field(..., description="目标平台列表：['youtube', 'tiktok', 'bilibili']")
    title: str = Field(..., description="视频标题")
    description: str = Field(..., description="视频描述")
    tags: List[str] = Field(default=[], description="标签列表")
    privacy: str = Field(default="public", description="隐私设置：public, unlisted, private")
    thumbnail_url: Optional[str] = Field(None, description="封面图 URL")
    category: Optional[str] = Field(None, description="分区/分类")


class PlatformSpecific(BaseModel):
    youtube: Optional[Dict] = None  # playlist_id, license, made_for_kids
    tiktok: Optional[Dict] = None   # allow_duet, allow_stitch
    bilibili: Optional[Dict] = None # copyright, source, no_reprint


class UploadResponse(BaseModel):
    success: bool
    task_id: str
    message: str
    platforms: List[str]
    estimated_time: int  # seconds


class TaskStatus(BaseModel):
    task_id: str
    status: str  # pending, processing, completed, failed
    progress: Dict[str, int]  # platform -> percentage
    results: Dict[str, Dict]
    error: Optional[str] = None


# ============ Mock Storage ============

publish_tasks: Dict[str, dict] = {}

SUPPORTED_PLATFORMS = [
    PlatformInfo(
        id="youtube",
        name="YouTube",
        icon="📺",
        color="#FF0000",
        oauth_required=True,
        supported_formats=["mp4", "mov", "avi", "wmv"],
        max_duration=43200,  # 12 hours
        max_file_size=256,   # 256 GB
        description="全球最大的视频分享平台"
    ),
    PlatformInfo(
        id="tiktok",
        name="TikTok",
        icon="🎵",
        color="#000000",
        oauth_required=True,
        supported_formats=["mp4", "mov"],
        max_duration=600,    # 10 minutes
        max_file_size=287,   # 287 MB
        description="短视频创意平台"
    ),
    PlatformInfo(
        id="bilibili",
        name="哔哩哔哩",
        icon="📱",
        color="#FB7299",
        oauth_required=True,
        supported_formats=["mp4", "flv", "mkv", "avi"],
        max_duration=10800,  # 3 hours
        max_file_size=10240, # 10 GB
        description="中国知名弹幕视频网站"
    ),
    PlatformInfo(
        id="instagram",
        name="Instagram Reels",
        icon="📸",
        color="#E4405F",
        oauth_required=True,
        supported_formats=["mp4", "mov"],
        max_duration=540,    # 9 minutes
        max_file_size=100,   # 100 MB
        description="Instagram 短视频功能"
    ),
]


# ============ Endpoints ============

@router.get("/platforms", response_model=List[PlatformInfo])
async def get_platforms():
    """获取所有支持的平台列表"""
    return SUPPORTED_PLATFORMS


@router.post("/auth/{platform}")
async def get_auth_url(platform: str):
    """获取平台 OAuth 授权 URL"""
    # Mock OAuth URLs
    auth_urls = {
        "youtube": "https://accounts.google.com/oauth/authorize?client_id=xxx&redirect_uri=xxx",
        "tiktok": "https://www.tiktok.com/auth/authorize?client_key=xxx&redirect_uri=xxx",
        "bilibili": "https://passport.bilibili.com/oauth2/authorize?app_id=xxx&redirect_uri=xxx",
        "instagram": "https://api.instagram.com/oauth/authorize?client_id=xxx&redirect_uri=xxx",
    }
    
    if platform not in auth_urls:
        raise HTTPException(status_code=404, detail=f"平台 {platform} 不支持")
    
    return {
        "success": True,
        "platform": platform,
        "auth_url": auth_urls[platform],
        "message": "请在浏览器中打开此 URL 完成授权"
    }


@router.post("/callback/{platform}")
async def oauth_callback(
    platform: str,
    code: str = Query(...),
    state: Optional[str] = Query(None)
):
    """OAuth 回调处理 - 存储 access_token"""
    # Mock token storage
    # 实际实现需要：
    # 1. 用 code 换取 access_token
    # 2. 存储到数据库或加密存储
    # 3. 处理 refresh_token
    
    return {
        "success": True,
        "platform": platform,
        "message": "授权成功",
        "expires_in": 3600  # 1 hour
    }


@router.post("/upload", response_model=UploadResponse)
async def upload_to_platforms(request: PublishRequest):
    """上传视频到多个平台"""
    task_id = str(uuid.uuid4())
    
    # 验证平台
    valid_platforms = [p.id for p in SUPPORTED_PLATFORMS]
    for platform in request.platforms:
        if platform not in valid_platforms:
            raise HTTPException(
                status_code=400, 
                detail=f"不支持的平台：{platform}"
            )
    
    # 创建任务
    publish_tasks[task_id] = {
        "status": "pending",
        "request": request,
        "progress": {p: 0 for p in request.platforms},
        "results": {},
        "created_at": datetime.now(),
    }
    
    # Mock 上传 (实际实现需要后台任务)
    # 这里模拟每个平台的上传时间
    total_time = len(request.platforms) * 30  # 每个平台约 30 秒
    
    return UploadResponse(
        success=True,
        task_id=task_id,
        message=f"开始上传到 {len(request.platforms)} 个平台",
        platforms=request.platforms,
        estimated_time=total_time
    )


@router.get("/status/{task_id}", response_model=TaskStatus)
async def get_upload_status(task_id: str):
    """查询上传状态"""
    if task_id not in publish_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task = publish_tasks[task_id]
    
    # Mock 进度更新
    # 实际实现需要查询各平台的上传状态
    import random
    
    if task["status"] == "pending":
        task["status"] = "processing"
    
    if task["status"] == "processing":
        for platform in task["progress"]:
            if task["progress"][platform] < 100:
                # 随机增加进度
                task["progress"][platform] = min(100, task["progress"][platform] + random.randint(10, 30))
        
        # 检查是否全部完成
        if all(p == 100 for p in task["progress"].values()):
            task["status"] = "completed"
            task["results"] = {
                platform: {
                    "success": True,
                    "url": f"https://{platform}.com/video/{uuid.uuid4().hex[:8]}",
                    "message": "发布成功"
                }
                for platform in task["progress"]
            }
    
    return TaskStatus(
        task_id=task_id,
        status=task["status"],
        progress=task["progress"],
        results=task["results"],
        error=task.get("error")
    )


@router.post("/cancel/{task_id}")
async def cancel_upload(task_id: str):
    """取消上传任务"""
    if task_id not in publish_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task = publish_tasks[task_id]
    if task["status"] == "completed":
        raise HTTPException(status_code=400, detail="任务已完成，无法取消")
    
    task["status"] = "cancelled"
    
    return {
        "success": True,
        "message": "已取消上传任务"
    }


@router.get("/history")
async def get_publish_history(
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0)
):
    """获取发布历史"""
    # Mock 历史数据
    return {
        "total": len(publish_tasks),
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "task_id": tid,
                "status": task["status"],
                "platforms": task["request"].platforms,
                "title": task["request"].title,
                "created_at": task["created_at"].isoformat(),
            }
            for tid, task in list(publish_tasks.items())[offset:offset+limit]
        ]
    }