"""asr_client 本地单元测试（不触碰真实 faster-whisper / 权重 / 网络）。

通过直接注入模块级假模型（asr_client._model）验证：
  1. 中文识别：prompt_text + detected=zh + prompt_language=zh
  2. 葡萄牙语识别：detected=pt -> prompt_language=auto（不发明 pt/pt-br）
  3. ASR 成功 / 失败 / 超时 / 空转写拒绝
  4. prompt_language 映射（zh/en/ja/ko/yue 直传，其它含 pt -> auto）
  5. 参考音频大小 / 格式 / 时长校验
  6. 格式魔数识别
"""

import asyncio
import struct
import sys
import time

import pytest

from app.services import asr_client

# ═══════════════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════════════

def _wav_bytes(seconds: float = 0.1, rate: int = 8000) -> bytes:
    """构造最小合法 16-bit PCM WAV（mono），供校验/假模型使用。"""
    n_frames = int(rate * seconds)
    data = b"\x00\x00" * n_frames
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
    riff_size = 36 + len(data)
    return (
        b"RIFF" + struct.pack("<I", riff_size) + b"WAVE"
        + b"fmt " + struct.pack("<I", 16) + fmt
        + b"data" + struct.pack("<I", len(data)) + data
    )


class _FakeSeg:
    def __init__(self, text: str):
        self.text = text


class _FakeInfo:
    def __init__(self, language: str):
        self.language = language


class _FakeWhisperModel:
    def __init__(self, *, segments=(), language="zh", error=None, delay=0.0):
        self.segments = segments
        self.language = language
        self.error = error
        self.delay = delay

    def transcribe(self, audio, **kwargs):
        if self.error:
            raise self.error
        if self.delay:
            time.sleep(self.delay)
        return iter(self.segments), _FakeInfo(self.language)


@pytest.fixture(autouse=True)
def _reset_model():
    asr_client._model = None
    yield
    asr_client._model = None


# ═══════════════════════════════════════════════════════════════════
# prompt_language 映射
# ═══════════════════════════════════════════════════════════════════

def test_map_prompt_language_zh():
    assert asr_client.map_prompt_language("zh") == "zh"


def test_map_prompt_language_en_ja_ko_yue():
    assert asr_client.map_prompt_language("en") == "en"
    assert asr_client.map_prompt_language("ja") == "ja"
    assert asr_client.map_prompt_language("ko") == "ko"
    assert asr_client.map_prompt_language("yue") == "yue"


def test_map_prompt_language_portuguese_is_auto():
    """葡语无 GPT-SoVITS 原生项，必须映射 auto，禁止发明 pt/pt-br。"""
    assert asr_client.map_prompt_language("pt") == "auto"
    assert asr_client.map_prompt_language("pt-BR") == "auto"


def test_map_prompt_language_other_is_auto():
    assert asr_client.map_prompt_language("es") == "auto"
    assert asr_client.map_prompt_language("fr") == "auto"
    assert asr_client.map_prompt_language("") == "auto"


# ═══════════════════════════════════════════════════════════════════
# ASR 转写
# ═══════════════════════════════════════════════════════════════════

def test_transcribe_success_zh():
    asr_client._model = _FakeWhisperModel(
        segments=[_FakeSeg("你好世界")], language="zh",
    )
    result = asyncio.run(asr_client.transcribe_ref_audio(_wav_bytes(), timeout=5))
    assert result["prompt_text"] == "你好世界"
    assert result["detected_language"] == "zh"
    assert result["prompt_language"] == "zh"


def test_transcribe_success_portuguese():
    asr_client._model = _FakeWhisperModel(
        segments=[_FakeSeg("Olá, tudo bem?")], language="pt",
    )
    result = asyncio.run(asr_client.transcribe_ref_audio(_wav_bytes(), timeout=5))
    assert result["prompt_text"] == "Olá, tudo bem?"
    assert result["detected_language"] == "pt"
    assert result["prompt_language"] == "auto"


def test_transcribe_success_concatenates_segments():
    asr_client._model = _FakeWhisperModel(
        segments=[_FakeSeg("你好"), _FakeSeg("，世界")], language="zh",
    )
    result = asyncio.run(asr_client.transcribe_ref_audio(_wav_bytes(), timeout=5))
    assert result["prompt_text"] == "你好，世界"


def test_transcribe_failure_raises():
    asr_client._model = _FakeWhisperModel(error=RuntimeError("boom"))
    with pytest.raises(asr_client.TranscriptionError):
        asyncio.run(asr_client.transcribe_ref_audio(_wav_bytes(), timeout=5))


def test_transcribe_timeout_raises():
    asr_client._model = _FakeWhisperModel(segments=[_FakeSeg("慢")], language="zh", delay=0.5)
    with pytest.raises(asr_client.TranscriptionError, match="超时"):
        asyncio.run(asr_client.transcribe_ref_audio(_wav_bytes(), timeout=0.05))


def test_transcribe_empty_rejected():
    """空转写不得生成假 prompt_text。"""
    asr_client._model = _FakeWhisperModel(segments=[_FakeSeg("   ")], language="zh")
    with pytest.raises(asr_client.TranscriptionError, match="为空"):
        asyncio.run(asr_client.transcribe_ref_audio(_wav_bytes(), timeout=5))


# ═══════════════════════════════════════════════════════════════════
# 参考音频校验
# ═══════════════════════════════════════════════════════════════════

def test_validate_ref_audio_ok():
    asr_client.validate_ref_audio(_wav_bytes())


def test_validate_ref_audio_rejects_oversize(monkeypatch):
    monkeypatch.setattr(asr_client, "MAX_REF_BYTES", 10)
    with pytest.raises(asr_client.TranscriptionError, match="大小"):
        asr_client.validate_ref_audio(_wav_bytes())


def test_validate_ref_audio_rejects_bad_format():
    with pytest.raises(asr_client.TranscriptionError, match="格式"):
        asr_client.validate_ref_audio(b"NOTAN-AUDIO-FILE" * 10)


def test_validate_ref_audio_rejects_overlong(monkeypatch):
    monkeypatch.setattr(asr_client, "MAX_REF_SECONDS", 0.01)
    with pytest.raises(asr_client.TranscriptionError, match="过长"):
        asr_client.validate_ref_audio(_wav_bytes(seconds=0.5))


def test_detect_audio_format_magic_bytes():
    assert asr_client.detect_audio_format(b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 4) == "wav"
    assert asr_client.detect_audio_format(b"fLaC" + b"\x00" * 4) == "flac"
    assert asr_client.detect_audio_format(b"OggS" + b"\x00" * 4) == "ogg"
    assert asr_client.detect_audio_format(b"ID3" + b"\x00" * 4) == "mp3"
    assert asr_client.detect_audio_format(b"\x00\x00\x00\x18ftyp" + b"\x00" * 4) == "m4a"
    assert asr_client.detect_audio_format(b"garbagebytes" * 2) is None


def test_wav_duration_parses_header():
    assert asr_client._wav_duration(_wav_bytes(seconds=0.5)) == pytest.approx(0.5, abs=0.01)


def test_wav_duration_none_for_non_wav():
    assert asr_client._wav_duration(b"fLaC" + b"\x00" * 20) is None


# ═══════════════════════════════════════════════════════════════════
# 引擎不可用
# ═══════════════════════════════════════════════════════════════════

def test_model_unavailable_raises():
    import types
    fake = types.ModuleType("faster_whisper")  # 空模块，无 WhisperModel -> ImportError 分支
    saved = sys.modules.get("faster_whisper")
    sys.modules["faster_whisper"] = fake
    try:
        with pytest.raises(asr_client.TranscriptionError, match="未安装"):
            asr_client._get_model()
    finally:
        if saved is not None:
            sys.modules["faster_whisper"] = saved
        else:
            sys.modules.pop("faster_whisper", None)
