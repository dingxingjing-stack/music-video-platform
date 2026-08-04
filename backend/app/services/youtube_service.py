"""
YouTube Data API v3 Service

功能:
- OAuth 2.0 授权
- 视频上传 (Title/Description/Tags/Privacy)
- 缩略图上传
- Token 自动刷新
- 多账号管理
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import os
import httpx
import asyncio


class YouTubePublishRequest(BaseModel):
    """YouTube 发布请求"""
    video_url: str = Field(..., description="视频文件 URL")
    title: str = Field(..., min_length=1, max_length=200, description="视频标题")
    description: str = Field("", max_length=10000, description="视频描述")
    tags: list[str] = Field(default_factory=list, description="标签")
    category_id: str = Field("10", description="分类 ID (10=Music)")
    privacy: str = Field("public", description="隐私：public/unlisted/private")
    made_for_kids: bool = Field(False, description="儿童内容")
    thumbnail_url: Optional[str] = Field(None, description="缩略图 URL")


class YouTubeService:
    """YouTube 服务"""
    
    def __init__(self):
        self.api_key = os.getenv("YOUTUBE_API_KEY")
        self.access_token = os.getenv("YOUTUBE_ACCESS_TOKEN")
        self.refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")
        
        self.base_url = "https://www.googleapis.com/upload/youtube/v3"
        self.auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
        self.token_url = "https://oauth2.googleapis.com/token"
    
    def is_authorized(self) -> bool:
        """检查是否已授权"""
        return bool(self.access_token) or bool(self.api_key)
    
    def get_auth_url(self, redirect_uri: str) -> str:
        """获取 OAuth 授权 URL"""
        params = {
            "client_id": os.getenv("YOUTUBE_CLIENT_ID"),
            "redirect_uri": redirect_uri,
            "scope": "https://www.googleapis.com/auth/youtube.upload",
            "response_type": "code",
            "access_type": "offline",
        }
        return self.auth_url + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    
    async def refresh_access_token(self) -> bool:
        """刷新 access token"""
        if not self.refresh_token:
            return False
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_url,
                    data={
                        "client_id": os.getenv("YOUTUBE_CLIENT_ID"),
                        "client_secret": os.getenv("YOUTUBE_CLIENT_SECRET"),
                        "refresh_token": self.refresh_token,
                        "grant_type": "refresh_token"
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    self.access_token = data["access_token"]
                    return True
        except Exception as e:
            print(f"Failed to refresh token: {e}")
            
        return False
    
    async def publish_video(self, request: YouTubePublishRequest) -> Dict[str, Any]:
        """
        上传视频到 YouTube
        
        Mock 模式：当无 API Key 时模拟成功
        """
        # Mock 模式
        if not self.api_key and not self.access_token:
            await asyncio.sleep(2)  # 模拟上传延迟
            
            return {
                "success": True,
                "mock": True,
                "video_id": f"mock_{asyncio.get_event_loop().time()}",
                "url": "https://www.youtube.com/watch?v=mock_video_id",
                "title": request.title,
                "message": "Mock 上传成功 (无 API Key)",
            }
        
        # 正式上传逻辑
        try:
            # 确保有有效的 token
            if not self.access_token:
                success = await self.refresh_access_token()
                if not success:
                    return {
                        "success": False,
                        "error": "需要授权，请先完成 OAuth 流程"
                    }
            
            # 准备视频元数据
            video_metadata = {
                "snippet": {
                    "title": request.title,
                    "description": request.description,
                    "tags": request.tags,
                    "categoryId": request.category_id,
                },
                "status": {
                    "privacyStatus": request.privacy,
                    "madeForKids": request.made_for_kids,
                    "selfDeclaredMadeForKids": request.made_for_kids,
                }
            }
            
            # 下载视频文件
            video_content = await self._download_video(request.video_url)
            
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }
            
            params = {
                "part": "snippet,status",
                "uploadType": "multipart",
            }
            
            async with httpx.AsyncClient(timeout=300.0) as client:
                # YouTube 使用 multipart 上传
                files = {
                    "file": ("video.mp4", video_content, "video/mp4"),
                }
                data = {
                    "data": (None, str(video_metadata), "application/json"),
                }
                
                response = await client.post(
                    self.base_url,
                    headers=headers,
                    params=params,
                    files={**files, **data}
                )
            
            if response.status_code != 200 and response.status_code != 201:
                error_msg = f"YouTube API error: {response.status_code}"
                try:
                    error_data = response.json()
                    if "error" in error_data and "message" in error_data["error"]:
                        error_msg = error_data["error"]["message"]
                except:
                    pass
                return {"success": False, "error": error_msg}
            
            result = response.json()
            
            # 如果提供了缩略图，上传它
            if request.thumbnail_url:
                await self._upload_thumbnail(result["id"]["video_id"], request.thumbnail_url)
            
            return {
                "success": True,
                "video_id": result["id"]["videoId"],
                "url": f"https://www.youtube.com/watch?v={result['id']['videoId']}",
                "title": result["snippet"]["title"],
                "message": "视频上传成功",
            }
            
        except httpx.TimeoutException:
            return {"success": False, "error": "上传超时，请检查网络连接"}
        except Exception as e:
            return {"success": False, "error": f"上传失败：{str(e)}"}
    
    async def _download_video(self, url: str) -> bytes:
        """下载视频文件"""
        # 如果是本地路径，直接读取
        if url.startswith("/results/") or url.startswith("/"):
            # 在 Windows 上可能需要处理路径
            if url.startswith("/results/"):
                from pathlib import Path
                current_dir = Path(__file__).parent.parent
                local_path = current_dir / url.lstrip("/")
                if local_path.exists():
                    return local_path.read_bytes()
        
        # 如果是 HTTP URL，下载
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
    
    async def _upload_thumbnail(self, video_id: str, thumbnail_url: str) -> Dict[str, Any]:
        """上传缩略图"""
        try:
            # 下载缩略图
            async with httpx.AsyncClient(timeout=60.0) as client:
                thumbnail_data = (await client.get(thumbnail_url)).content
            
            # 上传到 YouTube
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
                    headers=headers,
                    params={"videoId": video_id},
                    data=thumbnail_data
                )
                response.raise_for_status()
                return response.json()
                
        except Exception as e:
            print(f"Failed to upload thumbnail: {e}")
            return {"error": str(e)}
    
    def get_watcher_channels(self) -> Dict[str, Any]:
        """获取已授权的账号信息"""
        return {
            "accounts": [
                {
                    "channel_id": "mock_channel_1",
                    "channel_name": "Mock Channel 1",
                    "email": "user@example.com"
                }
            ] if not self.access_token else [
                {
                    "channel_id": "authenticated_channel",
                    "channel_name": "Authenticated",
                }
            ]
        }


# 全局服務实例
youtube_service = YouTubeService()