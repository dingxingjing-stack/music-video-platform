"""
自动字幕识别 API 路由

功能:
- POST /api/v1/subtitles/recognize - 上传音频文件，返回带时间戳的歌词
- POST /api/v1/subtitles/align     - 上传音频+歌词文本，返回对齐后的时间戳
- 使用 Whisper 模型 (openai/whisper) 进行语音识别
- Mock 模式: 当无 Whisper 时返回模拟数据 (均匀分配时间)
- 支持 5 种语言: 中文/英文/日文/韩文/自动检测
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/subtitles", tags=["字幕识别"])

# --------------------------------------------------------------------------- #
# 语言映射
# --------------------------------------------------------------------------- #

LANGUAGE_MAP = {
    "zh": "中文",
    "en": "英文",
    "ja": "日文",
    "ko": "韩文",
    "auto": "自动检测",
}

# Whisper 模型大小 → 别名
WHISPER_MODELS = ["tiny", "base", "small", "medium", "large"]

# --------------------------------------------------------------------------- #
# 响应模型
# --------------------------------------------------------------------------- #


class SubtitleSegment(BaseModel):
    """单条字幕片段"""
    index: int = Field(..., description="片段序号 (从 0 开始)")
    text: str = Field(..., description="字幕文本")
    start: float = Field(..., description="开始时间 (秒)")
    end: float = Field(..., description="结束时间 (秒)")


class RecognizeResponse(BaseModel):
    """语音识别响应"""
    success: bool
    segments: List[SubtitleSegment]
    language: str = Field(..., description="检测到/使用的语言")
    duration: float = Field(0.0, description="音频时长 (秒)")
    model: str = Field(..., description="使用的模型 (whisper-xxx 或 mock)")
    message: str = ""


class AlignResponse(BaseModel):
    """歌词对齐响应"""
    success: bool
    segments: List[SubtitleSegment]
    duration: float = Field(0.0, description="音频时长 (秒)")
    model: str = Field(..., description="使用的模型 (whisper-xxx 或 mock)")
    message: str = ""


class LanguagesResponse(BaseModel):
    """支持的语言列表"""
    languages: List[dict]


# --------------------------------------------------------------------------- #
# Whisper 加载 (惰性 — 仅在首次调用时尝试)
# --------------------------------------------------------------------------- #

_whisper_model = None
_whisper_load_attempted = False
_whisper_error: Optional[str] = None


def _try_load_whisper(model_name: str = "base"):
    """惰性加载 Whisper 模型。成功返回 model 对象，失败返回 None。"""
    global _whisper_model, _whisper_load_attempted, _whisper_error

    if _whisper_load_attempted:
        return _whisper_model

    _whisper_load_attempted = True
    try:
        import whisper  # type: ignore  # openai/whisper
        _whisper_model = whisper.load_model(model_name)
        logger.info("Whisper 模型 '%s' 加载成功", model_name)
        return _whisper_model
    except ImportError:
        _whisper_error = "whisper 包未安装 (pip install openai-whisper)"
        logger.warning("Whisper 不可用 → 使用 Mock 模式: %s", _whisper_error)
    except Exception as exc:
        _whisper_error = str(exc)
        logger.warning("Whisper 加载失败 → 使用 Mock 模式: %s", exc)
    return None


def _whisper_to_segments(result: dict) -> List[SubtitleSegment]:
    """将 whisper 转写结果转换为 SubtitleSegment 列表。"""
    segments: List[SubtitleSegment] = []
    for i, seg in enumerate(result.get("segments", [])):
        segments.append(
            SubtitleSegment(
                index=i,
                text=seg.get("text", "").strip(),
                start=round(float(seg.get("start", 0.0)), 3),
                end=round(float(seg.get("end", 0.0)), 3),
            )
        )
    return segments


# --------------------------------------------------------------------------- #
# Mock 模式工具
# --------------------------------------------------------------------------- #


def _get_audio_duration(file_path: str) -> float:
    """尝试获取音频时长 (秒)。失败时返回 30.0 作为默认值。"""
    try:
        from pydub.utils import mediainfo  # type: ignore
        info = mediainfo(file_path)
        return float(info.get("duration", 30.0))
    except Exception:
        pass
    try:
        import wave  # type: ignore
        with wave.open(file_path, "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate > 0:
                return frames / rate
    except Exception:
        pass
    return 30.0


def _mock_recognize(duration: float, language: str) -> List[SubtitleSegment]:
    """Mock 模式: 生成均匀分配的模拟歌词片段。"""
    mock_lines = [
        "♪ (伴奏)",
        "每当夜幕降临",
        "星光洒满了天空",
        "我听见远方的歌",
        "呼唤着心的归属",
        "♪ (间奏)",
        "走过风雨的旅途",
        "才懂何为珍贵",
        "就让这首歌",
        "陪你到天涯海角",
        "♪ (尾奏)",
    ]
    n = len(mock_lines)
    seg_duration = duration / n if n > 0 else 0.0
    segments: List[SubtitleSegment] = []
    for i, line in enumerate(mock_lines):
        start = round(i * seg_duration, 3)
        end = round((i + 1) * seg_duration, 3)
        segments.append(SubtitleSegment(index=i, text=line, start=start, end=end))
    return segments


def _mock_align(lines: List[str], duration: float) -> List[SubtitleSegment]:
    """Mock 模式: 将歌词行均匀分配到音频时长上。"""
    n = len(lines)
    if n == 0:
        return []
    seg_duration = duration / n
    segments: List[SubtitleSegment] = []
    for i, line in enumerate(lines):
        start = round(i * seg_duration, 3)
        end = round((i + 1) * seg_duration, 3)
        segments.append(SubtitleSegment(index=i, text=line.strip(), start=start, end=end))
    return segments


# --------------------------------------------------------------------------- #
# API 端点
# --------------------------------------------------------------------------- #


@router.get("/languages", response_model=LanguagesResponse)
async def get_supported_languages():
    """获取支持的语言列表"""
    return LanguagesResponse(
        languages=[
            {"code": code, "name": name}
            for code, name in LANGUAGE_MAP.items()
        ]
    )


@router.post("/recognize", response_model=RecognizeResponse)
async def recognize_subtitles():
    """P5-B.5：语音识别已退休（410 Gone）。

    whisper / faster-whisper 均未安装（不在 backend/requirements.txt），
    原实现在 ImportError 后返回 HTTP 200 + success=True + model="mock"，
    并伪造 11 条中文歌词的时间轴 —— 属把不存在的能力报告为成功。
    """
    raise HTTPException(
        status_code=410,
        detail=("Subtitle recognition has been retired (no ASR model installed). "
              "GET /api/v1/subtitles/health reports the real availability."),
    )




@router.post("/align", response_model=AlignResponse)
async def align_subtitles():
    """P5-B.5：歌词对齐已退休（410 Gone，原 mock 分支同样返回 success=True）。"""
    raise HTTPException(
        status_code=410,
        detail=("Subtitle alignment has been retired (no ASR model installed). "
              "GET /api/v1/subtitles/health reports the real availability."),
    )




@router.get("/health")
async def subtitle_health():
    """检查字幕识别服务状态"""
    available = _try_load_whisper() is not None
    return {
        "available": available,
        "mode": "whisper" if available else "mock",
        "error": _whisper_error,
        "supported_languages": list(LANGUAGE_MAP.keys()),
        "models": WHISPER_MODELS,
    }
