"""
音频上下文分析服务
提供 BPM、Key、Chord、Rhythm 等音乐特征提取
优先使用 CPU (librosa)，避免额外 GPU 开销
"""

import asyncio
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional

import librosa
import numpy as np
from scipy.ndimage import gaussian_filter1d

from app.services.beat_detector import beat_detector
from app.services.chord_track_service import chord_track_service

logger = logging.getLogger(__name__)


# Key 检测配置
KEY_PROFILES = {
    "major": [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88],
    "minor": [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17],
}

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


async def analyze_audio_context(
    audio_bytes: bytes,
    sample_rate: int = 44100,
) -> Dict[str, Any]:
    """
    综合音频分析：BPM、Key、Chord、Rhythm
    返回用于续写的音乐上下文
    """
    # 保存临时文件供 librosa 加载
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    
    try:
        # 并行执行各项分析
        bpm_task = asyncio.to_thread(_detect_bpm, tmp_path)
        key_task = asyncio.to_thread(_detect_key, tmp_path)
        chords_task = asyncio.to_thread(_detect_chords, tmp_path)
        rhythm_task = asyncio.to_thread(_analyze_rhythm, tmp_path)
        
        bpm, beats, beat_strength = await bpm_task
        key = await key_task
        chords = await chords_task
        rhythm_grid = await rhythm_task
        
        return {
            "bpm": bpm,
            "beats": beats,
            "beat_strength": beat_strength,
            "key": key,
            "chords": chords,
            "rhythm_grid": rhythm_grid,
            "tempo_stable": True,  # 可扩展：检测 tempo 变化
        }
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _detect_bpm(audio_path: str) -> tuple:
    """检测 BPM 和节拍位置"""
    try:
        # 使用 beat_detector 服务
        result = beat_detector.detect(audio_path)
        return result.tempo, result.beats, result.beat_strength
    except Exception as e:
        logger.warning(f"BPM 检测失败，使用默认值: {e}")
        return 120.0, np.array([]), np.array([])


def _detect_key(audio_path: str) -> str:
    """检测调性 - 基于 Krumhansl-Schmuckler 算法"""
    try:
        # 加载音频
        y, sr = librosa.load(audio_path, sr=22050, duration=30.0)
        
        # 计算 chromagram
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=512)
        
        # 计算每帧的平均 chroma
        chroma_mean = np.mean(chroma, axis=1)
        
        # 与大小调模板相关性匹配
        best_key = "C major"
        best_score = -1
        
        for root_idx in range(12):
            # 大调
            major_template = np.roll(KEY_PROFILES["major"], root_idx)
            major_score = np.corrcoef(chroma_mean, major_template)[0, 1]
            
            # 小调
            minor_template = np.roll(KEY_PROFILES["minor"], root_idx)
            minor_score = np.corrcoef(chroma_mean, minor_template)[0, 1]
            
            if major_score > best_score:
                best_score = major_score
                best_key = f"{NOTE_NAMES[root_idx]} major"
            if minor_score > best_score:
                best_score = minor_score
                best_key = f"{NOTE_NAMES[root_idx]} minor"
        
        return best_key
    except Exception as e:
        logger.warning(f"Key 检测失败，使用默认值: {e}")
        return "C major"


def _detect_chords(audio_path: str) -> List[Dict]:
    """检测和弦进行"""
    try:
        y, sr = librosa.load(audio_path, sr=22050, duration=30.0)
        
        # 使用 chord_track_service
        chords = chord_track_service.detect_chords_from_audio(y, sr)
        
        result = []
        for c in chords:
            result.append({
                "time": c.time,
                "chord": c.chord_name,
                "confidence": c.confidence,
                "duration": c.duration,
            })
        return result
    except Exception as e:
        logger.warning(f"Chord 检测失败: {e}")
        return []


def _analyze_rhythm(audio_path: str) -> Dict:
    """分析节奏网格和 groove"""
    try:
        y, sr = librosa.load(audio_path, sr=22050, duration=30.0)
        
        # 使用 beat_detector
        track = beat_detector.detect(y)
        
        # 生成节奏网格
        grid = beat_detector.generate_rhythm_grid(y, track.beats, subdivisions=4)
        
        return {
            "grid_times": grid.grid_times.tolist() if len(grid.grid_times) > 0 else [],
            "subdivisions": grid.subdivisions,
            "quantize_error": grid.quantize_error,
            "tempo_curve": track.tempo,  # 可扩展：返回 tempo_curve
        }
    except Exception as e:
        logger.warning(f"Rhythm 分析失败: {e}")
        return {}


async def extract_reference_features(
    audio_bytes: bytes,
    reference_seconds: int = 30,
) -> Dict[str, Any]:
    """
    从参考音频提取续写所需的特征
    用于 Audio2Audio 生成
    """
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    
    try:
        # 只分析最后 reference_seconds 秒
        total_duration = librosa.get_duration(path=tmp_path)
        offset = max(0, total_duration - reference_seconds)
        y, sr = librosa.load(tmp_path, sr=None, offset=offset)
        
        # BPM
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
        
        # Key
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=512)
        chroma_mean = np.mean(chroma, axis=1)
        
        best_key = "C major"
        best_score = -1
        for root_idx in range(12):
            major_template = np.roll(KEY_PROFILES["major"], root_idx)
            major_score = np.corrcoef(chroma_mean, major_template)[0, 1]
            minor_template = np.roll(KEY_PROFILES["minor"], root_idx)
            minor_score = np.corrcoef(chroma_mean, minor_template)[0, 1]
            
            if major_score > best_score:
                best_score = major_score
                best_key = f"{NOTE_NAMES[root_idx]} major"
            if minor_score > best_score:
                best_score = minor_score
                best_key = f"{NOTE_NAMES[root_idx]} minor"
        
        # Chords (简化版)
        chords = []
        
        return {
            "bpm": float(tempo),
            "key": best_key,
            "chords": [],
            "sample_rate": sr,
            "duration": len(y) / sr,
        }
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass