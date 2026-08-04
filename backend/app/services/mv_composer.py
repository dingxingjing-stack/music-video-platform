"""
MV 简易合成器 — 零成本 FFmpeg 图片拼接视频。

用 Pillow 生成多张渐变封面图，再用 FFmpeg 把图片按时间轴拼接成视频，
最后混入音频（MusicGen 生成的 wav）。全程本地 FFmpeg，无外部付费 API。
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

# 图片宽高
MV_WIDTH = 1280
MV_HEIGHT = 720


def _local_generated_dir() -> str:
    """本地生成目录，与 musicgen_client.local_dir 保持一致。"""
    return os.getenv(
        "GENERATED_DIR",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "generated"),
    )


async def _probe_duration(audio_path: str) -> float:
    """用 ffprobe 获取音频时长（秒），失败返回默认值。"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", audio_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        return float(out.decode().strip())
    except Exception:
        return 30.0


async def _run_ffmpeg(args, timeout: int = 300) -> bool:
    """执行 FFmpeg 命令，返回是否成功。"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode != 0:
            logger.error("FFmpeg 失败: %s", stderr.decode(errors="ignore")[-500:])
            return False
        return True
    except Exception as exc:
        logger.error("FFmpeg 异常: %s", exc)
        return False


def _safe_filename(text: str) -> str:
    import re
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", text or "")
    return s.strip("_") or "mv"


async def compose_slideshow_video(
    audio_path: str,
    title: str = "AI Music",
    lyric_lines: Optional[list] = None,
    out_dir: Optional[str] = None,
) -> str:
    """
    图片拼接视频：生成 N 张渐变图 → FFmpeg 拼接 → 混入音频 → 返回 /generated/ 下的文件名。

    Returns:
        生成的文件名（如 mv-xxxx.mp4），调用方拼 /generated/{filename}
    """
    out_dir = out_dir or _local_generated_dir()
    os.makedirs(out_dir, exist_ok=True)

    lyric_lines = lyric_lines or [title, "AI Music Video"]
    # 用图片帧数 = 歌词行数（至少 2，最多 6）
    scenes = max(2, min(len(lyric_lines), 6))

    duration = await _probe_duration(audio_path)
    scene_dur = max(2.0, duration / scenes)

    # 1. 用 Pillow 生成渐变封面图（无外部图片资源，零成本）
    try:
        from PIL import Image, ImageDraw, ImageFont
        HAVE_PIL = True
    except ImportError:
        HAVE_PIL = False

    img_paths = []
    tmp_dir = os.path.join(out_dir, "tmp_" + uuid.uuid4().hex[:8])
    os.makedirs(tmp_dir, exist_ok=True)

    try:
        colors = ["#1a1a2e", "#16213e", "#0f3460", "#533483", "#e94560", "#16213e"]
        for i, line in enumerate(lyric_lines[:scenes]):
            img_path = os.path.join(tmp_dir, f"scene_{i:02d}.png")
            if HAVE_PIL:
                color = colors[i % len(colors)]
                img = Image.new("RGB", (MV_WIDTH, MV_HEIGHT), color)
                draw = ImageDraw.Draw(img)
                font = None
                for fp in [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                ]:
                    if os.path.exists(fp):
                        try:
                            font = ImageFont.truetype(fp, 56)
                            break
                        except Exception:
                            continue
                if font is None:
                    font = ImageFont.load_default()
                draw.text(
                    (MV_WIDTH // 2, MV_HEIGHT // 2),
                    line[:80],
                    font=font,
                    fill="white",
                    anchor="mm",
                )
                img.save(img_path)
            else:
                # 无 Pillow 兜底：纯色 PNG（FFmpeg color 源）
                await _run_ffmpeg(
                    ["-f", "lavfi", "-i", f"color=c={colors[i % len(colors)]}:s={MV_WIDTH}x{MV_HEIGHT}:d=1",
                     "-frames:v", "1", img_path],
                    timeout=30,
                )
            img_paths.append(img_path)

        if not img_paths:
            return ""

        # 2. 每张图生成 scene_dur 秒片段
        seg_paths = []
        for i, img_path in enumerate(img_paths):
            seg_path = os.path.join(tmp_dir, f"seg_{i:02d}.mp4")
            ok = await _run_ffmpeg([
                "-loop", "1", "-i", img_path,
                "-t", f"{scene_dur:.2f}",
                "-c:v", "libx264", "-tune", "stillimage",
                "-pix_fmt", "yuv420p", "-r", "24",
                seg_path,
            ], timeout=120)
            if ok:
                seg_paths.append(seg_path)

        if not seg_paths:
            return ""

        # 3. concat 拼接
        list_file = os.path.join(tmp_dir, "concat_list.txt")
        with open(list_file, "w") as f:
            for p in seg_paths:
                f.write(f"file '{os.path.abspath(p)}'\n")

        concat_path = os.path.join(tmp_dir, "concat.mp4")
        ok = await _run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", list_file,
            "-c", "copy", concat_path,
        ], timeout=120)
        if not ok:
            return ""

        # 4. 混入音频
        fname = f"mv-{uuid.uuid4().hex[:10]}.mp4"
        final_path = os.path.join(out_dir, fname)
        ok = await _run_ffmpeg([
            "-i", concat_path, "-i", audio_path,
            "-c:v", "copy", "-c:a", "aac", "-shortest",
            final_path,
        ], timeout=180)
        if not ok or not os.path.exists(final_path) or os.path.getsize(final_path) == 0:
            return ""

        logger.info("[MV] 合成成功 %s (%.1fs)", final_path, duration)
        return fname

    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
