"""
分段生成规划器
- 将 SongPlan 转换为具体的 ACE-Step 生成任务
- 处理分段依赖、并行度控制
- 失败重试与恢复策略
"""

import os
import logging
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable
from enum import Enum
import uuid

logger = logging.getLogger(__name__)

# ========== 配置 ==========
MAX_PARALLEL_SEGMENTS = int(os.getenv("MAX_PARALLEL_SEGMENTS", "2"))  # 最大并行分段数
SEGMENT_RETRY_LIMIT = int(os.getenv("SEGMENT_RETRY_LIMIT", "2"))  # 单分段最大重试次数
SEGMENT_TIMEOUT = int(os.getenv("SEGMENT_TIMEOUT", "180"))  # 单分段超时（秒）


class SegmentStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    GENERATING = "generating"
    ANALYZING = "analyzing"  # 等待节拍分析
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"


@dataclass
class GenerationSegment:
    """生成分段任务"""
    segment_id: str
    name: str
    type: str
    prompt: str
    lyrics: str
    duration: int
    style: str
    bpm: int
    key: str
    vocal_type: str
    start_time: float
    end_time: float
    energy_level: float
    depends_on: List[str] = field(default_factory=list)  # 依赖的前置分段 ID
    status: SegmentStatus = SegmentStatus.PENDING
    retry_count: int = 0
    audio_url: Optional[str] = None
    local_path: Optional[str] = None
    beat_info: Optional[Dict[str, Any]] = None  # 节拍分析结果
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_ace_step_request(self) -> Dict[str, Any]:
        """转换为 ACE-Step 生成请求"""
        return {
            "prompt": self.prompt,
            "lyrics": self.lyrics,
            "duration": self.duration,
            "style": self.style,
            "bpm": self.bpm,
            "key": self.key,
            "vocal_type": self.vocal_type,
            "time_signature": "4/4",
        }


@dataclass
class SegmentPlan:
    """分段生成计划"""
    plan_id: str
    song_plan_id: str
    segments: List[GenerationSegment] = field(default_factory=list)
    total_duration: float = 0.0
    parallel_groups: List[List[str]] = field(default_factory=list)  # 可并行的分段组
    
    def get_ready_segments(self, completed: set) -> List[GenerationSegment]:
        """获取可执行的分段（依赖已满足）"""
        ready = []
        for seg in self.segments:
            if seg.status == SegmentStatus.PENDING:
                if all(dep in completed for dep in seg.depends_on):
                    ready.append(seg)
        return ready
    
    def get_segment(self, segment_id: str) -> Optional[GenerationSegment]:
        for seg in self.segments:
            if seg.segment_id == segment_id:
                return seg
        return None
    
    def all_completed(self) -> bool:
        return all(s.status == SegmentStatus.COMPLETED for s in self.segments)
    
    def has_failed(self) -> bool:
        return any(s.status == SegmentStatus.FAILED and s.retry_count >= SEGMENT_RETRY_LIMIT for s in self.segments)


class SegmentPlanner:
    """分段生成规划与执行器"""
    
    def __init__(self):
        self._ace_client = None
        self._beat_detector = None
    
    async def _get_ace_client(self):
        if self._ace_client is None:
            from app.services.ace_step_client import get_ace_step_client
            self._ace_client = get_ace_step_client()
        return self._ace_client
    
    async def _get_beat_detector(self):
        if self._beat_detector is None:
            from app.services.beat_detector import get_beat_detector
            self._beat_detector = get_beat_detector()
        return self._beat_detector
    
    def create_segment_plan(self, song_plan: "SongPlan") -> SegmentPlan:
        """从 SongPlan 创建分段生成计划"""
        plan_id = f"segplan_{uuid.uuid4().hex[:12]}"
        segments = []
        
        # 构建依赖关系：通常按顺序依赖，但可以并行生成不相邻的段落
        for i, seg_data in enumerate(song_plan.to_generation_segments()):
            segment_id = f"seg_{uuid.uuid4().hex[:8]}"
            depends_on = []
            if i > 0:
                # 简单策略：每个段落依赖前一个（保证顺序分析）
                # 实际可优化：只依赖需要 beat-align 的前置段落
                depends_on.append(segments[-1].segment_id)
            
            segment = GenerationSegment(
                segment_id=segment_id,
                name=seg_data["name"],
                type=seg_data["type"],
                prompt=seg_data["prompt"],
                lyrics=seg_data["lyrics"],
                duration=seg_data["duration"],
                style=seg_data["style"],
                bpm=seg_data["bpm"],
                key=seg_data["key"],
                vocal_type=seg_data["vocal_type"],
                start_time=seg_data["start_time"],
                end_time=seg_data["end_time"],
                energy_level=seg_data["energy_level"],
                depends_on=depends_on,
            )
            segments.append(segment)
        
        # 计算并行组：无依赖关系的可以并行
        # 这里简化为：首尾段落可并行，中间按顺序
        parallel_groups = []
        if len(segments) <= 2:
            parallel_groups = [[s.segment_id for s in segments]]
        else:
            # intro 和 outro 可并行（如果都不依赖中间段落）
            # 但通常需要中间段落的 beat 信息来对齐，所以保守按顺序
            parallel_groups = [[s.segment_id] for s in segments]
        
        return SegmentPlan(
            plan_id=plan_id,
            song_plan_id=getattr(song_plan, 'metadata', {}).get('plan_id', 'unknown'),
            segments=segments,
            total_duration=song_plan.total_duration,
            parallel_groups=parallel_groups,
        )
    
    async def execute_plan(
        self,
        segment_plan: SegmentPlan,
        progress_callback: Optional[Callable[[str, SegmentStatus, Dict[str, Any]], Any]] = None,
        segment_callback: Optional[Callable[[GenerationSegment], Any]] = None,
    ) -> SegmentPlan:
        """
        执行分段生成计划
        
        Args:
            segment_plan: 分段计划
            progress_callback: 进度回调 (segment_id, status, metadata)
            segment_callback: 单分段完成回调
        
        Returns:
            更新后的 SegmentPlan
        """
        ace_client = await self._get_ace_client()
        completed = set()
        semaphore = asyncio.Semaphore(MAX_PARALLEL_SEGMENTS)
        
        async def _call_progress(segment, status, meta=None):
            if progress_callback is None:
                return
            result = progress_callback(segment.segment_id, status, meta or {})
            if asyncio.iscoroutine(result):
                await result

        async def generate_segment(segment: GenerationSegment):
            async with semaphore:
                import time as _t
                _t0 = _t.time()
                # 更新状态
                segment.status = SegmentStatus.GENERATING
                logger.info(f"[segplanner] {segment.name} GENERATING start ({len(segment.depends_on)} deps)")
                await _call_progress(segment, segment.status, {"name": segment.name})
                
                for attempt in range(SEGMENT_RETRY_LIMIT + 1):
                    try:
                        if attempt > 0:
                            segment.status = SegmentStatus.RETRYING
                            segment.retry_count = attempt
                            await _call_progress(segment, segment.status, {"attempt": attempt})
                            await asyncio.sleep(2 ** attempt)  # 指数退避
                        
                        # 调用 ACE-Step 生成
                        request = segment.to_ace_step_request()
                        logger.info(f"[segplanner] {segment.name} request keys: {sorted(request.keys())}")
                        # 续写模式：包含参考音频参数时调用 continue_audio 端点
                        if request.get("reference_audio_b64") or request.get("reference_audio_url"):
                            result = await asyncio.wait_for(
                                ace_client.continue_audio(
                                    reference_audio_url=request.pop("reference_audio_url", "") or "",
                                    **request,
                                ),
                                timeout=SEGMENT_TIMEOUT
                            )
                        else:
                            result = await asyncio.wait_for(
                                ace_client.generate_full_song(**request),
                                timeout=SEGMENT_TIMEOUT
                            )
                        
                        if result and result.get("audio_url"):
                            segment.audio_url = result["audio_url"]
                            segment.metadata.update({
                                "sample_rate": result.get("sample_rate", 44100),
                                "channels": result.get("channels", 2),
                                "actual_duration": result.get("duration", segment.duration),
                                "task_id": result.get("task_id"),
                            })
                            
                            # 下载到本地进行节拍分析
                            local_path = await ace_client.download_file(result["audio_url"])
                            segment.local_path = local_path
                            
                            # 节拍分析
                            segment.status = SegmentStatus.ANALYZING
                            if progress_callback:
                                await progress_callback(segment.segment_id, segment.status, {"name": segment.name})
                            
                            beat_detector = await self._get_beat_detector()
                            beat_info = await beat_detector.analyze(local_path)
                            segment.beat_info = beat_info
                            
                            segment.status = SegmentStatus.COMPLETED
                            completed.add(segment.segment_id)
                            
                            await _call_progress(segment, segment.status, {
                                    "name": segment.name,
                                    "audio_url": segment.audio_url,
                                    "beat_info": beat_info,
                                })
                            
                            if segment_callback:
                                await segment_callback(segment)
                            return
                        else:
                            raise Exception(result.get("error") if result else "No response from ACE-Step")
                            
                    except asyncio.TimeoutError:
                        segment.error = f"Generation timeout after {SEGMENT_TIMEOUT}s"
                        logger.error(f"Segment {segment.name} timeout")
                    except Exception as e:
                        segment.error = str(e)
                        import traceback
                        logger.error(f"Segment {segment.name} failed (attempt {attempt+1}): {e}\n{traceback.format_exc()}")
                
            # 所有重试都失败
                segment.status = SegmentStatus.FAILED
                logger.error(f"[segplanner] {segment.name} FAILED after {_t.time()-_t0:.1f}s: {segment.error}")
                await _call_progress(segment, segment.status, {"error": segment.error})
                logger.error(f"Segment {segment.name} failed permanently: {segment.error}")
        
        # 执行所有分段（按依赖顺序，但组内并行）
        for group in segment_plan.parallel_groups:
            # 获取该组中状态为 PENDING 的分段
            group_segments = [
                segment_plan.get_segment(sid) 
                for sid in group 
                if segment_plan.get_segment(sid) and segment_plan.get_segment(sid).status == SegmentStatus.PENDING
            ]
            if not group_segments:
                continue
            
            # 等待依赖完成
            for seg in group_segments:
                while not all(dep in completed for dep in seg.depends_on):
                    await asyncio.sleep(0.5)
            
            # 并行执行该组
            await asyncio.gather(*[generate_segment(seg) for seg in group_segments], return_exceptions=True)
        
        return segment_plan
    
    async def retry_failed_segments(
        self,
        segment_plan: SegmentPlan,
        progress_callback: Optional[Callable] = None,
        segment_callback: Optional[Callable] = None,
    ) -> SegmentPlan:
        """重试失败的分段"""
        for segment in segment_plan.segments:
            if segment.status == SegmentStatus.FAILED and segment.retry_count < SEGMENT_RETRY_LIMIT:
                segment.status = SegmentStatus.PENDING
                segment.error = None
        
        return await self.execute_plan(segment_plan, progress_callback, segment_callback)
    
    def get_failed_segments(self, segment_plan: SegmentPlan) -> List[GenerationSegment]:
        return [s for s in segment_plan.segments if s.status == SegmentStatus.FAILED]
    
    def get_completed_segments(self, segment_plan: SegmentPlan) -> List[GenerationSegment]:
        return [s for s in segment_plan.segments if s.status == SegmentStatus.COMPLETED]


# 全局实例
_segment_planner: Optional[SegmentPlanner] = None


def get_segment_planner() -> SegmentPlanner:
    global _segment_planner
    if _segment_planner is None:
        _segment_planner = SegmentPlanner()
    return _segment_planner