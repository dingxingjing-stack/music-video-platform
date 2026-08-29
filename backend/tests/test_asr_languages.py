"""ASR 产品 9 语言覆盖验证（阶段 1，只读审计结论落实）。

产品正式语言：zh/en/ja/ko/es/fr/pt/ru/de（无 ar / pt-BR / pt-PT，pt 统一）。

验证内容（不触碰真实 faster-whisper / 权重 / 网络，直接注入模块级假模型）：
  1. 9 种产品语言均可转写：detected_language 正确、prompt_text 非空。
  2. prompt_language 映射符合 GPT-SoVITS 约束：
     zh/en/ja/ko -> 直传；es/fr/pt/ru/de -> auto（不发明 pt / pt-br 参数）。
  3. auto（语言参数）路径：language=None 自动检测不受 9 语言限制。

依据：asr_client 用 faster-whisper（language=None，原生 99 语言自动检测），
模型层无需改动；本测试仅固化「业务映射 + 转写链路」对 9 语言的兼容性。
"""

import asyncio
import struct

import pytest

from app.services import asr_client

# 产品 9 语言：(code, 示例转写文本, 期望 prompt_language)
PRODUCT_LANGUAGES = [
    ("zh", "你好，世界", "zh"),
    ("en", "Hello, world", "en"),
    ("ja", "こんにちは、世界", "ja"),
    ("ko", "안녕하세요, 세계", "ko"),
    ("es", "Hola, mundo", "auto"),
    ("fr", "Bonjour le monde", "auto"),
    ("pt", "Olá, mundo", "auto"),
    ("ru", "Привет, мир", "auto"),
    ("de", "Hallo, Welt", "auto"),
]


def _wav_bytes(seconds: float = 0.1, rate: int = 8000) -> bytes:
    """构造最小合法 16-bit PCM WAV（mono），供假模型/校验使用。"""
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
    def __init__(self, *, segments=(), language="zh"):
        self.segments = segments
        self.language = language

    def transcribe(self, audio, **kwargs):
        return iter(self.segments), _FakeInfo(self.language)


@pytest.fixture(autouse=True)
def _reset_model():
    asr_client._model = None
    yield
    asr_client._model = None


# ═══════════════════════════════════════════════════════════════════
# 1. 9 种产品语言转写链路
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("lang,text,expected_prompt_lang", PRODUCT_LANGUAGES)
def test_transcribe_all_product_languages(lang, text, expected_prompt_lang):
    asr_client._model = _FakeWhisperModel(segments=[_FakeSeg(text)], language=lang)
    result = asyncio.run(asr_client.transcribe_ref_audio(_wav_bytes(), timeout=5))
    assert result["prompt_text"] == text
    assert result["detected_language"] == lang
    assert result["prompt_language"] == expected_prompt_lang


# ═══════════════════════════════════════════════════════════════════
# 2. prompt_language 映射（GPT-SoVITS 约束）
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("lang,expected", [(l, e) for l, _, e in PRODUCT_LANGUAGES])
def test_map_prompt_language_product_languages(lang, expected):
    assert asr_client.map_prompt_language(lang) == expected


def test_map_prompt_language_pt_variants_auto():
    """pt 统一为 auto，禁止发明 pt / pt-br 参数。"""
    assert asr_client.map_prompt_language("pt-BR") == "auto"
    assert asr_client.map_prompt_language("pt-PT") == "auto"


# ═══════════════════════════════════════════════════════════════════
# 3. auto 语言路径（language=None 自动检测）
# ═══════════════════════════════════════════════════════════════════

def test_transcribe_auto_detects_any_product_language():
    """language=None 自动检测不受 9 语言白名单限制（faster-whisper 原生 99 语言）。"""
    asr_client._model = _FakeWhisperModel(segments=[_FakeSeg("Bonjour le monde")], language="fr")
    result = asyncio.run(asr_client.transcribe_ref_audio(_wav_bytes(), timeout=5))
    assert result["detected_language"] == "fr"
    assert result["prompt_language"] == "auto"