"""
音频分离服务 (Demucs) - 进程内常驻模型版本
使用 Meta 开源 Demucs 模型进行音频分离（人声/鼓/贝斯/其他 四轨分离）

核心改造：
- 彻底移除 subprocess 调用 demucs CLI
- 改用原生 Python API：load_model + apply_model
- 模型单例常驻主进程内存，仅首次请求加载一次，后续复用
- 消除 "每次请求重复加载模型" 导致的内存峰值
"""

import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Optional, Callable, List

import librosa
import soundfile as sf
import torch
import torchaudio


# 全局模型缓存（懒加载，线程安全）
_DEMUCS_MODEL = None
_MODEL_NAME = "htdemucs"  # 固定使用 htdemucs，避免多模型占内存
_MODEL_LOCK = threading.Lock()
_AVAILABLE = None
_AVAILABLE_LOCK = threading.Lock()


def _check_demucs_available() -> bool:
    """懒加载检查 demucs 是否可用（线程安全，仅首次调用时检查）"""
    global _AVAILABLE
    if _AVAILABLE is not None:
        return _AVAILABLE
    with _AVAILABLE_LOCK:
        if _AVAILABLE is not None:
            return _AVAILABLE
        try:
            import demucs  # noqa: F401
            _AVAILABLE = True
        except ImportError:
            _AVAILABLE = False
            print("⚠️  Demucs 未安装，音频分离功能将使用 Mock 模式")
        return _AVAILABLE


def _get_model() -> Optional[torch.nn.Module]:
    """获取单例模型实例（懒加载，线程安全）"""
    global _DEMUCS_MODEL
    if _DEMUCS_MODEL is not None:
        return _DEMUCS_MODEL
    
    if not _check_demucs_available():
        return None
    
    with _MODEL_LOCK:
        if _DEMUCS_MODEL is not None:
            return _DEMUCS_MODEL
        try:
            # 使用 demucs 预训练模型加载器（Dockerfile 已预下载到 TORCH_HOME）
            from demucs.pretrained import get_model
            print(f"🔄 正在加载 Demucs 模型 ({_MODEL_NAME})...")
            _DEMUCS_MODEL = get_model(_MODEL_NAME)
            _DEMUCS_MODEL.eval()
            # 强制 CPU 推理（Render 免费实例无 GPU）
            _DEMUCS_MODEL.to("cpu")
            print(f"✅ Demucs 模型加载完成，常驻内存")
            return _DEMUCS_MODEL
        except Exception as e:
            print(f"❌ Demucs 模型加载失败：{e}")
            return None


class DemucsService:
    """Demucs 音频分离服务（进程内常驻模型版本）"""
    
    # 输出轨道名称
    STEM_NAMES = ["vocals", "drums", "bass", "other"]
    
    # 音频时长限制（秒）— 适配 Render 512MB 内存上限
    MAX_AUDIO_DURATION = 10.0
    
    def __init__(self, output_dir: Optional[str] = None):
        """
        初始化服务（轻量级，不加载模型）
        
        Args:
            output_dir: 输出目录，默认使用系统临时目录
        """
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
        """
        分离音频为多轨（进程内推理，模型常驻内存）
        
        Args:
            input_path: 输入音频文件路径
            model: 模型名称（当前仅支持 htdemucs）
            progress_callback: 进度回调 (0.0-1.0)
        
        Returns:
            {
                "success": bool,
                "stems": List[str],  # 分离后的文件路径
                "duration": float,   # 音频时长 (秒)
                "message": str
            }
        """
        # 1. 基础校验
        input_path = Path(input_path)
        if not input_path.exists():
            return {
                "success": False,
                "stems": [],
                "duration": 0,
                "message": f"文件不存在：{input_path}"
            }
        
        # 2. 音频时长前置校验（双层保护：router 层 + service 层）
        try:
            duration = librosa.get_duration(path=str(input_path))
        except Exception as e:
            return {
                "success": False,
                "stems": [],
                "duration": 0,
                "message": f"无法读取音频时长：{e}"
            }
        
        if duration > self.MAX_AUDIO_DURATION:
            return {
                "success": False,
                "stems": [],
                "duration": duration,
                "message": f"音频过长：{duration:.1f}s，最大允许 {self.MAX_AUDIO_DURATION}s（512MB 内存保护）"
            }
        
        # 3. 获取模型实例（懒加载单例）
        if not _check_demucs_available():
            return self._mock_separate(input_path, progress_callback)
        
        model_instance = _get_model()
        if model_instance is None:
            return {
                "success": False,
                "stems": [],
                "duration": duration,
                "message": "模型加载失败，请检查日志"
            }
        
        # 4. 准备输出目录
        temp_output = self.output_dir / input_path.stem
        if temp_output.exists():
            shutil.rmtree(temp_output)
        temp_output.mkdir(parents=True, exist_ok=True)
        
        try:
            # 5. 读取音频（使用 torchaudio，保持张量格式）
            print(f"📥 读取音频：{input_path}")
            waveform, sample_rate = torchaudio.load(str(input_path))
            
            # 确保单声道转立体声（Demucs 期望 [channels, samples]）
            if waveform.shape[0] == 1:
                waveform = waveform.repeat(2, 1)
            elif waveform.shape[0] > 2:
                waveform = waveform[:2, :]
            
            # 重采样到 44.1kHz（Demucs 要求）
            if sample_rate != 44100:
                waveform = torchaudio.functional.resample(waveform, sample_rate, 44100)
                sample_rate = 44100
            
            # 添加 batch 维度：[batch=1, channels, samples]
            waveform = waveform.unsqueeze(0)
            
            if progress_callback:
                progress_callback(0.1)
            
            # 6. 执行推理（核心：apply_model，进程内、无子进程、模型已加载）
            print("🔄 执行 Demucs 推理（segment=4, shifts=1, overlap=0.25）...")
            
            from demucs.apply import apply_model
            
            with torch.no_grad():  # 关闭梯度，降低显存/内存
                sources = apply_model(
                    model_instance,
                    waveform,
                    device="cpu",
                    segment=4,        # 分片 4 秒（默认 7.8s），降低推理峰值内存
                    shifts=1,         # 单次推理（默认 2），减少内存开销
                    overlap=0.25,     # 重叠比例
                    split=True,       # 启用分片
                    progress=progress_callback is not None,
                )
            
            if progress_callback:
                progress_callback(0.8)
            
            # 7. 保存分离结果
            # sources shape: [batch, sources, channels, samples]
            sources = sources.squeeze(0)  # 去掉 batch 维度
            
            stems = []
            for i, stem_name in enumerate(self.STEM_NAMES):
                stem_audio = sources[i]  # [channels, samples]
                
                # 转为单声道保存（或保留立体声）
                if stem_audio.shape[0] == 2:
                    stem_mono = stem_audio.mean(dim=0, keepdim=True)  # 转单声道
                else:
                    stem_mono = stem_audio
                
                stem_path = temp_output / f"{stem_name}.wav"
                sf.write(
                    str(stem_path),
                    stem_mono.squeeze().numpy(),
                    sample_rate,
                    subtype="PCM_16"  # 16-bit 输出，文件更小、内存更省
                )
                stems.append(str(stem_path))
                print(f"  ✅ 已保存：{stem_path}")
            
            if progress_callback:
                progress_callback(1.0)
            
            return {
                "success": True,
                "stems": stems,
                "duration": duration,
                "message": f"分离成功，{len(stems)} 轨音频"
            }
            
        except torch.cuda.OutOfMemoryError as e:
            # CPU 模式不应触发，但以防万一
            return {
                "success": False,
                "stems": [],
                "duration": duration,
                "message": f"显存不足（CPU 模式不应发生）：{e}"
            }
        except Exception as e:
            print(f"❌ 分离失败：{e}")
            return {
                "success": False,
                "stems": [],
                "duration": duration,
                "message": f"分离失败：{str(e)}"
            }
    
    def _mock_separate(
        self,
        input_path: Path,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> dict:
        """Mock 模式（Demucs 未安装时）"""
        import time
        
        for i in range(20):
            if progress_callback:
                progress_callback((i + 1) / 20)
            time.sleep(0.2)
        
        if progress_callback:
            progress_callback(1.0)
        
        return {
            "success": True,
            "stems": [str(input_path)] * 4,  # Mock 数据
            "duration": 3.0,
            "message": "Mock 模式：Demucs 未安装 (pip install demucs)"
        }
    
    def get_available_models(self) -> List[str]:
        """获取可用模型列表"""
        if _check_demucs_available():
            return ["htdemucs", "htdemucs_ft", "htdemucs_6s"]
        return ["mock"]


# 全局实例（轻量级初始化，不加载模型）
demucs_service = DemucsService()