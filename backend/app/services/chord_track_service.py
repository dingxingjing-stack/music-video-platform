"""
和弦轨道服务 (Chord Track Service)

功能:
- 和弦定义库 (大三/小三/七和弦等)
- 音频和弦检测 (简化版：Mock)
- 和弦进行生成
- 自动和声编排
"""

from typing import List, Dict, Optional
from pydantic import BaseModel
import numpy as np


class ChordDefinition(BaseModel):
    """和弦定义"""
    name: str  # 和弦名称 (如 "C", "Dm", "G7")
    root: str  # 根音 (如 "C", "D#")
    quality: str  # 品质 (major, minor, 7th, dim, aug)
    intervals: List[int]  # 音程 (半音数)
    notes: List[str]  # 组成音


class DetectedChord(BaseModel):
    """检测到的和弦"""
    time: float  # 时间点 (秒)
    chord_name: str  # 和弦名称
    confidence: float  # 置信度 (0-1)
    duration: float  # 持续时间
    bass_note: Optional[str] = None  # 低音音符


class ChordProgression(BaseModel):
    """和弦进行"""
    chords: List[DetectedChord]
    key: str  # 调性 (如 "C major", "A minor")
    tempo: int  # BPM
    total_duration: float


class ChordTrackService:
    """和弦轨道服务"""
    
    # 和弦库
    CHORD_LIBRARY: Dict[str, ChordDefinition] = {
        # 大三和弦
        'C': ChordDefinition(name='C', root='C', quality='major', intervals=[0, 4, 7], notes=['C', 'E', 'G']),
        'D': ChordDefinition(name='D', root='D', quality='major', intervals=[0, 4, 7], notes=['D', 'F#', 'A']),
        'E': ChordDefinition(name='E', root='E', quality='major', intervals=[0, 4, 7], notes=['E', 'G#', 'B']),
        'F': ChordDefinition(name='F', root='F', quality='major', intervals=[0, 4, 7], notes=['F', 'A', 'C']),
        'G': ChordDefinition(name='G', root='G', quality='major', intervals=[0, 4, 7], notes=['G', 'B', 'D']),
        'A': ChordDefinition(name='A', root='A', quality='major', intervals=[0, 4, 7], notes=['A', 'C#', 'E']),
        'B': ChordDefinition(name='B', root='B', quality='major', intervals=[0, 4, 7], notes=['B', 'D#', 'F#']),
        
        # 小三和弦
        'Cm': ChordDefinition(name='Cm', root='C', quality='minor', intervals=[0, 3, 7], notes=['C', 'D#', 'G']),
        'Dm': ChordDefinition(name='Dm', root='D', quality='minor', intervals=[0, 3, 7], notes=['D', 'F', 'A']),
        'Em': ChordDefinition(name='Em', root='E', quality='minor', intervals=[0, 3, 7], notes=['E', 'G', 'B']),
        'Fm': ChordDefinition(name='Fm', root='F', quality='minor', intervals=[0, 3, 7], notes=['F', 'G#', 'C']),
        'Gm': ChordDefinition(name='Gm', root='G', quality='minor', intervals=[0, 3, 7], notes=['G', 'A#', 'D']),
        'Am': ChordDefinition(name='Am', root='A', quality='minor', intervals=[0, 3, 7], notes=['A', 'C', 'E']),
        'Bm': ChordDefinition(name='Bm', root='B', quality='minor', intervals=[0, 3, 7], notes=['B', 'D', 'F#']),
        
        # 七和弦
        'C7': ChordDefinition(name='C7', root='C', quality='7th', intervals=[0, 4, 7, 10], notes=['C', 'E', 'G', 'A#']),
        'D7': ChordDefinition(name='D7', root='D', quality='7th', intervals=[0, 4, 7, 10], notes=['D', 'F#', 'A', 'C']),
        'E7': ChordDefinition(name='E7', root='E', quality='7th', intervals=[0, 4, 7, 10], notes=['E', 'G#', 'B', 'D']),
        'F7': ChordDefinition(name='F7', root='F', quality='7th', intervals=[0, 4, 7, 10], notes=['F', 'A', 'C', 'D#']),
        'G7': ChordDefinition(name='G7', root='G', quality='7th', intervals=[0, 4, 7, 10], notes=['G', 'B', 'D', 'F']),
        'A7': ChordDefinition(name='A7', root='A', quality='7th', intervals=[0, 4, 7, 10], notes=['A', 'C#', 'E', 'G']),
        'B7': ChordDefinition(name='B7', root='B', quality='7th', intervals=[0, 4, 7, 10], notes=['B', 'D#', 'F#', 'A']),
        
        # 减和弦
        'Cdim': ChordDefinition(name='Cdim', root='C', quality='dim', intervals=[0, 3, 6], notes=['C', 'D#', 'F#']),
        'Ddim': ChordDefinition(name='Ddim', root='D', quality='dim', intervals=[0, 3, 6], notes=['D', 'F', 'G#']),
        
        # 增和弦
        'Caug': ChordDefinition(name='Caug', root='C', quality='aug', intervals=[0, 4, 8], notes=['C', 'E', 'G#']),
    }
    
    # 常用和弦进行 (级数表示)
    COMMON_PROGRESSIONS = {
        'pop_basic': ['I', 'V', 'vi', 'IV'],  # C - G - Am - F
        'pop_variant': ['I', 'vi', 'IV', 'V'],  # C - Am - F - G
        'jazz_ii_v_i': ['ii', 'V', 'I'],  # Dm - G7 - C
        'blues_12': ['I', 'I', 'I', 'I', 'IV', 'IV', 'I', 'I', 'V', 'IV', 'I', 'I'],
        'emotional': ['vi', 'IV', 'I', 'V'],  # Am - F - C - G
        'epic': ['I', 'V', 'vi', 'iii', 'IV', 'I', 'IV', 'V'],  # C - G - Am - Em - F - C - F - G
    }
    
    def __init__(self):
        pass
    
    def get_chord(self, chord_name: str) -> Optional[ChordDefinition]:
        """获取和弦定义"""
        return self.CHORD_LIBRARY.get(chord_name)
    
    def get_all_chords(self) -> List[ChordDefinition]:
        """获取所有和弦"""
        return list(self.CHORD_LIBRARY.values())
    
    def get_chords_by_quality(self, quality: str) -> List[ChordDefinition]:
        """按品质筛选和弦"""
        return [ch for ch in self.CHORD_LIBRARY.values() if ch.quality == quality]
    
    def detect_chords_from_audio(self, audio_data: np.ndarray, sample_rate: int) -> List[DetectedChord]:
        """
        从音频检测和弦
        
        使用 librosa.feature.chromagram + 模板匹配
        如果不可用则回退到 Mock
        """
        try:
            import librosa
            import numpy as np
            
            # 1. 计算 Chromagram (12 个半音的能量)
            chroma = librosa.feature.chromagram(y=audio_data, sr=sample_rate, hop_length=512)
            
            # 2. 计算每个时刻的主要和弦 (简化模板匹配)
            # 3 个主要和弦模板：Major, Minor, 7th
            major_template = np.zeros(12)
            minor_template = np.zeros(12)
            major_template[[0, 4, 7]] = 1  # Root, Major 3rd, Perfect 5th
            minor_template[[0, 3, 7]] = 1  # Root, Minor 3rd, Perfect 5th
            
            chords = []
            times = librosa.times_like(chroma[0], sr=sample_rate, hop_length=512)
            
            # 简化：每 4 拍检测一次
            step = max(1, len(times) // 16)
            
            for i in range(0, len(times), step):
                frame = chroma[:, i]
                frame = frame / (np.max(frame) + 1e-10)  # 归一化
                
                # 对 12 个根音做相关匹配
                best_chord = None
                best_score = 0
                
                for root in range(12):
                    # 移位模板
                    major_shifted = np.roll(major_template, root)
                    minor_shifted = np.roll(minor_template, root)
                    
                    # 计算相关度
                    major_score = np.corrcoef(frame, major_shifted)[0, 1]
                    minor_score = np.corrcoef(frame, minor_shifted)[0, 1]
                    
                    if major_score > best_score:
                        best_score = major_score
                        quality = 'major'
                    elif minor_score > best_score:
                        best_score = minor_score
                        quality = 'minor'
                    
                    if best_score > 0.3:  # 阈值
                        root_name = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'][root]
                        chord_name = root_name if quality == 'major' else root_name + 'm'
                        best_chord = chord_name
                
                if best_chord and best_score > 0.3:
                    detected = DetectedChord(
                        time=float(times[i]),
                        chord_name=best_chord,
                        confidence=float(best_score),
                        duration=4.0,  # 假设 4 拍
                        bass_note=None
                    )
                    chords.append(detected)
            
            return chords if chords else self._generate_mock_chords()
            
        except Exception:
            # 回退到 Mock
            return self._generate_mock_chords()
    
    def _generate_mock_chords(self) -> List[DetectedChord]:
        """生成 Mock 和弦 (备用)"""
        return [
            DetectedChord(time=0.0, chord_name='C', confidence=0.95, duration=4.0, bass_note='C3'),
            DetectedChord(time=4.0, chord_name='G', confidence=0.92, duration=4.0, bass_note='G2'),
            DetectedChord(time=8.0, chord_name='Am', confidence=0.89, duration=4.0, bass_note='A2'),
            DetectedChord(time=12.0, chord_name='F', confidence=0.94, duration=4.0, bass_note='F3'),
        ]
    
    def generate_progression(
        self,
        progression_type: str,
        key: str = 'C',
        tempo: int = 120,
        bars: int = 4
    ) -> ChordProgression:
        """
        生成和弦进行
        
        Args:
            progression_type: 进行类型 (pop_basic, jazz_ii_v_i, 等)
            key: 调性 (如 "C", "Am")
            tempo: BPM
            bars: 小节数
        
        Returns:
            和弦进行
        """
        progression = self.COMMON_PROGRESSIONS.get(progression_type, ['I', 'IV', 'V', 'I'])
        
        # 级数转和弦 (简化版：只支持 C 大调和 A 小调)
        roman_to_chord = {
            'C': {'I': 'C', 'ii': 'Dm', 'iii': 'Em', 'IV': 'F', 'V': 'G', 'vi': 'Am', 'vii°': 'Bdim'},
            'Am': {'i': 'Am', 'ii°': 'Bdim', 'III': 'C', 'iv': 'Dm', 'v': 'Em', 'VI': 'F', 'VII': 'G'},
        }
        
        key_chords = roman_to_chord.get(key, roman_to_chord['C'])
        
        # 生成和弦
        chords = []
        chord_duration = 60 / tempo * 4  # 每和弦 4 拍
        
        for i, roman in enumerate(progression * bars):
            if roman not in key_chords:
                continue
            
            chord_name = key_chords[roman]
            chords.append(DetectedChord(
                time=i * chord_duration,
                chord_name=chord_name,
                confidence=0.9,
                duration=chord_duration,
                bass_note=None,  # 由前端根据乐器决定
            ))
        
        return ChordProgression(
            chords=chords,
            key=key,
            tempo=tempo,
            total_duration=len(chords) * chord_duration,
        )
    
    def generate_harmony(
        self,
        melody_notes: List[int],
        chord: ChordDefinition,
        style: str = 'block'
    ) -> List[List[int]]:
        """
        为旋律生成和声
        
        Args:
            melody_notes: 旋律音符 (MIDI 编号)
            chord: 当前和弦
            style: 和声风格 ('block'=柱式，'arpeggio'=分解，'pad'=长音)
        
        Returns:
            和声音符列表 (每个旋律音符对应一个和声音符组)
        """
        harmony = []
        chord_midi = [60 + interval for interval in chord.intervals]  # 以 C4 为根
        
        for note in melody_notes:
            if style == 'block':
                # 柱式和声：添加和弦内音
                harmony.append(chord_midi)
            elif style == 'arpeggio':
                # 分解和弦：按顺序播放和弦音
                harmony.append([chord_midi[note % len(chord_midi)]])
            elif style == 'pad':
                # 长音和声：最低的和弦音
                harmony.append([chord_midi[0]])
        
        return harmony


# 全局服务实例
chord_track_service = ChordTrackService()