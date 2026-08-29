"""faster-whisper ASR 客户端 — 参考音频自动转写为 GPT-SoVITS prompt_text。

License（Phase 3 只读审查已核验，存档）：
  - faster-whisper 代码：MIT（SYSTRAN/faster-whisper，GitHub LICENSE）
  - 模型权重：openai/whisper-large-v3（Hugging Face 模型卡 `License: apache-2.0`），
    经 Systran/faster-whisper-large-v3（HF 模型卡 `License: mit`，CTranslate2 转换件）
    以 CTranslate2 格式加载 —— 两者均宽松许可，允许商业使用、可自托管。
  - 底层 CTranslate2：MIT。
  - 本模块只调用成熟 faster-whisper 实现，不自行实现 ASR；不访问 OpenAI 托管 API。

运行形态（用户已确认 Phase 3 方案 B）：
  - Web 容器 CPU int8（faster-whisper + CTranslate2），不新增 ASR Modal GPU；
    参考音频通常较短，若实测 CPU 过慢再单独评估 ASR Modal。
  - 模型进程内加载一次常驻（模块级单例），懒加载，faster-whisper 未安装时
    抛 TranscriptionError，由调用方把任务标记 failed，禁止伪造转写。

语言映射（GPT-SoVITS 官方 api.py prompt_language 仅支持 zh/en/ja/ko/yue/auto，
无葡语原生项）：
  zh->zh, en->en, ja->ja, ko->ko, yue->yue；其它语言（含 pt）-> auto。
  不发明 pt / pt-br 参数。

失败语义：ASR 失败 / 超时 / 空转写 一律抛 TranscriptionError。
参考音频校验（大小 / 格式魔数 / 时长）在转写前完成，超标直接拒绝。
"""

import asyncio
import io
import logging
import os
import struct

logger = logging.getLogger(__name__)

# 模型 / 运行参数（可经环境变量覆盖，便于实测后切 small/base 或 GPU）
ASR_MODEL = os.getenv("VOICE_CLONE_ASR_MODEL", "large-v3")
ASR_DEVICE = os.getenv("VOICE_CLONE_ASR_DEVICE", "cpu")
ASR_COMPUTE_TYPE = os.getenv("VOICE_CLONE_ASR_COMPUTE_TYPE", "int8")
ASR_TIMEOUT = float(os.getenv("VOICE_CLONE_ASR_TIMEOUT", "180"))

# 参考音频限制
MAX_REF_BYTES = int(os.getenv("VOICE_CLONE_MAX_REF_BYTES", str(20 * 1024 * 1024)))
MAX_REF_SECONDS = float(os.getenv("VOICE_CLONE_MAX_REF_SECONDS", "60"))

_PROMPT_LANG_MAP = {"zh": "zh", "en": "en", "ja": "ja", "ko": "ko", "yue": "yue"}
_DEFAULT_PROMPT_LANG = "auto"


class TranscriptionError(Exception):
    """ASR 失败 / 超时 / 空转写 / 参考音频不合规。

    调用方必须把任务标记 failed，禁止伪造 prompt_text，禁止继续调用 GPT-SoVITS。
    """


_model = None  # faster_whisper.WhisperModel 单例（懒加载）


def map_prompt_language(detected_language: str) -> str:
    """GPT-SoVITS prompt_language：官方支持语言直传，其余（含 pt）-> auto。"""
    return _PROMPT_LANG_MAP.get((detected_language or "").lower(), _DEFAULT_PROMPT_LANG)


def _get_model():
    global _model
    if _model is not None:
        return _model
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionError("ASR 引擎不可用（faster-whisper 未安装）") from exc
    _model = WhisperModel(ASR_MODEL, device=ASR_DEVICE, compute_type=ASR_COMPUTE_TYPE)
    return _model


# ═══════════════════════════════════════════════════════════════════════
# 参考音频校验：大小 / 格式魔数 / 时长
# ═══════════════════════════════════════════════════════════════════════

def detect_audio_format(data: bytes) -> str | None:
    """按魔数识别音频格式：wav / flac / ogg / mp3 / m4a，无法识别返回 None。"""
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data[:4] == b"fLaC":
        return "flac"
    if data[:4] == b"OggS":
        return "ogg"
    if data[:3] == b"ID3" or data[:2] == b"\xff\xfb":
        return "mp3"
    if len(data) >= 8 and data[4:8] == b"ftyp":
        return "m4a"
    return None


def _wav_duration(data: bytes) -> float | None:
    """解析 WAV 头（fmt + data 块）估算时长；不依赖 soundfile/av。"""
    try:
        if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
            return None
        pos = 12
        rate = None
        block_align = None
        frames = None
        while pos + 8 <= len(data):
            chunk_id = data[pos:pos + 4]
            size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
            if chunk_id == b"fmt " and size >= 16:
                _, _, rate, _, block_align, _ = struct.unpack("<HHIIHH", data[pos + 8:pos + 24])
            elif chunk_id == b"data":
                if block_align:
                    frames = size // block_align
                break
            pos += 8 + size + (size % 2)
        if rate and frames:
            return frames / float(rate)
    except Exception:  # noqa: BLE001 - 解析失败返回 None，交由上层判定
        return None
    return None


def _duration_via_soundfile(data: bytes) -> float | None:
    try:
        import soundfile as sf
        info = sf.info(io.BytesIO(data))
        return float(info.duration)
    except Exception:  # noqa: BLE001
        return None


def _duration_via_av(data: bytes) -> float | None:
    try:
        import av
        with av.open(io.BytesIO(data)) as container:
            for stream in container.streams:
                if stream.type == "audio" and stream.duration and stream.time_base:
                    return float(stream.duration * stream.time_base)
            if container.duration is not None and container.time_base:
                return float(container.duration * container.time_base)
    except Exception:  # noqa: BLE001
        return None
    return None


def audio_duration(data: bytes) -> float | None:
    """尽力获取时长（soundfile -> av -> WAV 头解析），均失败返回 None。"""
    dur = _duration_via_soundfile(data)
    if dur is not None and dur > 0:
        return dur
    dur = _duration_via_av(data)
    if dur is not None and dur > 0:
        return dur
    return _wav_duration(data)


def validate_ref_audio(data: bytes) -> None:
    """参考音频合规校验：大小 / 格式 / 时长。不合规抛 TranscriptionError。

    时长无法解析（如某些 m4a 环境缺解码库）时不阻断，交由 ASR 解码判定。
    """
    if not data:
        raise TranscriptionError("参考音频为空，请重新上传更清晰的音频")
    if len(data) > MAX_REF_BYTES:
        raise TranscriptionError(f"参考音频超过大小限制（{MAX_REF_BYTES // (1024 * 1024)}MB）")
    fmt = detect_audio_format(data)
    if not fmt:
        raise TranscriptionError("参考音频格式不支持（仅 WAV/MP3/M4A/OGG/FLAC）")
    dur = audio_duration(data)
    if dur is not None and dur > MAX_REF_SECONDS:
        raise TranscriptionError(f"参考音频过长（{dur:.0f}s），上限 {MAX_REF_SECONDS:.0f}s，请重新上传更短的音频")
    if dur is None:
        logger.warning("参考音频时长无法解析（format=%s），跳过时长校验", fmt)


# ═══════════════════════════════════════════════════════════════════════
# 转写
# ═══════════════════════════════════════════════════════════════════════

def _transcribe_sync(audio_bytes: bytes) -> dict:
    """阻塞转写（运行在线程池中）。返回 {prompt_text, detected_language, prompt_language}。"""
    model = _get_model()
    try:
        segments, info = model.transcribe(
            io.BytesIO(audio_bytes),
            language=None,
            beam_size=5,
        )
    except TranscriptionError:
        raise
    except Exception as exc:
        raise TranscriptionError("参考音频转写失败，请重新上传更清晰的音频") from exc

    detected = (info.language or "").lower()
    text = "".join(seg.text for seg in segments).strip()
    if not text:
        raise TranscriptionError("参考音频转写为空，请重新上传更清晰的音频")
    return {
        "prompt_text": text,
        "detected_language": detected,
        "prompt_language": map_prompt_language(detected),
    }


async def transcribe_ref_audio(audio_bytes: bytes, timeout: float = ASR_TIMEOUT) -> dict:
    """异步转写参考音频，超时抛 TranscriptionError。

    返回 {"prompt_text", "detected_language", "prompt_language"}。
    """
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_transcribe_sync, audio_bytes),
            timeout=timeout,
        )
    except TimeoutError as exc:
        raise TranscriptionError("参考音频转写超时，请重新上传更清晰的音频") from exc