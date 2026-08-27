"""Modal GPT-SoVITS 客户端 — web 容器调用 avireon-music-platform-gptsovits 的 GPU 函数。

参考音频经共享数据卷（/root/data/refs/）传入，生成的克隆音频由 Modal 函数写入
共享数据卷（/root/data/generated/），web 容器经 download_generated() 取回本地后
再上传 R2（私有对象 + 预签名下载），Modal 内部路径与公开 URL 均不暴露给前端。

参考音频与生成结果分离保存（refs/ vs generated/），跨容器文件可见性依赖
Modal Volume 显式 commit() 时序（AGENTS.md 约定）。
"""

import asyncio
import logging
import os
import tempfile

from .ace_step_client import QueueFullError

logger = logging.getLogger(__name__)

_TTS_APP_NAME = "avireon-music-platform-gptsovits"
_DATA_VOLUME_NAME = "avireon-music-platform-data-v1"

# 卷内路径（与 gpt_sovits_modal.py 常量一致）
_REF_DIR = "/root/data/refs"
_GENERATED_DIR = "/root/data/generated"

# Modal Volume 写入后，文件对其他容器可见前需要 commit；读取 commit 快照。
_WRITE_COMMIT_WAIT = 5.0


def _tts_client():
    import modal
    return modal.Function.from_name(_TTS_APP_NAME, "synthesize_cloned")


def _upload_client():
    import modal
    return modal.Function.from_name(_TTS_APP_NAME, "upload_ref_audio")


def _data_volume():
    import modal
    return modal.Volume.from_name(_DATA_VOLUME_NAME)


def _local_generated_dir() -> str:
    """本地（容器内）生成目录，与 Modal 端 GENERATED_DIR 保持一致。"""
    return os.getenv("GENERATED_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "generated"))


def _write_bytes(path: str, data: bytes) -> None:
    with open(path, "wb") as fh:
        fh.write(data)


async def upload_ref_audio(voice_id: str, audio_bytes: bytes) -> str | None:
    """通过 Modal 函数在容器内写参考音频到共享卷，返回卷内 ref 文件名。

    失败返回 None（由业务层决定重试/降级）。
    """
    if not voice_id or not audio_bytes:
        return None
    try:
        import modal  # noqa: F401
    except ImportError:
        logger.warning("modal SDK 不可用（本地环境），无法上传参考音频")
        return None

    fname = f"{voice_id}.wav"
    try:
        fn = _upload_client()
        result = await asyncio.to_thread(fn.remote, audio_bytes, voice_id)
        if result:
            await asyncio.sleep(_WRITE_COMMIT_WAIT)
            logger.info("参考音频已写入共享卷 refs/%s", fname)
            return result
        return None
    except Exception as exc:  # noqa: BLE001 - 网络/卷错误统一降级
        logger.warning("上传参考音频到共享卷失败: %s", exc)
        return None


async def synthesize_cloned(
    audio_bytes: bytes,
    voice_id: str,
    text: str,
    language: str,
    prompt_text: str = "",
    prompt_language: str = "",
    speed: float = 1.0,
    out_stem: str = "",
) -> dict | None:
    """调用 Modal 克隆合成（合并上传+合成），返回共享卷 generated 目录文件名映射；失败返回 None。

    队列满抛 QueueFullError；其它失败返回 None（由业务层决定重试/降级）。
    prompt_text/prompt_language 为官方 api.py 参考音频转写必需参数，由调用方提供。
    """
    try:
        import modal  # noqa: F401
    except ImportError:
        logger.warning("modal SDK 不可用（本地环境），GPT-SoVITS 不可用")
        return None

    try:
        fn = _tts_client()
        result = await asyncio.to_thread(
            fn.remote,
            audio_bytes,
            voice_id,
            text,
            language,
            prompt_text or "",
            prompt_language or "",
            float(speed),
            out_stem or "",
        )
        if not result or not isinstance(result, dict) or not result.get("wav"):
            logger.warning("GPT-SoVITS 返回空结果")
            return None
        return result
    except QueueFullError:
        raise
    except Exception as exc:
        if "queue is full" in str(exc).lower() or "503" in str(exc):
            logger.warning("GPT-SoVITS 队列已满: %s", exc)
            raise QueueFullError("服务器繁忙，克隆队列已满，请稍后再试") from exc
        logger.warning("GPT-SoVITS 调用失败: %s", exc)
        return None


async def download_generated(filename: str, dest_dir: str | None = None) -> str | None:
    """把共享卷 generated/ 中的生成文件取回 web 容器本地临时目录，返回本地路径。

    三层取数（对齐 ace_step_client.download_file）：
      1. 本地挂载路径（同容器写）→ 直接返回
      2. Modal Volume API read_file（读已 commit 数据）
      3. 失败返回 None
    """
    fname = os.path.basename(filename)
    base = os.path.join(dest_dir or _local_generated_dir(), fname)

    for _ in range(3):
        if os.path.exists(base):
            return base
        await asyncio.sleep(1.0)

    out = os.path.join(tempfile.gettempdir(), fname)
    try:
        vol = _data_volume()
        data = b"".join(vol.read_file(f"{_GENERATED_DIR}/{fname}"))
        if data and len(data) > 1000:
            await asyncio.to_thread(_write_bytes, out, data)
            return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("download_generated Volume 读取失败: %s", exc)
    return None