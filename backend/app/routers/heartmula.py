"""
HeartMuLa 本地推理路由 - Hugging Face Spaces / RunPod / Kaggle T4 部署专用
提供直接的本地 GPU 推理接口，不依赖外部 API

端点:
  POST /api/v1/heartmula/generate     生成音乐（本地 GPU 推理）
  GET  /api/v1/heartmula/health       健康检查（GPU/模型/显存状态）
  GET  /api/v1/heartmula/memory       显存使用统计
  GET  /api/v1/heartmula/info         模型信息

特点:
- 使用 HeartMuLaLocalService 直接推理
- lazy_load=True 适配 T4 16GB VRAM
- 无 Mock fallback - 任何错误直接返回 500/503
- 音频上传 R2 返回预签名 URL
"""

import os
import uuid
from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

from app.services.heartmula_service import get_heartmula_service, HeartMuLaRequest, HeartMuLaLocalError
from app.services.cdn_uploader import cdn_uploader

router = APIRouter(prefix="/api/v1/heartmula", tags=["heartmula"])

# 最大时长限制（4分钟，与 HeartMuLaGenPipeline 默认一致）
MAX_DURATION_SECONDS = 240


class GenerateRequest(BaseModel):
    """本地生成请求"""
    prompt: str = Field(..., min_length=5, description="音乐描述/标签，如: pop, chinese, female vocal, emotional")
    lyrics: Optional[str] = Field(None, description="歌词文本（可选）")
    duration: int = Field(180, ge=10, le=MAX_DURATION_SECONDS, description="时长（秒），默认 180s，最大 240s")
    topk: Optional[int] = Field(50, ge=1, le=100, description="Top-k 采样")
    temperature: Optional[float] = Field(1.0, ge=0.1, le=2.0, description="采样温度")
    cfg_scale: Optional[float] = Field(1.5, ge=1.0, le=5.0, description="CFG 引导强度")


class GenerateResponse(BaseModel):
    """生成响应"""
    success: bool
    audio_url: Optional[str] = None
    duration: Optional[float] = None
    sample_rate: int = 48000
    channels: int = 2
    format: str = "wav"
    error: Optional[str] = None
    task_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    """健康检查响应"""
    healthy: bool
    mode: str
    gpu_available: bool
    gpu_name: Optional[str] = None
    vram_total_gb: Optional[float] = None
    vram_allocated_gb: Optional[float] = None
    models_loaded: bool = False
    error: Optional[str] = None


@router.post("/generate", response_model=GenerateResponse)
async def generate_music(
    request: Request,
    req: GenerateRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """
    本地 GPU 生成音乐
    
    - 使用 HeartMuLa-oss-3B-happy-new-year + HeartCodec-oss-20260123
    - T4 16GB: lazy_load=True 自动管理显存
    - 生成音频上传 Cloudflare R2，返回预签名下载 URL
    - 无 Mock：GPU/模型/CUDA 任何问题直接返回 500/503
    """
    # 验证输入
    if not req.prompt or len(req.prompt.strip()) < 5:
        raise HTTPException(status_code=400, detail="提示词至少需要 5 个字符")
    
    # 获取服务（自动根据 HEARTMULA_LOCAL_ENABLED 选择模式）
    service = get_heartmula_service()
    if service is None:
        raise HTTPException(
            status_code=503,
            detail="HeartMuLa 服务不可用：HEARTMULA_LOCAL_ENABLED=false 且未配置 HEARTMULA_API_KEY"
        )
    
    if not service.local_mode:
        raise HTTPException(
            status_code=503,
            detail="当前为 API 模式，本地推理端点需要 HEARTMULA_LOCAL_ENABLED=true"
        )
    
    # 任务 ID
    task_id = f"heartmula-{uuid.uuid4().hex[:8]}"
    
    try:
        # 转换为内部请求格式
        internal_request = HeartMuLaRequest(
            prompt=req.prompt,
            lyrics=req.lyrics,
            duration=req.duration,
            top_k=req.topk,
            temperature=req.temperature,
        )
        
        # 生成音乐
        result = await service.generate_music(internal_request)
        
        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "生成失败")
            )
        
        return GenerateResponse(
            success=True,
            audio_url=result["audio_url"],
            duration=result.get("duration"),
            sample_rate=result.get("sample_rate", 48000),
            channels=result.get("channels", 2),
            format=result.get("format", "wav"),
            task_id=result.get("task_id", task_id),
            metadata=result.get("metadata"),
        )
        
    except HeartMuLaLocalError as e:
        raise HTTPException(status_code=500, detail=f"本地推理错误: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        # 捕获所有未预期异常，返回 500
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"生成异常: {type(e).__name__}: {str(e)}")


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    健康检查 - 验证 GPU、模型、显存状态
    
    用于：
    - HF Spaces 启动探针
    - 部署后验证
    - 监控告警
    """
    import torch
    
    service = get_heartmula_service()
    mode = service.get_mode() if service else "unknown"
    
    gpu_available = torch.cuda.is_available()
    gpu_name = None
    vram_total_gb = None
    vram_allocated_gb = None
    models_loaded = False
    error = None
    
    if gpu_available:
        try:
            gpu_name = torch.cuda.get_device_name(0)
            vram_total_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            vram_allocated_gb = torch.cuda.memory_allocated() / (1024**3)
        except Exception as e:
            error = f"GPU 信息获取失败: {e}"
    
    # 检查本地服务是否已加载模型
    if service and service.local_mode:
        try:
            # 触发懒加载检查
            if hasattr(service, '_local_service') and service._local_service is not None:
                models_loaded = service._local_service._models_loaded
        except Exception:
            models_loaded = False
    
    healthy = gpu_available and (not service or service.local_mode == False or models_loaded)
    
    return HealthResponse(
        healthy=healthy,
        mode=mode,
        gpu_available=gpu_available,
        gpu_name=gpu_name,
        vram_total_gb=round(vram_total_gb, 2) if vram_total_gb else None,
        vram_allocated_gb=round(vram_allocated_gb, 2) if vram_allocated_gb else None,
        models_loaded=models_loaded,
        error=error,
    )


@router.get("/memory")
async def memory_stats():
    """显存使用统计"""
    import torch
    
    if not torch.cuda.is_available():
        raise HTTPException(status_code=503, detail="GPU 不可用")
    
    service = get_heartmula_service()
    
    stats = {
        "gpu_name": torch.cuda.get_device_name(0),
        "vram_total_gb": round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 2),
        "vram_allocated_gb": round(torch.cuda.memory_allocated() / (1024**3), 2),
        "vram_reserved_gb": round(torch.cuda.memory_reserved() / (1024**3), 2),
        "vram_max_allocated_gb": round(torch.cuda.max_memory_allocated() / (1024**3), 2),
        "vram_max_reserved_gb": round(torch.cuda.max_memory_reserved() / (1024**3), 2),
    }
    
    if service and service.local_mode:
        try:
            local_stats = service.get_memory_stats()
            stats.update(local_stats)
        except Exception:
            pass
    
    return stats


@router.get("/info")
async def model_info():
    """模型信息"""
    service = get_heartmula_service()
    
    info = {
        "model": "HeartMuLa-oss-3B-happy-new-year",
        "codec": "HeartCodec-oss-20260123",
        "version": "3B",
        "mode": service.get_mode() if service else "unknown",
        "sample_rate": 48000,
        "max_duration_seconds": MAX_DURATION_SECONDS,
        "supports_lyrics": True,
        "supports_tags": True,
        "lazy_load": True,
        "device": "cuda",
        "mula_dtype": "bfloat16",
        "codec_dtype": "float32",
    }
    
    if service and service.local_mode:
        info.update({
            "model_repo": os.getenv("HEARTMULA_MODEL_REPO", "HeartMuLa/HeartMuLa-oss-3B-happy-new-year"),
            "codec_repo": os.getenv("HEARTCODEC_MODEL_REPO", "HeartMuLa/HeartCodec-oss-20260123"),
        })
    
    return info