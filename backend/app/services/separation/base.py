"""分离后端统一接口与返回协议。

契约（与现有 app/routers/audio_processing.py 的 SeparateResponse 一致）：
    {
        "success": bool,
        "stems": List[str],   # 分离后的本地文件路径（真实模型输出 + 明确推导的轨道）
        "duration": float,    # 输入音频时长（秒）
        "message": str,
    }

新增元数据（不破坏既有契约，供审计/前端将来读取）：
    backend: str          # "mdx" | "spleeter" | "mock"
    model: str            # 实际使用的模型标识
    fallback_used: bool   # 是否发生 fallback
    fallback_reason: str  # fallback 原因（fallback_used=True 时）
    real_stems: List[str] # 由模型真实输出的轨道名
    derived_stems: List[str]  # 由真实轨道推导而来（如 instrumental → other）
    missing_stems: List[str]  # 请求但未产出的轨道（不得虚假填充）
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

# 与现有 spleeter_modal / 前端约定一致的 4-stem 输出轨道名
STEM_NAMES: List[str] = ["vocals", "drums", "bass", "other"]

# 既有 /separate 接口契约字段
SEPARATION_CONTRACT_KEYS: List[str] = ["success", "stems", "duration", "message"]


@dataclass
class SeparationResult:
    """统一分离结果（包含契约字段 + 审计元数据）。"""

    success: bool
    stems: List[str]
    duration: float
    message: str
    backend: str = "unknown"
    model: str = ""
    fallback_used: bool = False
    fallback_reason: str = ""
    real_stems: List[str] = field(default_factory=list)
    derived_stems: List[str] = field(default_factory=list)
    missing_stems: List[str] = field(default_factory=list)

    def to_contract_dict(self) -> dict:
        """严格返回既有契约（不追加任何字段，保证前端兼容）。"""
        return {
            "success": self.success,
            "stems": self.stems,
            "duration": self.duration,
            "message": self.message,
        }

    def to_audit_dict(self) -> dict:
        """完整审计视图（含元数据）。"""
        d = self.to_contract_dict()
        d.update({
            "backend": self.backend,
            "model": self.model,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "real_stems": self.real_stems,
            "derived_stems": self.derived_stems,
            "missing_stems": self.missing_stems,
        })
        return d

    @classmethod
    def failure(cls, message: str, backend: str = "unknown", **kwargs) -> "SeparationResult":
        kwargs.setdefault("duration", 0.0)
        return cls(
            success=False,
            stems=[],
            message=message,
            backend=backend,
            **kwargs,
        )


class SeparatorBackend:
    """分离后端抽象基类。各 backend 实现须线程安全、懒加载。"""

    backend_name: str = "base"

    def __init__(
        self,
        output_dir: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        progress_callback: Optional[Callable[[float], None]] = None,
    ):
        self.output_dir = Path(output_dir) if output_dir else Path(tempfile_dir())
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = timeout_seconds
        self.progress_callback = progress_callback
        self._lock = threading.RLock()

    def separate(self, input_path: str, model: str = "") -> SeparationResult:
        """同步分离入口。子类实现；须返回 SeparationResult。"""
        raise NotImplementedError

    def get_available_models(self) -> List[str]:
        raise NotImplementedError


def tempfile_dir() -> str:
    import tempfile
    return tempfile.gettempdir()


def ensure_input_exists(input_path: str) -> Optional[str]:
    """输入校验：存在 + 非空。返回错误信息或 None。"""
    p = Path(input_path)
    if not p.exists():
        return f"文件不存在：{input_path}"
    if p.stat().st_size == 0:
        return f"文件为空：{input_path}"
    return None


def get_duration_seconds(input_path: str) -> float:
    """获取音频时长（秒）。失败返回 0。"""
    try:
        import librosa
        return float(librosa.get_duration(path=input_path))
    except Exception:  # noqa: BLE001
        try:
            import soundfile as sf
            info = sf.info(input_path)
            return float(info.frames / info.samplerate)
        except Exception:  # noqa: BLE001
            return 0.0


def map_mdx_stems(output_files: List[str]) -> List[str]:
    """把 python-audio-separator 的 MDX 2-stem 输出文件名映射为本地路径列表。

    框架输出文件名形如 "<base>_(Vocals).wav" / "<base>_(Instrumental).wav"。
    此函数只做文件名规整，不做轨道语义映射（轨道语义在 MdxSeparator 内处理）。
    """
    return [os.path.abspath(f) for f in output_files if f and os.path.exists(f)]