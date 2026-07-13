"""
Comping 路由 (多次录制取最佳)

API 端点:
POST /api/v1/comping/session — 创建 Comping 会话
GET  /api/v1/comping/session/{id} — 获取会话信息
POST /api/v1/comping/segment — 添加片段
PUT  /api/v1/comping/select — 选择/取消选择片段
PUT  /api/v1/comping/rate — 为片段评分
POST /api/v1/comping/compile — 编译最佳片段
GET  /api/v1/comping/timeline/{id} — 获取时间线
POST /api/v1/comping/analyze — 分析录音质量
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional
import numpy as np

from app.services.comping_service import (
    comping_service,
    CompingSession,
    TakeSegment,
)


router = APIRouter(prefix="/api/v1/comping", tags=["Comping"])


@router.post("/session")
async def create_comping_session(
    track_name: str = Form(...),
    num_takes: int = Form(default=3, ge=1, le=20),
    duration: float = Form(default=60.0, gt=0),
    sample_rate: int = Form(default=44100),
):
    """
    创建 Comping 会话
    
    Args:
        track_name: 轨道名称
        num_takes: 录音次数 (1-20)
        duration: 时长 (秒)
        sample_rate: 采样率
    """
    try:
        session = comping_service.create_session(
            track_name=track_name,
            num_takes=num_takes,
            duration=duration,
            sample_rate=sample_rate,
        )
        
        return {
            "success": True,
            "session_id": session.session_id,
            "track_name": session.track_name,
            "takes_count": len(session.takes),
            "duration": session.total_duration,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建失败：{str(e)}")


@router.get("/session/{session_id}", response_model=CompingSession)
async def get_session(session_id: str):
    """获取 Comping 会话信息"""
    session = comping_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    return session


@router.post("/segment")
async def add_segment(
    session_id: str = Form(...),
    start_time: float = Form(..., ge=0),
    end_time: float = Form(..., gt=0),
    take_index: int = Form(..., ge=0),
):
    """
    添加片段到会话
    
    Args:
        session_id: 会话 ID
        start_time: 开始时间
        end_time: 结束时间
        take_index: 第几次录音
    """
    try:
        segment = comping_service.add_segment(
            session_id=session_id,
            start_time=start_time,
            end_time=end_time,
            take_index=take_index,
        )
        
        return {
            "success": True,
            "segment_id": segment.id,
            "start_time": segment.start_time,
            "end_time": segment.end_time,
            "take_index": segment.take_index,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加失败：{str(e)}")


@router.put("/select")
async def select_segment(
    session_id: str = Form(...),
    segment_id: str = Form(...),
    selected: bool = Form(default=True),
):
    """
    选择/取消选择片段
    
    Args:
        session_id: 会话 ID
        segment_id: 片段 ID
        selected: 是否选中
    """
    success = comping_service.select_segment(session_id, segment_id, selected)
    if not success:
        raise HTTPException(status_code=400, detail="选择失败")
    
    return {"success": True, "selected": selected}


@router.put("/rate")
async def rate_segment(
    session_id: str = Form(...),
    segment_id: str = Form(...),
    rating: float = Form(..., ge=0, le=5),
):
    """
    为片段评分
    
    Args:
        session_id: 会话 ID
        segment_id: 片段 ID
        rating: 评分 (0-5 星)
    """
    success = comping_service.rate_segment(session_id, segment_id, rating)
    if not success:
        raise HTTPException(status_code=400, detail="评分失败")
    
    return {"success": True, "rating": rating}


@router.post("/compile")
async def compile_comping(
    session_id: str = Form(...),
    crossfade_duration: float = Form(default=0.05, ge=0, le=1),
):
    """
    编译最佳片段为完整轨道
    
    Args:
        session_id: 会话 ID
        crossfade_duration: 交叉淡入淡出时长 (秒)
    """
    try:
        session = comping_service.compile_comping(
            session_id=session_id,
            crossfade_duration=crossfade_duration,
        )
        
        return {
            "success": True,
            "session_id": session.session_id,
            "is_compiled": session.is_compiled,
            "compiled_url": session.compiled_url,
            "selected_segments": sum(1 for seg in session.takes if seg.is_selected),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"编译失败：{str(e)}")


@router.get("/timeline/{session_id}")
async def get_timeline(session_id: str):
    """获取片段时间线 (用于前端可视化)"""
    timeline = comping_service.export_segments_timeline(session_id)
    
    return {
        "success": True,
        "session_id": session_id,
        "timeline": timeline,
        "total_segments": len(timeline),
    }


@router.post("/analyze")
async def analyze_take_quality(
    audio_file: UploadFile = File(...),
):
    """
    分析录音质量
    
    返回：
    - 整体评分
    - 音准稳定性
    - 节奏准确度
    - 动态范围
    - 信噪比
    """
    try:
        # 读取音频文件
        audio_bytes = await audio_file.read()
        
        # TODO: 使用 librosa 加载
        # audio_data, sample_rate = librosa.load(io.BytesIO(audio_bytes), sr=None)
        
        # Mock 数据
        audio_data = np.random.randn(44100 * 10) * 0.1  # 10 秒白噪声
        sample_rate = 44100
        
        # 分析质量
        analysis = comping_service.analyze_take_quality(audio_data, sample_rate)
        
        return {
            "success": True,
            "analysis": analysis,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败：{str(e)}")