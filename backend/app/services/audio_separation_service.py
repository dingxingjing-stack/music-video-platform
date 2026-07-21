"""
音频分离服务 (Spleeter 5stems) - 进程内常驻单例版本
使用 Spleeter 5stems 模型进行人声/鼓/贝斯/其他/伴奏 5 轨分离
输出对前端对齐 4 轨接口：vocals/drums/bass/other

核心架构：
- 彻底替换 Demucs，单进程内 Spleeter Separator 单例常驻
- 仅首次请求加载 5stems 模型（约 70MB），后续复用内存
- Spleeter 原生 5 轨输出：vocals, drums, bass, other, accompaniment
  → 业务上对齐前端消费约定，丢弃 accompaniment，保留 4 轨
- 复用原有临时目录、wav 输出、自动清理逻辑
- 保留 10 秒音频时长校验、异常捕获、进度日志
"""

import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Optional, Callable, List

import librosa
import numpy as np


# 全局单例 Separator 缓存（懒加载，线程安全）
_SEPARATOR = None
_SEPARATOR_LOCK = threading.Lock()
_SPLEETER_AVAILABLE: Optional[bool] = None
_AVAILABLE_LOCK = threading.Lock()


def _check_spleeter_available() -> bool:
    """懒加载检查 spleeter 是否可用（线程安全，仅首次调用时检查）"""
    global _SPLEETER_AVAILABLE
    if _SPLEETER_AVAILABLE is not None:
        return _SPLEETER_AVAILABLE
    with _AVAILABLE_LOCK:
        if _SPLEETER_AVAILABLE is not None:
            return _SPLEETER_AVAILABLE
        try:
            import spleeter  # noqa: F401
            _SPLEETER_AVAILABLE = True
        except ImportError:
            _SPLEETER_AVAILABLE = False
            print("⚠️  Spleeter 未安装，音频分离功能将使用 Mock 模式")
        return _SPLEETER_AVAILABLE


def _get_separator():
    """获取单例 Separator 实例（懒加载，线程安全）"""
    global _SEPARATOR
    if _SEPARATOR is not None:
        return _SEPARATOR
    
    if not _check_spleeter_available():
        return None
    
    with _SEPARATOR_LOCK:
        if _SEPARATOR is not None:
            return _SEPARATOR
        try:
            from spleeter.separator import Separator
            
            print("🔄 正在加载 Spleeter Separator (5stems)...")
            # 关闭多进程 Spleeter 内部多 worker，保持 WEB_CONCURRENCY=1
            # 使用预训练模型 '5stems'，固定使用 tensorflow 默认 backend
            _SEPARATOR = Separator('spleeter:5stems', multiprocess=False)
            print(f"✅ Spleeter 5stems 已加载，常驻内存（~70MB）")
            return _SEPARATOR
        except Exception as e:
            print(f"❌ Spleeter Separator 初始化失败：{e}")
            return None


class DemucsService:
    """音频分离服务 - Spleeter 5stems 适配版
    
    类名保持 DemucsService 是为了兼容性（router 端 import 路径不变）
    实际底层实现已切换为 Spleeter
    """
    
    # 对前端输出 4 轨：vocals/drums/bass/other
    STEM_NAMES = ["vocals", "drums", "bass", "other"]
    
    # 音频时长限制（秒）— 适配 Render 512MB 内存上限
    MAX_AUDIO_DURATION = 10.0
    
    # 兼容字段（保留，便于 router 端使用与历史接口一致）
    MODELS = {
        "htdemucs": "高性能 Demucs 5 轨（保留兼容说明，实际由 Spleeter 提供）",
        "htdemucs_ft": "Demucs 微调版（保留兼容说明）",
        "htdemucs_6s": "Demucs 6 轨（保留兼容说明）",
    }
    
    def __init__(self, output_dir: Optional[str] = None):
        if output_dir:
            self.output_dir = Path(output_dir)
            self.output_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.output_dir = Path(tempfile.gettempdir()) / "demucs_output"
            self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def separate(
        self,
        input_path: str,
        model: str = "htdemucs",
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> dict:
        """分离音频为 4 轨（Spleeter 5stems 内部处理，丢弃 accompaniment）"""
        # 1. 基础校验
        input_path = Path(input_path)
        if not input_path.exists():
            return {
                "success": False, "stems": [], "duration": 0,
                "message": f"文件不存在：{input_path}"
            }
        
        # 2. 时长校验
        try:
            duration = librosa.get_duration(path=str(input_path))
        except Exception as e:
            return {
                "success": False, "stems": [], "duration": 0,
                "message": f"无法读取音频时长：{e}"
            }
        
        if duration > self.MAX_AUDIO_DURATION:
            return {
                "success": False, "stems": [], "duration": duration,
                "message": f"音频过长：{duration:.1f}s，最大允许 {self.MAX_AUDIO_DURATION}s（512MB 内存保护）"
            }
        
        # 3. 获取 Separator 单例
        if not _check_spleeter_available():
            return self._mock_separate(input_path, progress_callback)
        
        separator = _get_separator()
        if separator is None:
            return {
                "success": False, "stems": [], "duration": duration,
                "message": "Separator 初始化失败，请检查日志"
            }
        
        # 4. 准备输出目录
        stem_name = input_path.stem
        temp_output = self.output_dir / stem_name
        if temp_output.exists():
            shutil.rmtree(temp_output)
        temp_output.mkdir(parents=True, exist_ok=True)
        
        # 5. 读取音频
        if progress_callback:
            progress_callback(0.1)
        print(f"📥 读取音频：{input_path}")
        
        try:
            waveform, sample_rate = librosa.load(str(input_path), sr=None, mono=False)
        except Exception as e:
            return {
                "success": False, "stems": [], "duration": duration,
                "message": f"音频读取失败：{e}"
            }
        
        # Spleeter 要求格式: (channels, samples) float32
        if waveform.ndim == 1:
            waveform = np.stack([waveform, waveform], axis=0)  # 单声道转双声道
        elif waveform.shape[0] == 1:
            waveform = np.concatenate([waveform, waveform], axis=0)
        elif waveform.shape[0] > 2:
            waveform = waveform[:2, :]
        
        # 重采样到 44100（Spleeter 期望）
        if sample_rate != 44100:
            waveform = librosa.resample(waveform, orig_sr=sample_rate, target_sr=44100, axis=-1)
            sample_rate = 44100
        
        # 转为 shape: (batch, channels, samples) = (1, 2, samples)
        waveform_input = waveform.astype(np.float32)[np.newaxis, :, :]
        
        if progress_callback:
            progress_callback(0.3)
        
        # 6. Spleeter 核心分离
        print("🔄 执行 Spleeter 5stems 分离...")
        try:
            prediction = separator.separate(waveform_input)
            # prediction shape: (1, 5, 2, samples)
            stems_data = prediction[0]  # (5, 2, samples)
            
            if progress_callback:
                progress_callback(0.8)
            
            # 7. 保存 4 轨（丢弃 accompaniment）
            # Spleeter 5stems 输出顺序固定: ['vocals', 'drums', 'bass', 'other', 'accompaniment']
            spleeter_stem_order = ['vocals', 'drums', 'bass', 'other', 'accompaniment']
            
            import soundfile as sf
            
            stems = []
            for target_name in self.STEM_NAMES:  # vocals/drums/bass/other
                idx = spleeter_stem_order.index(target_name)
                stem_audio = stems_data[idx]  # (2, samples)
                
                # 转单声道保存（接口约定）
                stem_mono = stem_audio.mean(axis=0)  # (samples,)
                
                stem_path = temp_output / f"{target_name}.wav"
                sf.write(
                    str(stem_path),
                    stem_mono,
                    sample_rate,
                    subtype="PCM_16"  # 16-bit 输出
                )
                stems.append(str(stem_path))
                print(f"  ✅ 已保存：{stem_path}")
            
            if progress_callback:
                progress_callback(1.0)
            
            return {
                "success": True,
                "stems": stems,
                "duration": duration,
                "message": f"分离成功，{len(stems)} 轨音频（Spleeter 5stems）"
            }
            
        except Exception as e:
            print(f"❌ Spleeter 分离失败：{e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False, "stems": [], "duration": duration,
                "message": f"Spleeter 分离失败：{str(e)}"
            }
    
    def _mock_separate(
        self,
        input_path: Path,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> dict:
        """Mock 模式——Spleeter 未安装或初始化失败时退回"""
        import time
        for i in range(20):
            if progress_callback:
                progress_callback((i + 1) / 20)
            time.sleep(0.2)
        if progress_callback:
            progress_callback(1.0)
        return {
            "success": True,
            "stems": [str(input_path)] * 4,
            "duration": 3.0,
            "message": "Mock 模式：Spleeter 未安装 (pip install spleeter)"
        }
    
    def get_available_models(self) -> List[str]:
        """保持与原有路由契约一致，返回 3 个模型名称字符串"""
        if _check_spleeter_available():
            return ["htdemucs", "htdemucs_ft", "htdemucs_6s"]
        return ["mock"]


# 全局实例（轻量级初始化，不加载模型，也不导入 spleeter）
demucs_service = DemucsService()