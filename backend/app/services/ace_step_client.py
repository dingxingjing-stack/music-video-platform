"""Modal ACE-Step 客户端 — web 容器调用 avireon-music-platform-acestep 的 GPU 函数。

生成的音频由 Modal 函数写入共享数据卷（/root/data/generated/），web 容器经
download_file() 取回本地临时目录后再上传 R2（私有对象 + 预签名下载），
Modal 内部路径与公开 URL 均不暴露给前端。
"""

import asyncio
import logging
import os
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

_APP_NAME = "avireon-music-platform-acestep"
_SPLEETER_APP_NAME = "avireon-music-platform-spleeter"


class QueueFullError(Exception):
    """Modal GPU 请求队列已满（免费账号 503），需向业务层返回友好错误而非裸 503。"""
    pass


def _client() -> "modal.Function":
    import modal
    return modal.Function.from_name(_APP_NAME, "generate_full_song")


def _separate_client() -> "modal.Function":
    import modal
    return modal.Function.from_name(_SPLEETER_APP_NAME, "separate_audio")


async def generate_full_song(
    prompt: str,
    lyrics: str,
    duration: int = 180,
    reference_audio_b64: Optional[str] = None,
    enable_audio2audio: bool = False,
    reference_strength: float = 0.7,
) -> dict | None:
    """调用 Modal 生成完整歌曲 + 分轨，返回共享卷中的文件名映射；失败返回 None。

    Step 4: ENVIRONMENT=production 时直接返回 None（Modal 已下线，生产走 Fal），
    不尝试 import modal，避免 Koyeb 无凭据启动失败。
    队列满抛 QueueFullError；其它失败返回 None（由业务层决定重试/降级）。
    
    新增 Audio2Audio 支持：
    - enable_audio2audio: 是否启用 Audio2Audio 续写模式
    - reference_audio_b64: base64 编码的参考音频
    - reference_strength: 参考音频强度 (0.0-1.0)
    """
    if os.getenv("ENVIRONMENT", "development").lower() == "production":
        logger.info("ACE-Step Modal 已在生产下线（ENVIRONMENT=production），跳过")
        return None
    try:
        import modal  # noqa: F401
    except ImportError:
        logger.warning("modal SDK 不可用（本地环境），ACE-Step 不可用")
        return None

    try:
        fn = _client()
        result = await asyncio.to_thread(
            fn.remote,
            prompt,
            lyrics or "",
            int(duration),
            reference_audio_b64,
            enable_audio2audio,
            reference_strength,
        )
        if not result or not isinstance(result, dict):
            logger.warning("ACE-Step 返回空结果")
            return None
        return result
    except QueueFullError:
        raise
    except Exception as exc:
        if "queue is full" in str(exc).lower() or "503" in str(exc):
            logger.warning("ACE-Step 队列已满: %s", exc)
            raise QueueFullError("服务器繁忙，生成队列已满，请稍后再试") from exc
        logger.warning("ACE-Step 调用失败: %s", exc)
        return None


async def separate_only(filename_in_volume: str) -> dict | None:
    """分轨失败重试：对共享卷中的完整 WAV 单独执行四轨分离（独立 Spleeter App）。返回 stems 文件名映射。"""
    if os.getenv("ENVIRONMENT", "development").lower() == "production":
        logger.info("Spleeter Modal 已在生产下线，separate_only 跳过")
        return None
    try:
        import modal  # noqa: F401
    except ImportError:
        logger.warning("modal SDK 不可用，无法重试分轨")
        return None
    try:
        fn = _separate_client()
        result = await asyncio.to_thread(fn.remote, filename_in_volume)
        if not result or not isinstance(result, dict):
            return None
        return result
    except Exception as exc:
        logger.warning("Spleeter 分轨重试失败: %s", exc)
        return None


async def download_file(filename: str, dest_dir: str | None = None) -> str | None:
    """把共享卷中的文件取回 web 容器本地临时目录，返回本地路径。

    三层取数：
      1. 本地挂载路径（同容器写）→ 直接返回
      2. Modal Volume API read_file（读已 commit 数据）
      3. 失败返回 None
    """
    fname = os.path.basename(filename)
    base = os.path.join(dest_dir or local_dir(), fname)

    for _ in range(3):
        if os.path.exists(base):
            return base
        await asyncio.sleep(1.0)

    out = os.path.join(tempfile.gettempdir(), fname)
    try:
        import modal
        vol = modal.Volume.from_name("avireon-music-platform-data-v1")
        data = b"".join(vol.read_file(f"/generated/{fname}"))
        if data and len(data) > 1000:
            with open(out, "wb") as fh:
                fh.write(data)
            return out
    except Exception as exc:
        logger.warning("download_file Volume 读取失败: %s", exc)
    return None


def local_dir() -> str:
    """本地（容器内）生成目录，与 Modal 端 GENERATED_DIR 保持一致。"""
    return os.getenv("GENERATED_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "generated"))