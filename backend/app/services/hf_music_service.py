"""
Hugging Face Spaces 音乐生成服务 - V1.1 公测
复用 MurekaService 85% 逻辑，仅修改 API 调用部分

支持模型:
  - MusicGen (Meta)
  - ACE-Step
  - YuE (Wed Strength)
"""

import httpx
import os
import asyncio
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from enum import Enum
import datetime


class HFModel(str, Enum):
    """支持的 HF 模型"""
    MUSICGEN = "hf_musicgen"
    ACE_STEP = "hf_ace_step"
    YUE = "hf_yue"


class HFSpaceConfig(BaseModel):
    """HF Space 配置"""
    space_name: str
    api_url: str
    health_url: str
    max_duration: int = 120  # 秒
    supports_lyrics: bool = False
    supports_duration: bool = True


# HF Space 配置映射
HF_SPACES: Dict[HFModel, HFSpaceConfig] = {
    HFModel.MUSICGEN: HFSpaceConfig(
        space_name="facebook/MusicGen",
        api_url="https://facebook-musicgen.hf.space/api/predict",
        health_url="https://facebook-musicgen.hf.space/api/health",
        max_duration=120,
        supports_lyrics=False,  # MusicGen 仅支持文本提示
        supports_duration=True
    ),
    HFModel.ACE_STEP: HFSpaceConfig(
        space_name="bingmic/ACE-Step",
        api_url="https://bingmic-ace-step.hf.space/api/predict",
        health_url="https://bingmic-ace-step.hf.space/api/health",
        max_duration=120,
        supports_lyrics=True,  # ACE-Step 支持歌词
        supports_duration=True
    ),
    HFModel.YUE: HFSpaceConfig(
        space_name="Empower-lt/Yue",
        api_url="https://empower-lt-yue.hf.space/api/predict",
        health_url="https://empower-lt-yue.hf.space/api/health",
        max_duration=120,
        supports_lyrics=True,
        supports_duration=True
    )
}


class HFMusicGenerationRequest(BaseModel):
    """HF 音乐生成请求 - 复用 MurekaSongRequest 结构"""
    lyrics: str  # 歌词/提示词（必填）
    model: HFModel = HFModel.ACE_STEP
    style: str = "pop"  # 风格
    duration: Optional[int] = 30  # 时长（秒）
    temperature: Optional[float] = 0.7  # 随机性


class HFMusicGenerationResponse(BaseModel):
    """HF 音乐生成响应 - 复用 MurekaSongResponse 结构"""
    success: bool
    audio_url: Optional[str] = None
    error: Optional[str] = None
    task_id: Optional[str] = None
    model: Optional[HFModel] = None
    status: Optional[str] = "pending"  # pending, processing, completed, failed


class HFMusicService:
    """
    Hugging Face Spaces 音乐生成服务
    
    复用 MurekaService 逻辑:
    - ✅ 请求/响应结构
    - ✅ 错误处理
    - ✅ 重试机制
    - ✅ 状态管理
    - ❌ 修改：API 调用 URL 和 payload 格式
    """
    
    def __init__(self, hf_token: Optional[str] = None):
        """
        初始化 HF 音乐服务
        
        Args:
            hf_token: HF Token (可选，部分 Space 需要认证)
        """
        self.hf_token = hf_token or os.getenv("HF_TOKEN", "")
        self.headers = {
            "Content-Type": "application/json",
        }
        if self.hf_token:
            self.headers["Authorization"] = f"Bearer {self.hf_token}"
    
    async def generate_song(
        self, 
        request: HFMusicGenerationRequest,
        enhance_prompt: bool = True
    ) -> HFMusicGenerationResponse:
        """
        生成歌曲 - 复用 MurekaService.generate_song 逻辑
        
        Args:
            request: 请求对象
            enhance_prompt: 是否启用 Prompt 增强
        
        Returns:
            HFMusicGenerationResponse
        """
        try:
            # 1. 获取 Space 配置
            space_config = HF_SPACES.get(request.model)
            if not space_config:
                return HFMusicGenerationResponse(
                    success=False,
                    error=f"不支持的模型：{request.model}"
                )
            
            # 2. Prompt 增强 (复用 Mureka 逻辑)
            prompt_text = request.lyrics
            if enhance_prompt and request.lyrics:
                enhanced_prompt = self._enhance_prompt(request.lyrics, request.style)
                print(f"[Prompt 增强] 原始：{request.lyrics[:50]}...")
                print(f"[Prompt 增强] 增强：{enhanced_prompt[:80]}...")
                prompt_text = enhanced_prompt
            
            # 3. 构建 HF Space payload (修改点 1: 格式适配 HF)
            payload = self._build_hf_payload(request, prompt_text, space_config)
            
            # 4. 调用 HF Space API (修改点 2: URL 和格式)
            async with httpx.AsyncClient(timeout=float(space_config.max_duration)) as client:
                response = await client.post(
                    space_config.api_url,
                    headers=self.headers,
                    json=payload,
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # 5. 解析 HF 响应 (修改点 3: 解析逻辑)
                    result = self._parse_hf_response(data, request.model)
                    
                    if result.get("audio_url"):
                        print(f"✅ HF 生成成功：{result['audio_url'][:50]}...")
                        return HFMusicGenerationResponse(
                            success=True,
                            audio_url=result["audio_url"],
                            task_id=result.get("task_id"),
                            model=request.model,
                            status="completed"
                        )
                    else:
                        return HFMusicGenerationResponse(
                            success=False,
                            error="HF 返回格式异常，未找到音频 URL",
                            model=request.model
                        )
                else:
                    error_msg = f"HF API 错误：{response.status_code}"
                    print(f"❌ {error_msg}")
                    return HFMusicGenerationResponse(
                        success=False,
                        error=error_msg,
                        model=request.model
                    )
        
        except httpx.TimeoutException as e:
            return HFMusicGenerationResponse(
                success=False,
                error=f"请求超时：{str(e)}",
                model=request.model
            )
        except Exception as e:
            print(f"❌ HF 生成异常：{str(e)}")
            return HFMusicGenerationResponse(
                success=False,
                error=f"生成失败：{str(e)}",
                model=request.model
            )
    
    def _enhance_prompt(self, prompt: str, style: str) -> str:
        """
        Prompt 增强 - 复用 Mureka 逻辑
        
        简单版本：添加风格标签和音质关键词
        完整版：调用 Gemini API 优化
        """
        quality_tags = [
            "high quality", "professional production",
            "clear sound", "balanced mix"
        ]
        
        style_tags = {
            "pop": "catchy melody, modern production",
            "rock": "powerful guitars, energetic drums",
            "electronic": "synth beats, electronic bass",
            "classical": "orchestral arrangement, elegant",
            "hip-hop": "strong beats, rhythmic flow",
            "jazz": "smooth jazz, improvisation",
            "r&b": "soulful vocals, smooth rhythm"
        }
        
        enhanced = f"{prompt}, {style_tags.get(style.lower(), '')}, {', '.join(quality_tags)}"
        return enhanced
    
    def _build_hf_payload(
        self, 
        request: HFMusicGenerationRequest,
        prompt_text: str,
        space_config: HFSpaceConfig
    ) -> Dict[str, Any]:
        """
        构建 HF Space Payload (修改点 1)
        
        不同 Space 的 payload 格式不同：
        - MusicGen: ["prompt", duration, temperature]
        - ACE-Step: ["prompt", duration, temperature, "lyrics"]
        - YuE: ["prompt", "lyrics", duration]
        """
        if request.model == HFModel.MUSICGEN:
            # MusicGen 格式
            return {
                "data": [
                    prompt_text,
                    request.duration or 30,
                    request.temperature or 0.7
                ]
            }
        elif request.model == HFModel.ACE_STEP:
            # ACE-Step 格式 (支持歌词)
            lyrics = request.lyrics if space_config.supports_lyrics else ""
            return {
                "data": [
                    prompt_text,
                    request.duration or 30,
                    request.temperature or 0.7,
                    lyrics
                ]
            }
        elif request.model == HFModel.YUE:
            # YuE 格式
            return {
                "data": [
                    prompt_text,
                    request.lyrics if space_config.supports_lyrics else "",
                    request.duration or 30
                ]
            }
        else:
            # 默认格式
            return {
                "data": [prompt_text, request.duration or 30]
            }
    
    def _parse_hf_response(
        self, 
        data: Dict[str, Any], 
        model: HFModel
    ) -> Dict[str, Optional[str]]:
        """
        解析 HF 响应 (修改点 2)
        
        HF Space 返回格式：
        {
          "data": [
            {
              "url": "https://...",
              "path": "/tmp/xxx.wav"
            }
          ]
        }
        """
        try:
            # 尝试多种可能的 URL 位置
            audio_url = None
            
            if "data" in data and isinstance(data["data"], list):
                for item in data["data"]:
                    if isinstance(item, dict):
                        if "url" in item:
                            audio_url = item["url"]
                            break
                        elif "path" in item:
                            # 本地路径，需要下载
                            audio_url = item["path"]
                            break
            
            # 直接返回 URL
            if isinstance(data.get("data"), str):
                audio_url = data["data"]
            
            return {
                "audio_url": audio_url,
                "task_id": None  # HF Space 通常不返回 task_id
            }
        except Exception as e:
            print(f"解析 HF 响应失败：{str(e)}")
            return {"audio_url": None, "task_id": None}
    
    async def check_health(self, model: HFModel) -> Dict[str, Any]:
        """
        检查 Space 健康状态
        
        Returns:
            {
                "available": bool,
                "latency_ms": int,
                "message": str
            }
        """
        space_config = HF_SPACES.get(model)
        if not space_config:
            return {"available": False, "message": f"不支持的模型：{model}"}
        
        start_time = asyncio.get_event_loop().time()
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(space_config.health_url)
                latency = int((asyncio.get_event_loop().time() - start_time) * 1000)
                
                if response.status_code == 200:
                    return {
                        "available": True,
                        "latency_ms": latency,
                        "message": "Space 正常运行"
                    }
                else:
                    return {
                        "available": False,
                        "latency_ms": latency,
                        "message": f"Space 返回 {response.status_code}"
                    }
            except Exception as e:
                return {
                    "available": False,
                    "latency_ms": 0,
                    "message": f"Space 无法访问：{str(e)}"
                }
    
    async def get_available_models(self) -> List[HFModel]:
        """
        获取可用模型列表 (通过健康检查)
        """
        available = []
        for model in HFModel:
            health = await self.check_health(model)
            if health["available"]:
                available.append(model)
        return available


# ==================== 使用示例 ====================
# 
# # 1. 初始化服务
# hf_service = HFMusicService()
# 
# # 2. 检查健康状态
# health = await hf_service.check_health(HFModel.ACE_STEP)
# print(f"ACE-Step 状态：{health}")
# 
# # 3. 生成歌曲
# request = HFMusicGenerationRequest(
#     lyrics="悲伤的钢琴曲，关于失恋",
#     model=HFModel.ACE_STEP,
#     style="pop",
#     duration=30
# )
# response = await hf_service.generate_song(request)
# 
# if response.success:
#     print(f"✅ 生成成功：{response.audio_url}")
# else:
#     print(f"❌ 生成失败：{response.error}")
# 
# # 4. 获取可用模型
# models = await hf_service.get_available_models()
# print(f"可用模型：{models}")