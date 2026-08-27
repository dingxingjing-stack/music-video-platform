"""声音克隆编排器 — 将克隆人声与歌曲结构/歌词/时长对齐。

核心设计（与产品目标对齐）：
  - song_duration 与 reference_audio_duration 完全解耦：
       song_duration            = 最终歌曲时长（AI 或用户决定，<= 330s）
       reference_audio_duration = 用户上传声音样本实际长度（10~60s）
       vocal_output_duration    = 按歌曲结构分段生成的人声总时长（<= song_duration）
  - 分段生成：不把整首歌一次性送给 TTS。按 song_plan.sections 中非
    instrumental 的段落（verse/chorus/bridge 等）逐段调用 GPT-SoVITS，
    每段用该段歌词；instrumental 段落跳过。
  - 对齐：各人声段按 start_time 定位，混入音乐轨（mix_engine.mix_tracks 重叠混音）。
  - 失败语义：单段失败默认 fallback（跳过该段人声，不失败整首歌）；
    全部失败 / 队列满 / Provider 不可用 -> 返回失败由上层决定。

输入：
  - song_plan（含 sections/lyrics 分配）
  - reference_audio_path（用户上传、已校验归属）
  - 可选 voice_id / prompt_text（续写复用同一声音，避免重建）
"""

import asyncio
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from app.services.voice_clone_provider import (
    VoiceCloneRequest,
    VoiceCloneProvider,
    VoiceCloneQueueFullError,
    get_voice_clone_provider,
    VOCAL_SEGMENT_MAX_SECONDS,
)

logger = logging.getLogger(__name__)

# 人声轨混音音量（相对音乐轨）
VOCAL_MIX_VOLUME = float(os.getenv("VOCAL_MIX_VOLUME", "1.0"))
# 人声轨与音乐轨交叉淡化
VOCAL_CROSSFADE = float(os.getenv("VOCAL_CROSSFADE", "0.05"))
# 歌词分配：段落歌词为空时使用默认歌词兜底
DEFAULT_VOCAL_LYRICS = "la la la"


@dataclass
class VocalSegment:
    """一段克隆人声"""
    name: str
    section_type: str
    start_time: float
    duration: float
    text: str
    local_path: Optional[str] = None
    actual_duration: float = 0.0
    success: bool = False
    error: Optional[str] = None
    tts_seconds: float = 0.0


@dataclass
class VocalCloneResult:
    """克隆人声结果"""
    success: bool
    vocal_path: Optional[str] = None
    segments: List[VocalSegment] = field(default_factory=list)
    total_vocal_duration: float = 0.0
    error: Optional[str] = None
    tts_total_seconds: float = 0.0
    cost_estimate_usd: float = 0.0
    skipped_segments: int = 0
    voice_id: str = ""


async def _get_duration(path: str) -> float:
    """获取音频时长（ffprobe）。"""
    try:
        proc = await asyncio.to_thread(
            lambda: subprocess_run_ffprobe(path)
        )
        return proc
    except Exception:
        return 0.0


def subprocess_run_ffprobe(path: str) -> float:
    import subprocess
    from app.services.audio_trim import FFPROBE_PATH
    cmd = [FFPROBE_PATH, "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode == 0 and result.stdout.strip():
        return float(result.stdout.strip())
    return 0.0


class VoiceCloneOrchestrator:
    """按歌曲结构编排克隆人声分段生成与混音。"""

    def __init__(self):
        self._provider: Optional[VoiceCloneProvider] = None
        self._mix_engine = None

    def _get_provider(self) -> VoiceCloneProvider:
        if self._provider is None:
            self._provider = get_voice_clone_provider()
        return self._provider

    async def _get_mix_engine(self):
        if self._mix_engine is None:
            from app.services.mix_engine import get_mix_engine
            self._mix_engine = get_mix_engine()
        return self._mix_engine

    def _build_vocal_sections(self, song_plan) -> List[Dict[str, Any]]:
        """从 SongPlan 提取需要人声的段落（非 instrumental），组装歌词与时长。

        时长对齐 song_duration：section.duration 决定该段目标时长；
        若单段超过 VOCAL_SEGMENT_MAX_SECONDS 拆分为子段（每子段 <= 上限）。
        """
        from app.services.song_planner import SongSectionType
        vocal_sections = []
        for section in song_plan.sections:
            vtype = getattr(section, "vocal_type", "auto")
            if vtype == "instrumental":
                continue
            sec_type = section.type.value if hasattr(section.type, "value") else str(section.type)
            # 纯器乐段落跳过
            if sec_type in ("intro", "outro", "build_up", "breakdown", "solo", "dub_section", "guitar_solo"):
                continue
            lyrics = (section.lyrics or "").strip()
            if not lyrics:
                lyrics = DEFAULT_VOCAL_LYRICS
            dur = int(section.duration) if section.duration > 0 else 30
            vocal_sections.append({
                "name": section.name,
                "section_type": sec_type,
                "start_time": float(getattr(section, "start_time", 0) or 0),
                "duration": dur,
                "text": lyrics,
            })
        return vocal_sections

    async def generate_vocals(
        self,
        song_plan,
        reference_audio_path: str,
        voice_id: str = "",
        prompt_text: Optional[str] = None,
        prompt_language: Optional[str] = None,
        language: str = "zh",
        speed: float = 1.0,
        progress_callback=None,
    ) -> VocalCloneResult:
        """生成整首歌的分段克隆人声。

        - 单段失败：默认 fallback（跳过该段，记录 error），不中断整首歌。
        - 队列满：抛 VoiceCloneQueueFullError（由上层决定重试/失败）。
        - 全部失败 / 无可用段落：success=False。
        """
        provider = self._get_provider()

        # 校验参考音频（Provider 层）
        check = await provider.validate_reference(reference_audio_path)
        if not check["valid"]:
            return VocalCloneResult(success=False, error=check["error"])

        sections = self._build_vocal_sections(song_plan)
        if not sections:
            return VocalCloneResult(success=False, error="歌曲结构中无可用人声段落")

        segments: List[VocalSegment] = []
        total_tts = 0.0
        total_cost = 0.0
        skipped = 0

        for idx, sec in enumerate(sections):
            # 拆分子段（时长 > VOCAL_SEGMENT_MAX_SECONDS 时按比例拆）
            sub_durations = self._split_duration(sec["duration"], VOCAL_SEGMENT_MAX_SECONDS)
            sub_start = sec["start_time"]
            for sub_idx, sub_dur in enumerate(sub_durations):
                seg_name = f"{sec['name']}_{sub_idx}" if len(sub_durations) > 1 else sec["name"]
                seg = VocalSegment(
                    name=seg_name,
                    section_type=sec["section_type"],
                    start_time=sub_start,
                    duration=sub_dur,
                    text=sec["text"],
                )
                if progress_callback:
                    await progress_callback("voice_cloning", {
                        "segment": seg_name,
                        "index": idx + 1,
                        "total": len(sections),
                    })

                try:
                    req = VoiceCloneRequest(
                        reference_audio_path=reference_audio_path,
                        text=sec["text"],
                        language=language,
                        duration=sub_dur,
                        voice_id=voice_id,
                        prompt_text=prompt_text,
                        prompt_language=prompt_language,
                        speed=speed,
                        out_stem=f"vocal_{voice_id or 'x'}",
                    )
                    result = await provider.clone_voice(req)
                except VoiceCloneQueueFullError as exc:
                    raise
                except Exception as exc:
                    result = None
                    logger.warning("声音克隆异常: %s", exc)

                if result and result.success and result.local_path:
                    actual_dur = await _get_duration(result.local_path)
                    if actual_dur <= 0:
                        actual_dur = sub_dur
                    seg.local_path = result.local_path
                    seg.actual_duration = actual_dur
                    seg.success = True
                    seg.tts_seconds = result.tts_seconds
                    total_tts += result.tts_seconds
                    total_cost += result.cost_estimate_usd
                else:
                    err = (result.error if result else "声音克隆异常")
                    seg.error = err
                    seg.success = False
                    skipped += 1
                    logger.warning("人声段 %s 失败（跳过）: %s", seg_name, err)

                segments.append(seg)
                sub_start += sub_dur

        successful = [s for s in segments if s.success]
        if not successful:
            return VocalCloneResult(
                success=False,
                segments=segments,
                error="所有人声分段生成失败",
                tts_total_seconds=total_tts,
                cost_estimate_usd=total_cost,
                skipped_segments=skipped,
                voice_id=voice_id,
            )

        total_vocal_duration = sum(s.actual_duration for s in successful)
        return VocalCloneResult(
            success=True,
            segments=segments,
            total_vocal_duration=total_vocal_duration,
            tts_total_seconds=total_tts,
            cost_estimate_usd=total_cost,
            skipped_segments=skipped,
            voice_id=voice_id,
        )

    @staticmethod
    def _split_duration(duration: int, max_seg: int) -> List[int]:
        """把段落时长拆分为不超过 max_seg 的子段（>=1 段）。"""
        if duration <= max_seg:
            return [max(1, int(duration))]
        n = (duration + max_seg - 1) // max_seg
        base = duration // n
        out = [base] * n
        for i in range(duration - base * n):
            out[i] += 1
        return [max(1, x) for x in out]

    async def generate_vocals_from_sections(
        self,
        sections: List[Dict[str, Any]],
        reference_audio_path: str,
        voice_id: str = "",
        prompt_text: Optional[str] = None,
        prompt_language: Optional[str] = None,
        language: str = "zh",
        speed: float = 1.0,
        progress_callback=None,
    ) -> VocalCloneResult:
        """从简单段落列表生成人声（不需要 SongPlan）。

        sections: 列表，每项含 {name, text, duration, start_time}
        """
        provider = self._get_provider()

        check = await provider.validate_reference(reference_audio_path)
        if not check["valid"]:
            return VocalCloneResult(success=False, error=check["error"])

        if not sections:
            return VocalCloneResult(success=False, error="无可用人声段落")

        segments: List[VocalSegment] = []
        total_tts = 0.0
        total_cost = 0.0
        skipped = 0

        for idx, sec in enumerate(sections):
            sub_durations = self._split_duration(sec["duration"], VOCAL_SEGMENT_MAX_SECONDS)
            sub_start = sec["start_time"]
            for sub_idx, sub_dur in enumerate(sub_durations):
                seg_name = f"{sec['name']}_{sub_idx}" if len(sub_durations) > 1 else sec["name"]
                seg = VocalSegment(
                    name=seg_name,
                    section_type=sec.get("section_type", "vocal"),
                    start_time=sub_start,
                    duration=sub_dur,
                    text=sec["text"],
                )
                if progress_callback:
                    await progress_callback("voice_cloning", {
                        "segment": seg_name,
                        "index": idx + 1,
                        "total": len(sections),
                    })

                try:
                    req = VoiceCloneRequest(
                        reference_audio_path=reference_audio_path,
                        text=sec["text"],
                        language=language,
                        duration=sub_dur,
                        voice_id=voice_id,
                        prompt_text=prompt_text,
                        prompt_language=prompt_language,
                        speed=speed,
                        out_stem=f"vocal_{voice_id or 'x'}",
                    )
                    result = await provider.clone_voice(req)
                except VoiceCloneQueueFullError as exc:
                    raise
                except Exception as exc:
                    result = None
                    logger.warning("声音克隆异常: %s", exc)

                if result and result.success and result.local_path:
                    actual_dur = await _get_duration(result.local_path)
                    if actual_dur <= 0:
                        actual_dur = sub_dur
                    seg.local_path = result.local_path
                    seg.actual_duration = actual_dur
                    seg.success = True
                    seg.tts_seconds = result.tts_seconds
                    total_tts += result.tts_seconds
                    total_cost += result.cost_estimate_usd
                else:
                    err = (result.error if result else "声音克隆异常")
                    seg.error = err
                    seg.success = False
                    skipped += 1
                    logger.warning("人声段 %s 失败（跳过）: %s", seg_name, err)

                segments.append(seg)
                sub_start += sub_dur

        successful = [s for s in segments if s.success]
        if not successful:
            return VocalCloneResult(
                success=False,
                segments=segments,
                error="所有人声分段生成失败",
                tts_total_seconds=total_tts,
                cost_estimate_usd=total_cost,
                skipped_segments=skipped,
                voice_id=voice_id,
            )

        total_vocal_duration = sum(s.actual_duration for s in successful)
        return VocalCloneResult(
            success=True,
            segments=segments,
            total_vocal_duration=total_vocal_duration,
            tts_total_seconds=total_tts,
            cost_estimate_usd=total_cost,
            skipped_segments=skipped,
            voice_id=voice_id,
        )

    async def mix_vocal_with_music(
        self,
        music_path: str,
        vocal_result: VocalCloneResult,
        output_path: str,
        song_duration: float,
    ) -> Dict[str, Any]:
        """把克隆人声轨与音乐轨混音。

        - 各人声段按 start_time 作为 MixTrack 重叠叠加到音乐轨上。
        - 混音后响度标准化（mix_engine 默认 target_lufs=-14）。
        返回 {"success", "output_path", "duration", "tracks_used", "error"}。
        """
        mix_engine = await self._get_mix_engine()
        from app.services.mix_engine import MixTrack

        tracks = [MixTrack(path=music_path, volume=1.0, label="music")]
        for seg in vocal_result.segments:
            if not seg.success or not seg.local_path:
                continue
            tracks.append(MixTrack(
                path=seg.local_path,
                volume=VOCAL_MIX_VOLUME,
                start_time=seg.start_time,
                fade_in=VOCAL_CROSSFADE,
                fade_out=VOCAL_CROSSFADE,
                label=seg.name,
            ))

        result = await mix_engine.mix_tracks(
            tracks,
            output_path,
            master_volume=1.0,
            master_limiter=True,
            target_lufs=-14.0,
            crossfade_mode="overlap",
        )
        return {
            "success": result.success,
            "output_path": result.output_path,
            "duration": result.duration,
            "tracks_used": result.tracks_used,
            "error": result.error,
        }


# 全局实例
_voice_clone_orchestrator: Optional[VoiceCloneOrchestrator] = None


def get_voice_clone_orchestrator() -> VoiceCloneOrchestrator:
    global _voice_clone_orchestrator
    if _voice_clone_orchestrator is None:
        _voice_clone_orchestrator = VoiceCloneOrchestrator()
    return _voice_clone_orchestrator