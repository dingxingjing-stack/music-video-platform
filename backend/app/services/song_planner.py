"""
AI 歌曲结构规划器
- 根据风格、歌词、BPM、情绪、目标时长自动规划完整歌曲结构
- 支持 AI 自动决定长度和风格
- 生成分段计划供 segment_planner 使用
"""

import os
import json
import logging
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Literal
from enum import Enum
import httpx

logger = logging.getLogger(__name__)

# ========== 配置 ==========
MAX_SONG_DURATION = int(os.getenv("MAX_SONG_DURATION", "330"))  # 5分30秒
MIN_SEGMENT_DURATION = int(os.getenv("MIN_SEGMENT_DURATION", "15"))  # 最短分段15秒
MAX_SEGMENT_DURATION = int(os.getenv("MAX_SEGMENT_DURATION", "60"))  # 最长分段60秒（单次ACE-Step生成上限）

# 预设时长选项（秒）
PRESET_DURATIONS = {
    "auto": None,           # AI 自动决定
    "2:00": 120,
    "2:30": 150,
    "3:00": 180,
    "3:30": 210,
    "4:00": 240,
    "4:30": 270,
    "5:00": 300,
    "5:30": 330,
}

# 默认歌曲结构模板
DEFAULT_STRUCTURES = {
    "pop": ["intro", "verse", "pre_chorus", "chorus", "verse", "pre_chorus", "chorus", "bridge", "chorus", "outro"],
    "rock": ["intro", "verse", "chorus", "verse", "chorus", "bridge", "guitar_solo", "chorus", "outro"],
    "electronic": ["intro", "build_up", "drop", "breakdown", "build_up", "drop", "outro"],
    "hip-hop": ["intro", "verse", "chorus", "verse", "chorus", "verse", "chorus", "outro"],
    "r&b": ["intro", "verse", "pre_chorus", "chorus", "verse", "pre_chorus", "chorus", "bridge", "chorus", "outro"],
    "jazz": ["intro", "head", "solo", "head", "outro"],
    "classical": ["exposition", "development", "recapitulation", "coda"],
    "ambient": ["intro", "layer_1", "layer_2", "layer_3", "climax", "fade_out"],
    "cinematic": ["intro", "theme_a", "theme_b", "development", "climax", "resolution", "outro"],
    "lo-fi": ["intro", "verse", "chorus", "verse", "chorus", "outro"],
    "country": ["intro", "verse", "chorus", "verse", "chorus", "bridge", "chorus", "outro"],
    "folk": ["intro", "verse", "chorus", "verse", "chorus", "bridge", "verse", "chorus", "outro"],
    "reggae": ["intro", "verse", "chorus", "verse", "chorus", "dub_section", "chorus", "outro"],
    "blues": ["intro", "verse", "verse", "verse", "solo", "verse", "outro"],
    "funk": ["intro", "verse", "chorus", "verse", "chorus", "breakdown", "chorus", "outro"],
    "disco": ["intro", "verse", "pre_chorus", "chorus", "verse", "pre_chorus", "chorus", "bridge", "chorus", "outro"],
    "house": ["intro", "build_up", "drop", "breakdown", "build_up", "drop", "outro"],
    "techno": ["intro", "main_loop", "variation", "main_loop", "breakdown", "main_loop", "outro"],
    "trance": ["intro", "build_up", "breakdown", "climax", "drop", "outro"],
    "dubstep": ["intro", "build_up", "drop", "breakdown", "build_up", "drop", "outro"],
    "drum-and-bass": ["intro", "main_section", "breakdown", "main_section", "outro"],
}


class SongSectionType(str, Enum):
    INTRO = "intro"
    VERSE = "verse"
    PRE_CHORUS = "pre_chorus"
    CHORUS = "chorus"
    BRIDGE = "bridge"
    OUTRO = "outro"
    BUILD_UP = "build_up"
    DROP = "drop"
    BREAKDOWN = "breakdown"
    SOLO = "solo"
    GUITAR_SOLO = "guitar_solo"
    DUB_SECTION = "dub_section"
    HEAD = "head"
    THEME_A = "theme_a"
    THEME_B = "theme_b"
    EXPOSITION = "exposition"
    DEVELOPMENT = "development"
    RECAPITULATION = "recapitulation"
    CODA = "coda"
    LAYER_1 = "layer_1"
    LAYER_2 = "layer_2"
    LAYER_3 = "layer_3"
    CLIMAX = "climax"
    FADE_OUT = "fade_out"
    RESOLUTION = "resolution"
    MAIN_LOOP = "main_loop"
    VARIATION = "variation"
    MAIN_SECTION = "main_section"


@dataclass
class SongSection:
    """歌曲片段"""
    name: str
    type: SongSectionType
    duration: int  # 秒
    lyrics: str = ""
    prompt_suffix: str = ""  # 给 ACE-Step 的额外提示词
    energy_level: float = 0.5  # 0-1 能量级别
    bpm: Optional[int] = None
    key: Optional[str] = None
    vocal_type: str = "auto"  # auto, male, female, instrumental
    is_repeat: bool = False  # 是否为重复段落（如第2段verse）


@dataclass
class SongPlan:
    """完整歌曲计划"""
    total_duration: int
    target_duration: int
    style: str
    bpm: int
    key: str
    time_signature: str = "4/4"
    sections: List[SongSection] = field(default_factory=list)
    lyrics: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_generation_segments(self) -> List[Dict[str, Any]]:
        """转换为分段生成参数列表"""
        segments = []
        current_time = 0.0
        for section in self.sections:
            segments.append({
                "name": section.name,
                "type": section.type.value,
                "prompt": self._build_segment_prompt(section),
                "lyrics": section.lyrics,
                "duration": section.duration,
                "style": self.style,
                "bpm": section.bpm or self.bpm,
                "key": section.key or self.key,
                "vocal_type": section.vocal_type,
                "start_time": current_time,
                "end_time": current_time + section.duration,
                "energy_level": section.energy_level,
            })
            current_time += section.duration
        return segments
    
    def _build_segment_prompt(self, section: SongSection) -> str:
        base = f"{self.style} music"
        type_descriptions = {
            SongSectionType.INTRO: "atmospheric introduction, setting the mood",
            SongSectionType.VERSE: "verse section, storytelling vocals, moderate energy",
            SongSectionType.PRE_CHORUS: "pre-chorus, building tension, rising energy",
            SongSectionType.CHORUS: "chorus, main hook, high energy, memorable melody",
            SongSectionType.BRIDGE: "bridge section, contrast, emotional peak",
            SongSectionType.OUTRO: "outro, fading out, resolving atmosphere",
            SongSectionType.BUILD_UP: "build up section, rising tension, increasing energy",
            SongSectionType.DROP: "drop, main climax, maximum energy, heavy beat",
            SongSectionType.BREAKDOWN: "breakdown, stripped back, minimal arrangement",
            SongSectionType.SOLO: "instrumental solo, virtuosic performance",
            SongSectionType.GUITAR_SOLO: "guitar solo, expressive lead guitar",
        }
        desc = type_descriptions.get(section.type, "")
        energy_desc = "high energy" if section.energy_level > 0.7 else "moderate energy" if section.energy_level > 0.4 else "low energy"
        vocal_desc = {
            "auto": "appropriate vocals",
            "male": "male vocals",
            "female": "female vocals",
            "instrumental": "instrumental, no vocals"
        }.get(section.vocal_type, "auto vocals")
        
        parts = [base, desc, energy_desc, vocal_desc]
        if section.prompt_suffix:
            parts.append(section.prompt_suffix)
        return ", ".join(filter(None, parts))


class SongPlanner:
    """歌曲结构规划器"""
    
    def __init__(self):
        self._agnes_service = None
    
    async def _get_agnes(self):
        if self._agnes_service is None:
            from app.services.agnes_music_service import agnes_service
            self._agnes_service = agnes_service
        return self._agnes_service
    
    def _estimate_auto_duration(self, style: str, lyrics: str, bpm: int, mood: str) -> int:
        """根据风格、歌词长度、BPM、情绪估算合理时长"""
        # 基础时长
        base_durations = {
            "pop": 180, "rock": 210, "electronic": 240, "hip-hop": 180,
            "r&b": 210, "jazz": 240, "classical": 300, "ambient": 300,
            "cinematic": 240, "lo-fi": 180, "country": 180, "folk": 210,
            "reggae": 210, "blues": 180, "funk": 180, "disco": 180,
            "house": 240, "techno": 300, "trance": 300, "dubstep": 180,
            "drum-and-bass": 180,
        }
        base = base_durations.get(style, 180)
        
        # 根据歌词长度调整
        if lyrics:
            word_count = len(lyrics.split())
            if word_count > 200:
                base += 60
            elif word_count > 100:
                base += 30
        
        # 根据 BPM 调整（快歌通常短一些）
        if bpm > 140:
            base -= 30
        elif bpm < 80:
            base += 30
        
        # 根据情绪调整
        mood_adjust = {
            "energetic": -30, "upbeat": -15, "chill": 30,
            "melancholic": 30, "epic": 60, "romantic": 15,
            "dark": 30, "happy": -15,
        }
        base += mood_adjust.get(mood, 0)
        
        # 限制在合理范围内
        return max(90, min(base, MAX_SONG_DURATION))
    
    def _get_structure_template(self, style: str) -> List[SongSectionType]:
        """获取风格对应的结构模板"""
        template = DEFAULT_STRUCTURES.get(style, DEFAULT_STRUCTURES["pop"])
        return [SongSectionType(s) for s in template]
    
    def _allocate_durations(self, structure: List[SongSectionType], total_duration: int) -> List[int]:
        """将总时长分配给各段落"""
        n = len(structure)
        if n == 0:
            return []
        
        # 基础权重
        weights = {
            SongSectionType.INTRO: 0.08,
            SongSectionType.VERSE: 0.15,
            SongSectionType.PRE_CHORUS: 0.08,
            SongSectionType.CHORUS: 0.18,
            SongSectionType.BRIDGE: 0.12,
            SongSectionType.OUTRO: 0.08,
            SongSectionType.BUILD_UP: 0.12,
            SongSectionType.DROP: 0.15,
            SongSectionType.BREAKDOWN: 0.10,
            SongSectionType.SOLO: 0.12,
            SongSectionType.GUITAR_SOLO: 0.12,
            SongSectionType.DUB_SECTION: 0.10,
            SongSectionType.HEAD: 0.20,
            SongSectionType.THEME_A: 0.15,
            SongSectionType.THEME_B: 0.15,
            SongSectionType.EXPOSITION: 0.20,
            SongSectionType.DEVELOPMENT: 0.25,
            SongSectionType.RECAPITULATION: 0.20,
            SongSectionType.CODA: 0.10,
            SongSectionType.LAYER_1: 0.15,
            SongSectionType.LAYER_2: 0.15,
            SongSectionType.LAYER_3: 0.15,
            SongSectionType.CLIMAX: 0.15,
            SongSectionType.FADE_OUT: 0.08,
            SongSectionType.RESOLUTION: 0.10,
            SongSectionType.MAIN_LOOP: 0.20,
            SongSectionType.VARIATION: 0.15,
            SongSectionType.MAIN_SECTION: 0.25,
        }
        
        # 计算总权重
        total_weight = sum(weights.get(s, 0.1) for s in structure)
        
        # 分配时长
        durations = []
        remaining = total_duration
        for i, section_type in enumerate(structure):
            weight = weights.get(section_type, 0.1)
            if i == n - 1:
                # 最后一个段落拿剩余时间
                duration = remaining
            else:
                duration = int(total_duration * weight / total_weight)
                # 限制在合理范围
                duration = max(MIN_SEGMENT_DURATION, min(duration, MAX_SEGMENT_DURATION))
            durations.append(duration)
            remaining -= duration
        
        # 如果最后一个段落太短，从前面借一点
        if durations and durations[-1] < MIN_SEGMENT_DURATION:
            deficit = MIN_SEGMENT_DURATION - durations[-1]
            for i in range(len(durations) - 1):
                if durations[i] > MIN_SEGMENT_DURATION + 5:
                    take = min(deficit, durations[i] - MIN_SEGMENT_DURATION - 5)
                    durations[i] -= take
                    durations[-1] += take
                    deficit -= take
                    if deficit <= 0:
                        break
        
        return durations
    
    def _parse_lyrics_to_sections(self, lyrics: str, structure: List[SongSectionType]) -> Dict[str, str]:
        """将歌词按结构分配到各段落"""
        section_lyrics = {}
        if not lyrics:
            return section_lyrics
        
        # 尝试解析标记
        import re
        markers = {
            "verse": r"\[verse\s*\d*\]",
            "pre_chorus": r"\[pre.?chorus\]",
            "chorus": r"\[chorus\]",
            "bridge": r"\[bridge\]",
            "intro": r"\[intro\]",
            "outro": r"\[outro\]",
        }
        
        found_sections = {}
        for sec_type, pattern in markers.items():
            matches = list(re.finditer(pattern, lyrics, re.IGNORECASE))
            if matches:
                found_sections[sec_type] = matches
        
        # 简单分配：按结构顺序分段
        lines = lyrics.split("\n")
        if len(lines) <= len(structure):
            # 每行一个段落
            for i, sec_type in enumerate(structure):
                if i < len(lines):
                    section_lyrics[sec_type.value] = lines[i]
        else:
            # 平均分配
            lines_per_section = len(lines) // len(structure)
            for i, sec_type in enumerate(structure):
                start = i * lines_per_section
                end = start + lines_per_section if i < len(structure) - 1 else len(lines)
                section_lyrics[sec_type.value] = "\n".join(lines[start:end])
        
        return section_lyrics
    
    async def plan_song(
        self,
        prompt: str,
        lyrics: str = "",
        style: str = "auto",
        duration: str = "auto",  # "auto" 或 "2:00" 等
        bpm: Optional[int] = None,
        key: Optional[str] = None,
        mood: str = "neutral",
        vocal_type: str = "auto",
        time_signature: str = "4/4",
        custom_structure: Optional[List[str]] = None,
    ) -> SongPlan:
        """
        规划完整歌曲结构
        
        Args:
            prompt: 音乐描述提示词
            lyrics: 歌词（可选）
            style: 音乐风格，"auto" 表示 AI 自动决定
            duration: 目标时长，"auto" 表示 AI 自动决定，或 "2:00", "3:00" 等
            bpm: BPM（可选）
            key: 调性（可选）
            mood: 情绪
            vocal_type: 人声类型
            time_signature: 拍号
            custom_structure: 自定义结构（可选）
        
        Returns:
            SongPlan: 完整歌曲计划
        """
        agnes = await self._get_agnes()
        
        # 1. 确定风格
        if style == "auto":
            style = await self._infer_style(prompt, lyrics, mood)
        
        # 2. 确定目标时长
        target_duration = PRESET_DURATIONS.get(duration)
        if target_duration is None:
            # AI 自动决定
            target_duration = self._estimate_auto_duration(style, lyrics, bpm or 120, mood)
        else:
            target_duration = min(target_duration, MAX_SONG_DURATION)
        
        # 3. 确定 BPM 和 Key
        if bpm is None:
            bpm = self._infer_bpm(style, mood)
        if key is None:
            key = self._infer_key(style, mood)
        
        # 4. 确定结构
        if custom_structure:
            structure = [SongSectionType(s) for s in custom_structure]
        else:
            structure = self._get_structure_template(style)
        
        # 5. 分配时长
        durations = self._allocate_durations(structure, target_duration)
        
        # 6. 分配歌词
        section_lyrics = self._parse_lyrics_to_sections(lyrics, structure)
        
        # 7. 构建段落
        sections = []
        current_time = 0.0
        verse_count = 0
        chorus_count = 0
        
        for i, (sec_type, dur) in enumerate(zip(structure, durations)):
            # 确定段落名称
            if sec_type == SongSectionType.VERSE:
                verse_count += 1
                name = f"verse_{verse_count}"
            elif sec_type == SongSectionType.CHORUS:
                chorus_count += 1
                name = f"chorus_{chorus_count}"
            else:
                name = sec_type.value
            
            # 能量级别
            energy_map = {
                SongSectionType.INTRO: 0.3,
                SongSectionType.VERSE: 0.4,
                SongSectionType.PRE_CHORUS: 0.6,
                SongSectionType.CHORUS: 0.9,
                SongSectionType.BRIDGE: 0.8,
                SongSectionType.OUTRO: 0.2,
                SongSectionType.BUILD_UP: 0.7,
                SongSectionType.DROP: 1.0,
                SongSectionType.BREAKDOWN: 0.3,
                SongSectionType.SOLO: 0.8,
                SongSectionType.GUITAR_SOLO: 0.85,
            }
            energy = energy_map.get(sec_type, 0.5)
            
            # 人声类型
            vocal_map = {
                SongSectionType.INTRO: "instrumental",
                SongSectionType.OUTRO: "instrumental",
                SongSectionType.BUILD_UP: "instrumental",
                SongSectionType.DROP: vocal_type,
                SongSectionType.BREAKDOWN: "instrumental",
                SongSectionType.SOLO: "instrumental",
                SongSectionType.GUITAR_SOLO: "instrumental",
            }
            sec_vocal = vocal_map.get(sec_type, vocal_type)
            
            section = SongSection(
                name=name,
                type=sec_type,
                duration=dur,
                lyrics=section_lyrics.get(sec_type.value, ""),
                energy_level=energy,
                bpm=bpm,
                key=key,
                vocal_type=sec_vocal,
                is_repeat=(verse_count > 1 or chorus_count > 1)
            )
            sections.append(section)
            current_time += dur
        
        actual_duration = sum(s.duration for s in sections)
        
        return SongPlan(
            total_duration=actual_duration,
            target_duration=target_duration,
            style=style,
            bpm=bpm,
            key=key,
            time_signature=time_signature,
            sections=sections,
            lyrics=lyrics,
            metadata={
                "prompt": prompt,
                "mood": mood,
                "vocal_type": vocal_type,
                "structure_template": [s.value for s in structure],
                "ai_generated": True,
            }
        )
    
    async def _infer_style(self, prompt: str, lyrics: str, mood: str) -> str:
        """使用 AI 推断风格"""
        try:
            agnes = await self._get_agnes()
            # 使用 Agnes 分析
            from app.services.agnes_music_service import AgnesSongRequest
            request = AgnesSongRequest(
                prompt=f"Analyze the music style for: {prompt}. Lyrics: {lyrics[:200]}. Mood: {mood}",
                style="pop",  # 临时值
                duration=30,
                type="analysis"
            )
            response = await agnes.generate_song(request)
            if response.success and response.style_suggestions:
                return response.style_suggestions[0].lower()
        except Exception as e:
            logger.warning(f"Style inference failed: {e}")
        
        # 启发式推断
        prompt_lower = (prompt + " " + lyrics).lower()
        if any(w in prompt_lower for w in ["rock", "guitar", "drum", "band", "metal"]):
            return "rock"
        elif any(w in prompt_lower for w in ["electronic", "edm", "synth", "dance", "club", "beat"]):
            return "electronic"
        elif any(w in prompt_lower for w in ["rap", "hip hop", "hip-hop", "flow", "bars"]):
            return "hip-hop"
        elif any(w in prompt_lower for w in ["r&b", "rnb", "soul", "smooth", "groove"]):
            return "r&b"
        elif any(w in prompt_lower for w in ["jazz", "swing", "improvis", "sax"]):
            return "jazz"
        elif any(w in prompt_lower for w in ["classical", "orchestra", "symphony", "piano", "violin"]):
            return "classical"
        elif any(w in prompt_lower for w in ["ambient", "atmosphere", "space", "drone", "texture"]):
            return "ambient"
        elif any(w in prompt_lower for w in ["cinematic", "film", "movie", "soundtrack", "epic"]):
            return "cinematic"
        elif any(w in prompt_lower for w in ["lo-fi", "lofi", "chill", "study", "relax"]):
            return "lo-fi"
        elif any(w in prompt_lower for w in ["country", "acoustic", "folk", "guitar", "story"]):
            return "country"
        return "pop"
    
    def _infer_bpm(self, style: str, mood: str) -> int:
        """推断 BPM"""
        bpm_ranges = {
            "pop": (100, 130), "rock": (110, 150), "electronic": (120, 140),
            "hip-hop": (80, 100), "r&b": (70, 95), "jazz": (80, 140),
            "classical": (60, 120), "ambient": (60, 90), "cinematic": (70, 110),
            "lo-fi": (70, 90), "country": (80, 110), "folk": (70, 100),
            "reggae": (70, 90), "blues": (70, 100), "funk": (90, 120),
            "disco": (110, 130), "house": (120, 130), "techno": (125, 140),
            "trance": (130, 145), "dubstep": (140, 150), "drum-and-bass": (160, 180),
        }
        base_min, base_max = bpm_ranges.get(style, (100, 130))
        mood_adjust = {
            "energetic": 15, "upbeat": 10, "chill": -15,
            "melancholic": -10, "epic": 0, "romantic": -5,
            "dark": -5, "happy": 10,
        }
        adjust = mood_adjust.get(mood, 0)
        bpm = (base_min + base_max) // 2 + adjust
        return max(60, min(bpm, 200))
    
    def _infer_key(self, style: str, mood: str) -> str:
        """推断调性"""
        # 简化：根据情绪选择大调/小调
        major_keys = ["C", "G", "D", "A", "E", "F", "Bb", "Eb"]
        minor_keys = ["Am", "Em", "Bm", "F#m", "C#m", "Dm", "Gm", "Cm"]
        
        if mood in ["melancholic", "dark", "epic"]:
            import random
            return random.choice(minor_keys)
        elif mood in ["happy", "upbeat", "energetic"]:
            import random
            return random.choice(major_keys)
        else:
            import random
            return random.choice(major_keys + minor_keys)


# 全局实例
_song_planner: Optional[SongPlanner] = None


def get_song_planner() -> SongPlanner:
    global _song_planner
    if _song_planner is None:
        _song_planner = SongPlanner()
    return _song_planner