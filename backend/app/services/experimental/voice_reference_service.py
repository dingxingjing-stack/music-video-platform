"""声音参考样本服务 — 上传/校验/授权/R2 私有存储/所有权隔离。

安全约束（Voice Clone 授权与安全要求）：
  - 参考音频存储于 R2 私有对象：users/{user_id}/voice-references/{reference_id}.wav
  - 下载仅返回短期 presigned URL（10 分钟），绝不暴露公开 URL
  - 所有按 reference_id 的读取必须校验归属 user_id，跨用户访问返回 404
  - 授权确认由路由层校验 agree_authorized=True，本服务不绕过
  - 日志不打印音频内容

存储说明：
  - 参考音频以 WAV 规范化后落盘本地临时文件（用于 GPT-SoVITS 卷上传与 ASR），
    同时上传 R2 私有对象作为持久存档；R2 上传失败不阻断本地上传使用
    （Provider 直读本地，R2 仅作持久化）。
"""

import asyncio
import io
import logging
import os
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# 参考音频限制
MAX_REF_BYTES = int(os.getenv("VOICE_CLONE_MAX_REF_BYTES", str(20 * 1024 * 1024)))
MAX_REF_SECONDS = float(os.getenv("VOICE_CLONE_MAX_REF_SECONDS", "60"))
MIN_REF_SECONDS = float(os.getenv("VOICE_CLONE_MIN_REF_SECONDS", "5"))

FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
FFPROBE_PATH = os.getenv("FFPROBE_PATH", "ffprobe")

# 本地参考音频暂存目录（持久化为 R2 对象，本地文件可清理）
LOCAL_REF_DIR = os.getenv(
    "VOICE_REF_DIR",
    os.path.join(tempfile.gettempdir(), "voice_references"),
)


@dataclass
class VoiceReference:
    """声音参考样本元数据"""
    reference_id: str
    user_id: str
    duration: float
    format: str
    size_bytes: int
    status: str = "ready"          # ready/processing/failed
    prompt_text: str = ""          # ASR 转写（可选，懒加载）
    prompt_language: str = ""
    detected_language: str = ""
    r2_object_key: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    agree_authorized: bool = False  # 授权确认（路由层校验后写入）
    metadata: Dict[str, Any] = field(default_factory=dict)


class VoiceReferenceError(Exception):
    """参考音频校验/存储错误"""


class _ReferenceStore:
    """进程内参考样本注册表（生产环境可替换为 Redis/SQLite，结构对齐 task_store）。"""

    def __init__(self):
        self._refs: Dict[str, VoiceReference] = {}       # reference_id -> VoiceReference
        self._user_refs: Dict[str, list] = {}            # user_id -> [reference_id]

    def create(self, user_id: str, ref: VoiceReference) -> None:
        self._refs[ref.reference_id] = ref
        self._user_refs.setdefault(user_id, []).append(ref.reference_id)

    def get(self, reference_id: str) -> Optional[VoiceReference]:
        return self._refs.get(reference_id)

    def get_user_ref(self, user_id: str, reference_id: str) -> Optional[VoiceReference]:
        ref = self._refs.get(reference_id)
        if ref and ref.user_id == user_id:
            return ref
        return None

    def list_user(self, user_id: str) -> list:
        return [self._refs[rid] for rid in self._user_refs.get(user_id, []) if rid in self._refs]

    def delete(self, user_id: str, reference_id: str) -> bool:
        ref = self._refs.get(reference_id)
        if not ref or ref.user_id != user_id:
            return False
        self._refs.pop(reference_id, None)
        if user_id in self._user_refs and reference_id in self._user_refs[user_id]:
            self._user_refs[user_id].remove(reference_id)
        return True


_store = _ReferenceStore()


def _detect_format(data: bytes) -> Optional[str]:
    from app.services.asr_client import detect_audio_format
    return detect_audio_format(data)


def _duration_of(data: bytes) -> Optional[float]:
    from app.services.asr_client import audio_duration
    return audio_duration(data)


def _normalize_to_wav(input_path: str) -> str:
    """统一为 44.1kHz/16bit/mono WAV（GPT-SoVITS 参考音频要求）。返回新路径。"""
    out = tempfile.mktemp(suffix="_ref_norm.wav")
    cmd = [
        FFMPEG_PATH, "-y", "-hide_banner", "-loglevel", "error",
        "-i", input_path,
        "-ar", "44100", "-ac", "1", "-sample_fmt", "s16",
        out,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=60)
    if result.returncode != 0:
        raise VoiceReferenceError(f"参考音频规范化失败: {result.stderr.decode(errors='replace')[:300]}")
    return out


async def _upload_to_r2(local_path: str, user_id: str, reference_id: str) -> Optional[str]:
    """上传参考音频到 R2 私有对象。返回 object_key；失败返回 None（不阻断本地链路）。"""
    try:
        from app.services.cdn_uploader import cdn_uploader
        res = await cdn_uploader.upload_file(
            local_path,
            category="voice_reference",
            user_id=user_id,
            task_id=reference_id,
            filename=f"voice_ref_{reference_id}.wav",
            metadata={"type": "voice_reference", "user_id": user_id, "reference_id": reference_id},
        )
        if res.success:
            return res.object_key
        logger.warning("参考音频 R2 上传失败（本地链路继续）: %s", res.error)
        return None
    except Exception as exc:
        logger.warning("参考音频 R2 上传异常（本地链路继续）: %s", exc)
        return None


async def create_voice_reference(
    user_id: str,
    audio_bytes: bytes,
    agree_authorized: bool = False,
) -> VoiceReference:
    """创建声音参考样本：校验 -> 规范化 -> 持久化 R2 -> 注册。

    校验失败抛 VoiceReferenceError（中文原因）。
    授权确认由路由层保证；此处仍校验 agree_authorized 并记录。
    """
    if not audio_bytes:
        raise VoiceReferenceError("参考音频为空，请重新上传")
    if len(audio_bytes) > MAX_REF_BYTES:
        raise VoiceReferenceError(f"参考音频超过大小限制（{MAX_REF_BYTES // (1024 * 1024)}MB）")
    if not agree_authorized:
        raise VoiceReferenceError("必须确认你拥有该声音的使用权或已获得声音本人授权")

    fmt = _detect_format(audio_bytes)
    if not fmt:
        raise VoiceReferenceError("参考音频格式不支持（仅 WAV/MP3/M4A/OGG/FLAC）")
    duration = _duration_of(audio_bytes)
    if duration is not None and duration > MAX_REF_SECONDS:
        raise VoiceReferenceError(f"参考音频过长（{duration:.0f}s），上限 {MAX_REF_SECONDS:.0f}s")
    if duration is not None and duration < MIN_REF_SECONDS:
        raise VoiceReferenceError(f"参考音频过短（{duration:.0f}s），建议至少 {MIN_REF_SECONDS:.0f}s（推荐 10~30s）")

    # 落本地临时文件 -> 规范化
    os.makedirs(LOCAL_REF_DIR, exist_ok=True)
    reference_id = f"ref_{uuid.uuid4().hex[:12]}"
    raw_path = os.path.join(LOCAL_REF_DIR, f"{reference_id}_raw")
    with open(raw_path, "wb") as f:
        f.write(audio_bytes)

    try:
        norm_path = await asyncio.to_thread(_normalize_to_wav, raw_path)
    except VoiceReferenceError:
        norm_path = raw_path  # 规范化失败（如缺 ffmpeg）退回原始字节
        logger.warning("参考音频规范化失败，使用原始文件")
    finally:
        try:
            os.unlink(raw_path)
        except OSError:
            pass

    ref = VoiceReference(
        reference_id=reference_id,
        user_id=user_id,
        duration=duration or 0.0,
        format=fmt,
        size_bytes=len(audio_bytes),
        status="ready",
        agree_authorized=agree_authorized,
        metadata={"local_path": norm_path},
    )

    # 持久化 R2（失败不阻断，Provider 直读本地）
    obj_key = await _upload_to_r2(norm_path, user_id, reference_id)
    ref.r2_object_key = obj_key

    _store.create(user_id, ref)
    logger.info("voice reference created: %s for user %s (%.1fs, %s)", reference_id, user_id, duration or 0, fmt)
    return ref


async def get_reference_path(reference_id: str, user_id: str) -> Optional[str]:
    """取回参考音频本地路径（仅限本人）。不存在/越权返回 None。"""
    ref = _store.get_user_ref(user_id, reference_id)
    if not ref:
        return None
    local = ref.metadata.get("local_path")
    if local and os.path.exists(local):
        return local
    return None


def get_reference(user_id: str, reference_id: str) -> Optional[VoiceReference]:
    """读取参考样本元数据（仅限本人）。"""
    return _store.get_user_ref(user_id, reference_id)


def list_references(user_id: str) -> list:
    """列出用户全部参考样本（不含本地路径，避免泄露）。"""
    out = []
    for ref in _store.list_user(user_id):
        out.append({
            "reference_id": ref.reference_id,
            "duration": round(ref.duration, 1),
            "format": ref.format,
            "status": ref.status,
            "created_at": ref.created_at,
            "agree_authorized": ref.agree_authorized,
            "prompt_language": ref.prompt_language,
            "detected_language": ref.detected_language,
        })
    return out


async def delete_reference(user_id: str, reference_id: str) -> bool:
    """删除参考样本（仅限本人）。同时删除本地文件与 R2 对象（尽力）。"""
    ref = _store.get_user_ref(user_id, reference_id)
    if not ref:
        return False
    local = ref.metadata.get("local_path")
    if local:
        try:
            os.unlink(local)
        except OSError:
            pass
    if ref.r2_object_key:
        try:
            from app.services.cdn_uploader import cdn_uploader
            await cdn_uploader.delete_object(ref.r2_object_key)
        except Exception as exc:
            logger.warning("删除 R2 参考音频失败: %s", exc)
    return _store.delete(user_id, reference_id)


def get_reference_presigned_url(user_id: str, reference_id: str, filename: str = "voice_reference.wav") -> Optional[str]:
    """返回参考音频短期 presigned 下载 URL（10 分钟）。仅限本人。"""
    ref = _store.get_user_ref(user_id, reference_id)
    if not ref or not ref.r2_object_key:
        return None
    try:
        from app.services.cdn_uploader import cdn_uploader
        result = cdn_uploader.generate_presigned_download(ref.r2_object_key, filename)
        return result.url if result else None
    except Exception as exc:
        logger.warning("生成参考音频 presigned URL 失败: %s", exc)
        return None