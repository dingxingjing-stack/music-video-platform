"""
续写分析服务
- 分析现有歌曲结构、节拍、和弦、调性
- 确定续写位置、长度、风格策略
- 生成续写提示词和参数
"""

import os
import logging
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Literal, Tuple
from enum import Enum

logger = logging.getLogger(__name__)

# ========== 配置 ==========
MAX_SONG_DURATION = int(os.getenv("MAX_SONG_DURATION", "330"))  # 5:30
MAX_CONTINUATION_DURATION = int(os.getenv("MAX_CONTINUATION_DURATION", "120"))  # 单次续写最长 2 分钟
MIN_CONTINUATION_DURATION = int(os.getenv("MIN_CONTINUATION_DURATION", "10"))  # 最短 10 秒


class ContinuationMode(str, Enum):
    AUTO = "auto"                    # AI 自动继续
    KEEP_STYLE = "keep_style"        # 保持原风格继续
    NEW_STYLE = "new_style"          # 用户指定新风格
    VARIATION = "variation"          # 变奏（基于现有素材变化）
    BRIDGE = "bridge"                # 添加桥段
    OUTRO_EXTEND = "outro_extend"    # 延长结尾


@dataclass
class SongAnalysis:
    """歌曲分析结果"""
    duration: float
    bpm: float
    key: str
    time_signature: str
    structure: List[Dict[str, Any]]  # [{type, start, end, label}, ...]
    chords: List[Dict[str, Any]]     # [{time, chord, confidence}, ...]
    beats: List[float]
    downbeats: List[float]
    bars: List[Tuple[float, float]]
    energy_curve: List[Tuple[float, float]]  # [(time, energy), ...]
    last_section: Dict[str, Any]     # 最后一个段落信息
    ending_type: str                 # fade_out, cold_end, resolved, open
    vocal_presence: float            # 0-1 最后一段人声存在度
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContinuationPlan:
    """续写计划"""
    mode: ContinuationMode
    start_time: float                # 续写开始时间（通常 = 当前歌曲时长）
    duration: int                    # 续写时长（秒）
    target_total_duration: float     # 目标总时长
    style: str                       # 续写风格
    bpm: int
    key: str
    time_signature: str
    vocal_type: str
    prompt: str                      # 给 ACE-Step 的提示词
    lyrics: str                      # 续写歌词
    reference_audio_url: str         # 参考音频 URL
    reference_start_sec: float       # 参考音频开始位置
    reference_duration_sec: float    # 参考音频参考时长
    continuation_mode: str           # extend, vary, style_transfer
    structure_hint: List[str]        # 建议的结构 [bridge, chorus, outro] 等
    energy_target: float             # 目标能量级别
    metadata: Dict[str, Any] = field(default_factory=dict)


class ContinuationAnalyzer:
    """续写分析器"""
    
    def __init__(self):
        self._beat_detector = None
        self._agnes_service = None
    
    async def _get_beat_detector(self):
        if self._beat_detector is None:
            from app.services.beat_detector import get_beat_detector
            self._beat_detector = get_beat_detector()
        return self._beat_detector
    
    async def _get_agnes(self):
        if self._agnes_service is None:
            from app.services.agnes_music_service import agnes_service
            self._agnes_service = agnes_service
        return self._agnes_service
    
    async def analyze_song(self, audio_url: str, local_path: Optional[str] = None) -> SongAnalysis:
        """
        分析现有歌曲，为续写提供依据
        
        Args:
            audio_url: 音频公网 URL
            local_path: 本地文件路径（可选，优先使用）
        
        Returns:
            SongAnalysis
        """
        detector = await self._get_beat_detector()
        
        # 下载或使用本地文件
        if local_path and os.path.exists(local_path):
            analysis_path = local_path
        else:
            # 需要下载
            from app.services.ace_step_client import get_ace_step_client
            ace_client = get_ace_step_client()
            analysis_path = await ace_client.download_file(audio_url)
        
        # 节拍分析
        beat_info = await detector.analyze(analysis_path)
        
        # 提取结构信息
        structure = beat_info.get("segments", [])
        chords = beat_info.get("chords", [])
        beats = beat_info.get("beats", [])
        downbeats = beat_info.get("downbeats", [])
        bars = beat_info.get("bars", [])
        
        # 分析能量曲线
        energy_curve = self._compute_energy_curve(beat_info)
        
        # 确定最后一个段落
        last_section = structure[-1] if structure else {}
        
        # 分析结束类型
        ending_type = self._analyze_ending(beat_info, structure)
        
        # 分析人声存在度
        vocal_presence = self._analyze_vocal_presence(beat_info, structure)
        
        return SongAnalysis(
            duration=beat_info.get("duration", 0),
            bpm=beat_info.get("bpm", 120),
            key=beat_info.get("key", "C"),
            time_signature=beat_info.get("time_signature", "4/4"),
            structure=structure,
            chords=chords,
            beats=beats,
            downbeats=downbeats,
            bars=bars,
            energy_curve=energy_curve,
            last_section=last_section,
            ending_type=ending_type,
            vocal_presence=vocal_presence,
            metadata={
                "beat_confidence": beat_info.get("confidence", 0),
                "key_confidence": beat_info.get("key_confidence", 0),
            }
        )
    
    def _compute_energy_curve(self, beat_info: Dict[str, Any]) -> List[Tuple[float, float]]:
        """计算能量曲线"""
        rms = beat_info.get("rms_energy", [])
        if not rms:
            return []
        
        # 重采样到统一时间点
        duration = beat_info.get("duration", 1)
        n_points = min(100, len(rms))
        times = [i * duration / n_points for i in range(n_points)]
        
        # 简单插值
        import numpy as np
        rms_arr = np.array(rms)
        if len(rms_arr) > 1:
            orig_times = np.linspace(0, duration, len(rms_arr))
            interp = np.interp(times, orig_times, rms_arr)
            return list(zip(times, interp.tolist()))
        return [(t, float(rms[0])) for t in times]
    
    def _analyze_ending(self, beat_info: Dict[str, Any], structure: List[Dict]) -> str:
        """分析结束类型"""
        if not structure:
            return "unknown"
        
        last_seg = structure[-1]
        duration = beat_info.get("duration", 0)
        last_end = last_seg.get("end", duration)
        
        # 检查最后是否有淡出
        rms = beat_info.get("rms_energy", [])
        if len(rms) > 10:
            last_rms = rms[-10:]
            if all(last_rms[i] > last_rms[i+1] for i in range(len(last_rms)-1)):
                return "fade_out"
        
        # 检查和弦解决
        chords = beat_info.get("chords", [])
        if chords:
            last_chord = chords[-1].get("chord", "")
            key = beat_info.get("key", "C")
            if self._is_resolved_chord(last_chord, key):
                return "resolved"
        
        # 检查是否在小节边界结束
        downbeats = beat_info.get("downbeats", [])
        if downbeats and abs(last_end - downbeats[-1]) < 0.5:
            return "resolved"
        
        return "open"
    
    def _is_resolved_chord(self, chord: str, key: str) -> bool:
        """判断和弦是否为解决和弦"""
        # 简化：主三和弦视为解决
        tonic = key.replace("m", "").replace("#", "").replace("b", "")
        return chord.upper().startswith(tonic.upper()) and "m" not in chord.lower()
    
    def _analyze_vocal_presence(self, beat_info: Dict[str, Any], structure: List[Dict]) -> float:
        """分析最后一段人声存在度（基于频谱质心）"""
        spectral = beat_info.get("spectral_centroid", [])
        if not spectral:
            return 0.5
        
        # 人声通常在 200-4000Hz，频谱质心较高
        last_spectral = spectral[-min(50, len(spectral)):]
        avg_centroid = sum(last_spectral) / len(last_spectral)
        
        # 归一化
        return min(1.0, max(0.0, (avg_centroid - 500) / 3000))
    
    async def create_continuation_plan(
        self,
        analysis: SongAnalysis,
        mode: ContinuationMode = ContinuationMode.AUTO,
        user_duration: Optional[int] = None,  # 用户指定的续写时长
        user_style: Optional[str] = None,      # 用户指定的新风格
        user_prompt: str = "",                 # 用户额外提示词
        user_lyrics: str = "",                 # 用户提供的续写歌词
    ) -> ContinuationPlan:
        """
        创建续写计划
        
        Args:
            analysis: 歌曲分析结果
            mode: 续写模式
            user_duration: 用户指定续写时长（None 则 AI 自动决定）
            user_style: 用户指定新风格（仅在 mode=NEW_STYLE 时使用）
            user_prompt: 用户额外提示词
            user_lyrics: 用户提供的续写歌词
        
        Returns:
            ContinuationPlan
        """
        current_duration = analysis.duration
        remaining_time = MAX_SONG_DURATION - current_duration
        
        if remaining_time <= MIN_CONTINUATION_DURATION:
            raise ValueError(f"Song already at maximum duration ({current_duration:.0f}s), cannot continue")
        
        # 确定续写时长
        if user_duration is not None:
            duration = min(user_duration, remaining_time, MAX_CONTINUATION_DURATION)
        else:
            duration = self._auto_determine_duration(analysis, remaining_time)
        
        # 确定风格
        if mode == ContinuationMode.NEW_STYLE and user_style:
            style = user_style
        elif mode == ContinuationMode.KEEP_STYLE:
            style = analysis.metadata.get("original_style", "pop")
        else:
            style = self._infer_continuation_style(analysis, mode)
        
        # 确定人声类型
        vocal_type = "auto"
        if analysis.vocal_presence > 0.6:
            vocal_type = "auto"  # 保持人声
        elif analysis.vocal_presence < 0.3:
            vocal_type = "instrumental"
        
        # 生成提示词
        prompt = self._build_continuation_prompt(analysis, mode, style, user_prompt)
        
        # 生成歌词
        lyrics = self._generate_continuation_lyrics(analysis, mode, user_lyrics, duration)
        
        # 结构提示
        structure_hint = self._suggest_structure(analysis, mode, duration)
        
        # 能量目标
        energy_target = self._determine_energy_target(analysis, mode, structure_hint)
        
        # 参考音频设置
        reference_start = max(0, current_duration - 30)  # 参考最后 30 秒
        reference_duration = min(30, current_duration)
        
        return ContinuationPlan(
            mode=mode,
            start_time=current_duration,
            duration=duration,
            target_total_duration=current_duration + duration,
            style=style,
            bpm=int(analysis.bpm),
            key=analysis.key,
            time_signature=analysis.time_signature,
            vocal_type=vocal_type,
            prompt=prompt,
            lyrics=lyrics,
            reference_audio_url="",  # 由调用者填入
            reference_start_sec=reference_start,
            reference_duration_sec=reference_duration,
            continuation_mode=self._map_mode_to_ace(mode),
            structure_hint=structure_hint,
            energy_target=energy_target,
            metadata={
                "analysis_duration": analysis.duration,
                "analysis_bpm": analysis.bpm,
                "analysis_key": analysis.key,
                "ending_type": analysis.ending_type,
                "remaining_time": remaining_time,
            }
        )
    
    def _auto_determine_duration(self, analysis: SongAnalysis, remaining: int) -> int:
        """自动决定续写时长"""
        # 基于歌曲结构决定
        last_section = analysis.last_section
        last_type = last_section.get("label", "").lower()
        
        # 如果刚结束 chorus，适合加 bridge + chorus + outro
        if "chorus" in last_type:
            return min(90, remaining)
        # 如果是 verse，适合加 chorus
        elif "verse" in last_type:
            return min(60, remaining)
        # 如果是 bridge，适合加 final chorus + outro
        elif "bridge" in last_type:
            return min(70, remaining)
        # 如果是 outro，延长 outro
        elif "outro" in last_type or "fade" in last_type:
            return min(40, remaining)
        # 默认
        return min(60, remaining)
    
    def _infer_continuation_style(self, analysis: SongAnalysis, mode: ContinuationMode) -> str:
        """推断续写风格"""
        # 基于原风格和模式决定
        original_style = analysis.metadata.get("original_style", "pop")
        
        if mode == ContinuationMode.VARIATION:
            return original_style
        elif mode == ContinuationMode.BRIDGE:
            return original_style
        elif mode == ContinuationMode.OUTRO_EXTEND:
            return original_style
        else:  # AUTO
            # 根据能量曲线决定
            if analysis.energy_curve:
                last_energy = analysis.energy_curve[-1][1]
                if last_energy > 0.7:
                    return original_style  # 高能量保持
                elif last_energy < 0.3:
                    return "ambient"  # 低能量转氛围
        return original_style
    
    def _build_continuation_prompt(
        self, analysis: SongAnalysis, mode: ContinuationMode, style: str, user_prompt: str
    ) -> str:
        """构建续写提示词"""
        parts = [
            f"Continue the song seamlessly from {analysis.duration:.0f}s",
            f"Style: {style}",
            f"BPM: {int(analysis.bpm)}",
            f"Key: {analysis.key}",
            f"Time signature: {analysis.time_signature}",
        ]
        
        if mode == ContinuationMode.BRIDGE:
            parts.append("Add a contrasting bridge section with emotional peak")
        elif mode == ContinuationMode.OUTRO_EXTEND:
            parts.append("Extend the outro with gradual fade out, resolving atmosphere")
        elif mode == ContinuationMode.VARIATION:
            parts.append("Create a variation of the main theme, development section")
        
        if user_prompt:
            parts.append(f"User direction: {user_prompt}")
        
        # 添加和弦进行提示
        if analysis.chords:
            last_chords = [c["chord"] for c in analysis.chords[-4:]]
            parts.append(f"Continue chord progression from: {' -> '.join(last_chords)}")
        
        return ", ".join(parts)
    
    def _generate_continuation_lyrics(
        self, analysis: SongAnalysis, mode: ContinuationMode, user_lyrics: str, duration: int
    ) -> str:
        """生成续写歌词"""
        if user_lyrics:
            return user_lyrics
        
        # 如果有原歌词结构，尝试继续
        structure = analysis.structure
        if structure:
            last_label = structure[-1].get("label", "").lower()
            if "chorus" in last_label:
                return "[Bridge]\n[Chorus]\n[Outro]"
            elif "verse" in last_label:
                return "[Chorus]\n[Bridge]\n[Chorus]\n[Outro]"
            elif "bridge" in last_label:
                return "[Chorus]\n[Outro]"
        
        # 默认结构
        if duration > 90:
            return "[Bridge]\n[Chorus]\n[Outro]"
        elif duration > 45:
            return "[Chorus]\n[Outro]"
        else:
            return "[Outro]"
    
    def _suggest_structure(self, analysis: SongAnalysis, mode: ContinuationMode, duration: int) -> List[str]:
        """建议续写结构"""
        last_label = analysis.last_section.get("label", "").lower()
        
        # 短续写（<45s）只生成收尾段，避免多段时长不足
        if duration < 45:
            return ["outro"]
        
        if mode == ContinuationMode.BRIDGE:
            return ["bridge", "chorus", "outro"]
        elif mode == ContinuationMode.OUTRO_EXTEND:
            return ["outro"]
        elif "chorus" in last_label:
            return ["bridge", "chorus", "outro"]
        elif "verse" in last_label:
            return ["chorus", "bridge", "chorus", "outro"]
        elif "bridge" in last_label:
            return ["chorus", "outro"]
        else:
            if duration > 90:
                return ["bridge", "chorus", "outro"]
            elif duration > 45:
                return ["chorus", "outro"]
            else:
                return ["outro"]
    
    def _determine_energy_target(self, analysis: SongAnalysis, mode: ContinuationMode, structure: List[str]) -> float:
        """确定目标能量级别"""
        if mode == ContinuationMode.OUTRO_EXTEND:
            return 0.2
        elif mode == ContinuationMode.BRIDGE:
            return 0.8
        elif "bridge" in structure and "chorus" in structure:
            return 0.7  # bridge 高，chorus 高，outro 低
        elif "chorus" in structure:
            return 0.6
        else:
            return 0.3
    
    def _map_mode_to_ace(self, mode: ContinuationMode) -> str:
        """映射到 ACE-Step continuation_mode"""
        mapping = {
            ContinuationMode.AUTO: "extend",
            ContinuationMode.KEEP_STYLE: "extend",
            ContinuationMode.NEW_STYLE: "style_transfer",
            ContinuationMode.VARIATION: "vary",
            ContinuationMode.BRIDGE: "extend",
            ContinuationMode.OUTRO_EXTEND: "extend",
        }
        return mapping.get(mode, "extend")
    
    async def validate_continuation_request(
        self,
        current_duration: float,
        requested_duration: int,
    ) -> Tuple[bool, Optional[str], int]:
        """
        验证续写请求是否合法
        
        Returns:
            (is_valid, error_message, max_allowed_duration)
        """
        max_allowed = MAX_SONG_DURATION - current_duration
        
        if current_duration >= MAX_SONG_DURATION:
            return False, f"Song already at maximum duration ({MAX_SONG_DURATION}s)", 0
        
        if max_allowed < MIN_CONTINUATION_DURATION:
            return False, f"Only {max_allowed:.0f}s remaining, minimum {MIN_CONTINUATION_DURATION}s required", 0
        
        if requested_duration > max_allowed:
            return False, f"Requested {requested_duration}s exceeds remaining {max_allowed:.0f}s", max_allowed
        
        if requested_duration > MAX_CONTINUATION_DURATION:
            return False, f"Single continuation limited to {MAX_CONTINUATION_DURATION}s", MAX_CONTINUATION_DURATION
        
        return True, None, max_allowed


# 全局实例
_continuation_analyzer: Optional[ContinuationAnalyzer] = None


def get_continuation_analyzer() -> ContinuationAnalyzer:
    global _continuation_analyzer
    if _continuation_analyzer is None:
        _continuation_analyzer = ContinuationAnalyzer()
    return _continuation_analyzer