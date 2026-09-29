"""
AI 续写核心服务
- 接续现有歌曲生成新片段
- 支持多种续写模式
- 集成分段生成、节拍对齐、混音拼接
- 失败恢复与重试
"""

import os
import base64
import math
import time
import logging
import asyncio
import uuid
import tempfile
import shutil
from dataclasses import asdict, dataclass, field
from typing import Optional, Dict, Any, List, Callable, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)
from app.services.ai_limits import MAX_AUTO_RETRIES, MIN_AUDIO_DURATION_SECONDS
from app.services import task_store


# ========== 配置 ==========
MAX_SONG_DURATION = int(os.getenv("MAX_SONG_DURATION", "330"))
MAX_CONTINUATION_DURATION = int(os.getenv("MAX_CONTINUATION_DURATION", "120"))
REFERENCE_SEGMENT_DURATION = int(os.getenv("REFERENCE_SEGMENT_DURATION", "30"))  # 参考片段时长(秒)
DEFAULT_SEGMENT_DURATION = 150
CROSSFADE_DURATION = 1.5


class DurationValidationError(RuntimeError):
    """P6-B-C2 D1/D3：成品实测时长不足最低要求（或无法实测）时抛出的失败类型。

    刻意不在本模块内退款：它只是向上冒泡，由 ai_music._run_generation 的既有
    except Exception 统一走 failed + refund（避免第二套退款语义）。
    """


def _part_keys_of(task_id: str, manifest: Any) -> List[str]:
    """从 _upload_parts 返回的 manifest 中提取本任务的 part R2 key（白名单前缀）。

    只接受 music/{task_id}_part 前缀的值：parts 由 upload_music_package 上传，
    manifest 值即真实 key；绝不接受 full_wav/full_mp3 等最终对象。
    """
    if not isinstance(manifest, dict):
        return []
    prefix = f"music/{task_id}_part"
    return [v for v in manifest.values() if isinstance(v, str) and v.startswith(prefix)]


def cleanup_continuation_artifacts(
    task_id: str,
    part_keys: Optional[List[str]] = None,
    local_paths: Optional[List[Optional[str]]] = None,
) -> None:
    """C3-5-B best-effort 清理：continuation 中间分片（R2）+ 本地临时文件。

    契约：
    - 永不抛出任何异常（含每个 key/路径粒度的捕获）：清理失败绝不覆盖
      原始 generation 结果，也不改变 timeout/cancel 语义。
    - 只删除带 music/{task_id}_part 前缀的 R2 key —— 最终 full_wav/full_mp3
      与用户下载对象绝不会进入删除列表。
    - 幂等：对象不存在（NoSuchKey/404）由 cdn_uploader.delete_object 视为成功；
      本地路径不存在则跳过，可安全重复执行。
    同步实现（无 await 点）：在任务被取消（超时）时也能确定性跑完，不吞
    CancelledError，不影响 _run_with_timeout 的既有超时退款语义。
    """
    for key in part_keys or []:
        try:
            if isinstance(key, str) and key.startswith(f"music/{task_id}_part"):
                from app.services.cdn_uploader import cdn_uploader
                cdn_uploader.delete_object(key)
        except Exception as e:  # noqa: BLE001
            print(f"[C3-5-B] part 清理失败(忽略): {key}: {type(e).__name__}: {e}")
    for path in local_paths or []:
        try:
            if path and isinstance(path, str) and os.path.isfile(path):
                os.remove(path)
        except Exception as e:  # noqa: BLE001
            print(f"[C3-5-B] 本地临时清理失败(忽略): {path}: {type(e).__name__}: {e}")


@dataclass
class ContinuationRequest:
    """续写请求"""
    task_id: str
    user_id: str
    source_audio_url: str           # 原歌曲 URL
    source_audio_path: Optional[str] = None  # 本地路径（可选）
    source_duration: float = 0.0    # 原歌曲时长
    mode: str = "auto"              # auto, keep_style, new_style, variation, bridge, outro_extend
    style: Optional[str] = None     # 新风格（mode=new_style 时）
    duration: Optional[int] = None  # 续写时长（秒），None 则 AI 自动
    prompt: str = ""                # 额外提示词
    lyrics: str = ""                # 续写歌词
    reference_audio_url: Optional[str] = None  # 指定参考音频（默认用源歌曲）


@dataclass
class ContinuationResult:
    """续写结果"""
    success: bool
    task_id: str
    output_audio_url: Optional[str] = None
    output_audio_path: Optional[str] = None
    continuation_duration: float = 0.0
    total_duration: float = 0.0
    segments: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SongContext:
    song_id: str = ""
    task_id: str = ""
    user_key: str = ""
    target_duration: int = 300
    current_duration: float = 0.0
    bpm: Optional[float] = None
    key: Optional[str] = None
    genre: Optional[str] = None
    style: Optional[str] = None
    vocal_style: Optional[str] = None
    lyrics: Optional[str] = None
    segment_history: List[Dict] = None
    def __post_init__(self):
        if self.segment_history is None:
            self.segment_history = []
    def to_dict(self) -> Dict:
        return asdict(self)
    @classmethod
    def from_dict(cls, data: Dict) -> "SongContext":
        return cls(**data)

class ContinuationService:
    """AI 续写服务"""

    def __init__(self):
        self._ace_client = None
        self._analyzer = None
        self._segment_planner = None
        self._mix_engine = None
        self._cdn_uploader = None
        self._task_store = None
        self.temp_dir = tempfile.gettempdir()

    async def _get_ace_client(self):
        if self._ace_client is None:
            from app.services.ace_step_client import get_ace_step_client
            self._ace_client = get_ace_step_client()
        return self._ace_client

    async def _get_analyzer(self):
        if self._analyzer is None:
            from app.services.continuation_analysis import get_continuation_analyzer
            self._analyzer = get_continuation_analyzer()
        return self._analyzer

    async def _get_segment_planner(self):
        if self._segment_planner is None:
            from app.services.segment_planner import get_segment_planner
            self._segment_planner = get_segment_planner()
        return self._segment_planner

    async def _get_mix_engine(self):
        if self._mix_engine is None:
            from app.services.mix_engine import get_mix_engine
            self._mix_engine = get_mix_engine()
        return self._mix_engine

    async def _get_audio_trimmer(self):
        from app.services.audio_trim import get_audio_trimmer
        return get_audio_trimmer()

    async def _get_beat_detector(self):
        from app.services.beat_detector import get_beat_detector
        return get_beat_detector()

    async def _get_cdn_uploader(self):
        if self._cdn_uploader is None:
            from app.services.cdn_uploader import cdn_uploader
            self._cdn_uploader = cdn_uploader
        return self._cdn_uploader

    async def _get_task_store(self):
        if self._task_store is None:
            from app.services.task_store import get_task_store
            self._task_store = await get_task_store()
        return self._task_store

    async def continue_song(
        self,
        request: ContinuationRequest,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    ) -> ContinuationResult:
        """
        执行歌曲续写

        Args:
            request: 续写请求
            progress_callback: 进度回调 (stage, metadata)

        Returns:
            ContinuationResult
        """
        task_store = await self._get_task_store()

        try:
            # 1. 验证请求
            analyzer = await self._get_analyzer()
            valid, error, max_allowed = await analyzer.validate_continuation_request(
                request.source_duration, request.duration or 60
            )
            if not valid:
                return ContinuationResult(
                    success=False,
                    task_id=request.task_id,
                    error=error,
                )

            # 更新任务状态
            await task_store.update_task_status(request.task_id, "processing", "analyzing")
            if progress_callback:
                await progress_callback("analyzing", {"message": "分析原歌曲结构..."})

            # 2. 分析原歌曲
            analysis = await analyzer.analyze_song(
                request.source_audio_url,
                request.source_audio_path
            )

            # 3. 创建续写计划
            from app.services.continuation_analysis import ContinuationMode
            mode_map = {
                "auto": ContinuationMode.AUTO,
                "keep_style": ContinuationMode.KEEP_STYLE,
                "new_style": ContinuationMode.NEW_STYLE,
                "variation": ContinuationMode.VARIATION,
                "bridge": ContinuationMode.BRIDGE,
                "outro_extend": ContinuationMode.OUTRO_EXTEND,
            }
            mode = mode_map.get(request.mode, ContinuationMode.AUTO)

            plan = await analyzer.create_continuation_plan(
                analysis=analysis,
                mode=mode,
                user_duration=request.duration,
                user_style=request.style,
                user_prompt=request.prompt,
                user_lyrics=request.lyrics,
            )

            # 更新任务进度
            await task_store.update_task_status(request.task_id, "processing", "planning")
            if progress_callback:
                await progress_callback("planning", {
                    "message": f"规划续写: {plan.duration}秒, 风格: {plan.style}",
                    "plan": {
                        "duration": plan.duration,
                        "style": plan.style,
                        "structure": plan.structure_hint,
                    }
                })

            # 4. 下载源音频文件（如果未提供本地路径）
            if request.source_audio_path and os.path.exists(request.source_audio_path):
                source_local_path = request.source_audio_path
            else:
                await task_store.update_task_status(request.task_id, "processing", "downloading")
                if progress_callback:
                    await progress_callback("downloading", {"message": "下载原歌曲音频..."})
                source_local_path = await self._download_audio_from_r2(
                    request.source_audio_url, request.task_id
                )

            # 4. 填入参考音频 URL（用于 ACE-Step Audio2Audio）
            plan.reference_audio_url = request.reference_audio_url or request.source_audio_url

            # 5. 提取参考片段（用于 Audio2Audio 的参考音频）
            await task_store.update_task_status(request.task_id, "processing", "extracting_reference")
            if progress_callback:
                await progress_callback("extracting_reference", {"message": "提取参考音频片段..."})

            ref_path, ref_start, ref_beat_info = await self._extract_reference_segment(
                source_local_path,
                request.source_duration,
                REFERENCE_SEGMENT_DURATION
            )

            # 更新 plan 的参考音频路径为本地文件
            plan.reference_audio_url = f"file://{ref_path}"
            plan.reference_start_sec = ref_start
            plan.reference_duration_sec = min(REFERENCE_SEGMENT_DURATION, request.source_duration - ref_start)

            # 6. 生成续写分段
            await task_store.update_task_status(request.task_id, "processing", "generating")
            if progress_callback:
                await progress_callback("generating", {"message": "生成续写片段..."})

            segments = await self._generate_continuation_segments(
                plan, request, ref_path, progress_callback
            )

            # 清理参考音频临时文件
            try:
                os.unlink(ref_path)
            except:
                pass

            # 7. 拼接：原歌曲 + 新片段
            await task_store.update_task_status(request.task_id, "processing", "concatenating")
            if progress_callback:
                await progress_callback("concatenating", {"message": "拼接音频..."})

            final_audio_path = await self._concatenate_with_source(
                source_local_path,
                segments,
                plan,
                progress_callback
            )

            # 7. 上传结果
            await task_store.update_task_status(request.task_id, "processing", "uploading")
            if progress_callback:
                await progress_callback("uploading", {"message": "上传结果..."})

            cdn = await self._get_cdn_uploader()
            upload_result = await cdn.upload_file(
                final_audio_path,
                category="full_song",
                user_id=request.user_id,
                task_id=request.task_id,
                filename=f"continuation_{request.task_id}.wav"
            )

            if not upload_result.success:
                raise Exception(f"Upload failed: {upload_result.error}")

            # 8. 完成
            total_duration = request.source_duration + plan.duration
            result = ContinuationResult(
                success=True,
                task_id=request.task_id,
                output_audio_url=upload_result.public_url,
                output_audio_path=final_audio_path,
                continuation_duration=plan.duration,
                total_duration=total_duration,
                segments=[{
                    "name": s.name,
                    "duration": s.duration,
                    "audio_url": s.audio_url,
                    "beat_info": s.beat_info,
                } for s in segments],
                metadata={
                    "plan": {
                        "mode": plan.mode.value,
                        "style": plan.style,
                        "bpm": plan.bpm,
                        "key": plan.key,
                        "structure": plan.structure_hint,
                    },
                    "analysis": {
                        "original_duration": analysis.duration,
                        "original_bpm": analysis.bpm,
                        "original_key": analysis.key,
                    },
                    "cdn": {
                        "object_key": upload_result.object_key,
                        "size": upload_result.size,
                    }
                }
            )

            await task_store.update_task_status(request.task_id, "completed")
            if progress_callback:
                await progress_callback("completed", {"message": "续写完成", "result": result.metadata})

            return result

        except Exception as e:
            logger.error(f"Continuation failed for task {request.task_id}: {e}")
            await task_store.update_task_status(request.task_id, "failed", str(e))
            if progress_callback:
                await progress_callback("failed", {"error": str(e)})

            return ContinuationResult(
                success=False,
                task_id=request.task_id,
                error=str(e),
            )

    async def _generate_continuation_segments(
        self,
        plan: "ContinuationPlan",
        request: ContinuationRequest,
        ref_path: str,
        progress_callback: Optional[Callable] = None,
    ) -> List["GenerationSegment"]:
        """生成续写分段"""
        segment_planner = await self._get_segment_planner()
        ace_client = await self._get_ace_client()

        # 将 ContinuationPlan 转换为 SongPlan 格式
        from app.services.song_planner import SongPlan, SongSection, SongSectionType

        # 构建临时 SongPlan
        sections = []
        current_time = 0
        # 结构裁剪：总时长不够时只保留最后一段（outro）
        structure_hint = list(plan.structure_hint)
        if plan.duration < 45 and len(structure_hint) > 1:
            structure_hint = structure_hint[-1:]
        for i, struct_name in enumerate(structure_hint):
            # 分配时长
            remaining = plan.duration - current_time
            remaining_sections = len(structure_hint) - i
            if remaining_sections == 1:
                dur = remaining
            else:
                dur = min(remaining // remaining_sections, 60)
                dur = max(15, dur)
                if dur > remaining:
                    dur = remaining

            sec_type = SongSectionType(struct_name) if struct_name in [s.value for s in SongSectionType] else SongSectionType.OUTRO
            sections.append(SongSection(
                name=f"cont_{struct_name}_{i}",
                type=sec_type,
                duration=dur,
                lyrics="",  # 由 ACE-Step 生成
                energy_level=plan.energy_target,
                bpm=plan.bpm,
                key=plan.key,
                vocal_type=plan.vocal_type,
            ))
            current_time += dur

        # 创建 SongPlan
        song_plan = SongPlan(
            total_duration=plan.duration,
            target_duration=plan.duration,
            style=plan.style,
            bpm=plan.bpm,
            key=plan.key,
            time_signature=plan.time_signature,
            sections=sections,
        )

        # 创建分段计划
        segment_plan = segment_planner.create_segment_plan(song_plan)

        # 修改分段参数以支持 Audio2Audio
        # 参考音频 base64 直传（无需 R2 URL，绕过 R2 依赖）
        import base64 as _b64
        try:
            with open(ref_path, "rb") as _f:
                reference_audio_b64 = _b64.b64encode(_f.read()).decode()
        except Exception as e:
            raise Exception(f"Failed to read reference audio: {e}")

        # 修改分段参数以支持 Audio2Audio
        for seg in segment_plan.segments:
            seg.to_ace_step_request = lambda s=seg: {
                "prompt": s.prompt,
                "lyrics": s.lyrics,
                "duration": s.duration,
                "style": s.style,
                "bpm": s.bpm,
                "key": s.key,
                "vocal_type": s.vocal_type,
                "reference_audio_b64": reference_audio_b64,
                "reference_start_sec": plan.reference_start_sec,
                "reference_duration_sec": plan.reference_duration_sec,
                "continuation_mode": plan.continuation_mode,
            }

        # 执行生成
        completed_segments = []

        async def segment_callback(segment):
            completed_segments.append(segment)
            if progress_callback:
                await progress_callback("generating", {
                    "segment": segment.name,
                    "progress": len(completed_segments) / len(segment_plan.segments),
                })

        await segment_planner.execute_plan(
            segment_plan,
            progress_callback=None,  # 内部进度
            segment_callback=segment_callback,
        )

        # 检查失败
        failed = segment_planner.get_failed_segments(segment_plan)
        if failed:
            # 重试失败分段
            logger.warning(f"Retrying {len(failed)} failed segments")
            await segment_planner.retry_failed_segments(segment_plan, segment_callback=segment_callback)
            failed = segment_planner.get_failed_segments(segment_plan)
            if failed:
                raise Exception(f"Segments failed permanently: {[s.name for s in failed]}")

        return segment_planner.get_completed_segments(segment_plan)

    async def _download_audio_from_r2(self, audio_url: str, task_id: str) -> str:
        """从 R2/CDN 下载音频文件到本地"""
        from app.services.ace_step_client import get_ace_step_client
        ace_client = get_ace_step_client()
        local_path = tempfile.mktemp(suffix=f"_{task_id}_source.wav")
        await ace_client.download_file(audio_url, local_path)
        return local_path

    async def _extract_reference_segment(
        self,
        source_path: str,
        source_duration: float,
        reference_duration: float = REFERENCE_SEGMENT_DURATION,
    ) -> Tuple[str, float, Dict[str, Any]]:
        """
        从源歌曲末尾提取参考片段用于 Audio2Audio

        Returns:
            (reference_audio_path, reference_start_time, beat_info)
        """
        from app.services.audio_trim import get_audio_trimmer
        from app.services.beat_detector import get_beat_detector

        trimmer = await self._get_audio_trimmer()
        detector = await self._get_beat_detector()

        # 分析源歌曲获取节拍信息
        beat_info = await detector.analyze(source_path)

        # 计算参考片段的开始时间（从末尾倒推）
        ref_start = max(0, source_duration - reference_duration)
        ref_end = source_duration

        # 尝试对齐到下拍
        downbeats = beat_info.get("downbeats", [])
        if downbeats:
            # 找到最接近 ref_start 的下拍
            aligned_start = min(downbeats, key=lambda d: abs(d - ref_start))
            # 确保不超出范围
            if aligned_start < source_duration - 5:  # 至少留 5 秒
                ref_start = aligned_start

        # 提取参考片段
        ref_path = tempfile.mktemp(suffix="_reference.wav")
        trimmer = await self._get_audio_trimmer()
        result = await trimmer.trim(
            source_path,
            ref_start,
            ref_end,
            ref_path,
            fade_in=0.05,
            fade_out=0.05,
        )

        if not result.success:
            # 兜底：直接使用原始时间
            result = await trimmer.trim(source_path, ref_start, ref_end, ref_path)
            if not result.success:
                raise Exception(f"Failed to extract reference segment: {result.error}")

        return ref_path, ref_start, beat_info

    async def _concatenate_with_source(
        self,
        source_path: str,
        segments: List["GenerationSegment"],
        plan: "ContinuationPlan",
        progress_callback: Optional[Callable] = None,
    ) -> str:
        """将原歌曲与新片段拼接，包含后处理"""
        from app.services.mix_engine import get_mix_engine
        from app.services.audio_trim import get_audio_trimmer
        from app.services.beat_detector import get_beat_detector
        from app.services.audio_postprocess import get_audio_postprocessor

        mix_engine = await self._get_mix_engine()
        trimmer = await self._get_audio_trimmer()
        detector = await self._get_beat_detector()
        post_processor = get_audio_postprocessor()

        # 分析源歌曲
        source_beat_info = await detector.analyze(source_path)

        # 准备所有片段路径
        segment_paths = [source_path]
        beat_infos = [source_beat_info]

        # 添加新片段
        for seg in segments:
            if seg.local_path and os.path.exists(seg.local_path):
                segment_paths.append(seg.local_path)
                beat_infos.append(seg.beat_info or {})

        # 创建输出路径
        output_path = tempfile.mktemp(suffix="_final.wav")

        # 使用节拍对齐拼接
        result = await mix_engine.concatenate_segments(
            segment_paths,
            output_path,
            crossfade_duration=0.15,
            beat_infos=beat_infos,
            alignment="downbeat",
            normalize=True,
        )

        if not result.success:
            raise Exception(f"Concatenation failed: {result.error}")

        # 后处理：响度标准化 + MP3 生成
        final_wav = tempfile.mktemp(suffix="_final_processed.wav")
        final_mp3 = tempfile.mktemp(suffix="_final.mp3")

        pp_result = await post_processor.normalize_loudness(
            input_path=output_path,
            output_wav_path=final_wav,
            output_mp3_path=final_mp3,
        )

        if not pp_result.success:
            logger.warning(f"Post-processing failed, using raw output: {pp_result.error}")
            return output_path

        # 清理临时文件
        try:
            os.unlink(output_path)
        except:
            pass

        return final_wav


    async def generate_long_music(
        self,
        prompt: str,
        style: str,
        duration: int,
        lyrics: Optional[str],
        task_id: str,
        user_key: str,
        mood: Optional[str] = None,
        vocal: Optional[str] = None,
        provider_chain: Optional[List] = None,
    ) -> Dict[str, Any]:
        """150+150 300s 长生成（对外唯一入口；C3-5-B 清理包装层）。

        语义（与 _generate_long_music_impl 相同）：
        1. 首段 150s (真实 provider)
        2. 第二段 150s 基于首段末尾 30s 的 Audio2Audio (独立重试)
        3. FFmpeg 1.5s crossfade 拼接 (独立重试)
        4. duration gate 通过后只交付本地成品（final 上传唯一 owner = route）

        C3-5-B 生命周期：
        - 失败（含取消/超时）：finally best-effort 清理本任务已上传的 part 对象
          与全部本地临时文件（first/second/combined），随后原样重抛原始异常，
          绝不改变失败/退款/超时语义。
        - 成功：清理 segment 本地文件；part R2 对象与 combined 留给
          ai_music 路由在 _upload_and_finalize 完成 finalize 之后统一清理
          （B1：final 已建立才删 parts，且清理失败不影响 completed）。
        """
        state: Dict[str, Any] = {
            "part_keys": [],
            "first_local": None,
            "second_local": None,
            "combined_path": None,
            "handed_off": False,
        }
        try:
            return await self._generate_long_music_impl(
                prompt, style, duration, lyrics, task_id, user_key,
                mood=mood, vocal=vocal, provider_chain=provider_chain, state=state,
            )
        finally:
            if state["handed_off"]:
                # 成功：只清本地 segment；parts/combined 由 route finalize 后清理
                cleanup_continuation_artifacts(
                    task_id, None,
                    [state["first_local"], state["second_local"]],
                )
            else:
                # 失败/取消：parts + 全部本地临时（含 combined）best-effort 清理
                cleanup_continuation_artifacts(
                    task_id, state["part_keys"],
                    [state["first_local"], state["second_local"], state["combined_path"]],
                )

    async def _generate_long_music_impl(
        self,
        prompt: str,
        style: str,
        duration: int,
        lyrics: Optional[str],
        task_id: str,
        user_key: str,
        mood: Optional[str] = None,
        vocal: Optional[str] = None,
        provider_chain: Optional[List] = None,
        state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """generate_long_music 的实现体（调用方必须经 generate_long_music 包装层）。"""
        state = state if state is not None else {}
        # 限制目标（P6-B-C2 D2：target 就是请求上限本身，不再预加 crossfade 补偿）
        target = min(float(duration), 300)
        if target <= 180:
            raise ValueError("generate_long_music 仅用于 >180s，短时长请走单段")

        # 分段：crossfade 会吃掉 CROSSFADE_DURATION 秒，因此补偿只加在第二段上，
        # 使 首段 + 次段 - 交叉淡化 ≥ target（例：target=300 → 150 + 152 - 1.5 =
        # 300.5 ≥ 300；ceil 必需：int() 截断会得到 299.5）。成品是否 ≥MIN=240
        # 由统一质量门 _enforce_duration_gate 实测裁决（不再有 270 上限语义）。
        first_dur = 150
        second_dur = math.ceil(target - first_dur + CROSSFADE_DURATION)

        task_store.update(task_id, state="processing", progress=5)
        # P6-B-C1：调用方可显式注入首段 chain，与 HTTP 路由共用同一份 provider 选择结果；
        # 注入时不再解析全局 registry（否则调用方注入的链会被真实注册表旁路）。
        # 未注入时行为与既有语义一致：
        # 首段 Provider fallback（production 自动模式）：Yinchao → TemPolor；
        # 显式 AI_GENERATION_PROVIDER 保持单 provider 语义（Commit 4 contract），失败不自动切换；
        # 非生产 fallback_chain() 本身即单元素链，不改变既有行为。
        if provider_chain is not None:
            first_chain = list(provider_chain)
            if not first_chain:
                raise ValueError("provider_chain 为空时无法生成首段")
        else:
            from app.services.provider_registry import get_provider_registry, PROVIDER_ENV
            registry = get_provider_registry()
            if (os.getenv(PROVIDER_ENV) or "").strip():
                first_chain = [registry.select()]
            else:
                first_chain = registry.fallback_chain()

        # ── 第一段 150s (真实 provider, 首段失败才按链换家；不退款，交外层统一 refund) ──
        # P6-B-C1-R：与 ai_music._run_generation 同一套 provider 失败语义——
        # 每家共 1+MAX_AUTO_RETRIES 次，重试耗尽才换链中下一家；
        # non_retryable（参数/内容/能力类错误）不重试、不换家：同一输入必再被判错，徒耗额度。
        provider = None
        first_result = None
        first_err = "unknown"
        first_non_retryable = False
        for candidate in first_chain:
            provider = candidate
            task_store.update(task_id, state="generating", progress=10)
            for attempt in range(1 + MAX_AUTO_RETRIES):
                first_result = await self._generate_single_segment(
                    provider=provider,
                    prompt=prompt,
                    lyrics=lyrics or "",
                    duration=first_dur,
                    reference_b64=None,
                    enable_a2a=False,
                )
                if first_result and first_result.get("success"):
                    break
                first_err = first_result.get("error") if first_result else "unknown"
                if first_result and first_result.get("non_retryable"):
                    first_non_retryable = True
                    task_store.update(task_id, error=f"首段 {provider.name} 不可重试错误，停止换家: {first_err}")
                    break
                task_store.update(
                    task_id,
                    error=f"首段 {provider.name} 第 {attempt + 1} 次尝试失败: {first_err}",
                )
            if (first_result and first_result.get("success")) or first_non_retryable:
                break
            task_store.update(task_id, error=f"首段 {provider.name} 重试耗尽，尝试链中下一个 Provider: {first_err}")
        if provider is None:
            raise RuntimeError("首段 150s 无可用 Provider")
        if not first_result or not first_result.get("success"):
            raise RuntimeError(f"首段 150s 生成失败: {first_err}")

        first_files = first_result.get("volume_files") or {}
        first_local = self._resolve_local_path(first_files)
        if not first_local or not os.path.exists(first_local):
            raise RuntimeError("首段本地文件丢失")
        state["first_local"] = first_local

        task_store.update(task_id, progress=40)
        # 中间段先上传 R2 保留（可选，但满足“中间片段保存到 R2”）
        part1_manifest = await self._upload_parts(task_id, {"part1_wav": first_local}, suffix="part1")
        state["part_keys"].extend(_part_keys_of(task_id, part1_manifest))

        # ── 参考音频截取 + 分析 + 歌词续写 ──
        ref_b64, analysis = await self._prepare_continuation_context(
            first_local=first_local,
            prompt=prompt,
            style=style,
            mood=mood,
            vocal=vocal,
            lyrics=lyrics,
        )
        # 构建续写 prompt：保持 BPM/key/genre/mood/vocal 连续性
        bpm = analysis.get("bpm") or 120
        key = analysis.get("key") or "C major"
        style_hint = style or "pop"
        vocal_hint = vocal or ""
        mood_hint = mood or ""
        continuation_prompt = (
            f"Continuation of previous music, seamless, same {style_hint} style, "
            f"{bpm:.0f} BPM, key {key}, mood {mood_hint} {vocal_hint}, same instrumentation and vocal style as reference. "
            f"Original prompt: {prompt}"
        ).strip()
        # 歌词续写
        continuation_lyrics = await self._continue_lyrics(lyrics, style_hint)

        # ── 第二段 150s (独立重试，不重跑首段) ──
        task_store.update(task_id, state="generating", progress=50)
        second_result = None
        last_err = None
        for attempt in range(1 + MAX_AUTO_RETRIES):
            try:
                second_result = await self._generate_single_segment(
                    provider=provider,
                    prompt=continuation_prompt,
                    lyrics=continuation_lyrics or lyrics or "",
                    duration=second_dur,
                    reference_b64=ref_b64,
                    enable_a2a=True,
                )
                if second_result and second_result.get("success"):
                    break
                last_err = second_result.get("error") if second_result else "unknown"
                task_store.update(task_id, error=f"续写段第 {attempt} 次失败: {last_err}")
            except Exception as e:
                last_err = str(e)
                task_store.update(task_id, error=f"续写异常 {attempt}: {last_err}")
            # 重试前短暂等待
            if attempt < MAX_AUTO_RETRIES:
                await asyncio.sleep(2)
        if not second_result or not second_result.get("success"):
            raise RuntimeError(f"续写段生成失败(已重试 {MAX_AUTO_RETRIES} 次): {last_err}")

        second_files = second_result.get("volume_files") or {}
        second_local = self._resolve_local_path(second_files)
        if not second_local or not os.path.exists(second_local):
            raise RuntimeError("续写段本地文件丢失")
        state["second_local"] = second_local
        task_store.update(task_id, progress=70)
        part2_manifest = await self._upload_parts(task_id, {"part2_wav": second_local}, suffix="part2")
        state["part_keys"].extend(_part_keys_of(task_id, part2_manifest))

        # ── FFmpeg 拼接 (独立重试，不重跑 GPU) ──
        task_store.update(task_id, state="generating", progress=80)
        combined_path = None
        last_ff_err = None
        for attempt in range(1 + MAX_AUTO_RETRIES + 1):
            try:
                combined_path = await self._stitch_with_crossfade(first_local, second_local, CROSSFADE_DURATION)
                if combined_path and os.path.exists(combined_path):
                    break
            except Exception as e:
                last_ff_err = str(e)
                task_store.update(task_id, error=f"合并失败 {attempt}: {last_ff_err}")
                if attempt < MAX_AUTO_RETRIES + 1:
                    await asyncio.sleep(1)
        if not combined_path or not os.path.exists(combined_path):
            raise RuntimeError(f"FFmpeg 合并失败: {last_ff_err}")
        state["combined_path"] = combined_path

        task_store.update(task_id, progress=85)
        # ── P6-B-C2 D1/N1 成品时长硬闸：必须在任何最终上传之前 ──
        # 实测失败（librosa 异常）同样判失败：测不到 = 无法证明合规 = 不得交付。
        try:
            measured = await self._measure_final_duration(combined_path)
        except Exception as exc:  # noqa: BLE001
            raise DurationValidationError(
                f"final duration could not be measured: {type(exc).__name__}: {exc}"
            ) from exc
        if measured < MIN_AUDIO_DURATION_SECONDS:
            raise DurationValidationError(
                f"final duration {measured:.1f}s is below minimum {MIN_AUDIO_DURATION_SECONDS}s"
            )

        # C3-5-A：final R2 上传的唯一 owner 是 ai_music._upload_and_finalize。
        # 此处通过 duration gate 后只交付本地成品 + 实测时长，不产生 final PUT、
        # 不返回 manifest（route 侧 upload 才是真实 download manifest 的来源）。
        task_store.update(task_id, state="uploading", progress=90)
        state["handed_off"] = True  # C3-5-B：combined/parts 交由 route finalize 后清理
        return {
            "success": True,
            "volume_files": {
                "full_wav": os.path.basename(combined_path),
                "_local_path": combined_path,
                "_measured_duration_sec": measured,
            },
            "provider": f"{provider.name}+continuation",
            "segments": 2,
            "part_keys": list(state["part_keys"]),

        }

    async def _generate_single_segment(self, provider, prompt: str, lyrics: str, duration: int, reference_b64: Optional[str], enable_a2a: bool) -> Dict:
        return await provider.generate({
            "prompt": prompt,
            "lyrics": lyrics,
            "duration": int(duration),
            "reference_audio": reference_b64,
            "enable_audio2audio": enable_a2a,
            "reference_strength": 0.7,
        })

    async def _measure_final_duration(self, path: str) -> float:
        """成品时长实测的唯一出口（P6-B-C2）。异常一律向上抛，不在此吞掉。"""
        import librosa
        return float(librosa.get_duration(path=path))

    def _resolve_local_path(self, volume_files: Dict) -> Optional[str]:
        if not volume_files:
            return None
        # 优先 _local_path（Fal 已下载）
        if volume_files.get("_local_path") and os.path.exists(volume_files["_local_path"]):
            return volume_files["_local_path"]
        # 尝试 full_wav
        for k in ("full_wav", "full_mp3", "full", "part1_wav", "part2_wav"):
            v = volume_files.get(k)
            if v and os.path.exists(v):
                return v
            # 尝试 GENERATED_DIR
            if v and isinstance(v, str):
                try:
                    from app.services.fal_client import local_dir as fal_local_dir
                    cand2 = os.path.join(fal_local_dir(), os.path.basename(v))
                    if os.path.exists(cand2):
                        return cand2
                except Exception:
                    pass
        # 最后尝试 filename 在 temp
        for v in volume_files.values():
            if isinstance(v, str) and os.path.exists(v):
                return v
        return None

    async def _prepare_continuation_context(self, first_local: str, prompt: str, style: str, mood: Optional[str], vocal: Optional[str], lyrics: Optional[str]):
        # 截取末尾 30s 作为参考
        ref_start = 0
        try:
            import librosa
            total = librosa.get_duration(path=first_local)
            ref_start = max(0, total - 30)
            ref_end = total
        except Exception:
            ref_start, ref_end = 120, 150
        # 使用 trim_audio 截取（返回 bytes）
        from app.services.audio_trim import trim_audio
        from app.services.continuation_analysis import analyze_audio_context
        ref_bytes, _ = await trim_audio(first_local, ref_start, ref_end, "wav")
        ref_b64 = base64.b64encode(ref_bytes).decode()
        # 分析 BPM/key
        try:
            analysis = await analyze_audio_context(ref_bytes)
        except Exception as e:
            print(f"[Continuation] 分析失败 fallback: {e}")
            analysis = {"bpm": 120, "key": "C major", "chords": []}
        return ref_b64, analysis

    async def _continue_lyrics(self, existing_lyrics: Optional[str], style: str) -> str:
        try:
            from app.services.lyric_service import lyric_service
            if existing_lyrics:
                res = await lyric_service.continue_lyrics(existing_lyrics=existing_lyrics, style=style)
                # lyric_service 返回对象可能有 .lyrics
                if hasattr(res, 'lyrics'):
                    return res.lyrics or existing_lyrics
                if isinstance(res, dict):
                    return res.get('lyrics') or existing_lyrics
            return existing_lyrics or ""
        except Exception as e:
            print(f"[Continuation] 歌词续写失败 fallback: {e}")
            return existing_lyrics or ""

    async def _stitch_with_crossfade(self, first_path: str, second_path: str, crossfade: float = 1.5) -> str:
        """
        使用 ffmpeg acrossfade 无缝拼接
        输入为本地 wav 路径，输出到临时 combined wav
        """
        import subprocess
        import tempfile
        fd, out_path = tempfile.mkstemp(suffix="_combined_300s.wav")
        os.close(fd)
        # 使用 ffmpeg acrossfade filter，1.5s 三角过渡
        cmd = [
            "ffmpeg", "-y",
            "-i", first_path,
            "-i", second_path,
            "-filter_complex", f"[0:a][1:a]acrossfade=d={crossfade}:c1=tri:c2=tri[a]",
            "-map", "[a]",
            "-c:a", "pcm_s16le",
            out_path
        ]
        try:
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                err = stderr.decode(errors="replace")[:800] if stderr else "unknown"
                raise RuntimeError(f"ffmpeg acrossfade failed: {err}")
            if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
                raise RuntimeError("ffmpeg 输出为空")
            return out_path
        except BaseException:
            # C3-5-B/§17：失败或被取消时清掉本次半成品临时文件（成功路径保留给上层）
            try:
                if os.path.exists(out_path):
                    os.remove(out_path)
            except OSError:
                pass
            raise

    async def _upload_parts(self, task_id: str, files: Dict[str, str], suffix: str) -> Dict:
        """上传中间段到 R2 保留，key 带 part 前缀"""
        try:
            from app.services.cdn_uploader import cdn_uploader
            # 为中间段构造临时 manifest key 避免覆盖
            manifest = await cdn_uploader.upload_music_package(f"{task_id}_{suffix}", files)
            return manifest
        except Exception as e:
            print(f"[Continuation] 中间段 {suffix} R2 上传失败(非致命): {e}")
            return {}

    async def _upload_final(self, task_id: str, combined_path: str, part1_manifest: Dict, part2_manifest: Dict) -> Dict:
        from app.services.cdn_uploader import cdn_uploader
        files = {"full_wav": combined_path, "full_mp3": combined_path}
        manifest = await cdn_uploader.upload_music_package(task_id, files)
        # 合并中间段 manifest 供审计（不覆盖最终 full）
        for k, v in {**part1_manifest, **part2_manifest}.items():
            if k not in manifest:
                manifest[k] = v
        return manifest

    # 兼容旧接口

# 全局实例
_continuation_service: Optional[ContinuationService] = None


def get_continuation_service() -> ContinuationService:
    global _continuation_service
    if _continuation_service is None:
        _continuation_service = ContinuationService()
    return _continuation_service


# 全局实例（按调用方需求提供单件）
continuation_service = ContinuationService()
