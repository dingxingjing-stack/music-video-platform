"""
音频分离服务 (Demucs) - 懒加载版本
使用 Meta 开源 Demucs 模型进行人声/鼓/贝斯/其他 四轨分离

功能:
- 四轨分离 (vocals, drums, bass, other)
- 支持多种 Demucs 变体 (htdemucs, htdemucs_ft)
- 进度回调
- 临时文件管理
- 懒加载：仅在首次调用分离接口时检查/加载 demucs，避免启动阻塞
- 内存优化：--segment=4 --shifts=1 适配 Render 512MB 免费实例
"""

import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Callable, List
import tempfile
import threading
import librosa


# Demucs 可用性缓存（懒加载，线程安全）
_DEMUCS_AVAILABLE: Optional[bool] = None
_DEMUCS_LOCK = threading.Lock()


def _check_demucs_available() -> bool:
    """
    懒加载检查 demucs 是否可用（线程安全，仅首次调用时检查）
    首次调用时导入 demucs，后续直接返回缓存结果
    """
    global _DEMUCS_AVAILABLE
    if _DEMUCS_AVAILABLE is not None:
        return _DEMUCS_AVAILABLE
    
    with _DEMUCS_LOCK:
        if _DEMUCS_AVAILABLE is not None:
            return _DEMUCS_AVAILABLE
        try:
            import demucs  # noqa: F401
            _DEMUCS_AVAILABLE = True
        except ImportError:
            _DEMUCS_AVAILABLE = False
            print("⚠️  Demucs 未安装，音频分离功能将使用 Mock 模式")
            print("   安装命令：pip install -U demucs")
        return _DEMUCS_AVAILABLE


class DemucsService:
    """Demucs 音频分离服务（懒加载版本）"""
    
    # Demucs 模型列表
    MODELS = {
        "htdemucs": "高性能混合 Transformer Demucs (推荐)",
        "htdemucs_ft": "微调版 (音质更好，速度慢)",
        "htdemucs_6s": "6 轨分离 (加钢琴/吉他)",
    }
    
    # 输出轨道名称
    STEM_NAMES = ["vocals", "drums", "bass", "other"]
    
    # 音频时长限制（秒）— 适配 Render 512MB 内存上限
    MAX_AUDIO_DURATION = 10.0
    
    def __init__(self, output_dir: Optional[str] = None):
        """
        初始化服务（轻量级初始化，不加载模型）
        
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
        分离音频为多轨（首次调用时才检查 demucs 可用性）
        
        Args:
            input_path: 输入音频文件路径
            model: Demucs 模型名称
            progress_callback: 进度回调 (0.0-1.0)
        
        Returns:
            {
                "success": bool,
                "stems": List[str],  # 分离后的文件路径
                "duration": float,   # 音频时长 (秒)
                "message": str
            }
        """
        # 懒加载检查：首次调用时才检查 demucs 是否可用
        if not _check_demucs_available():
            return self._mock_separate(input_path, progress_callback)
        
        input_path = Path(input_path)
        if not input_path.exists():
            return {
                "success": False,
                "stems": [],
                "duration": 0,
                "message": f"文件不存在：{input_path}"
            }
        
        # 【内存保护】前置音频时长校验：>10 秒直接拒绝，防止 OOM
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
                "message": f"音频过长：{duration:.1f}s，最大允许 {self.MAX_AUDIO_DURATION}s（内存保护）"
            }
        
        # 创建临时输出目录 (以文件名命名)
        temp_output = self.output_dir / input_path.stem
        if temp_output.exists():
            shutil.rmtree(temp_output)
        temp_output.mkdir(parents=True, exist_ok=True)
        
        # Demucs 命令：内存优化参数组合
        # --segment=4      分片 4 秒（默认 7.8），降低峰值内存 ~40%
        # --shifts=1       单次推理（默认 2），降低内存 ~15%
        # --overlap=0.25   保持默认重叠
        # -j 1             单进程推理（配合 WEB_CONCURRENCY=1）
        # 移除 --float32   默认 16-bit 输出，写入内存减半
        cmd = [
            "demucs",
            "-n", model,
            "-o", str(self.output_dir),
            "--segment", "4",
            "--shifts", "1",
            "--overlap", "0.25",
            "-j", "1",
            str(input_path),
        ]
        
        try:
            # 执行分离
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            # 监控进度
            duration_estimate = max(60, duration * 4)  # 估算：音频时长 × 4（CPU 推理约 1.5-2×实时）
            elapsed = 0
            
            for line in process.stderr:
                if progress_callback:
                    elapsed += 0.5
                    progress = min(0.95, elapsed / duration_estimate)
                    progress_callback(progress)
            
            process.wait(timeout=600)  # 10 分钟超时
            
            if progress_callback:
                progress_callback(1.0)
            
            # 检查输出文件
            stems = []
            for stem_name in self.STEM_NAMES:
                stem_path = temp_output / model / f"{stem_name}.wav"
                if stem_path.exists():
                    stems.append(str(stem_path))
            
            return {
                "success": len(stems) > 0,
                "stems": stems,
                "duration": duration,
                "message": f"分离成功，{len(stems)} 轨音频" if stems else "分离失败"
            }
            
        except subprocess.TimeoutExpired:
            process.kill()
            return {
                "success": False,
                "stems": [],
                "duration": 0,
                "message": "分离超时 (>10 分钟)"
            }
        except Exception as e:
            return {
                "success": False,
                "stems": [],
                "duration": 0,
                "message": f"分离失败：{str(e)}"
            }
    
    def _mock_separate(
        self,
        input_path: str,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> dict:
        """
        Mock 模式 (Demucs 未安装时)
        
        返回输入文件本身的 4 个引用 (实际未分离)
        """
        import time
        
        # 模拟进度
        for i in range(20):
            if progress_callback:
                progress_callback((i + 1) / 20)
            time.sleep(0.3)
        
        if progress_callback:
            progress_callback(1.0)
        
        # Mock: 返回同一文件 4 次 (实际项目中应返回真实分离结果)
        return {
            "success": True,
            "stems": [input_path] * 4,  # Mock 数据
            "duration": 180,  # 3 分钟
            "message": "Mock 模式：Demucs 未安装 (pip install demucs)"
        }
    
    def get_available_models(self) -> List[str]:
        """获取可用模型列表（懒加载检查）"""
        if _check_demucs_available():
            return list(self.MODELS.keys())
        return ["mock"]


# 全局实例（轻量级初始化，不加载模型，不导入 demucs）
demucs_service = DemucsService()