"""
AI 续写核心服务
- 接续现有歌曲生成新片段
- 支持多种续写模式
- 集成分段生成、节拍对齐、混音拼接
- 失败恢复与重试
"""

import os
import logging
import asyncio
import uuid
import tempfile
import shutil
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# ========== 配置 ==========
MAX_SONG_DURATION = int(os.getenv("MAX_SONG_DURATION", "330"))
MAX_CONTINUATION_DURATION = int(os.getenv("MAX_CONTINUATION_DURATION", "120"))
REFERENCE_SEGMENT_DURATION = int(os.getenv("REFERENCE_SEGMENT_DURATION", "30"))  # 参考片段时长(秒)


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


class ContinuationService:
    """AI 续写服务"""
    
    def __init__(self):
        self._ace_client = None
        self._analyzer = None
        self._segment_planner = None
        self._mix_engine = None
        self._cdn_uploader = None
        self._task_store = None
    
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


# 全局实例
_continuation_service: Optional[ContinuationService] = None


def get_continuation_service() -> ContinuationService:
    global _continuation_service
    if _continuation_service is None:
        _continuation_service = ContinuationService()
    return _continuation_service