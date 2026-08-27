"""统一声音克隆 Provider — 上层业务不直接依赖 GPT-SoVITS 具体 API。

本 Provider 封装：
  - 参考音频校验（asr_client.validate_ref_audio）
  - 参考音频自动转写 prompt_text（asr_client.transcribe_ref_audio，faster-whisper CPU）
  - 参考音频上传到 Modal 共享数据卷（tts_client.upload_ref_audio）
  - GPT-SoVITS 克隆合成（tts_client.synthesize_cloned）
  - 生成音频从共享卷取回本地（tts_client.download_generated）

隔离点：
  - 上层（voice_clone_orchestrator / ai_music）只依赖本 Provider 的 clone_voice()
    与 VoiceCloneSegmentResult，不 import tts_client / asr_client。
  - Modal 未部署 / SDK 缺失 / 队列满：按失败语义返回，绝不伪造音频。

成本统计：
  - 每次合成记录 voice_clone_cost（估算 GPU 秒）与 tts_seconds（推理耗时），
    供 ai_music 写入 TaskResult.metadata 的 generation_cost 明细。
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# 参考音频限制（与 asr_client 保持一致，可被环境变量覆盖）
MAX_REF_SECONDS = float(os.getenv("VOICE_CLONE_MAX_REF_SECONDS", "60"))
MIN_REF_SECONDS = float(os.getenv("VOICE_CLONE_MIN_REF_SECONDS", "5"))
RECOMMEND_REF_SECONDS = (10, 30)  # 推荐 10~30 秒

# 单次 TTS 合成超时（与 segment SEGMENT_TIMEOUT 对齐，GPT-SoVITS T4 推理）
TTS_TIMEOUT_SECONDS = float(os.getenv("TTS_TIMEOUT_SECONDS", "180"))
# 单段人声最大合成时长：TTS 分段的建议上限，避免超长生成音色漂移/显存问题
VOCAL_SEGMENT_MAX_SECONDS = int(os.getenv("VOCAL_SEGMENT_MAX_SECONDS", "60"))


class VoiceCloneError(Exception):
    """声音克隆失败（校验/转写/合成/取回任一环节失败）"""


class VoiceCloneQueueFullError(VoiceCloneError):
    """GPT-SoVITS 队列满，稍后重试"""


@dataclass
class VoiceCloneSegmentResult:
    """单段克隆人声结果"""
    success: bool
    local_path: Optional[str] = None
    duration: float = 0.0
    text: str = ""
    language: str = "zh"
    error: Optional[str] = None
    tts_seconds: float = 0.0
    cost_estimate_usd: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VoiceCloneRequest:
    """克隆请求（Provider 层统一契约）"""
    reference_audio_path: str            # 本地参考音频路径
    text: str                            # 该段歌词/文本
    language: str = "zh"                 # 生成语言（zh/en/ja/ko/yue/auto）
    duration: int = 30                   # 目标时长（秒），Provider 据此提示但由模型决定
    voice_id: str = ""                   # 声音参考 ID（用于卷内文件名与日志）
    prompt_text: Optional[str] = None    # 参考音频转写（None 则自动 ASR）
    prompt_language: Optional[str] = None
    speed: float = 1.0
    out_stem: str = ""


class VoiceCloneProvider:
    """GPT-SoVITS 声音克隆统一 Provider。

    clone_voice() 是唯一对外入口。返回 VoiceCloneSegmentResult；
    任何失败都不抛未捕获异常（除 VoiceCloneQueueFullError 供上层重试决策），
    而是返回 success=False + error，由编排层决定 fallback。
    """

    def __init__(self):
        self._tts_available: Optional[bool] = None

    # ---------- 内部依赖（延迟 import，便于单测注入） ----------
    @staticmethod
    def _asr_module():
        from app.services import asr_client
        return asr_client

    @staticmethod
    def _tts_module():
        from app.services import tts_client
        return tts_client

    # ---------- 公开接口 ----------
    async def validate_reference(self, audio_path: str) -> Dict[str, Any]:
        """校验本地参考音频，返回 {duration, format, valid, error}。

        校验项：文件存在、大小、格式魔数、时长区间（>= MIN_REF_SECONDS，<= MAX_REF_SECONDS）。
        返回 valid=False 时 error 为中文可读原因；valid=True 时 duration 为秒。
        """
        if not audio_path or not os.path.exists(audio_path):
            return {"valid": False, "error": "参考音频不存在", "duration": None, "format": None}
        try:
            with open(audio_path, "rb") as f:
                data = f.read()
        except OSError as exc:
            return {"valid": False, "error": f"读取参考音频失败: {exc}", "duration": None, "format": None}

        asr = self._asr_module()
        try:
            asr.validate_ref_audio(data)
        except asr.TranscriptionError as exc:
            return {"valid": False, "error": str(exc), "duration": None, "format": None}

        duration = asr.audio_duration(data)
        fmt = asr.detect_audio_format(data)
        if duration is not None and duration < MIN_REF_SECONDS:
            return {
                "valid": False,
                "error": f"参考音频过短（{duration:.0f}s），建议至少 {MIN_REF_SECONDS:.0f}s（推荐 10~30s）",
                "duration": duration,
                "format": fmt,
            }
        return {"valid": True, "error": None, "duration": duration, "format": fmt}

    async def transcribe_reference(self, audio_path: str) -> Dict[str, Any]:
        """转写参考音频，返回 {prompt_text, prompt_language, detected_language}。

        失败抛 VoiceCloneError（不伪造转写）。
        """
        try:
            with open(audio_path, "rb") as f:
                data = f.read()
        except OSError as exc:
            raise VoiceCloneError(f"读取参考音频失败: {exc}")
        asr = self._asr_module()
        try:
            return await asr.transcribe_ref_audio(data)
        except asr.TranscriptionError as exc:
            raise VoiceCloneError(str(exc))

    async def clone_voice(self, request: VoiceCloneRequest) -> VoiceCloneSegmentResult:
        """执行一段克隆人声合成。返回 VoiceCloneSegmentResult（不抛异常，除队列满）。"""
        t0 = time.time()
        try:
            if not request.reference_audio_path or not os.path.exists(request.reference_audio_path):
                return VoiceCloneSegmentResult(success=False, error="参考音频不存在", text=request.text, language=request.language)

            if not request.text or not request.text.strip():
                return VoiceCloneSegmentResult(success=False, error="人声文本为空", text=request.text, language=request.language)

            # 1. 校验参考音频
            check = await self.validate_reference(request.reference_audio_path)
            if not check["valid"]:
                return VoiceCloneSegmentResult(success=False, error=check["error"], text=request.text, language=request.language)

            # 2. 读取参考音频字节（用于上传卷 + ASR）
            with open(request.reference_audio_path, "rb") as f:
                audio_bytes = f.read()

            # 3. 转写（显式提供则跳过 ASR）
            prompt_text = request.prompt_text
            prompt_language = request.prompt_language
            if not prompt_text:
                try:
                    trans = await self.transcribe_reference(request.reference_audio_path)
                    prompt_text = trans["prompt_text"]
                    prompt_language = trans["prompt_language"]
                except VoiceCloneError as exc:
                    return VoiceCloneSegmentResult(success=False, error=str(exc), text=request.text, language=request.language)

            # 4. 上传参考音频到共享卷
            voice_id = request.voice_id or "ref_default"
            tts = self._tts_module()
            ref_name = await tts.upload_ref_audio(voice_id, audio_bytes)
            if not ref_name:
                return VoiceCloneSegmentResult(success=False, error="参考音频上传到共享卷失败", text=request.text, language=request.language)

            # 5. 调用 GPT-SoVITS 合成（合并上传+合成）
            try:
                volume_result = await tts.synthesize_cloned(
                    audio_bytes=audio_bytes,
                    voice_id=voice_id,
                    text=request.text,
                    language=request.language,
                    prompt_text=prompt_text,
                    prompt_language=prompt_language,
                    speed=request.speed,
                    out_stem=request.out_stem or f"vocal_{voice_id}",
                )
            except Exception as exc:  # QueueFullError 由调用方捕获
                if "queue" in str(exc).lower() and "full" in str(exc).lower():
                    raise VoiceCloneQueueFullError(str(exc))
                return VoiceCloneSegmentResult(success=False, error=f"GPT-SoVITS 合成调用失败: {exc}", text=request.text, language=request.language)

            if not volume_result or not volume_result.get("wav"):
                return VoiceCloneSegmentResult(success=False, error="GPT-SoVITS 未返回生成音频", text=request.text, language=request.language)

            # 6. 取回本地
            local_path = await tts.download_generated(volume_result["wav"])
            if not local_path:
                return VoiceCloneSegmentResult(success=False, error="生成音频从共享卷取回失败", text=request.text, language=request.language)

            tts_seconds = time.time() - t0
            return VoiceCloneSegmentResult(
                success=True,
                local_path=local_path,
                duration=0.0,  # 由编排层 ffprobe 填充实际时长
                text=request.text,
                language=request.language,
                tts_seconds=tts_seconds,
                cost_estimate_usd=tts_seconds * 0.0001,  # 估算：T4 秒单价（占位，可调）
                metadata={"prompt_language": prompt_language, "prompt_text_len": len(prompt_text)},
            )
        except VoiceCloneQueueFullError:
            raise
        except Exception as exc:
            logger.exception("clone_voice unexpected error")
            return VoiceCloneSegmentResult(success=False, error=f"声音克隆异常: {exc}", text=request.text, language=request.language)


# 全局实例
_voice_clone_provider: Optional[VoiceCloneProvider] = None


def get_voice_clone_provider() -> VoiceCloneProvider:
    global _voice_clone_provider
    if _voice_clone_provider is None:
        _voice_clone_provider = VoiceCloneProvider()
    return _voice_clone_provider