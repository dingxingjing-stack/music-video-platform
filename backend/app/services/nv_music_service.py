"""
NVIDIA NVAPI 音乐生成服务

功能:
- 调用 NVIDIA NVAPI 生成音乐
- 作为 Mureka 的备用引擎
- 支持多种音乐风格

API 文档：https://docs.api.nvidia.com
"""

import httpx
import os
from typing import Optional, Dict, Any
from pydantic import BaseModel


class NVAudioRequest(BaseModel):
    """NVAPI 音乐生成请求"""
    prompt: str  # 音乐描述
    style: str = "pop"  # 风格
    duration: int = 60  # 时长 (秒)


class NVAudioResponse(BaseModel):
    """NVAPI 音乐生成响应"""
    success: bool
    audio_url: Optional[str] = None
    error: Optional[str] = None
    task_id: Optional[str] = None


class NVMusicService:
    """NVIDIA NVAPI 音乐生成服务"""
    
    # NVAPI 端点 (示例，实际需根据 NVIDIA 文档调整)
    BASE_URL = "https://api.nvidia.com/v1/audio"
    API_KEY = os.getenv("NVIDIA_API_KEY", "")
    
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {self.API_KEY}",
            "Content-Type": "application/json",
        } if self.API_KEY else {}
    
    async def generate_music(self, request: NVAudioRequest) -> NVAudioResponse:
        """
        生成音乐
        
        Args:
            request: 请求对象
        
        Returns:
            响应对象
        """
        if not self.API_KEY:
            return NVAudioResponse(
                success=False,
                error="NVAPI_KEY 未配置，跳过 NVAPI 生成"
            )
        
        try:
            # 构建请求体
            payload: Dict[str, Any] = {
                "prompt": request.prompt,
                "style": request.style,
                "duration": request.duration,
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/generate",
                    headers=self.headers,
                    json=payload,
                )
                
                if response.status_code == 200:
                    data = response.json()
                    audio_url = data.get("audio_url") or data.get("output_url")
                    task_id = data.get("task_id") or data.get("id")
                    
                    return NVAudioResponse(
                        success=True,
                        audio_url=audio_url,
                        task_id=task_id,
                    )
                elif response.status_code == 429:
                    return NVAudioResponse(
                        success=False,
                        error="NVAPI 配额已用完"
                    )
                else:
                    return NVAudioResponse(
                        success=False,
                        error=f"NVAPI 错误：{response.status_code}"
                    )
        
        except httpx.TimeoutException:
            return NVAudioResponse(
                success=False,
                error="NVAPI 生成超时"
            )
        except Exception as e:
            return NVAudioResponse(
                success=False,
                error=f"NVAPI 异常：{str(e)[:100]}"
            )
    
    async def is_available(self) -> bool:
        """检查 NVAPI 是否可用"""
        return bool(self.API_KEY)


# 全局实例
nv_music_service = NVMusicService()