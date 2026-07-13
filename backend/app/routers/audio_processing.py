"""
音频处理 API 路由
- 音频分离 (Demucs)
- 母带处理
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import os
import tempfile
from pathlib import Path

from app.services.audio_separation_service import demucs_service
from app.services.mastering_service import mastering_service

router = APIRouter()


# ========== 请求模型 ==========

class SeparateRequest(BaseModel):
    """音频分离请求"""
    model: str = "htdemucs"  # 模型选择


class MasteringRequest(BaseModel):
    """母带处理请求"""
    target_loudness: float = -14.0  # LUFS
    stereo_width: float = 0.3  # 立体声增强


# ========== 响应模型 ==========

class SeparateResponse(BaseModel):
    success: bool
    stems: List[str]  # 分离后的文件路径
    duration: float
    message: str


class MasteringResponse(BaseModel):
    success: bool
    output_path: str
    loudness_before: float
    loudness_after: float
    peak_before: float
    peak_after: float
    message: str


# ========== API 端点 ==========

@router.get("/separate/models")
async def get_separation_models():
    """获取可用分离模型列表"""
    return {
        "models": demucs_service.get_available_models(),
        "model_descriptions": demucs_service.MODELS
    }


@router.post("/separate", response_model=SeparateResponse)
async def separate_audio(
    file: UploadFile = File(...),
    model: str = Form("htdemucs")
):
    """
    音频分离 (人声/鼓/贝斯/其他)
    
    上传音频文件，返回 4 轨分离后的文件路径
    """
    # 保存上传文件
    temp_dir = Path(tempfile.gettempdir()) / "audio_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    input_path = temp_dir / file.filename
    with open(input_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    # 执行分离
    result = demucs_service.separate(
        str(input_path),
        model=model,
        progress_callback=lambda p: print(f"分离进度：{p*100:.0f}%")
    )
    
    # 清理上传文件
    input_path.unlink(missing_ok=True)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    
    return SeparateResponse(**result)


@router.post("/master", response_model=MasteringResponse)
async def master_audio(
    file: UploadFile = File(...),
    target_loudness: float = Form(-14.0),
    stereo_width: float = Form(0.3)
):
    """
    自动母带处理
    
    上传音频文件，返回母带处理后的文件路径和分析数据
    """
    # 保存上传文件
    temp_dir = Path(tempfile.gettempdir()) / "audio_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    input_path = temp_dir / file.filename
    with open(input_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    # 执行母带处理
    result = mastering_service.master(
        str(input_path),
        target_loudness=target_loudness,
        stereo_width=stereo_width,
        progress_callback=lambda p: print(f"母带进度：{p*100:.0f}%")
    )
    
    # 清理上传文件
    input_path.unlink(missing_ok=True)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    
    return MasteringResponse(**result)


@router.get("/master/presets")
async def get_mastering_presets():
    """获取母带预设"""
    return {
        "presets": [
            {
                "name": "流媒体标准",
                "target_loudness": -14.0,
                "stereo_width": 0.3,
                "description": "Spotify/Apple Music 标准"
            },
            {
                "name": "YouTube",
                "target_loudness": -13.0,
                "stereo_width": 0.4,
                "description": "YouTube 优化"
            },
            {
                "name": "俱乐部/夜店",
                "target_loudness": -8.0,
                "stereo_width": 0.5,
                "description": "高响度，宽立体声"
            },
            {
                "name": "古典/爵士",
                "target_loudness": -16.0,
                "stereo_width": 0.6,
                "description": "保留动态范围"
            },
            {
                "name": "电子/舞曲",
                "target_loudness": -10.0,
                "stereo_width": 0.7,
                "description": "强劲低音，宽声场"
            }
        ]
    }