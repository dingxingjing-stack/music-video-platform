"""
音频分离服务 — 产品功能占位（Modal Spleeter Provider 已删除）

历史：四轨分离（vocals/drums/bass/other）曾由独立 Spleeter Modal App 承担
（spleeter_modal.py，Spleeter 2.4.2 + TensorFlow 2.12.1，MIT）。
2026-10-01 第一阶段重构：Modal Spleeter Provider 实现已删除（spleeter_modal.py
一并移除），本文件仅保留公共接口骨架与既有返回协议，作为「音频分离」产品
功能的占位——后续将由 TemPolor stems（/open-apis/v1/stems，stems-v2 4 轨 /
stems-v3 8 轨）重新接入，接口协议不变。

功能:
- 四轨分离 (vocals, drums, bass, other) —— 接口占位
- 生产环境：明确失败（stem_separation_unavailable），绝不 Mock 假音频
- 非生产环境：Mock 模式用于开发/测试
"""

import os
import tempfile
from pathlib import Path
from typing import Optional, Callable, List


class DemucsService:
    """音频分离服务（产品功能占位）— Provider 已下线，等待 TemPolor stems 接入。"""

    # 模型列表（兼容原有 model 参数语义；接入 TemPolor stems 后扩展 4/8 轨）
    MODELS = {
        "spleeter:4stems": "Spleeter 官方四轨分离 (vocals/drums/bass/other, MIT)",
    }

    # 输出轨道名称
    STEM_NAMES = ["vocals", "drums", "bass", "other"]

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
            self.output_dir = Path(tempfile.gettempdir()) / "spleeter_output"
            self.output_dir.mkdir(parents=True, exist_ok=True)

    def separate(
        self,
        input_path: str,
        model: str = "spleeter:4stems",
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> dict:
        """
        分离音频为多轨（接口占位：Provider 已下线，当前恒不可用）

        Args:
            input_path: 输入音频文件路径
            model: 模型名称（默认官方 4stems 语义）
            progress_callback: 进度回调 (0.0-1.0)

        Returns:
            {
                "success": bool,
                "stems": List[str],  # 分离后的本地文件路径
                "duration": float,   # 音频时长 (秒)
                "message": str
            }
        """
        input_path = Path(input_path)
        if not input_path.exists():
            return {
                "success": False,
                "stems": [],
                "duration": 0,
                "message": f"文件不存在：{input_path}"
            }

        # 生产环境禁止 Mock 返回，必须明确失败
        if os.getenv("ENVIRONMENT", "development").lower() == "production":
            return {
                "success": False,
                "stems": [],
                "duration": 0,
                "message": "Stem separation is not available right now.",
                "error_code": "stem_separation_unavailable",
            }
        # 非生产环境允许 Mock 用于开发/测试
        return self._mock_separate(input_path, progress_callback)

    def _mock_separate(
        self,
        input_path: str,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> dict:
        """
        Mock 模式（非生产环境专用）

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
            "stems": [str(input_path)] * 4,  # Mock 数据
            "duration": 180,  # 3 分钟
            "message": "Mock 模式：分离 Provider 未接入（等待 TemPolor stems）"
        }

    def get_available_models(self) -> List[str]:
        """获取可用模型列表（Provider 已下线）"""
        # 生产环境不暴露 mock 模型
        if os.getenv("ENVIRONMENT", "development").lower() == "production":
            return []
        return ["mock"]


# 全局实例（轻量级初始化，不加载模型）
demucs_service = DemucsService()
