"""
HeartCodec 音频编解码服务
基于 HeartCodec 神经音频编解码器
用于高质量音频压缩/解压，替代传统音频编解码器

Kaggle 适配：默认 HEARTCODEC_LOCAL_MODE=false（API 模式），不下载本地权重；
如需本地，路径统一到 /kaggle/working/cache/heartcodec（不与 ~/.cache 双份）。
"""

import os
import httpx
import tempfile
import base64
from typing import Optional, Dict, Any, Union
from pydantic import BaseModel
from enum import Enum
import base64


class HeartCodecFormat(str, Enum):
    """支持的音频格式"""
    WAV = "wav"
    MP3 = "mp3"
    FLAC = "flac"
    OPUS = "opus"
    AAC = "aac"


class HeartCodecQuality(str, Enum):
    """压缩质量预设"""
    LOW = "low"           # 16 kbps
    MEDIUM = "medium"     # 32 kbps
    HIGH = "high"         # 64 kbps
    VERY_HIGH = "very_high"  # 128 kbps
    LOSSLESS = "lossless"   # 无损


class HeartCodecTask(str, Enum):
    """任务类型"""
    ENCODE = "encode"       # 压缩
    DECODE = "decode"       # 解压
    TRANSCODE = "transcode"  # 转码


class HeartCodecRequest(BaseModel):
    """HeartCodec 请求"""
    audio_data: str  # base64 编码的音频数据，或音频 URL
    task: HeartCodecTask = HeartCodecTask.ENCODE
    input_format: HeartCodecFormat = HeartCodecFormat.WAV
    output_format: HeartCodecFormat = HeartCodecFormat.WAV
    quality: HeartCodecQuality = HeartCodecQuality.HIGH
    sample_rate: int = 44100
    channels: int = 2
    bitrate: Optional[int] = None  # 自定义比特率 (kbps)
    # 高级参数
    bandwidth: Optional[float] = None  # 带宽 (kHz)
    channels_out: Optional[int] = None  # 输出声道数


class HeartCodecResponse(BaseModel):
    """HeartCodec 响应"""
    success: bool
    audio_data: Optional[str] = None  # base64 编码的音频数据
    output_url: Optional[str] = None  # 如果启用，返回下载 URL
    duration: Optional[float] = None
    sample_rate: int = 44100
    channels: int = 2
    bitrate: Optional[int] = None
    original_size: Optional[int] = None
    compressed_size: Optional[int] = None
    compression_ratio: Optional[float] = None
    error: Optional[str] = None
    task_id: Optional[str] = None


class HeartCodecService:
    """HeartCodec 音频编解码服务"""
    
    def __init__(self):
        self.api_url = os.getenv("HEARTCODEC_API_URL", "https://api.heartcodec.ai/v1/process")
        self.api_key = os.getenv("HEARTCODEC_API_KEY", "")
        # Kaggle 约束：保持 API 模式，不在 Kaggle 下载本地权重
        self.local_mode = os.getenv("HEARTCODEC_LOCAL_MODE", "false").lower() == "true"

        if not self.api_key and not self.local_mode:
            raise ValueError("HEARTCODEC_API_KEY or HEARTCODEC_LOCAL_MODE=true required")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        } if self.api_key else {}

        # 本地模式：使用本地模型推理 — 路径统一到 Kaggle working 缓存，避免 ./models 双份
        # 默认仍为 API 模式，此路径仅在显式开启 local 时生效
        default_cache = "/kaggle/working/cache/heartcodec" if os.path.isdir("/kaggle/working") else "./models/heartcodec"
        self.local_model_path = os.getenv("HEARTCODEC_MODEL_PATH", default_cache)
        self.local_model = None
    
    async def process_audio(self, request: "HeartCodecRequest") -> dict:
        """
        处理音频
        
        Returns:
            dict with keys: success, audio_data (base64), output_url, error, task_id
        """
        if self.local_mode:
            return await self._process_local(request)
        else:
            return await self._process_remote(request)
    
    async def _process_remote(self, request: "HeartCodecRequest") -> dict:
        """远程 API 处理"""
        api_url = os.getenv("HEARTCODEC_API_URL", "https://api.heartcodec.ai/v1/process")
        api_key = os.getenv("HEARTCODEC_API_KEY", "")
        
        if not api_key:
            return {"success": False, "error": "HEARTCODEC_API_KEY not configured", "task_id": None}
        
        headers = {
            "Authorization": f"Bearer {os.getenv('HEARTCODEC_API_KEY')}",
            "Content-Type": "application/json",
        }
        
        payload = self._build_payload(request)
        
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    os.getenv("HEARTCODEC_API_URL", "https://api.heartcodec.ai/v1/process"),
                    headers=self.headers,
                    json=payload,
                    timeout=300.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return self._parse_response(data)
                elif response.status_code == 429:
                    return {"success": False, "error": "Rate limited", "task_id": None}
                else:
                    return {"success": False, "error": f"API error: {response.status_code}", "task_id": None}
                    
        except httpx.TimeoutException:
            return {"success": False, "error": "Request timeout", "task_id": None}
        except Exception as e:
            return {"success": False, "error": str(e), "task_id": None}
    
    async def _process_local(self, request: "HeartCodecRequest") -> dict:
        """本地模式处理（使用本地模型）"""
        # 这里需要加载本地 HeartCodec 模型
        # 如果没有本地模型，返回错误
        try:
            if not self.local_model:
                await self._load_local_model()
            
            # 读取输入音频
            audio_data = await self._load_audio_input(request.audio_data)
            
            # 执行编解码
            processed_audio = await self._run_local_inference(
                audio_data=request.audio_data,
                task=request.task,
                quality=request.quality,
                sample_rate=request.sample_rate,
                channels=request.channels
            )
            
            # 编码为 base64
            import base64
            audio_b64 = base64.b64encode(processed_audio).decode()
            
            return {
                "success": True,
                "audio_data": audio_b64,
                "task_id": f"heartcodec-local-{os.urandom(4).hex()}",
                "duration": None,
                "sample_rate": request.sample_rate,
                "channels": request.channels,
            }
            
        except Exception as e:
            return {"success": False, "error": f"Local processing failed: {str(e)}", "task_id": None}
    
    async def _load_local_model(self):
        """加载本地 HeartCodec 模型"""
        # 这里需要实际加载模型
        # 示例：使用 torch 加载模型
        try:
            import torch
            model_path = self.local_model_path
            # self.local_model = torch.load(model_path, map_location='cpu')
            # self.local_model.eval()
            # 这里只是示例，实际需要根据 HeartCodec 官方代码加载
            self.local_model = "loaded"  # 占位符
        except ImportError:
            raise RuntimeError("PyTorch not available for local HeartCodec inference")
        except Exception as e:
            raise RuntimeError(f"Failed to load HeartCodec model: {e}")
    
    async def _load_audio_input(self, audio_data: str) -> bytes:
        """加载音频输入（base64 或 URL）"""
        import base64
        
        if audio_data.startswith("http://") or audio_data.startswith("https://"):
            # 从 URL 下载
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await httpx.AsyncClient().get(request.audio_data)
                return response.content
        else:
            # 假设是 base64
            return base64.b64decode(request.audio_data)
    
    async def _run_local_inference(self, audio_data: bytes, task: str, quality: str, sample_rate: int, channels: int) -> bytes:
        """运行本地推理"""
        # 这里需要实际的 HeartCodec 推理逻辑
        # 示例：简单的格式转换
        # 实际需要调用 HeartCodec 模型进行编解码
        
        # 示例：简单的格式转换（实际需要 HeartCodec 模型）
        import soundfile as sf
        import io
        import numpy as np
        
        # 读取音频
        audio_buffer = io.BytesIO(audio_data)
        data, sr = sf.read(audio_buffer)
        
        # 重采样（如果需要）
        if data.ndim == 1:
            data = data.reshape(-1, 1)
        
        # 简单处理：这里只是示例，实际需要 HeartCodec 模型推理
        # 实际实现需要调用 HeartCodec 的 encode/decode 方法
        
        # 重新编码
        output_buffer = io.BytesIO()
        sf.write(io.BytesIO(), data, 44100, format='WAV')
        
        # 这里只是占位符，实际需要 HeartCodec 推理
        # 暂时返回原始数据
        output_buffer = io.BytesIO()
        sf.write(output_buffer, data, 44100, format='WAV')
        output_data = output_buffer.getvalue()
        
        return output_data
    
    def _build_payload(self, request: "HeartCodecRequest") -> dict:
        """构建请求载荷"""
        return {
            "audio_data": request.audio_data,
            "task": request.task.value,
            "input_format": request.input_format.value,
            "output_format": request.output_format.value,
            "quality": request.quality.value,
            "sample_rate": request.sample_rate,
            "channels": request.channels,
            "bitrate": request.bitrate,
        }
    
    def _parse_response(self, data: dict) -> dict:
        """解析响应"""
        audio_data = data.get("audio_data") or data.get("audio_data_base64")
        output_url = data.get("output_url") or data.get("url") or data.get("download_url")
        
        return {
            "success": True,
            "audio_data": data.get("audio_data"),
            "output_url": output_url,
            "task_id": data.get("task_id"),
            "duration": data.get("duration"),
            "sample_rate": data.get("sample_rate", 44100),
            "channels": data.get("channels", 2),
            "bitrate": data.get("bitrate"),
            "original_size": data.get("original_size"),
            "compressed_size": data.get("compressed_size"),
            "compression_ratio": data.get("compression_ratio"),
        }


# 全局实例
heartcodec_service = None

def get_heartcodec_service():
    global heartcodec_service
    if heartcodec_service is None:
        try:
            heartcodec_service = HeartCodecService()
        except ValueError:
            # API key not configured
            pass
    return heartcodec_service