"""
音频分离服务 - 懒加载版本
四轨分离（vocals/drums/bass/other）由独立 Spleeter Modal App 承担
（spleeter_modal.py，Spleeter 2.4.2 + TensorFlow 2.12.1，MIT）。

本服务（web 容器）不安装 Spleeter/TensorFlow，仅通过 Modal SDK 调用独立 App：
  - 把上传音频经共享数据卷交给独立 Spleeter App
  - Spleeter App 写回 vocals/drums/bass/other.wav 并 commit
  - 本服务取回本地临时目录后返回（保持原有分离返回协议）

功能:
- 四轨分离 (vocals, drums, bass, other)
- 进度回调
- 临时文件管理
- 懒加载：仅在首次调用分离接口时检查 modal SDK 可用性，避免启动阻塞
"""

import os
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Optional, Callable, List


# Spleeter App 可用性缓存（懒加载，线程安全）
_SPLEETER_AVAILABLE: Optional[bool] = None
_SPLEETER_LOCK = threading.Lock()

_MODAL_APP_NAME = "avireon-music-platform-spleeter"
_MODAL_VOLUME_NAME = "avireon-music-platform-data-v1"


def _check_spleeter_available() -> bool:
    """
    懒加载检查独立 Spleeter App 是否可调用（线程安全，仅首次调用时检查）
    首次调用时导入 modal SDK，后续直接返回缓存结果
    Step 4: ENVIRONMENT=production 时直接禁用 Modal Spleeter（已下线），走 Mock/本地路径
    """
    # 生产禁止 Modal（Step 4）
    if os.getenv("ENVIRONMENT", "development").lower() == "production":
        return False
    global _SPLEETER_AVAILABLE
    if _SPLEETER_AVAILABLE is not None:
        return _SPLEETER_AVAILABLE

    with _SPLEETER_LOCK:
        if _SPLEETER_AVAILABLE is not None:
            return _SPLEETER_AVAILABLE
        try:
            import modal  # noqa: F401
            _SPLEETER_AVAILABLE = True
        except ImportError:
            _SPLEETER_AVAILABLE = False
            print("⚠️  modal SDK 不可用，音频分离功能将使用 Mock 模式")
            print("   安装命令：pip install modal")
        return _SPLEETER_AVAILABLE


class DemucsService:
    """音频分离服务（懒加载版本）— 四轨分离经独立 Spleeter Modal App 执行。"""

    # Spleeter 模型列表（兼容原有 model 参数，统一走官方 4stems）
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
        分离音频为多轨（经独立 Spleeter Modal App 执行）
        
        Args:
            input_path: 输入音频文件路径
            model: Spleeter 模型名称（默认官方 4stems）
            progress_callback: 进度回调 (0.0-1.0)
        
        Returns:
            {
                "success": bool,
                "stems": List[str],  # 分离后的本地文件路径
                "duration": float,   # 音频时长 (秒)
                "message": str
            }
        """
        # 懒加载检查：首次调用时才检查 modal SDK 是否可用
        if not _check_spleeter_available():
            return self._mock_separate(input_path, progress_callback)
        
        input_path = Path(input_path)
        if not input_path.exists():
            return {
                "success": False,
                "stems": [],
                "duration": 0,
                "message": f"文件不存在：{input_path}"
            }
        
        try:
            import modal

            # 上传到共享数据卷（独立 Spleeter App 从卷读取）
            vol = modal.Volume.from_name(_MODAL_VOLUME_NAME, create_if_missing=True)
            remote_name = f"sep_{uuid.uuid4().hex}.wav"
            vol.add_local_file(str(input_path), f"/generated/{remote_name}")
            vol.commit()

            if progress_callback:
                progress_callback(0.1)

            fn = modal.Function.from_name(_MODAL_APP_NAME, "separate_audio")
            stems_map = fn.remote(remote_name)

            if progress_callback:
                progress_callback(0.9)

            # 取回各轨到本地临时目录（保持原返回协议：本地文件路径列表）
            stems = []
            for stem_name in self.STEM_NAMES:
                fname = stems_map.get(stem_name)
                if not fname:
                    continue
                local = self.output_dir / fname
                try:
                    data = b"".join(vol.read_file(f"/generated/{fname}"))
                    if data and len(data) > 0:
                        local.write_bytes(data)
                        stems.append(str(local))
                except Exception:  # noqa: BLE001
                    print(f"[spleeter] 取回分轨失败（跳过）: {fname}")
                    continue

            return {
                "success": len(stems) > 0,
                "stems": stems,
                "duration": 0,
                "message": f"分离成功，{len(stems)} 轨音频" if stems else "分离失败"
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
        Mock 模式 (modal SDK 不可用时)
        
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
            "message": "Mock 模式：modal SDK 不可用 (pip install modal)"
        }
    
    def get_available_models(self) -> List[str]:
        """获取可用模型列表（懒加载检查）"""
        if _check_spleeter_available():
            return list(self.MODELS.keys())
        return ["mock"]


# 全局实例（轻量级初始化，不加载模型，不导入 modal/spleeter）
demucs_service = DemucsService()