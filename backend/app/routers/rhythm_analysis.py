"""
节拍检测与分析 API

端点:
- POST /beat/detect - 检测音频节拍
- GET /beat/info/{track_id} - 获取节拍信息
"""

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional
import os
import tempfile
import librosa

from app.services.beat_detector import BeatDetector, detect_beats

router = APIRouter(prefix="/api/v1/beat", tags=["节拍检测"])


class BeatDetectRequest(BaseModel):
    """节拍检测请求"""
    audio_url: Optional[str] = None  # 音频 URL
    audio_file: Optional[bytes] = None  # 音频文件 (二进制)


class BeatDetectResponse(BaseModel):
    """节拍检测响应"""
    success: bool
    tempo: float  # BPM
    beats: List[float]  # 节拍位置 (秒)
    downbeats: List[float]  # 强拍位置
    beat_strength: List[float]  # 节拍强度
    confidence: float  # 检测置信度
    num_beats: int  # 节拍数量
    duration: float  # 音频时长
    error: Optional[str] = None


class RhythmGridResponse(BaseModel):
    """节奏网格响应"""
    success: bool
    grid_times: List[float]  # 网格时间点
    subdivisions: int  # 细分
    quantize_error: float  # 量化误差
    error: Optional[str] = None


class TempoCurveResponse(BaseModel):
    """速度曲线响应"""
    success: bool
    times: List[float]  # 时间轴
    bpm_curve: List[float]  # 瞬时 BPM
    average_tempo: float  # 平均 BPM
    tempo_std: float  # BPM 标准差
    error: Optional[str] = None


@router.post("/detect", response_model=BeatDetectResponse)
async def detect_beat_endpoint(
    audio_url: Optional[str] = None,
    audio_file: Optional[UploadFile] = File(None)
):
    """
    检测音频节拍
    
    支持:
    - URL: 直接传入音频 URL
    - 上传文件：上传音频文件
    """
    try:
        # 1. 获取音频文件
        temp_path = None
        
        if audio_url:
            # 从 URL 下载
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(audio_url)
                if response.status_code != 200:
                    return BeatDetectResponse(
                        success=False,
                        tempo=0,
                        beats=[],
                        downbeats=[],
                        beat_strength=[],
                        confidence=0,
                        num_beats=0,
                        duration=0,
                        error=f"下载失败：HTTP {response.status_code}"
                    )
                
                # 写入临时文件
                temp_fd, temp_path = tempfile.mkstemp(suffix='.wav')
                os.close(temp_fd)
                with open(temp_path, 'wb') as f:
                    f.write(response.content)
        
        elif audio_file:
            # 上传文件
            temp_fd, temp_path = tempfile.mkstemp(suffix='.wav')
            os.close(temp_fd)
            content = await audio_file.read()
            with open(temp_path, 'wb') as f:
                f.write(content)
        
        else:
            return BeatDetectResponse(
                success=False,
                tempo=0,
                beats=[],
                downbeats=[],
                beat_strength=[],
                confidence=0,
                num_beats=0,
                duration=0,
                error="需要提供 audio_url 或 audio_file"
            )
        
        # 2. 检测节拍
        result = detect_beats(temp_path)
        
        # 3. 加载音频获取时长
        audio, sr = librosa.load(temp_path, sr=None, duration=30)  # 只加载 30s 用于估计
        result['duration'] = float(len(audio) / sr)
        
        # 4. 清理临时文件
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        
        # 5. 返回
        return BeatDetectResponse(
            success=True,
            tempo=result['tempo'],
            beats=result['beats'],
            downbeats=result['downbeats'],
            beat_strength=result['beat_strength'],
            confidence=result['confidence'],
            num_beats=result['num_beats'],
            duration=result['duration'],
            error=None
        )
    
    except Exception as e:
        return BeatDetectResponse(
            success=False,
            tempo=0,
            beats=[],
            downbeats=[],
            beat_strength=[],
            confidence=0,
            num_beats=0,
            duration=0,
            error=str(e)
        )


@router.post("/rhythm-grid", response_model=RhythmGridResponse)
async def generate_rhythm_grid(
    audio_url: str,
    subdivisions: int = 4  # 4=16 分音符，8=32 分音符
):
    """
    生成节奏网格
    
    用于音符量化、节奏对齐
    """
    try:
        # 1. 下载音频
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(audio_url)
            if response.status_code != 200:
                return RhythmGridResponse(
                    success=False,
                    grid_times=[],
                    subdivisions=subdivisions,
                    quantize_error=0,
                    error=f"下载失败：HTTP {response.status_code}"
                )
            
            temp_fd, temp_path = tempfile.mkstemp(suffix='.wav')
            os.close(temp_fd)
            with open(temp_path, 'wb') as f:
                f.write(response.content)
        
        # 2. 加载音频
        audio, sr = librosa.load(temp_path, sr=None)
        
        # 3. 创建检测器
        detector = BeatDetector(sample_rate=sr)
        
        # 4. 检测节拍
        beat_track = detector.detect(audio)
        
        # 5. 生成节奏网格
        grid = detector.generate_rhythm_grid(audio, beat_track.beats, subdivisions)
        
        # 6. 清理
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        
        return RhythmGridResponse(
            success=True,
            grid_times=grid.grid_times.tolist(),
            subdivisions=subdivisions,
            quantize_error=grid.quantize_error,
            error=None
        )
    
    except Exception as e:
        return RhythmGridResponse(
            success=False,
            grid_times=[],
            subdivisions=subdivisions,
            quantize_error=0,
            error=str(e)
        )


@router.post("/tempo-curve", response_model=TempoCurveResponse)
async def analyze_tempo_curve(audio_url: str):
    """
    分析速度曲线
    
    检测 rubato (自由速度)、accelerando (渐快)、ritardando (渐慢)
    """
    try:
        # 1. 下载音频
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(audio_url)
            if response.status_code != 200:
                return TempoCurveResponse(
                    success=False,
                    times=[],
                    bpm_curve=[],
                    average_tempo=0,
                    tempo_std=0,
                    error=f"下载失败：HTTP {response.status_code}"
                )
            
            temp_fd, temp_path = tempfile.mkstemp(suffix='.wav')
            os.close(temp_fd)
            with open(temp_path, 'wb') as f:
                f.write(response.content)
        
        # 2. 加载音频
        audio, sr = librosa.load(temp_path, sr=None)
        
        # 3. 创建检测器
        detector = BeatDetector(sample_rate=sr)
        
        # 4. 分析速度曲线
        times, bpm_curve = detector.analyze_tempo_curve(audio)
        
        # 5. 清理
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        
        # 6. 计算统计
        avg_tempo = float(np.mean(bpm_curve))
        tempo_std = float(np.std(bpm_curve))
        
        import numpy as np
        return TempoCurveResponse(
            success=True,
            times=times.tolist(),
            bpm_curve=bpm_curve.tolist(),
            average_tempo=avg_tempo,
            tempo_std=tempo_std,
            error=None
        )
    
    except Exception as e:
        return TempoCurveResponse(
            success=False,
            times=[],
            bpm_curve=[],
            average_tempo=0,
            tempo_std=0,
            error=str(e)
        )


@router.get("/info/{track_id}")
async def get_beat_info(track_id: str):
    """
    获取节拍信息 (从数据库)
    
    TODO: 连接数据库查询
    """
    # 临时实现：返回 mock 数据
    return {
        "success": True,
        "track_id": track_id,
        "tempo": 128.0,
        "beats": [0.5 * i for i in range(100)],
        "downbeats": [0.5 * i for i in range(0, 100, 4)],
        "confidence": 0.85,
    }