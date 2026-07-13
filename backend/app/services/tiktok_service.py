"""
TikTok Upload API Service

功能:
- OAuth 2.0 授权
- 视频上传 (标题/描述/标签/隐私)
- 背景音乐集成
- 直接上传/视频预上传
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import os
import httpx
import asyncio


class TikTokPublishRequest(BaseModel):
    """TikTok 发布请求"""
    video_url: str = Field(..., description="视频文件 URL")
    title: str = Field(..., min_length=1, max_length=200, description="视频标题")
    description: str = Field("", max_length=10000, description="视频描述")
    tags: list[str] = Field(default_factory=list, description="标签/话题")
    privacy: str = Field("PUBLIC_TO_EVERYONE", description="隐私：PUBLIC_TO_EVERYONE/MUTUAL_ONLY_FRIENDS/SELF_ONLY")
    music_info: Optional[Dict[str, Any]] = Field(None, description="背景音乐信息")


class TikTokService:
    """TikTok 服务"""
    
    def __init__(self):
        self.client_key = os.getenv("TIKTOK_CLIENT_KEY")
        self.client_secret = os.getenv("TIKTOK_CLIENT_SECRET")
        self.access_token = os.getenv("TIKTOK_ACCESS_TOKEN")
        self.refresh_token = os.getenv("TIKTOK_REFRESH_TOKEN")
        
        self.base_url = "https://open.tiktokapis.com/纵深/post/v1"
        self.auth_url = "https://www.tiktok.com/v2/auth/authorize/"
        self.token_url = "https://open.tiktokapis.com/纵深/oauth2/token/"
    
    def is_authorized(self) -> bool:
        """检查是否已授权"""
        return bool(self.access_token)
    
    def get_auth_url(self, redirect_uri: str) -> str:
        """获取 OAuth 授权 URL"""
        params = {
            "client_key": self.client_key,
            "redirect_uri": redirect_uri,
            "scope": "video.upload,user.info.basic",
            "response_type": "code",
            "state": str(asyncio.get_event_loop().time()),
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
                        "client_key": self.client_key,
                        "client_secret": self.client_secret,
                        "refresh_token": self.refresh_token,
                        "grant_type": "refresh_token"
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    self.access_token = data["access_token"]
                    return True
        except Exception as e:
            print(f"Failed to refresh TikTok token: {e}")
            
        return False
    
    async def publish_video(self, request: TikTokPublishRequest) -> Dict[str, Any]:
        """
        上传视频到 TikTok
        
        Mock 模式：当无 access_token 时模拟成功
        """
        # Mock 模式
        if not self.access_token:
            await asyncio.sleep(2)  # 模拟上传延迟
            
            return {
                "success": True,
                "mock": True,
                "video_id": f"tiktok_mock_{asyncio.get_event_loop().time()}",
                "url": "https://www.tiktok.com/@user/video/mock_video_id",
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
            
            # 步骤 1: 初始化视频上传
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json; charset=utf-8"
            }
            
            init_payload = {
                "post_info": {
                    "title": request.title,
                    "privacy_level": request.privacy,
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": 0,  # 稍后更新
                    "chunk_size": 10485760,  # 10MB chunks
                    "total_chunk_count": 1,  # 简化：单笔上传
                }
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                # 初始化上传
                init_response = await client.post(
                    "https://open.tiktokapis.com/纵深/post/v1/video/init/",
                    headers=headers,
                    json=init_payload
                )
                init_response.raise_for_status()
                init_data = init_response.json()
                
                if init_data.get("status_code") != 0:
                    return {
                        "success": False,
                        "error": f"TikTok init error: {init_data.get('data', {}).get('description', 'Unknown error')}"
                    }
                
                upload_url = init_data["data"]["upload_url"]
                video_id = init_data["data"]["id"][:8]
                
                # 步骤 2: 上传视频内容
                video_content = await self._download_video(request.video_url)
                
                upload_headers = headers.copy()
                upload_headers["Content-Type"] = "video/mp4"
                
                upload_response = await client.post(
                    upload_url,
                    headers=upload_headers,
                    content=video_content
                )
                upload_response.raise_for_status()
                
                # 步骤 3: 发布视频
                publish_payload = {
                    "publish_id": video_id,
                }
                
                publish_response = await client.post(
                    "https://open.tiktokapis.com/纵深/post/v1/video/publish/",
                    headers=headers,
                    json=publish_payload
                )
                publish_response.raise_for_status()
                publish_data = publish_response.json()
                
                if publish_data.get("status_code") != 0:
                    return {
                        "success": False,
                        "error": f"TikTok publish error: {publish_data.get('data', {}).get('description', 'Unknown error')}"
                    }
            
            return {
                "success": True,
                "video_id": video_id,
                "url": f"https://www.tiktok.com/@user/video/{video_id}",
                "message": "视频上传成功",
            }
            
        except httpx.TimeoutException:
            return {"success": False, "error": "上传超时，请检查网络连接"}
        except Exception as e:
            return {"success": False, "error": f"上传失败：{str(e)}"}
    
    async def _download_video(self, url: str) -> bytes:
        """下载视频文件"""
        if url.startswith("/results/") or url.startswith("/"):
            from pathlib import Path
            current_dir = Path(__file__).parent.parent
            local_path = current_dir / url.lstrip("/")
            if local_path.exists():
                return local_path.read_bytes()
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content


# 全局服务实例
tiktok_service = TikTokService()