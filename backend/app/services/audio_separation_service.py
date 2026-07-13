"""
音频分离服务 (Demucs)
使用 Meta 开源 Demucs 模型进行人声/鼓/贝斯/其他 四轨分离

功能:
- 四轨分离 (vocals, drums, bass, other)
- 支持多种 Demucs 变体 (htdemucs, htdemucs_ft)
- 进度回调
- 临时文件管理
"""

import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Callable, List
import tempfile

# Demucs 安装检查
try:
    import demucs
    DEMUCS_AVAILABLE = True
except ImportError:
    DEMUCS_AVAILABLE = False
    print("⚠️  Demucs 未安装，音频分离功能将使用 Mock 模式")
    print("   安装命令：pip install -U demucs")


class DemucsService:
    """Demucs 音频分离服务"""
    
    # Demucs 模型列表
    MODELS = {
        "htdemucs": "高性能混合 Transformer Demucs (推荐)",
        "htdemucs_ft": "微调版 (音质更好，速度慢)",
        "htdemucs_6s": "6 轨分离 (加钢琴/吉他)",
    }
    
    # 输出轨道名称
    STEM_NAMES = ["vocals", "drums", "bass", "other"]
    
    def __init__(self, output_dir: Optional[str] = None):
        """
        初始化服务
        
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
        分离音频为多轨
        
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
        if not DEMUCS_AVAILABLE:
            return self._mock_separate(input_path, progress_callback)
        
        input_path = Path(input_path)
        if not input_path.exists():
            return {
                "success": False,
                "stems": [],
                "duration": 0,
                "message": f"文件不存在：{input_path}"
            }
        
        # 创建临时输出目录 (以文件名命名)
        temp_output = self.output_dir / input_path.stem
        if temp_output.exists():
            shutil.rmtree(temp_output)
        temp_output.mkdir(parents=True, exist_ok=True)
        
        # Demucs 命令
        cmd = [
            "demucs",
            "-n", model,
            "-o", str(self.output_dir),
            str(input_path),
            "--int24",  # 高质量输出
            "--float32",
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
            duration_estimate = 120  # 估算 2 分钟
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
                "duration": duration_estimate,
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
        """获取可用模型列表"""
        if DEMUCS_AVAILABLE:
            return list(self.MODELS.keys())
        return ["mock"]


# 全局实例
demucs_service = DemucsService()