"""
歌曲续写编排服务 — 300s 分段生成核心
流程：
  150s 首段 (真实 provider) -> 截取末尾 30s 参考音频 -> 分析 BPM/key -> 歌词续写 -> 150s Audio2Audio 续写段 (独立重试) -> FFmpeg crossfade 拼接 -> R2 上传最终 300s
兼容：duration <=180 走单段，不进入此服务
"""
import asyncio
import base64
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from app.services.ai_limits import MAX_AUTO_RETRIES
from app.services import task_store

DEFAULT_SEGMENT_DURATION = 150
CROSSFADE_DURATION = 1.5

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
    def __init__(self):
        self.temp_dir = tempfile.gettempdir()

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
    ) -> Dict[str, Any]:
        """
        150+150 300s 长生成 — 单任务视角，对外只暴露一个 task_id
        1. 首段 150s (真实 provider)
        2. 第二段 150s 基于首段末尾 30s 的 Audio2Audio (独立重试)
        3. FFmpeg 1.5s crossfade 拼接 (独立重试)
        4. R2 上传最终 full_wav/full_mp3 + 中间段保留
        """
        # 限制目标
        target = min(int(duration), 300)
        if target <= 180:
            raise ValueError("generate_long_music 仅用于 >180s，短时长请走单段")

        # 分段：240->150+90, 300->150+150
        first_dur = 150
        second_dur = target - first_dur

        task_store.update(task_id, state="processing", progress=5)
        provider = None
        from app.services.provider_registry import get_provider_registry
        provider = get_provider_registry().select()  # RunPod (300) / fallback

        # ── 第一段 150s (真实 provider, 不重试绕过首段) ──
        task_store.update(task_id, state="generating", progress=10)
        first_result = await self._generate_single_segment(
            provider=provider,
            prompt=prompt,
            lyrics=lyrics or "",
            duration=first_dur,
            reference_b64=None,
            enable_a2a=False,
        )
        if not first_result or not first_result.get("success"):
            raise RuntimeError(f"首段 150s 生成失败: {first_result.get('error') if first_result else 'unknown'}")

        first_files = first_result.get("volume_files") or {}
        first_local = self._resolve_local_path(first_files)
        if not first_local or not os.path.exists(first_local):
            raise RuntimeError("首段本地文件丢失")

        task_store.update(task_id, progress=40)
        # 中间段先上传 R2 保留（可选，但满足“中间片段保存到 R2”）
        part1_manifest = await self._upload_parts(task_id, {"part1_wav": first_local}, suffix="part1")

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
        task_store.update(task_id, state="generating_continuation", progress=50)
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
        task_store.update(task_id, progress=70)
        part2_manifest = await self._upload_parts(task_id, {"part2_wav": second_local}, suffix="part2")

        # ── FFmpeg 拼接 (独立重试，不重跑 GPU) ──
        task_store.update(task_id, state="stitching", progress=80)
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

        task_store.update(task_id, progress=85)
        # 验证时长接近目标（±5s）
        try:
            import librosa
            dur = librosa.get_duration(path=combined_path)
            if abs(dur - target) > 5:
                print(f"[Continuation] 警告：合并后时长 {dur:.1f}s 与目标 {target}s 偏差 >5s")
        except Exception:
            pass

        # ── R2 最终上传 ──
        task_store.update(task_id, state="uploading", progress=90)
        final_manifest = await self._upload_final(task_id, combined_path, part1_manifest, part2_manifest)
        # task_store 写入最终 manifest，由 ai_music._upload_and_finalize 风格的 manifest 驱动播放
        return {
            "success": True,
            "volume_files": {"full_wav": os.path.basename(combined_path), "_local_path": combined_path},
            "manifest": final_manifest,
            "provider": f"{provider.name}+continuation",
            "segments": 2,
            
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

    def _resolve_local_path(self, volume_files: Dict) -> Optional[str]:
        if not volume_files:
            return None
        # 优先 _local_path（RunPod/Fal 已下载）
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
                    from app.services.runpod_client import local_dir as runpod_local_dir
                    cand = os.path.join(runpod_local_dir(), os.path.basename(v))
                    if os.path.exists(cand):
                        return cand
                except Exception:
                    pass
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
        # 使用 ffmpeg 的 acrossfade filter，1.5s 三角过渡
        cmd = [
            "ffmpeg", "-y",
            "-i", first_path,
            "-i", second_path,
            "-filter_complex", f"[0:a][1:a]acrossfade=d={crossfade}:c1=tri:c2=tri[a]",
            "-map", "[a]",
            "-c:a", "pcm_s16le",
            out_path
        ]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode(errors="replace")[:800] if stderr else "unknown"
            raise RuntimeError(f"ffmpeg acrossfade failed: {err}")
        if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
            raise RuntimeError("ffmpeg 输出为空")
        return out_path

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
    async def generate_full_song(self, *args, **kwargs):
        # limit to 270 legacy, but for >180 delegate to long
        duration = kwargs.get("duration") or (args[2] if len(args)>2 else 180)
        if int(duration) > 180:
            return await self.generate_long_music(*args, **kwargs)
        # fallback to single
        return await self.generate_long_music(*args, **kwargs)

# 全局实例
continuation_service = ContinuationService()
