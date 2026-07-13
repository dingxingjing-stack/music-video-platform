"""
时间伸缩服务 (Audio Warp / Time Stretch)

功能:
- 变速不变调 (Timestretch)
- 节拍检测 (BPM Detection)
- Warp Marker 管理
- 同步到目标 BPM
- 量化到网格

简化版：只实现基础变速功能
"""

from typing import List, Dict, Optional, Tuple
from pydantic import BaseModel
import numpy as np


class WarpMarker(BaseModel):
    """Warp 标记点"""
    id: str
    grid_time: float    # 网格时间 (拍数)
    audio_time: float   # 音频中的实际时间 (秒)
    bpm: float          # 局部 BPM
    is_locked: bool = False  # 是否锁定


class TimeStretchResult(BaseModel):
    """时间伸缩结果"""
    success: bool
    original_duration: float
    stretched_duration: float
    original_bpm: float
    target_bpm: float
    stretch_ratio: float
    warped_audio_url: Optional[str] = None
    markers: List[WarpMarker] = []
    error: Optional[str] = None


class TimeStretchService:
    """时间伸缩服务"""
    
    def __init__(self):
        pass
    
    def detect_bpm(
        self,
        audio_data: np.ndarray,
        sample_rate: int
    ) -> Tuple[float, List[float]]:
        """
        检测音频 BPM
        
        使用 librosa.beat.beat_track 进行真实检测
        如果 librosa 不可用则回退到 Mock
        
        Returns:
            (bpm, beat_times)
        """
        try:
            import librosa
            # 真实 BPM 检测
            tempo, beat_frames = librosa.beat.beat_track(y=audio_data, sr=sample_rate)
            beat_times = librosa.frames_to_time(beat_frames, sr=sample_rate).tolist()
            bpm = float(tempo)
            return bpm, beat_times
        except Exception:
            # 回退到 Mock
            bpm = 120.0
            duration = len(audio_data) / sample_rate
            beat_interval = 60.0 / bpm
            
            beat_times = []
            current_time = 0.0
            while current_time < duration:
                beat_times.append(current_time)
                current_time += beat_interval
            
            return bpm, beat_times
    
    def stretch_audio(
        self,
        audio_data: np.ndarray,
        sample_rate: int,
        target_bpm: float,
        original_bpm: Optional[float] = None
    ) -> TimeStretchResult:
        """
        时间伸缩 (变速不变调)
        
        Args:
            audio_data: 音频数据
            sample_rate: 采样率
            target_bpm: 目标 BPM
            original_bpm: 原始 BPM (自动检测如果未提供)
        
        Returns:
            伸缩结果
        """
        try:
            # 检测原始 BPM
            if original_bpm is None:
                original_bpm, _ = self.detect_bpm(audio_data, sample_rate)
            
            # 计算伸缩比例
            stretch_ratio = original_bpm / target_bpm
            
            # 原始时长
            original_duration = len(audio_data) / sample_rate
            stretched_duration = original_duration * stretch_ratio
            
            # 真实时间伸缩 (librosa)
            try:
                import librosa
                rate = 1.0 / stretch_ratio  # librosa rate = 原速/新速
                stretched = librosa.effects.time_stretch(audio_data, rate=rate)
                stretched_duration = len(stretched) / sample_rate
                warped_url = f"processed://warped_{original_bpm}to{target_bpm}.wav"
            except Exception:
                # 回退到 Mock
                stretched_duration = original_duration * stretch_ratio
                warped_url = f"mock://warped_{original_bpm}to{target_bpm}.wav"
            
            # 生成 Warp 标记
            duration = len(audio_data) / sample_rate
            beat_interval = 60.0 / original_bpm
            markers = []
            
            current_time = 0.0
            beat_num = 0
            while current_time < duration:
                marker = WarpMarker(
                    id=f"warp_{beat_num}",
                    grid_time=beat_num * 0.25,  # 每拍 4 个 16 分音符
                    audio_time=current_time,
                    bpm=original_bpm,
                    is_locked=(beat_num % 4 == 0),  # 每小节第一拍锁定
                )
                markers.append(marker)
                current_time += beat_interval
                beat_num += 1
            
            return TimeStretchResult(
                success=True,
                original_duration=original_duration,
                stretched_duration=stretched_duration,
                original_bpm=original_bpm,
                target_bpm=target_bpm,
                stretch_ratio=stretch_ratio,
                warped_audio_url=warped_url,
                markers=markers,
            )
            
        except Exception as e:
            return TimeStretchResult(
                success=False,
                original_duration=0,
                stretched_duration=0,
                original_bpm=0,
                target_bpm=target_bpm,
                stretch_ratio=1.0,
                error=str(e),
            )
    
    def add_warp_marker(
        self,
        markers: List[WarpMarker],
        grid_time: float,
        audio_time: float
    ) -> List[WarpMarker]:
        """添加 Warp 标记"""
        # 检查是否已存在
        for marker in markers:
            if abs(marker.grid_time - grid_time) < 0.01:
                # 更新现有标记
                marker.audio_time = audio_time
                return markers
        
        # 添加新标记
        new_marker = WarpMarker(
            id=f"warp_{len(markers)}",
            grid_time=grid_time,
            audio_time=audio_time,
            bpm=60.0 / (audio_time - markers[-1].audio_time) if markers else 120.0,
        )
        markers.append(new_marker)
        return markers
    
    def lock_marker(
        self,
        markers: List[WarpMarker],
        marker_id: str,
        locked: bool = True
    ) -> List[WarpMarker]:
        """锁定/解锁 Warp 标记"""
        for marker in markers:
            if marker.id == marker_id:
                marker.is_locked = locked
                break
        return markers
    
    def quantize_to_grid(
        self,
        markers: List[WarpMarker],
        grid_resolution: float = 0.25,  # 16 分音符
        strength: float = 1.0
    ) -> List[WarpMarker]:
        """
        量化到网格
        
        Args:
            markers: Warp 标记列表
            grid_resolution: 网格分辨率 (拍)
            strength: 量化强度 (0-1)
        """
        for marker in markers:
            if marker.is_locked:
                continue
            
            # 找到最近的网格点
            nearest_grid = round(marker.grid_time / grid_resolution) * grid_resolution
            offset = nearest_grid - marker.grid_time
            
            # 应用量化 (按强度)
            marker.grid_time += offset * strength
        
        return markers
    
    def calculate_stretch_between_markers(
        self,
        marker1: WarpMarker,
        marker2: WarpMarker
    ) -> float:
        """计算两个标记之间的伸缩比例"""
        time_diff = marker2.audio_time - marker1.audio_time
        if time_diff <= 0:
            return 1.0
        
        grid_diff = marker2.grid_time - marker1.grid_time
        if grid_diff <= 0:
            return 1.0
        
        # 计算局部 BPM
        local_bpm = 60.0 * grid_diff / time_diff
        return local_bpm / 120.0  # 相对于 120 BPM 的比例


# 全局服务实例
time_stretch_service = TimeStretchService()