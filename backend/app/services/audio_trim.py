"""
Audio Trimming Service

Uses ffmpeg to slice audio files by start/end time.
Supports both local files and HTTP URLs.

Usage:
    result = await trim_audio(url, start=3.0, end=15.0)
    # Returns: bytes (audio data) + content_type
"""

from __future__ import annotations

import asyncio
import io
import ipaddress
import logging
import os
import socket
import subprocess
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ── P0-2：媒体源白名单（SSRF / 任意本地文件读取防护）────────────────────────
# 只允许 https + 显式主机后缀；拒绝本地路径、file://、IP 字面量、非 443 端口、
# 以及解析到内网/回环/link-local（云 metadata）的主机。
_TRIM_ALLOWED_HOST_SUFFIXES = (
    ".r2.cloudflarestorage.com",
    ".r2.dev",
    "zyvexo-cdn.dingxingjing.workers.dev",
    "music-video-platform.zezhending90.workers.dev",
    "music-video-platform.pages.dev",
)


def _trim_allowed_suffixes() -> tuple[str, ...]:
    extra = tuple(
        h.strip().lower() for h in (os.getenv("AUDIO_TRIM_EXTRA_HOSTS") or "").split(",") if h.strip()
    )
    # 只从 CDN 基址派生可信媒体主机；不派生 API/FRONTEND 域（避免把 localhost 带进白名单）
    derived: list[str] = []
    host = urlparse(os.getenv("CDN_BASE_URL") or "").hostname
    if host:
        derived.append(host.lower())
    return _TRIM_ALLOWED_HOST_SUFFIXES + tuple(derived) + extra


def _is_blocked_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # 解析不出来就拒绝
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        or (ip.version == 4 and ip in ipaddress.ip_network("169.254.169.254/32"))
    )


def resolve_safe_media_source(source: str) -> str:
    """校验并返回可安全交给 ffmpeg 的媒体地址；不合法一律抛 ValueError。"""
    raw = (source or "").strip()
    if not raw:
        raise ValueError("媒体地址为空")
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.hostname:
        # 明确禁止：本地文件路径、file://、http://、gopher:// 等
        raise ValueError("仅允许 https 媒体地址")
    host = parsed.hostname.lower().rstrip(".")
    if host.replace(".", "").isdigit():
        raise ValueError("不允许使用 IP 字面量")
    if parsed.port not in (None, 443):
        raise ValueError("仅允许默认 443 端口")
    allowed = _trim_allowed_suffixes()
    if not any(host == a.lstrip(".") or host.endswith(a) for a in allowed if a):
        raise ValueError("媒体主机不在允许清单内")
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise ValueError(f"媒体主机解析失败：{exc}") from exc
    for info in infos:
        if _is_blocked_ip(str(info[4][0])):
            raise ValueError("媒体主机指向内网地址")
    return parsed.geturl()


async def trim_audio(
    url: str,
    start: float,
    end: float,
    output_format: str = "wav",
) -> tuple[bytes, str]:
    """
    Trim audio from url between start and end seconds.

    Args:
        url: Local file path or HTTP URL.
        start: Start time in seconds.
        end: End time in seconds.
        output_format: Output format (wav, mp3, etc.).

    Returns:
        Tuple of (audio_bytes, content_type).

    Raises:
        RuntimeError: If ffmpeg is not available or trimming fails.
    """
    duration = end - start
    if duration <= 0:
        raise ValueError(f"Invalid trim range: start={start}, end={end}")

    # P0-2：在服务层再校验一次，保证任何调用方（不只是 HTTP 端点）都不能喂本地路径/内网地址
    safe_url = resolve_safe_media_source(url)

    # Build ffmpeg command
    cmd = [
        "ffmpeg",
        "-y",                    # overwrite output
        "-ss", str(start),       # seek to start (accurate)
        "-i", safe_url,          # input（已通过 https + 主机白名单 + 非内网校验）
        "-t", str(duration),     # duration
        "-c:a", "copy" if output_format == "wav" else "aac",  # codec
        "-f", output_format,     # force format
        "-",                     # output to stdout
    ]

    logger.info("Trimming audio: %s [%.1fs-%.1fs]", url, start, end)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace")[:500]
            logger.error("ffmpeg error: %s", error_msg)
            raise RuntimeError(f"ffmpeg failed: {error_msg}")

        if not stdout:
            raise RuntimeError("Empty output from ffmpeg")

        content_type = "audio/wav" if output_format == "wav" else f"audio/{output_format}"
        return stdout, content_type

    except FileNotFoundError:
        raise RuntimeError(
            "ffmpeg is not installed. Install it with: pip install ffmpeg-python "
            "or download from https://ffmpeg.org/download.html"
        )


def is_ffmpeg_available() -> bool:
    """Check if ffmpeg is available on the system."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
