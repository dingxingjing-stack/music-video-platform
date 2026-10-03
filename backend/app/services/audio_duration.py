"""音频时长实测工具 — ffprobe 唯一出口（P1-D，2026-10-01）。

替代原 librosa.get_duration(path=...) 的「时长检测」职责：
- 生产镜像本就安装 ffmpeg（Dockerfile apt-get install ffmpeg），ffprobe 零新增依赖；
- 语义与原实现完全一致：**测不到 = 无法证明合规 = 不得交付**，异常一律向上抛，
  由调用方（ai_music._enforce_duration_gate / continuation_service）按既有
  DurationValidationError → failed + refund 路径处理；
- 只读取媒体容器元数据（stream/format duration），不解码音频，比 librosa 快
  数量级且无内存开销。

用法::

    from app.services.audio_duration import measure_duration, DurationMeasureError

    try:
        seconds = measure_duration("/path/to/song.mp3")
    except DurationMeasureError:
        ...  # 不得交付
"""

from __future__ import annotations

import shutil
import subprocess


class DurationMeasureError(RuntimeError):
    """ffprobe 无法测得时长（文件缺失/损坏/非音频/ffprobe 不可用）。

    刻意不在此模块内做任何业务决策：向上冒泡，由调用方统一走
    failed + refund 语义（测不到 = 不允许交付）。
    """


def _ffprobe_bin() -> str:
    """定位 ffprobe 可执行文件；不存在即抛 DurationMeasureError（不静默降级）。"""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise DurationMeasureError("ffprobe not found on PATH (ffmpeg/ffprobe required)")
    return ffprobe


def measure_duration(path: str) -> float:
    """实测音频文件时长（秒）。

    Args:
        path: 本地音频文件路径（WAV/MP3/FLAC 等 ffprobe 可读格式）。

    Returns:
        float 时长（秒，来自容器元数据，精度毫秒级）。

    Raises:
        DurationMeasureError: 文件不存在 / ffprobe 不可用 / 输出无法解析 /
        时长非法（≤0）。任何情况下绝不返回猜测值。
    """
    ffprobe = _ffprobe_bin()

    # -v error      静默常规日志，只留错误（stderr 非空即可疑）
    # -show_entries format=duration  容器总时长（覆盖所有流，与 librosa.get_duration 口径一致）
    # -of default=noprint_wrappers=1:nokey=1  只输出裸数值
    cmd = [
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, check=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise DurationMeasureError(f"ffprobe timed out measuring {path!r}") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip().splitlines()
        detail = stderr[-1] if stderr else f"exit code {exc.returncode}"
        raise DurationMeasureError(f"ffprobe failed for {path!r}: {detail}") from exc
    except OSError as exc:
        raise DurationMeasureError(f"ffprobe could not be executed: {exc}") from exc

    raw = (proc.stdout or "").strip()
    if not raw:
        raise DurationMeasureError(f"ffprobe returned no duration for {path!r}")
    try:
        measured = float(raw.splitlines()[-1].strip())
    except (ValueError, IndexError) as exc:
        raise DurationMeasureError(
            f"ffprobe output not a duration for {path!r}: {raw[:120]!r}"
        ) from exc
    if measured <= 0:
        raise DurationMeasureError(
            f"ffprobe reported non-positive duration {measured} for {path!r}"
        )
    return measured
