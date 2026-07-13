"""
节拍检测与节奏分析

基于 librosa 的专业节拍跟踪算法

功能:
1. BPM 检测 (每分钟节拍数)
2. 节拍位置检测 (强拍/弱拍)
3. 节奏网格生成 (量化对齐)
4. 速度曲线分析 (rubato/变速检测)
5. 节拍强度分析

目标：提供专业级节拍分析，支持节奏量化、速度对齐等功能
"""

import numpy as np
import librosa
import librosa.beat
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class BeatStrength(Enum):
    """节拍强度等级"""
    WEAK = 0.3      # 弱拍
    MEDIUM = 0.6    # 中强
    STRONG = 0.8    # 强拍
    ACCENT = 1.0    # 重音


@dataclass
class BeatTrack:
    """节拍轨迹"""
    beats: np.ndarray           # 节拍位置 (秒)
    tempo: float                # BPM
    beat_strength: np.ndarray   # 节拍强度 (0-1)
    downbeats: np.ndarray       # 强拍位置
    confidence: float           # 检测置信度


@dataclass
class RhythmGrid:
    """节奏网格"""
    grid_times: np.ndarray      # 网格时间点
    subdivisions: int           # 细分 (4=16 分音符，8=32 分音符)
    quantize_error: float       # 量化误差


class BeatDetector:
    """节拍检测器"""
    
    def __init__(self, sample_rate: int = 44100):
        self.sr = sample_rate
    
    def detect(self, audio: np.ndarray) -> BeatTrack:
        """
        检测节拍
        
        Args:
            audio: 音频信号
        
        Returns:
            BeatTrack 节拍轨迹
        """
        # 1. 节拍跟踪
        tempo, beats = librosa.beat.beat_track(
            y=audio,
            sr=self.sr,
            start_bpm=100,
            tight_bpm=True
        )
        
        # 2. 转换节拍为时间 (秒)
        beat_times = librosa.frames_to_time(beats, sr=self.sr)
        
        # 3. 检测强拍 (downbeats) - 简化版本
        # 实际应该使用谐波变化检测
        downbeat_mask = np.zeros(len(beat_times), dtype=bool)
        if len(beat_times) > 0:
            # 假设每 4 拍一个强拍 (4/4 拍)
            downbeat_mask[::4] = True
        downbeats = beat_times[downbeat_mask]
        
        # 4. 估计节拍强度 (基于 onset 强度)
        onset_env = librosa.onset.onset_strength(y=audio, sr=self.sr)
        onset_frames = np.arange(len(onset_env))
        onset_times = librosa.frames_to_time(onset_frames, sr=self.sr)
        
        # 为每个节拍分配强度
        beat_strength = np.zeros(len(beat_times))
        for i, beat_time in enumerate(beat_times):
            # 找到最近的 onset
            onset_idx = np.argmin(np.abs(onset_times - beat_time))
            beat_strength[i] = min(1.0, onset_env[onset_idx] / np.max(onset_env + 1e-10))
        
        # 5. 计算置信度
        confidence = self._estimate_confidence(beat_times, tempo)
        
        return BeatTrack(
            beats=beat_times,
            tempo=float(tempo),
            beat_strength=beat_strength,
            downbeats=downbeats,
            confidence=confidence
        )
    
    def detect_multi_resolution(self, audio: np.ndarray) -> List[BeatTrack]:
        """
        多分辨率节拍检测
        
        原理：在不同时间尺度上检测节拍，处理多层次节奏
        
        Returns:
            多个 BeatTrack (全速/半速倍速)
        """
        tracks = []
        
        # 1. 基础检测
        base_track = self.detect(audio)
        tracks.append(base_track)
        
        # 2. 半速检测 (更慢的节拍)
        # librosa 没有直接的半速检测，通过 TEMPO 推断
        half_tempo = base_track.tempo / 2
        half_track = BeatTrack(
            beats=base_track.beats[::2],  # 每隔一拍
            tempo=half_tempo,
            beat_strength=base_track.beat_strength[::2],
            downbeats=base_track.downbeats,
            confidence=base_track.confidence * 0.8
        )
        tracks.append(half_track)
        
        # 3. 倍速检测 (更快的细分)
        double_tempo = base_track.tempo * 2
        # 插值生成倍速节拍
        double_beats = self._interpolate_beats(base_track.beats)
        double_track = BeatTrack(
            beats=double_beats,
            tempo=double_tempo,
            beat_strength=np.interp(
                np.arange(len(double_beats)),
                np.linspace(0, len(base_track.beat_strength), len(base_track.beat_strength)),
                base_track.beat_strength
            ),
            downbeats=base_track.downbeats,
            confidence=base_track.confidence * 0.7
        )
        tracks.append(double_track)
        
        return tracks
    
    def generate_rhythm_grid(self, audio: np.ndarray, beats: np.ndarray, subdivisions: int = 4) -> RhythmGrid:
        """
        生成节奏网格
        
        Args:
            audio: 音频信号
            beats: 节拍位置 (秒)
            subdivisions: 细分 (4=16 分音符，8=32 分音符)
        
        Returns:
            RhythmGrid 节奏网格
        """
        if len(beats) < 2:
            return RhythmGrid(
                grid_times=np.array([]),
                subdivisions=subdivisions,
                quantize_error=0.0
            )
        
        # 1. 估计平均节拍间隔
        beat_intervals = np.diff(beats)
        avg_interval = np.mean(beat_intervals)
        
        # 2. 生成细分网格
        grid = []
        for i, beat in enumerate(beats[:-1]):
            interval = beat_intervals[i]
            for j in range(subdivisions):
                grid_time = beat + (interval / subdivisions) * j
                grid.append(grid_time)
        
        # 添加最后一个节拍后的细分
        last_beat = beats[-1]
        for j in range(subdivisions):
            grid_time = last_beat + (avg_interval / subdivisions) * j
            grid.append(grid_time)
        
        grid_times = np.array(grid)
        
        # 3. 计算量化误差
        # 找到 audio onset 与网格的偏差
        onset_env = librosa.onset.onset_strength(y=audio, sr=self.sr)
        onset_frames = np.arange(len(onset_env))
        onset_times = librosa.frames_to_time(onset_frames, sr=self.sr)
        
        # 找到显著 onset
        onset_peaks = self._find_onset_peaks(onset_env, threshold=0.5)
        onset_peak_times = onset_times[onset_peaks]
        
        # 计算 onset 与最近网格点的距离
        if len(onset_peak_times) > 0:
            errors = []
            for onset_time in onset_peak_times[:100]:  # 限制计算量
                dist = np.min(np.abs(grid_times - onset_time))
                errors.append(dist)
            quantize_error = np.mean(errors) if errors else 0.0
        else:
            quantize_error = 0.0
        
        return RhythmGrid(
            grid_times=grid_times,
            subdivisions=subdivisions,
            quantize_error=quantize_error
        )
    
    def analyze_tempo_curve(self, audio: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        分析速度曲线 (检测 rubato/变速)
        
        Returns:
            (时间轴，瞬时 BPM 曲线)
        """
        # 1. 检测节拍
        tempo, beats = librosa.beat.beat_track(y=audio, sr=self.sr)
        beat_times = librosa.frames_to_time(beats, sr=self.sr)
        
        if len(beat_times) < 2:
            return beat_times, np.full_like(beat_times, float(tempo))
        
        # 2. 计算瞬时 BPM (基于相邻节拍间隔)
        intervals = np.diff(beat_times)
        instantaneous_bpm = 60.0 / intervals
        
        # 3. 平滑 BPM 曲线 (避免抖动)
        from scipy.ndimage import gaussian_filter1d
        smoothed_bpm = gaussian_filter1d(instantaneous_bpm, sigma=1.0)
        
        # 对齐时间轴
        times = beat_times[1:]  # 去掉第一个点
        
        return times, smoothed_bpm
    
    def quantize_to_grid(self, notes: np.ndarray, grid: RhythmGrid, strength: float = 0.9) -> np.ndarray:
        """
        将音符量化到节奏网格
        
        Args:
            notes: 音符时间数组
            grid: 节奏网格
            strength: 量化强度 (0=不量化，1=完全量化)
        
        Returns:
            量化后的音符时间
        """
        quantized = np.copy(notes)
        
        for i, note_time in enumerate(notes):
            # 找到最近的网格点
            grid_idx = np.argmin(np.abs(grid.grid_times - note_time))
            grid_time = grid.grid_times[grid_idx]
            
            # 混合原时间和网格时间
            quantized[i] = note_time * (1 - strength) + grid_time * strength
        
        return quantized
    
    def _estimate_confidence(self, beats: np.ndarray, tempo: float) -> float:
        """
        估计节拍检测置信度
        
        基于:
        - 节拍间隔的一致性
        - BPM 是否在合理范围
        """
        if len(beats) < 2:
            return 0.0
        
        # 1. 检查间隔一致性
        intervals = np.diff(beats)
        mean_interval = np.mean(intervals)
        std_interval = np.std(intervals)
        cv = std_interval / mean_interval  # 变异系数
        
        # CV 越小越一致
        consistency_score = max(0, 1 - cv)
        
        # 2. BPM 合理性检查 (60-180 合理)
        if 60 <= tempo <= 180:
            tempo_score = 1.0
        elif tempo < 60:
            tempo_score = max(0, tempo / 60)
        else:
            tempo_score = max(0, 1 - (tempo - 180) / 60)
        
        # 3. 节拍数量 (越多越可靠)
        count_score = min(1.0, len(beats) / 100)
        
        # 加权平均
        confidence = 0.5 * consistency_score + 0.3 * tempo_score + 0.2 * count_score
        
        return confidence
    
    def _interpolate_beats(self, beats: np.ndarray) -> np.ndarray:
        """在现有节拍之间插入细分节拍"""
        if len(beats) < 2:
            return beats
        
        # 计算平均间隔
        intervals = np.diff(beats)
        avg_interval = np.mean(intervals)
        
        # 在每个节拍后插入细分
        interpolated = []
        for i, beat in enumerate(beats[:-1]):
            interpolated.append(beat)
            # 插入中间点
            mid = beat + intervals[i] / 2
            interpolated.append(mid)
        
        interpolated.append(beats[-1])
        
        return np.array(interpolated)
    
    def _find_onset_peaks(self, onset_env: np.ndarray, threshold: float = 0.3) -> np.ndarray:
        """检测 onset 峰值"""
        from scipy.signal import find_peaks
        
        # 归一化
        onset_env_norm = onset_env / (np.max(onset_env) + 1e-10)
        
        # 找峰值
        peaks, _ = find_peaks(onset_env_norm, height=threshold, distance=5)
        
        return peaks


# 全局实例
beat_detector = BeatDetector()


# 便捷函数
def detect_beats(audio_path: str) -> Dict:
    """
    从音频文件检测节拍
    
    Returns:
        字典包含：tempo, beats, downbeats, confidence
    """
    # 加载音频
    audio, sr = librosa.load(audio_path, sr=None)
    
    # 创建检测器
    detector = BeatDetector(sample_rate=sr)
    
    # 检测
    track = detector.detect(audio)
    
    return {
        'tempo': track.tempo,
        'beats': track.beats.tolist(),
        'downbeats': track.downbeats.tolist(),
        'beat_strength': track.beat_strength.tolist(),
        'confidence': track.confidence,
        'num_beats': len(track.beats),
    }