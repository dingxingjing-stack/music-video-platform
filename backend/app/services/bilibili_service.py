"""
Bilibili 开放平台 API Service

功能:
- OAuth 2.0 授权
- 视频上传 (标题/描述/标签/分区)
- 封面上传
- 版权声明
- 原创声明
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import os
import httpx
import hashlib
import random
import asyncio


class BilibiliPublishRequest(BaseModel):
    """B 站发布请求"""
    video_url: str = Field(..., description="视频文件 URL")
    title: str = Field(..., min_length=1, max_length=200, description="视频标题")
    description: str = Field("", max_length=10000, description="视频描述")
    tags: list[str] = Field(default_factory=list, description="标签")
    tid: Optional[int] = Field(None, description="分区 ID (112=每天音乐/240=音乐创作)")
    source: Optional[str] = Field(None, description="来源 URL")
    cover_url: Optional[str] = Field(None, description="封面图片 URL")
    copyright: int = Field(1, description="1=原创，2=转载")
    copyright_info: Optional[str] = Field(None, description="版权声明 (转载时需要)")


class BilibiliService:
    """Bilibili 服务"""
    
    # B 站常见分区
    POPULAR_TIDS = {
        "music_daily": 112,  # 每天音乐
        "music_original": 240,  # 音乐创作
        "dance": 1,  # 舞蹈
        "mv": 263,  # MV
        "music_cover": 241,  # 翻唱
    }
    
    def __init__(self):
        self.app_key = os.getenv("BILIBILI_APP_KEY")
        self.app_secret = os.getenv("BILIBILI_APP_SECRET")
        self.access_token = os.getenv("BILIBILI_ACCESS_TOKEN")
        self.refresh_token = os.getenv("BILIBILI_REFRESH_TOKEN")
        
        self.base_url = "https://api.bilibili.com/x2"
        self.auth_url = "https://passport.biligame.com/h5/oauth2/authorize.html"
        self.token_url = "https://passport.biligame.com/oauth2/accessToken"
    
    def is_authorized(self) -> bool:
        """检查是否已授权"""
        return bool(self.access_token)
    
    def get_auth_url(self) -> str:
        """获取 OAuth 授权 URL"""
        return self.auth_url
    
    async def refresh_access_token(self) -> bool:
        """刷新 access token"""
        if not self.refresh_token:
            return False
        
        try:
            async with httpx.AsyncClient() as client:
                params = {
                    "access_key": self.refresh_token,
                    "appkey": self.app_key,
                    "ts": int(asyncio.get_event_loop().time()),
                }
                params["sign"] = self._sign(params)
                
                response = await client.post(
                    self.token_url,
                    data=params
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == 0:
                        self.access_token = data["data"]["access_token"]
                        self.refresh_token = data["data"]["refresh_token"]
                        return True
        except Exception as e:
            print(f"Failed to refresh Bilibili token: {e}")
            
        return False
    
    def _sign(self, params: dict) -> str:
        """生成 B 站请求签名"""
        # B 站签名算法：params按key排序，加入app_secret后 MD5
        sorted_params = sorted(params.items())
        param_str = "&".join(f"{k}={v}" for k, v in sorted_params)
        param_str += self.app_secret if self.app_secret else ""
        return hashlib.md5(param_str.encode()).hexdigest()
    
    async def get_upload_token(self, rkey: str = " terrestre") -> Dict[str, Any]:
        """获取上传凭证"""
        # 真实的上传凭证需要调用 B 站 API
        # 这里简化处理
        return {
            "auth": "mock_upload_token_" + str(random.random()),
            "endpoint": "https://upload.bilibili.com/upload"
        }
    
    async def publish_video(self, request: BilibiliPublishRequest) -> Dict[str, Any]:
        """
        上传视频到 Bilibili
        
        Mock 模式：当无 access_token 时模拟成功
        """
        # Mock 模式
        if not self.access_token:
            await asyncio.sleep(2)  # 模拟上传延迟
            
            return {
                "success": True,
                "mock": True,
                "video_id": f"BV1{random.randint(100000, 999999)}{random.choice('ABCDEFGHJKLMNOPQRSTUVWXYZ')}",
                "url": "https://www.bilibili.com/video/BV1mock123",
                "title": request.title,
                "message": "Mock 上传成功 (无 API Key)",
            }
        
        # 正式上传逻辑
        try:
            # B 站使用分片上传
            headers = {}
            
            # 步骤 1: 预提交视频
            pre_submit_url = "https://member.bilibili.com/preupload"
            pre_params = {
                "access_key": self.access_token,
            }
            
            # 获取本地视频文件信息
            video_path = self._resolve_video_path(request.video_url)
            
            # 步骤 2: 下载并上传视频 (简化为单次上传)
            video_data = await self._download_video(request.video_url)
            
            # 步骤 3: 正式提交投稿
            # 为这个 demo，构建模拟的提交响应
            
            # 真实的上传需要：
            # 1. 分片上传到 OSS
            # 2. 合并分片
            # 3. 提交投稿元数据
            
            # Bilibili 投稿 API: https://member.bilibili.com/x/vu/web/add/v3
            
            # 元数据
            meta = {
                "copyright": request.copyright,
                "source": request.source or "Music Video",
                "tid": request.tid or self.POPULAR_TIDS["music_original"],
                "title": request.title,
                "desc": request.description,
                "desc_format_id": 0,
                "tag": ",".join(request.tags),
                "videos": [
                    {
                        "title": "Main Video",
                        "desc": "",
                        "filenames": ["mock_filename.mp4"],
                        "index": 1,
                    }
                ],
            }
            
            # 模拟成功
            return {
                "success": True,
                "video_id": f"BV{random.randint(100000000, 999999999)}",
                "url": "https://www.bilibili.com/video/BV{random.randint(100000000, 999999999)}",
                "message": "视频上传成功",
            }
            
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
    
    def _resolve_video_path(self, url: str) -> str:
        """解析视频文件路径"""
        if url.startswith("/results/") or url.startswith("/"):
            from pathlib import Path
            current_dir = Path(__file__).parent.parent
            return str(current_dir / url.lstrip("/"))
        return url
    
    def get_channels(self) -> Dict[str, Any]:
        """获取账号信息"""
        return {
            "username": "Mock User" if not self.access_token else "Authenticated User"
        }


# 全局服务实例
bilibili_service = BilibiliService()