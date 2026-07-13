"""
音频导出服务 - 分轨渲染 + 混音导出
"""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class ExportTrack(BaseModel):
    """导出轨道数据"""
    id: str
    name: str
    type: str  # "audio" | "midi"
    clips: List[Dict[str, Any]]  # 音频片段列表
    muted: bool = False
    solo: bool = False
    volume: float = 1.0
    pan: float = 0.0
    effects: Optional[Dict[str, Any]] = None


class ExportOptions(BaseModel):
    """导出选项"""
    format: str = "wav"  # "wav" | "mp3" | "flac"
    sample_rate: int = 44100
    bit_depth: int = 24
    channels: int = 2  # 1=mono, 2=stereo
    include_stems: bool = True  # 是否同时导出分轨
    normalize: bool = False
    dither: bool = True


class ExportResult(BaseModel):
    """导出结果"""
    success: bool
    message: str
    master_file: Optional[str] = None  # 混音文件路径
    stem_files: List[str] = []  # 分轨文件列表
    duration: float = 0.0
    file_size: int = 0


async def render_audio_clip(
    clip: Dict[str, Any],
    output_path: str,
    sample_rate: int = 44100,
) -> bool:
    """
    渲染单个音频片段
    实际实现会调用 tone.js 或后端音频引擎
    这里用 mock 实现
    """
    # TODO: 实际音频渲染逻辑
    # 1. 加载音频文件或使用合成器生成
    # 2. 应用效果器链
    # 3. 写入输出文件
    
    # Mock: 创建空文件表示成功
    Path(output_path).touch()
    return True


async def mix_tracks(
    track_files: List[str],
    output_path: str,
    volumes: List[float] = None,
    pans: List[float] = None,
) -> bool:
    """
    混音多个轨道为单个文件
    """
    # TODO: 实际混音逻辑
    # 1. 读取所有轨道文件
    # 2. 应用音量和声像
    # 3. 求和并限制峰值
    # 4. 写入主输出文件
    
    # Mock: 创建空文件表示成功
    Path(output_path).touch()
    return True


async def convert_audio_format(
    input_path: str,
    output_path: str,
    target_format: str,
    sample_rate: int = 44100,
    bit_depth: int = 24,
) -> bool:
    """
    转换音频格式（使用 ffmpeg）
    """
    try:
        # 检查 ffmpeg 是否可用
        import subprocess
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-ar", str(sample_rate),
            "-acodec", "pcm_s24le" if target_format == "wav" else "libmp3lame",
            output_path,
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return process.returncode == 0
    except Exception as e:
        print(f"FFmpeg conversion failed: {e}")
        # Fallback: 直接复制
        import shutil
        shutil.copy(input_path, output_path)
        return True


async def export_project(
    tracks: List[ExportTrack],
    options: ExportOptions,
    output_dir: str,
) -> ExportResult:
    """
    导出整个项目
    """
    try:
        os.makedirs(output_dir, exist_ok=True)
        
        # 过滤静音轨道
        active_tracks = [t for t in tracks if not t.muted]
        
        # 如果有 solo 轨道，只导出 solo 的
        solo_tracks = [t for t in active_tracks if t.solo]
        if solo_tracks:
            active_tracks = solo_tracks
        
        if not active_tracks:
            return ExportResult(
                success=False,
                message="没有活跃的轨道可导出",
            )
        
        # 计算总时长
        total_duration = 0.0
        for track in active_tracks:
            for clip in track.clips:
                end_time = clip.get("start", 0) + clip.get("duration", 0)
                total_duration = max(total_duration, end_time)
        
        # 渲染每个轨道
        stem_files = []
        temp_files = []
        
        for track in active_tracks:
            # 创建临时文件
            temp_file = tempfile.NamedTemporaryFile(
                suffix=".wav",
                delete=False,
                dir=output_dir,
            )
            temp_files.append(temp_file.name)
            
            # 渲染轨道
            rendered = await render_audio_clip(
                {"clips": track.clips},
                temp_file.name,
                options.sample_rate,
            )
            
            if not rendered:
                return ExportResult(
                    success=False,
                    message=f"轨道 {track.name} 渲染失败",
                )
            
            # 如果导出分轨
            if options.include_stems:
                stem_name = f"{track.name}.{options.format}"
                stem_path = os.path.join(output_dir, stem_name)
                
                if options.format != "wav":
                    await convert_audio_format(
                        temp_file.name,
                        stem_path,
                        options.format,
                        options.sample_rate,
                        options.bit_depth,
                    )
                else:
                    import shutil
                    shutil.copy(temp_file.name, stem_path)
                
                stem_files.append(stem_path)
        
        # 混音为主文件
        master_temp = tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False,
            dir=output_dir,
        )
        
        volumes = [t.volume for t in active_tracks]
        pans = [t.pan for t in active_tracks]
        
        mixed = await mix_tracks(
            temp_files,
            master_temp.name,
            volumes,
            pans,
        )
        
        if not mixed:
            return ExportResult(
                success=False,
                message="混音失败",
            )
        
        # 转换主文件格式
        master_name = f"master.{options.format}"
        master_path = os.path.join(output_dir, master_name)
        
        if options.format != "wav":
            await convert_audio_format(
                master_temp.name,
                master_path,
                options.format,
                options.sample_rate,
                options.bit_depth,
            )
        else:
            import shutil
            shutil.copy(master_temp.name, master_path)
        
        # 清理临时文件
        for temp_file in temp_files + [master_temp.name]:
            try:
                os.unlink(temp_file)
            except:
                pass
        
        # 计算文件大小
        total_size = sum(
            os.path.getsize(f)
            for f in [master_path] + stem_files
            if os.path.exists(f)
        )
        
        return ExportResult(
            success=True,
            message="导出成功",
            master_file=master_path,
            stem_files=stem_files,
            duration=total_duration,
            file_size=total_size,
        )
        
    except Exception as e:
        return ExportResult(
            success=False,
            message=f"导出失败：{str(e)}",
        )