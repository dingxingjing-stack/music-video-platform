"""
Mureka AI 音乐生成服务
"""

import httpx
from typing import Optional, Dict, Any
from pydantic import BaseModel

from app.core.secrets import get_secret


class QuotaExceededError(Exception):
    """API 配额耗尽异常"""
    pass


class MurekaSongRequest(BaseModel):
    """Mureka 歌曲生成请求"""
    lyrics: str  # 歌词/提示词（必填）
    style: str = "pop"  # 风格
    duration: Optional[int] = None  # 时长（秒）


class MurekaSongResponse(BaseModel):
    """Mureka 歌曲生成响应"""
    success: bool
    audio_url: Optional[str] = None
    error: Optional[str] = None
    task_id: Optional[str] = None


class MurekaService:
    """Mureka AI 音乐生成服务"""
    
    BASE_URL = "https://api.mureka.ai/v1"
    API_KEY = get_secret("MUREKA_API_KEY", required=True)
    
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {self.API_KEY}",
            "Content-Type": "application/json",
        }
    
    async def generate_song(self, request: MurekaSongRequest, enhance_prompt: bool = True) -> MurekaSongResponse:
        """
        生成歌曲
        
        根据 Mureka API 文档：
        - 只需 lyrics 和 style 字段
        - 不要传 model/prompt/num_songs（会 400 错误）
        
        Args:
            request: 请求对象
            enhance_prompt: 是否自动增强 Prompt (音质优化关键)
        """
        try:
            # 1. Prompt 增强 (新!)
            if enhance_prompt and request.lyrics:
                enhanced_lyrics = prompt_enhancer.enhance(
                    user_prompt=request.lyrics,
                    style=request.style,
                    production_quality=True,
                    template="professional"
                )
                print(f"[音质优化] 原始：{request.lyrics[:50]}...")
                print(f"[音质优化] 增强：{enhanced_lyrics[:80]}...")
            else:
                enhanced_lyrics = request.lyrics
            
            # 2. 构建请求体（只传必要字段）
            payload: Dict[str, Any] = {
                "lyrics": enhanced_lyrics,
                "style": request.style,
            }
            if request.duration:
                payload["duration"] = request.duration
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/song/generate",
                    headers=self.headers,
                    json=payload,
                )
                
                if response.status_code == 200:
                    data = response.json()
                    # 解析响应（音频 URL 可能在多个位置）
                    audio_url = (
                        data.get("data", {}).get("audio_url")
                        or data.get("data", {}).get("output_url")
                        or data.get("data", {}).get("url")
                        or data.get("data", {}).get("result", {}).get("audio_url")
                        or data.get("audio_url")
                    )
                    task_id = (
                        data.get("data", {}).get("task_id")
                        or data.get("task_id")
                        or data.get("id")
                    )
                    
                    # 3. 音频后处理 (新！)
                    if audio_url and enhance_prompt:  # 只在启用增强时进行后处理
                        print("[音质优化] 开始音频后处理...")
                        from app.services.audio_enhancement import process_generated_audio
                        enhanced_audio_path = await process_generated_audio(audio_url)
                        if enhanced_audio_path and enhanced_audio_path != audio_url:
                            print(f"[音质优化] ✅ 后处理完成：{enhanced_audio_path}")
                            # 注：这里返回本地路径，生产环境应上传到 CDN
                            # 临时方案：返回处理后的文件路径
                            audio_url = enhanced_audio_path
                    
                    return MurekaSongResponse(
                        success=True,
                        audio_url=audio_url,
                        task_id=task_id,
                    )
                elif response.status_code == 429:
                    # 配额限制 - 抛出异常让上层降级
                    raise QuotaExceededError("Mureka API 配额已用完，启用 Mock 降级")
                elif response.status_code == 400:
                    # 请求格式错误
                    error_data = response.json()
                    return MurekaSongResponse(
                        success=False,
                        error=f"请求格式错误：{error_data.get('detail', 'Unknown')}",
                    )
                else:
                    return MurekaSongResponse(
                        success=False,
                        error=f"API 错误：{response.status_code} - {response.text[:100]}",
                    )
                    
        except httpx.TimeoutException:
            return MurekaSongResponse(
                success=False,
                error="生成超时，请稍后重试",
            )
        except Exception as e:
            # Mureka 失败，尝试 NVAPI 备用引擎
            print(f"[多引擎] Mureka 失败：{str(e)[:100]}")
            print("[多引擎] 切换到 NVAPI 引擎...")
            
            from app.services.nv_music_service import nv_music_service
            from app.services.nv_music_service import NVAudioRequest
            
            # 用 NVAPI 重试
            nv_request = NVAudioRequest(
                prompt=request.lyrics,
                style=request.style,
                duration=request.duration or 60
            )
            nv_response = await nv_music_service.generate_music(nv_request)
            
            if nv_response.success and nv_response.audio_url:
                print("[多引擎] ✅ NVAPI 备用引擎成功")
                # NVAPI 成功后也进行后处理
                from app.services.audio_enhancement import process_generated_audio
                enhanced_path = await process_generated_audio(nv_response.audio_url)
                return MurekaSongResponse(
                    success=True,
                    audio_url=enhanced_path or nv_response.audio_url,
                    task_id=nv_response.task_id,
                )
            else:
                print(f"[多引擎] ❌ NVAPI 也失败：{nv_response.error}")
                return MurekaSongResponse(
                    success=False,
                    error=f"双引擎均失败 - Mureka: {str(e)[:50]}, NVAPI: {nv_response.error}",
                )
    
    async def generate_music(self, prompt: str, style: str = "instrumental") -> MurekaSongResponse:
        """生成纯音乐（无歌词）"""
        return await self.generate_song(MurekaSongRequest(
            lyrics=prompt,  # Mureka 用 lyrics 字段接收提示词
            style=style,
        ))
    
    async def generate_bgm(self, prompt: str, duration: int = 60) -> MurekaSongResponse:
        """生成背景音乐"""
        return await self.generate_song(MurekaSongRequest(
            lyrics=prompt,
            style="ambient",
            duration=duration,
        ))


# 全局实例
mureka_service = MurekaService()

# Prompt 增强器
from app.services.prompt_enhancer import prompt_enhancer

# 音频后处理器
from app.services.audio_post_processor import audio_processor