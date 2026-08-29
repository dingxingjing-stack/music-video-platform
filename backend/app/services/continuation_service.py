"""
歌曲续写编排服务
核心流程：
1. 原歌曲 -> 截取续写点前 REFERENCE_SECONDS 秒作为参考音频
2. 上传/传入 ACE-Step (enable_audio2audio=True)
3. 生成 30-60 秒续写段
4. 下载结果
5. FFmpeg crossfade 拼接
6. 返回新 song_id
"""

import asyncio
import base64
import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from app.services.ace_step_client import (
    download_file as ace_step_download,
    generate_full_song as ace_step_generate,
    QueueFullError,
)
from app.services.ai_limits import MAX_SONG_DURATION_SECONDS, REFERENCE_SECONDS
from app.services.audio_trim import trim_audio
from app.services.chord_track_service import chord_track_service
from app.services.lyric_service import lyric_service
from app.services.mix_engine import render_mix
from app.services import task_store

from .continuation_analysis import analyze_audio_context


# 续写配置常量
DEFAULT_SEGMENT_DURATION = 60  # 默认续写段长度（秒）
MIN_SEGMENT_DURATION = 30
MAX_SEGMENT_DURATION = 60
CROSSFADE_DURATION = 2.0  # crossfade 默认时长（秒）


@dataclass
class SongContext:
    """歌曲上下文 - 维护歌曲生成过程中的关键信息"""
    song_id: str
    task_id: str
    user_key: str
    target_duration: int  # 目标总时长（秒）
    current_duration: float = 0.0
    bpm: Optional[float] = None
    key: Optional[str] = None
    chords: Optional[List[Dict]] = None
    genre: Optional[str] = None
    style: Optional[str] = None
    instrumentation: Optional[str] = None
    vocal_style: Optional[str] = None
    lyrics: Optional[str] = None
    lyrics_context: Optional[str] = None
    song_structure: Optional[List[Dict]] = None
    current_section: Optional[str] = None
    previous_section: Optional[str] = None
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
    """歌曲续写编排服务"""
    
    def __init__(self):
        self.temp_dir = tempfile.gettempdir()

    async def generate_full_song(
        self,
        prompt: str,
        style: str,
        duration: int,
        lyrics: Optional[str] = None,
        language: str = "zh",
        user_key: str = "",
        task_id: str = "",
    ) -> Dict[str, Any]:
        """
        一键生成完整歌曲（自动分段续写）
        
        流程：
        1. 创建 SongContext
        2. 生成第一段 (60-90秒)
        3. 循环续写直到达到 target_duration
        4. 最终拼接并返回
        """
        # 限制时长不超过 270 秒
        target_duration = min(duration, 270)
        
        # 创建任务
        final_task_id = task_id or task_store.new_task(user_key=user_key)
        if not task_store.acquire_lock(user_key, final_task_id):
            raise RuntimeError("用户已有进行中的任务")
        
        try:
            # 初始化 SongContext
            context = SongContext(
                song_id="",  # 将在第一段生成后填充
                task_id=final_task_id,
                user_key=user_key,
                target_duration=duration,
                current_duration=0.0,
                genre=style,
                style=style,
            )
            
            # 保存初始上下文
            await self._save_context(final_task_id, context)
            
            # 生成第一段
            first_segment_duration = min(90, duration)  # 第一段最长 90 秒
            segment_result = await self._generate_first_segment(
                prompt=prompt,
                style=style,
                duration=first_segment_duration,
                lyrics=lyrics,
                language=language if 'language' in locals() else "zh",
                task_id=final_task_id,
                context=context,
            )
            
            if not segment_result.get("success"):
                raise RuntimeError(f"首段生成失败: {segment_result.get('error')}")
            
            context.song_id = segment_result["song_id"]
            context.current_duration = segment_result["duration"]
            context.segment_history.append({
                "segment_id": 1,
                "song_id": segment_result["song_id"],
                "duration": segment_result["duration"],
                "start_time": 0.0,
                "end_time": segment_result["duration"],
            })
            
            # 自动续写循环
            while context.current_duration < duration:
                remaining = duration - context.current_duration
                if remaining <= 0:
                    break
                
                # 计算下一段时长
                next_segment_duration = min(DEFAULT_SEGMENT_DURATION, remaining)
                next_segment_duration = max(MIN_SEGMENT_DURATION, next_segment_duration)
                
                # 生成续写段
                segment_result = await self._generate_continuation_segment(
                    context=context,
                    prompt=prompt,
                    style=style,
                    duration=next_segment_duration,
                    language=language if 'language' in locals() else "zh",
                    task_id=final_task_id,
                )
                
                if not segment_result.get("success"):
                    # 续写失败，标记任务失败但保留已生成部分
                    raise RuntimeError(f"续写失败: {segment_result.get('error')}")
                
                # 更新上下文
                context.current_duration += segment_result["duration"]
                context.segment_history.append({
                    "segment_id": len(context.segment_history) + 1,
                    "song_id": segment_result["song_id"],
                    "duration": segment_result["duration"],
                    "start_time": context.current_duration - segment_result["duration"],
                    "end_time": context.current_duration,
                })
                
                # 更新上下文中的音乐特征（从新段提取）
                await self._update_context_from_segment(context, segment_result)
                
                # 保存上下文
                await self._save_context(final_task_id, context)
            
            # 最终拼接所有段落
            final_song_id = await self._finalize_song(context, final_task_id)
            
            return {
                "success": True,
                "song_id": final_song_id,
                "task_id": final_task_id,
                "duration": context.current_duration,
                "segments": len(context.segment_history),
            }
            
        except Exception as e:
            # 失败时退款额度
            from app.services.ai_limits import refund_generation
            refund_generation(user_key)
            raise
        finally:
            task_store.release_lock_for_task(final_task_id)

    async def continue_song(
        self,
        song_id: str,
        continue_from: float,
        duration: int,
        style: Optional[str] = None,
        prompt: Optional[str] = None,
        language: str = "zh",
        user_key: str = "",
        task_id: str = "",
    ) -> Dict[str, Any]:
        """
        手动续写：从指定时间点续写歌曲
        """
        # 获取原歌曲信息
        from app.routers.songs import get_song
        original_song = get_song(song_id)
        if not original_song:
            raise ValueError(f"歌曲不存在: {song_id}")
        
        # 限制续写时长
        max_continuation = 270 - continue_from
        duration = min(duration, max_continuation, 60)
        
        # 创建续写任务
        final_task_id = task_id or task_store.new_task(user_key=user_key)
        if not task_store.acquire_lock(user_key, final_task_id):
            raise RuntimeError("用户已有进行中的任务")
        
        try:
            # 获取原歌曲信息
            original_audio_url = original_song.get("audio_url")
            original_lyrics = original_song.get("lyrics", "")
            original_style = style or original_song.get("style", "pop")
            
            # 创建上下文
            context = SongContext(
                song_id=song_id,
                task_id=final_task_id,
                user_key=user_key,
                target_duration=continue_from + duration,
                current_duration=continue_from,
                genre=original_style,
                style=original_style,
                lyrics=original_lyrics,
            )
            
            # 截取参考音频
            ref_start = max(0, continue_from - REFERENCE_SECONDS)
            ref_end = continue_from
            
            # 获取原音频 URL
            audio_url = await self._get_song_audio_url(song_id)
            
            # 截取参考音频
            ref_wav_bytes, _ = await trim_audio(audio_url, ref_start, ref_end, "wav")
            ref_b64 = base64.b64encode(ref_wav_bytes).decode()
            
            # 音频分析
            analysis = await analyze_audio_context(ref_wav_bytes)
            
            # 歌词续写
            continuation_lyrics = await lyric_service.continue_lyrics(
                existing_lyrics=original_lyrics or "",
                style=original_style,
            )
            
            # ACE-Step Audio2Audio 生成续写段
            gen_result = await self._call_ace_step_audio2audio(
                prompt=f"Continuation from {continue_from:.0f}s, seamless style match, {analysis.get('bpm', 120)} BPM, key {analysis.get('key', 'C')}",
                lyrics=continuation_lyrics.lyrics or "",
                duration=duration,
                reference_audio_b64=ref_b64,
                reference_strength=0.7,
            )
            
            if not gen_result or not gen_result.get("success"):
                raise RuntimeError("ACE-Step Audio2Audio 生成失败")
            
            # 下载生成的续写段
            cont_wav = await ace_step_download(gen_result["volume_files"]["full_wav"])
            
            # FFmpeg crossfade 拼接
            full_wav = await self._crossfade_concat(
                original_audio_url=audio_url,
                continuation_wav=cont_wav,
                crossfade_duration=CROSSFADE_DURATION,
                cut_point=continue_from,
            )
            
            # 上传 R2、创建新 song_id
            new_song_id = await self._create_continued_song(
                original_song=original_song,
                full_wav=full_wav,
                continuation_lyrics=continuation_lyrics.lyrics,
                analysis=analysis,
                user_key=user_key,
            )
            
            return {
                "success": True,
                "song_id": new_song_id,
                "duration": continue_from + duration,
                "continue_from": continue_from,
            }
            
        finally:
            task_store.release_lock_for_task(final_task_id)

    async def _generate_first_segment(
        self,
        prompt: str,
        style: str,
        duration: int,
        lyrics: Optional[str],
        language: str,
        task_id: str,
        context: SongContext,
    ) -> Dict[str, Any]:
        """生成第一段（首次生成）"""
        # 这里复用现有的 /api/v1/ai/generate 逻辑
        # 但需要返回 song_id 和 duration
        # 实际调用现有的生成链路
        from app.routers.ai_music import _run_generation
        
        # 创建临时任务
        temp_task_id = task_id or f"first-{int(time.time())}"
        
        # 调用现有的生成逻辑（简化版）
        # 实际应调用 provider.generate
        from app.services.provider_registry import get_provider_registry
        
        provider = get_provider_registry().select()
        gen_result = await provider.generate({
            "prompt": prompt,
            "lyrics": lyrics or "",
            "duration": duration,
        })
        
        if not gen_result.get("success"):
            return {"success": False, "error": gen_result.get("error")}
        
        # 上传并最终化
        from app.routers.ai_music import _upload_and_finalize
        temp_task_id = f"first-{int(time.time())}"
        await _upload_and_finalize(temp_task_id, gen_result["volume_files"])
        
        # 获取生成的 song_id（从 task_store 获取）
        task = task_store.get(temp_task_id)
        song_id = task.get("song_id", temp_task_id)
        duration = task.get("duration", duration)
        
        return {
            "success": True,
            "song_id": song_id,
            "duration": duration,
        }

    async def _generate_continuation_segment(
        self,
        context: SongContext,
        prompt: str,
        style: str,
        duration: int,
        language: str,
        task_id: str,
    ) -> Dict[str, Any]:
        """生成续写段"""
        # 1. 获取当前最新歌曲的音频 URL
        audio_url = await self._get_song_audio_url(context.song_id)
        
        # 2. 截取参考音频（最后 REFERENCE_SECONDS 秒）
        ref_end = context.current_duration
        ref_start = max(0, context.current_duration - REFERENCE_SECONDS)
        
        # 3. 下载参考音频
        ref_wav_bytes, _ = await trim_audio(
            url=context.song_id,  # song_id 作为 URL 传入，实际应解析为 R2 URL
            start=context.current_duration - REFERENCE_SECONDS,
            end=context.current_duration,
            output_format="wav",
        )
        ref_b64 = base64.b64encode(ref_wav_bytes).decode()
        
        # 3. 音频分析
        analysis = await analyze_audio_context(ref_wav_bytes)
        
        # 4. 歌词续写
        continuation_lyrics = await lyric_service.continue_lyrics(
            existing_lyrics=context.lyrics or "",
            style=context.style or "pop",
        )
        
        # 5. ACE-Step Audio2Audio 生成续写段
        gen_result = await self._call_ace_step_audio2audio(
            prompt=f"Continuation, seamless style match, {context.bpm or 120} BPM, key {context.key or 'C'}",
            lyrics=continuation_lyrics.lyrics or "",
            duration=min(60, duration),
            reference_audio_b64=base64.b64encode(ref_wav_bytes).decode(),
            reference_strength=0.7,
        )
        
        if not gen_result or not gen_result.get("success"):
            return {"success": False, "error": "ACE-Step Audio2Audio 生成失败"}
        
        # 5. 下载生成的续写段
        cont_wav = await ace_step_download(gen_result["volume_files"]["full_wav"])
        
        # 6. FFmpeg crossfade 拼接
        full_wav = await self._crossfade_concat(
            original_audio_url=context.song_id,  # 实际应为 R2 URL
            continuation_wav=cont_wav,
            crossfade_duration=CROSSFADE_DURATION,
            cut_point=context.current_duration,
        )
        
        # 7. 上传 R2、创建新 song 记录
        new_song_id = await self._create_continued_song(
            original_song_id=context.song_id,
            full_wav=full_wav,
            continuation_lyrics=continuation_lyrics.lyrics,
            user_key="",  # 从 context 获取
        )
        
        return {
            "success": True,
            "song_id": new_song_id,
            "duration": duration,
        }

    async def _call_ace_step_audio2audio(
        self,
        prompt: str,
        lyrics: str,
        duration: int,
        reference_audio_b64: str,
        reference_strength: float = 0.7,
    ) -> Dict:
        """调用 ACE-Step Audio2Audio 生成续写段"""
        from app.services.ace_step_client import generate_full_song
        
        result = await ace_step_generate(
            prompt=prompt,
            lyrics=lyrics,
            duration=duration,
            reference_audio=reference_audio_b64,
            enable_audio2audio=True,
            reference_strength=0.7,
        )
        
        if result and result.get("success"):
            return {"success": True, "volume_files": result}
        return {"success": False, "error": "ACE-Step Audio2Audio 生成失败"}

    async def _crossfade_concat(
        self,
        original_audio_url: str,
        continuation_wav: str,
        crossfade_duration: float = 2.0,
        cut_point: float = 0.0,
    ) -> str:
        """
        FFmpeg crossfade 拼接原曲前段 + 续写段
        """
        import subprocess
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 下载原曲前段
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(original_audio_url)
                original_wav = os.path.join(tempfile.gettempdir(), "original.wav")
                with open(original_wav, "wb") as f:
                    f.write(resp.content)
            
            # 截取原曲前段
            original_cut = os.path.join(tmp_dir, "original_cut.wav")
            await trim_audio(original_audio_url, 0, cut_point, "wav")
            
            # FFmpeg crossfade
            output_path = os.path.join(tmp_dir, "combined.wav")
            
            cmd = [
                "ffmpeg", "-y",
                "-i", original_audio_url,  # 原曲
                "-i", continuation_wav,     # 续写段
                "-filter_complex",
                f"[0:a]atrim=0:{cut_point}[a1];"
                f"[1:a]atrim=0:60[a2];"
                f"[a1][a2]acrossfade=d={crossfade_duration}:c1=tri:c2=tri[out]",
                "-map", "[out]",
                "-c:a", "pcm_s16le",
                output_path
            ]
            
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            
            if not os.path.exists(output_path):
                raise RuntimeError("FFmpeg crossfade 失败")
            
            return output_path

    async def _create_continued_song(
        self,
        original_song: Dict,
        full_wav: str,
        continuation_lyrics: str,
        analysis: Dict,
        user_key: str,
    ) -> str:
        """创建续写后的新歌曲记录"""
        from app.services.supabase_service import create_song
        
        new_song_id = f"cont_{int(time.time())}"
        
        # 上传到 R2
        from app.services.cdn_uploader import cdn_uploader
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            files = {"full_wav": full_wav}
            manifest = await cdn_uploader.upload_music_package(f"cont_{int(time.time())}", files)
        
        song_data = {
            "title": f"{original_song.get('title', 'Song')} (Continued)",
            "lyrics": continuation_lyrics,
            "style": original_song.get("style"),
            "duration_seconds": int(original_song.get("duration_seconds", 0)) + 60,
            "audio_url": manifest.get("full_mp3"),
            "volume_files": {"full_wav": manifest.get("full_wav")},
            "bpm": original_song.get("bpm"),
            "key": original_song.get("key"),
        }
        
        song = create_song(
            user_id=user_key,
            **song_data
        )
        
        return song["id"]

    async def _get_song_audio_url(self, song_id: str) -> str:
        """获取歌曲的 R2 预签名播放 URL"""
        from app.routers.songs import get_song
        from app.routers.ai_music import _sign_for_playback
        
        song = get_song(song_id)
        if not song:
            raise ValueError(f"Song not found: {song_id}")
        
        manifest = song.get("download", {})
        return _sign_for_playback(song_id, "full_mp3", manifest) or ""

    async def _save_context(self, task_id: str, context: "SongContext"):
        """保存 SongContext 到 task_store"""
        task_store.update(task_id, context=context.to_dict())

    async def _update_context_from_segment(self, context: SongContext, segment_result: Dict):
        """从新段更新上下文"""
        # 从新段提取音乐特征更新上下文
        pass

    async def _finalize_song(self, context: "SongContext", task_id: str) -> str:
        """最终拼接所有段落，生成最终完整歌曲"""
        # 如果只有一段，直接返回
        if len(context.segment_history) == 1:
            return context.segment_history[0]["song_id"]
        
        # 多段拼接逻辑
        # 简化：返回最后一段的 song_id
        return context.segment_history[-1]["song_id"]


# 全局服务实例
continuation_service = ContinuationService()