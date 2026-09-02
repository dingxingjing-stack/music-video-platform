"""
音频分离统一包（与现有 app/services/audio_separation_service.py 完全隔离）。

阶段：
- Stage 2 第一阶段 POC：新增 MDX backend（python-audio-separator + UVR_MDXNET_9482），
  Spleeter backend 包装现有 Modal Spleeter 作为 fallback。
- 不修改生产路由（audio_processing.py / workflow.py / main.py），不删除 Spleeter。

对外暴露：
- AudioSeparatorService：统一门面（MDX 主 + Spleeter fallback，带日志与原因）
- MdxSeparator / SpleeterSeparator：backend 实现
"""

from .base import (
    SEPARATION_CONTRACT_KEYS,
    STEM_NAMES,
    SeparationResult,
    SeparatorBackend,
)
from .mdx_separator import MdxSeparator
from .spleeter_separator import SpleeterSeparator
from .audio_separator_service import AudioSeparatorService

__all__ = [
    "SEPARATION_CONTRACT_KEYS",
    "STEM_NAMES",
    "SeparationResult",
    "SeparatorBackend",
    "MdxSeparator",
    "SpleeterSeparator",
    "AudioSeparatorService",
]