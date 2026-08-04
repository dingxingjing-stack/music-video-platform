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
async def recognize_subtitles(
    file: UploadFile = File(..., description="音频文件 (mp3/wav/flac/m4a)"),
    language: str = Form("auto", description="语言代码: zh/en/ja/ko/auto"),
    model_size: str = Form("base", description="Whisper 模型大小: tiny/base/small/medium/large"),
):
    """
    语音识别 — 上传音频文件，返回带时间戳的字幕片段

    - 使用 openai/whisper 进行语音转文字并附带时间戳
    - 当 Whisper 不可用时自动降级为 Mock 模式 (均匀分配时间)
    - 支持中文/英文/日文/韩文/自动检测
    """
    # 验证语言参数
    if language not in LANGUAGE_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的语言 '{language}'。可选: {', '.join(LANGUAGE_MAP.keys())}",
        )

    # 验证模型大小
    if model_size not in WHISPER_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的模型 '{model_size}'。可选: {', '.join(WHISPER_MODELS)}",
        )

    # 保存上传文件到临时目录
    suffix = Path(file.filename or "audio.mp3").suffix or ".mp3"
    temp_dir = Path(tempfile.gettempdir()) / "subtitle_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    input_path = temp_dir / f"subtitle_{int(time.time())}{suffix}"

    try:
        content = await file.read()
        input_path.write_bytes(content)

        duration = _get_audio_duration(str(input_path))

        # 尝试 Whisper
        wm = _try_load_whisper(model_size)
        if wm is not None:
            try:
                # Whisper 语言参数: auto → None (让模型自动检测)
                whisper_lang = None if language == "auto" else language
                result = wm.transcribe(
                    str(input_path),
                    language=whisper_lang,
                    verbose=False,
                )
                segments = _whisper_to_segments(result)
                detected = result.get("language", language)
                return RecognizeResponse(
                    success=True,
                    segments=segments,
                    language=detected,
                    duration=round(duration, 3),
                    model=f"whisper-{model_size}",
                    message=f"Whisper 识别完成，共 {len(segments)} 段",
                )
            except Exception as exc:
                logger.exception("Whisper 转写失败，降级为 Mock")
                # 降级到 mock
                segments = _mock_recognize(duration, language)
                return RecognizeResponse(
                    success=True,
                    segments=segments,
                    language=language,
                    duration=round(duration, 3),
                    model=f"mock (whisper-{model_size} 失败: {str(exc)[:100]})",
                    message=f"Whisper 转写出错，使用 Mock 数据。错误: {exc}",
                )
        else:
            # Mock 模式
            segments = _mock_recognize(duration, language)
            return RecognizeResponse(
                success=True,
                segments=segments,
                language=language,
                duration=round(duration, 3),
                model="mock",
                message=f"Mock 模式 (Whisper 不可用: {_whisper_error or '未知原因'})。均匀分配 {len(segments)} 段",
            )
    finally:
        # 清理临时文件
        try:
            input_path.unlink(missing_ok=True)
        except Exception:
            pass


@router.post("/align", response_model=AlignResponse)
async def align_subtitles(
    file: UploadFile = File(..., description="音频文件 (mp3/wav/flac/m4a)"),
    lyrics: str = Form(..., description="歌词文本 (每行一句)"),
    language: str = Form("auto", description="语言代码: zh/en/ja/ko/auto"),
    model_size: str = Form("base", description="Whisper 模型大小"),
):
    """
    歌词对齐 — 上传音频+歌词文本，返回每行歌词的时间戳

    - 利用 Whisper 的强制对齐能力 (segment-level) 与歌词行做时间映射
    - Mock 模式: 将歌词行均匀分配到音频时长上
    """
    if language not in LANGUAGE_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的语言 '{language}'。可选: {', '.join(LANGUAGE_MAP.keys())}",
        )

    if not lyrics or not lyrics.strip():
        raise HTTPException(status_code=400, detail="歌词文本不能为空")

    # 解析歌词行 (按换行分割，去空行)
    lines = [ln.strip() for ln in lyrics.strip().splitlines() if ln.strip()]
    if not lines:
        raise HTTPException(status_code=400, detail="歌词文本中没有有效行")

    # 保存上传文件
    suffix = Path(file.filename or "audio.mp3").suffix or ".mp3"
    temp_dir = Path(tempfile.gettempdir()) / "subtitle_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    input_path = temp_dir / f"align_{int(time.time())}{suffix}"

    try:
        content = await file.read()
        input_path.write_bytes(content)

        duration = _get_audio_duration(str(input_path))

        # 尝试 Whisper 做 forced-align 级别的对齐
        wm = _try_load_whisper(model_size)
        if wm is not None:
            try:
                whisper_lang = None if language == "auto" else language
                result = wm.transcribe(
                    str(input_path),
                    language=whisper_lang,
                    verbose=False,
                )
                whisper_segs = _whisper_to_segments(result)

                # 简易对齐: 将歌词行按顺序映射到 Whisper 分段
                # 若分段数与歌词行数接近则一一对应；否则按比例分配
                if len(whisper_segs) >= len(lines):
                    # 取前 N 段
                    segments = [
                        SubtitleSegment(
                            index=i,
                            text=lines[i],
                            start=whisper_segs[i].start,
                            end=whisper_segs[min(i + 1, len(whisper_segs) - 1)].start
                            if i < len(lines) - 1
                            else whisper_segs[-1].end,
                        )
                        for i in range(len(lines))
                    ]
                else:
                    # Whisper 分段少于歌词行 → 在_whisper分段范围内均匀分配
                    total_start = whisper_segs[0].start if whisper_segs else 0.0
                    total_end = whisper_segs[-1].end if whisper_segs else duration
                    span = max(total_end - total_start, 0.1)
                    seg_dur = span / len(lines)
                    segments = [
                        SubtitleSegment(
                            index=i,
                            text=lines[i],
                            start=round(total_start + i * seg_dur, 3),
                            end=round(total_start + (i + 1) * seg_dur, 3),
                        )
                        for i in range(len(lines))
                    ]

                return AlignResponse(
                    success=True,
                    segments=segments,
                    duration=round(duration, 3),
                    model=f"whisper-{model_size}",
                    message=f"对齐完成，共 {len(segments)} 行",
                )
            except Exception as exc:
                logger.exception("Whisper 对齐失败，降级为 Mock")
                segments = _mock_align(lines, duration)
                return AlignResponse(
                    success=True,
                    segments=segments,
                    duration=round(duration, 3),
                    model=f"mock (whisper-{model_size} 失败)",
                    message=f"Whisper 对齐出错，使用 Mock 均匀分配。错误: {exc}",
                )
        else:
            # Mock 模式: 均匀分配
            segments = _mock_align(lines, duration)
            return AlignResponse(
                success=True,
                segments=segments,
                duration=round(duration, 3),
                model="mock",
                message=f"Mock 模式均匀分配 {len(segments)} 行",
            )
    finally:
        try:
            input_path.unlink(missing_ok=True)
        except Exception:
            pass


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
