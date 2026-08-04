"""
和弦轨道路由 (Chord Track Router)

API 端点:
GET  /api/v1/chords/library — 获取和弦库
GET  /api/v1/chords/progressions — 获取常用和弦进行
POST /api/v1/chords/detect — 从音频检测和弦
POST /api/v1/chords/generate — 生成和弦进行
POST /api/v1/chords/harmony — 生成和声
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from typing import List, Optional
import numpy as np

from app.services.chord_track_service import (
    chord_track_service,
    ChordDefinition,
    DetectedChord,
    ChordProgression,
)


router = APIRouter(prefix="/api/v1/chords", tags=["和弦轨道"])


@router.get("/library", response_model=List[ChordDefinition])
async def get_chord_library(
    quality: Optional[str] = Query(default=None, description="按品质筛选 (major/minor/7th/dim/aug)")
):
    """获取和弦库"""
    if quality:
        chords = chord_track_service.get_chords_by_quality(quality)
    else:
        chords = chord_track_service.get_all_chords()
    
    return chords


@router.get("/progressions")
async def get_chord_progressions():
    """获取常用和弦进行类型"""
    progressions = {
        'pop_basic': '流行基础 (I-V-vi-IV)',
        'pop_variant': '流行变体 (I-vi-IV-V)',
        'jazz_ii_v_i': '爵士 II-V-I',
        'blues_12': '12 小节蓝调',
        'emotional': '情感/抒情 (vi-IV-I-V)',
        'epic': '史诗/电影 (I-V-vi-iii-IV-I-IV-V)',
    }
    return {"progressions": progressions}


@router.post("/detect", response_model=List[DetectedChord])
async def detect_chords(
    audio_file: UploadFile = File(...),
):
    """
    从音频检测和弦
    
    上传音频文件，返回检测到的和弦序列
    """
    try:
        # 读取音频文件
        audio_bytes = await audio_file.read()
        
        # TODO: 使用 librosa 加载
        # audio_data, sample_rate = librosa.load(io.BytesIO(audio_bytes), sr=None)
        
        # Mock 数据
        audio_data = np.zeros(44100 * 16)  # 16 秒
        sample_rate = 44100
        
        # 检测和弦
        chords = chord_track_service.detect_chords_from_audio(audio_data, sample_rate)
        
        return chords
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"和弦检测失败：{str(e)}")


@router.post("/generate", response_model=ChordProgression)
async def generate_chord_progression(
    progression_type: str = Form(default='pop_basic'),
    key: str = Form(default='C'),
    tempo: int = Form(default=120),
    bars: int = Form(default=4, ge=1, le=32),
):
    """
    生成和弦进行
    
    Args:
        progression_type: 进行类型 (pop_basic, jazz_ii_v_i, 等)
        key: 调性 (C, Am, 等)
        tempo: BPM
        bars: 小节数
    """
    try:
        progression = chord_track_service.generate_progression(
            progression_type=progression_type,
            key=key,
            tempo=tempo,
            bars=bars,
        )
        
        return progression
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成失败：{str(e)}")


@router.post("/harmony")
async def generate_harmony(
    melody_notes: List[int] = Form(..., description="旋律音符 (MIDI 编号列表)"),
    chord_name: str = Form(..., description="和弦名称 (如 C, Dm, G7)"),
    style: str = Form(default='block', description="和声风格 (block/arpeggio/pad)"),
):
    """
    为旋律生成和声
    
    Args:
        melody_notes: 旋律音符列表 (MIDI 编号)
        chord_name: 和弦名称
        style: 和声风格
            - block: 柱式和声 (同时演奏所有和弦音)
            - arpeggio: 分解和弦 (依次演奏)
            - pad: 长音和声 (持续低音)
    """
    try:
        chord = chord_track_service.get_chord(chord_name)
        if not chord:
            raise HTTPException(status_code=400, detail=f"无效的和弦：{chord_name}")
        
        harmony = chord_track_service.generate_harmony(
            melody_notes=melody_notes,
            chord=chord,
            style=style,
        )
        
        return {
            "success": True,
            "chord": chord.dict(),
            "style": style,
            "harmony": harmony,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"和声生成失败：{str(e)}")


@router.get("/{chord_name}")
async def get_chord_details(chord_name: str):
    """获取特定和弦的详细信息"""
    chord = chord_track_service.get_chord(chord_name)
    if not chord:
        raise HTTPException(status_code=404, detail=f"未找到和弦：{chord_name}")
    
    return chord