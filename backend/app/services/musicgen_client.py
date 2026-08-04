"""
Modal MusicGen 客户端 — web 容器调用同一 App 的 GPU 函数生成音频。

GPU 函数 musicgen_generate 将生成的 wav 写入共享数据卷
(Modal 下 GENERATED_DIR=/root/data/generated)，web 容器通过
/generated/{filename} 静态挂载下载。零外部付费 API。
"""

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

_APP_NAME = "avireon-music-platform-musicgen"


class QueueFullError(Exception):
    """Modal GPU 请求队列已满（免费账号 503），需向业务层返回友好错误而非裸 503。"""
    pass


def local_dir() -> str:
    """本地（容器内）生成目录，与 GENERATED_DIR 保持一致。"""
    return os.getenv("GENERATED_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "generated"))


async def generate_music(prompt: str, duration: int = 30) -> str | None:
    """调用 MusicGen 生成音频，返回 /generated/{filename} URL。

    队列已满时抛 QueueFullError；其它失败返回 None。
    """
    try:
        import modal
    except ImportError:
        logger.warning("modal SDK 不可用（本地环境），MusicGen 不可用")
        return None

    try:
        fn = modal.Function.from_name(_APP_NAME, "musicgen_generate")
        filename = await asyncio.to_thread(fn.remote, prompt, int(duration))
        if not filename:
            logger.warning("MusicGen 返回空文件名")
            return None
        return f"/generated/{filename}"
    except QueueFullError:
        raise
    except Exception as exc:
        # Modal 免费账号队列满 → 503 "The request queue is full"
        if "queue is full" in str(exc).lower() or "503" in str(exc):
            logger.warning("MusicGen 队列已满: %s", exc)
            raise QueueFullError("服务器繁忙，生成队列已满，请稍后再试") from exc
        logger.warning("MusicGen 调用失败: %s", exc)
        return None


async def download_audio(audio_url: str, dest_dir: str | None = None) -> str | None:
    """把 /generated/ 下的音频下载到容器本地临时目录，供 FFmpeg 合成使用。

    三层取数：
    1. 本地挂载路径（同容器写）→ 直接返回
    2. Modal Volume API read_file（读已 commit 数据，不受 warm 容器旧快照影响）
    3. 公网 HTTP /generated/ 兜底
    """
    if not audio_url or not audio_url.startswith("/generated/"):
        return None
    fname = audio_url.rsplit("/", 1)[-1]
    base = dest_dir or os.path.join(local_dir(), fname)

    for _ in range(3):
        if os.path.exists(base):
            return base
        await asyncio.sleep(1.0)

    import tempfile
    out = os.path.join(tempfile.gettempdir(), fname)

    # Modal Volume API 读取已提交数据
    try:
        import modal
        vol = modal.Volume.from_name("avireon-music-platform-data-v1")
        data = b"".join(vol.read_file(f"/generated/{fname}"))
        if data and len(data) > 1000:
            with open(out, "wb") as fh:
                fh.write(data)
            return out
    except Exception as exc:
        logger.warning("download_audio Modal Volume 读取失败: %s", exc)

    # 公网 HTTP 兜底
    import httpx
    try:
        host = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000")
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.get(f"{host}{audio_url}")
        if resp.status_code == 200 and len(resp.content) > 1000:
            with open(out, "wb") as fh:
                fh.write(resp.content)
            return out
    except Exception as exc:
        logger.warning("download_audio HTTP 回退失败: %s", exc)
    return None
