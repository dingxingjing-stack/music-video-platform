"""
Comping 服务 (多次录制取最佳片段)

功能:
- 管理多次录音片段 (Takes)
- 片段波形分析
- 最佳片段选择/标记
- 自动拼接合成
- 交叉淡入淡出
"""

from typing import List, Dict, Optional
from pydantic import BaseModel
import numpy as np


class TakeSegment(BaseModel):
    """录音片段"""
    id: str
    start_time: float  # 开始时间 (秒)
    end_time: float    # 结束时间
    take_index: int    # 第几次录音
    audio_url: Optional[str] = None  # 音频 URL (Mock 用)
    is_selected: bool = False  # 是否被选为最佳
    rating: float = 0.0  # 评分 (0-5)
    notes: Optional[str] = None  # 备注


class CompingSession(BaseModel):
    """Comping 会话"""
    session_id: str
    track_name: str
    takes: List[TakeSegment]
    total_duration: float
    sample_rate: int = 44100
    is_compiled: bool = False
    compiled_url: Optional[str] = None


class CompingService:
    """Comping 服务"""
    
    def __init__(self):
        self.sessions: Dict[str, CompingSession] = {}
    
    def create_session(
        self,
        track_name: str,
        num_takes: int,
        duration: float,
        sample_rate: int = 44100
    ) -> CompingSession:
        """
        创建 Comping 会话
        
        Args:
            track_name: 轨道名称
            num_takes: 录音次数
            duration: 总时长
            sample_rate: 采样率
        
        Returns:
            Comping 会话
        """
        session_id = f"comp_{track_name}_{len(self.sessions) + 1}"
        
        # 为每次录音创建片段列表
        takes = []
        for take_idx in range(num_takes):
            segment = TakeSegment(
                id=f"{session_id}_take{take_idx}",
                start_time=0.0,
                end_time=duration,
                take_index=take_idx,
                audio_url=f"mock://take_{take_idx}.wav",
                is_selected=False,
                rating=0.0,
            )
            takes.append(segment)
        
        session = CompingSession(
            session_id=session_id,
            track_name=track_name,
            takes=takes,
            total_duration=duration,
            sample_rate=sample_rate,
        )
        
        self.sessions[session_id] = session
        return session
    
    def add_segment(
        self,
        session_id: str,
        start_time: float,
        end_time: float,
        take_index: int
    ) -> TakeSegment:
        """
        添加片段到会话
        
        Args:
            session_id: 会话 ID
            start_time: 开始时间
            end_time: 结束时间
            take_index: 第几次录音
        
        Returns:
            创建的片段
        """
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        segment = TakeSegment(
            id=f"{session_id}_seg_{len(session.takes)}",
            start_time=start_time,
            end_time=end_time,
            take_index=take_index,
            is_selected=True,  # 新添加的片段默认选中
        )
        
        session.takes.append(segment)
        return segment
    
    def select_segment(
        self,
        session_id: str,
        segment_id: str,
        selected: bool = True
    ) -> bool:
        """
        选择/取消选择片段
        
        Args:
            session_id: 会话 ID
            segment_id: 片段 ID
            selected: 是否选中
        
        Returns:
            成功与否
        """
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        for segment in session.takes:
            if segment.id == segment_id:
                segment.is_selected = selected
                return True
        
        return False
    
    def rate_segment(
        self,
        session_id: str,
        segment_id: str,
        rating: float
    ) -> bool:
        """
        为片段评分
        
        Args:
            session_id: 会话 ID
            segment_id: 片段 ID
            rating: 评分 (0-5)
        
        Returns:
            成功与否
        """
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        for segment in session.takes:
            if segment.id == segment_id:
                segment.rating = min(max(rating, 0.0), 5.0)
                return True
        
        return False
    
    def analyze_take_quality(
        self,
        audio_data: np.ndarray,
        sample_rate: int
    ) -> Dict[str, float]:
        """
        分析录音质量 (简化版)
        
        实际实现会分析：
        - 音准稳定性
        - 节奏准确度
        - 动态范围
        - 信噪比
        
        简化版：返回 Mock 评分
        """
        # TODO: 实现真实质量分析
        # - 使用 librosa.feature.tempogram 分析节奏
        # - 使用 pyin 分析音准
        # - 计算 RMS 动态范围
        
        # Mock 分析
        rms = np.sqrt(np.mean(audio_data ** 2))
        zero_crossings = np.sum(np.diff(np.sign(audio_data)) != 0)
        
        return {
            "overall_score": 4.2,
            "pitch_stability": 4.0,
            "timing_accuracy": 4.5,
            "dynamic_range": 3.8,
            "signal_to_noise": 4.3,
            "rms_level": float(rms),
            "zero_crossing_rate": float(zero_crossings / len(audio_data)),
        }
    
    def compile_comping(
        self,
        session_id: str,
        crossfade_duration: float = 0.05
    ) -> CompingSession:
        """
        编译最佳片段为完整轨道
        
        Args:
            session_id: 会话 ID
            crossfade_duration: 交叉淡入淡出时长 (秒)
        
        Returns:
            更新后的会话 (包含编译结果)
        """
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        # 找出所有选中的片段
        selected_segments = [
            seg for seg in session.takes if seg.is_selected
        ]
        
        if not selected_segments:
            raise ValueError("No segments selected for comping")
        
        # 按时间排序
        selected_segments.sort(key=lambda x: x.start_time)
        
        # TODO: 实际音频拼接
        # - 加载每个选中的片段
        # - 应用交叉淡入淡出
        # - 拼接成完整音频
        # - 导出为 WAV/MP3
        
        # Mock: 创建编译后的 URL
        session.compiled_url = f"mock://compiled_{session_id}.wav"
        session.is_compiled = True
        
        return session
    
    def get_session(self, session_id: str) -> Optional[CompingSession]:
        """获取会话"""
        return self.sessions.get(session_id)
    
    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False
    
    def export_segments_timeline(self, session_id: str) -> List[Dict]:
        """
        导出片段时间线 (用于前端可视化)
        
        Returns:
            时间段列表，每个包含：
            - start, end: 时间范围
            - take_index: 第几次录音
            - is_selected: 是否选中
            - rating: 评分
        """
        session = self.sessions.get(session_id)
        if not session:
            return []
        
        timeline = []
        for segment in session.takes:
            timeline.append({
                "id": segment.id,
                "start": segment.start_time,
                "end": segment.end_time,
                "take_index": segment.take_index,
                "is_selected": segment.is_selected,
                "rating": segment.rating,
                "notes": segment.notes,
            })
        
        return timeline


# 全局服务实例
comping_service = CompingService()