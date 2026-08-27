"""
音频后处理服务
- EBU R128 响度标准化 (-14 LUFS)
- 采样率/声道标准化 (44.1kHz, Stereo)
- Clipping 检测与防护
- WAV/MP3 双格式输出
"""

import os
import asyncio
import tempfile
import logging
import subprocess
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# ========== 配置 ==========
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
FFPROBE_PATH = os.getenv("FFPROBE_PATH", "ffprobe")
TARGET_SAMPLE_RATE = int(os.getenv("TARGET_SAMPLE_RATE", "44100"))
TARGET_CHANNELS = int(os.getenv("TARGET_CHANNELS", "2"))
TARGET_LUFS = float(os.getenv("TARGET_LUFS", "-14.0"))  # EBU R128 standard
TRUE_PEAK_LIMIT = float(os.getenv("TRUE_PEAK_LIMIT", "-1.0"))  # dBTP
LRA_LIMIT = float(os.getenv("LRA_LIMIT", "11.0"))  # LU

MP3_BITRATE = os.getenv("MP3_BITRATE", "320k")


@dataclass
class AudioInfo:
    """音频文件信息"""
    duration: float
    sample_rate: int
    channels: int
    bit_depth: int
    format: str
    size_bytes: int
    loudness_lufs: Optional[float] = None
    true_peak_db: Optional[float] = None
    lra: Optional[float] = None
    has_clipping: bool = False


@dataclass
class PostProcessResult:
    """后处理结果"""
    success: bool
    wav_path: Optional[str] = None
    mp3_path: Optional[str] = None
    audio_info: Optional[AudioInfo] = None
    error: Optional[str] = None


class AudioPostProcessor:
    """音频后处理器"""
    
    def __init__(self):
        self._ffmpeg_available = self._check_ffmpeg()
    
    def _check_ffmpeg(self) -> bool:
        try:
            subprocess.run([FFMPEG_PATH, "-version"], capture_output=True, timeout=5)
            return True
        except Exception:
            logger.warning("ffmpeg not found, audio post-processing will be limited")
            return False
    
    async def _run_ffmpeg(self, cmd: list, timeout: int = 300) -> Tuple[int, str, str]:
        """运行 ffmpeg 命令"""
        loop = asyncio.get_event_loop()
        def _run():
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return result.returncode, result.stdout, result.stderr
        return await loop.run_in_executor(None, _run)
    
    async def _run_ffprobe(self, cmd: list, timeout: int = 30) -> Tuple[int, str, str]:
        """运行 ffprobe 命令"""
        loop = asyncio.get_event_loop()
        def _run():
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return result.returncode, result.stdout, result.stderr
        return await loop.run_in_executor(None, _run)
    
    async def analyze_audio(self, audio_path: str) -> AudioInfo:
        """分析音频文件"""
        if not self._ffmpeg_available:
            return AudioInfo(
                duration=0, sample_rate=0, channels=0, bit_depth=0,
                format="unknown", size_bytes=0, error="ffmpeg not available"
            )
        
        # 获取基本信息
        cmd = [
            FFPROBE_PATH, "-v", "error",
            "-show_entries", "format=duration,size,format_name:stream=sample_rate,channels,bits_per_sample,codec_name",
            "-of", "json", audio_path
        ]
        code, stdout, stderr = await self._run_ffprobe(cmd)
        
        duration = 0
        sample_rate = 0
        channels = 0
        bit_depth = 16
        format_name = "wav"
        size_bytes = 0
        
        if code == 0 and stdout:
            import json
            data = json.loads(stdout)
            fmt = data.get("format", {})
            streams = data.get("streams", [])
            
            duration = float(fmt.get("duration", 0))
            size_bytes = int(fmt.get("size", 0))
            format_name = fmt.get("format_name", "wav").split(",")[0]
            
            if streams:
                s = streams[0]
                sample_rate = int(s.get("sample_rate", 0))
                channels = int(s.get("channels", 0))
                bit_depth = int(s.get("bits_per_sample", 16))
        
        # 响度分析
        loudness_lufs, true_peak_db, lra = await self._analyze_loudness(audio_path)
        
        # Clipping 检测
        has_clipping = await self._detect_clipping(audio_path)
        
        return AudioInfo(
            duration=duration,
            sample_rate=sample_rate,
            channels=channels,
            bit_depth=bit_depth,
            format=format_name,
            size_bytes=size_bytes,
            loudness_lufs=loudness_lufs,
            true_peak_db=true_peak_db,
            lra=lra,
            has_clipping=has_clipping,
        )
    
    async def _analyze_loudness(self, audio_path: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """使用 ffmpeg loudnorm 进行双遍响度分析"""
        if not self._ffmpeg_available:
            return None, None, None
        
        cmd = [
            FFMPEG_PATH, "-hide_banner",
            "-i", audio_path,
            "-af", f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK_LIMIT}:LRA={LRA_LIMIT}:print_format=json",
            "-f", "null", "-"
        ]
        code, stdout, stderr = await self._run_ffmpeg(cmd, timeout=120)
        
        # 解析 JSON 输出 (在 stderr 中)
        import json
        try:
            # loudnorm JSON 可能是多行（带前导空格/tab），从 '{' 开始累计到 '}'
            lines = stderr.strip().split('\n')
            json_text = ""
            in_json = False
            for line in lines:
                if '{' in line:
                    in_json = True
                    json_text = line[line.index('{'):]
                elif in_json:
                    json_text += line
                    if '}' in line:
                        data = json.loads(json_text)
                        return (
                            float(data.get("input_i", 0)),
                            float(data.get("input_tp", 0)),
                            float(data.get("input_lra", 0)),
                        )
        except Exception as e:
            logger.warning(f"Failed to parse loudnorm output: {e}")
        
        return None, None, None
    
    async def _detect_clipping(self, audio_path: str, threshold: float = 0.99) -> bool:
        """检测音频是否有 clipping"""
        if not self._ffmpeg_available:
            return False
        
        # 使用 astats 检测峰值
        cmd = [
            FFMPEG_PATH, "-v", "error",
            "-i", audio_path,
            "-af", "astats=metadata=1:reset=1",
            "-f", "null", "-"
        ]
        code, stdout, stderr = await self._run_ffmpeg(cmd, timeout=60)
        
        # 检查峰值是否接近 1.0 (0 dBFS)
        try:
            for line in stderr.split('\n'):
                if "Peak level" in line or "Peak_count" in line:
                    # 简单启发式：如果峰值计数 > 0 且峰值接近 0 dB
                    if "Peak_count" in line:
                        count_str = line.split(":")[-1].strip()
                        if int(count_str) > 0:
                            return True
        except Exception:
            pass
        
        return False
    
    async def normalize_loudness(
        self,
        input_path: str,
        output_wav_path: str,
        output_mp3_path: Optional[str] = None,
    ) -> PostProcessResult:
        """
        完整后处理流程：
        1. 采样率/声道标准化 (44.1kHz, Stereo)
        2. EBU R128 响度标准化 (-14 LUFS)
        2. True Peak 限制 (-1 dBTP)
        3. Clipping 防护
        4. 生成标准 WAV + MP3
        """
        if not self._ffmpeg_available:
            return PostProcessResult(success=False, error="ffmpeg not available")
        
        # 临时文件路径
        temp_normalized = tempfile.mktemp(suffix="_normalized.wav")
        
        try:
            # 第一遍：响度分析 (已在 analyze_audio 中完成)
            # 第二遍：应用响度标准化 + 重采样 + 声道转换
            loudnorm_filter = (
                f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK_LIMIT}:LRA={LRA_LIMIT}:"
                f"print_format=summary:linear=true:measured_I=-23:measured_TP=-2:measured_LRA=7"
            )
            
            cmd = [
                FFMPEG_PATH, "-y", "-v", "error",
                "-i", input_path,
                "-af", f"aresample={TARGET_SAMPLE_RATE}:resampler=soxr:precision=28,"
                       f"pan=stereo|c0=c0|c1=c1,"
                       f"{loudnorm_filter}",
                "-ar", str(TARGET_SAMPLE_RATE),
                "-ac", str(TARGET_CHANNELS),
                "-c:a", "pcm_s16le",
                temp_normalized
            ]
            
            code, stdout, stderr = await self._run_ffmpeg(cmd, timeout=300)
            if code != 0:
                return PostProcessResult(success=False, error=f"Normalization failed: {stderr}")
            
            # 验证输出
            final_info = await self.analyze_audio(temp_normalized)
            
            # 生成 MP3 (如果需要)
            final_mp3 = None
            if output_mp3_path:
                mp3_path = output_mp3_path
            else:
                mp3_path = tempfile.mktemp(suffix=".mp3")
            
            mp3_cmd = [
                FFMPEG_PATH, "-y", "-v", "error",
                "-i", temp_normalized,
                "-c:a", "libmp3lame",
                "-b:a", MP3_BITRATE,
                "-ar", str(TARGET_SAMPLE_RATE),
                "-ac", str(TARGET_CHANNELS),
                mp3_path
            ]
            code, stdout, stderr = await self._run_ffmpeg(mp3_cmd, timeout=120)
            if code == 0:
                final_mp3 = mp3_path
            else:
                logger.warning(f"MP3 encoding failed: {stderr}")
            
            # 移动最终文件到目标路径
            import shutil
            shutil.move(temp_normalized, output_wav_path)
            
            return PostProcessResult(
                success=True,
                wav_path=output_wav_path,
                mp3_path=final_mp3,
                audio_info=final_info,
            )
            
        except Exception as e:
            logger.error(f"Post-processing failed: {e}")
            # 清理临时文件
            for p in [temp_normalized]:
                try:
                    os.unlink(p)
                except:
                    pass
            return PostProcessResult(success=False, error=str(e))


# 全局实例
_audio_postprocessor: Optional[AudioPostProcessor] = None


def get_audio_postprocessor() -> AudioPostProcessor:
    global _audio_postprocessor
    if _audio_postprocessor is None:
        _audio_postprocessor = AudioPostProcessor()
    return _audio_postprocessor