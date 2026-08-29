"""统一分离门面 AudioSeparatorService。

策略（用户批准的 Stage 2 目标）：
    统一分离接口 → MDX/其他高质量 backend → 4-stem pipeline → 失败自动 fallback 到 Spleeter

行为：
  1. 默认 MDX backend（python-audio-separator + UVR_MDXNET_9482）优先；
  2. MDX 成功 → 使用 MDX 结果（2-stem 真实输出，如实标记 missing_stems）；
  3. MDX 失败 → fallback 到 Spleeter 四轨，记录 fallback_used + fallback_reason + 日志；
  4. 绝不出现"接口 success 但轨道语义错误"：stems 只含真实/明确推导的本地文件。

4-stem 说明：
  - 当前 POC 阶段 MDX 只产出 vocals/instrumental（→ vocals/other），drums/bass
    在 missing_stems 中如实暴露，不虚假填充。
  - 4-stem 完整管线（第二级分离 drums/bass 或 Spleeter 补齐）进入下一阶段，
    先由 POC 验证质量与成本后决定。

本门面不修改生产路由；仅提供可被路由/工作流调用的统一入口。
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

from .base import SeparationResult, SeparatorBackend
from .mdx_separator import MdxSeparator
from .spleeter_separator import SpleeterSeparator

logger = logging.getLogger(__name__)


class AudioSeparatorService:
    """统一分离门面：MDX 主 + Spleeter fallback。"""

    def __init__(
        self,
        output_dir: Optional[str] = None,
        mdx_model: str = "UVR_MDXNET_9482.onnx",
        model_file_dir: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        progress_callback: Optional[Callable[[float], None]] = None,
        mdx_backend: Optional[MdxSeparator] = None,
        spleeter_backend: Optional[SpleeterSeparator] = None,
        enable_fallback: bool = True,
    ):
        self.output_dir = output_dir
        self.mdx_model = mdx_model
        self.model_file_dir = model_file_dir
        self.timeout_seconds = timeout_seconds
        self.progress_callback = progress_callback
        self.enable_fallback = enable_fallback

        # 懒加载两个 backend（避免 import 时触发现有 Modal Spleeter 检查）
        self._mdx: Optional[MdxSeparator] = mdx_backend
        self._spleeter: Optional[SpleeterSeparator] = spleeter_backend
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # backend 懒加载
    # ------------------------------------------------------------------

    def _get_mdx(self) -> MdxSeparator:
        if self._mdx is None:
            self._mdx = MdxSeparator(
                output_dir=self.output_dir,
                model_file_dir=self.model_file_dir,
                model_filename=self.mdx_model,
                timeout_seconds=self.timeout_seconds,
                progress_callback=self.progress_callback,
            )
        return self._mdx

    def _get_spleeter(self) -> SpleeterSeparator:
        if self._spleeter is None:
            self._spleeter = SpleeterSeparator(
                output_dir=self.output_dir,
                timeout_seconds=self.timeout_seconds,
                progress_callback=self.progress_callback,
            )
        return self._spleeter

    # ------------------------------------------------------------------
    # 统一入口
    # ------------------------------------------------------------------

    def separate(
        self,
        input_path: str,
        model: str = "",
        *,
        backend: str = "mdx",
    ) -> SeparationResult:
        """统一分离入口。

        Args:
            input_path: 输入音频本地路径
            model: 可选，MDX 模型名覆盖（对比测试用）
            backend: "mdx"（默认，MDX 优先 + Spleeter fallback）
                     "spleeter"（强制 Spleeter）
        """
        started = time.monotonic()
        if not Path(input_path).exists():
            return SeparationResult.failure(
                f"文件不存在：{input_path}", backend=self.backend_name(),
            )

        if backend == "spleeter":
            res = self._get_spleeter().separate(input_path, model="spleeter:4stems")
            logger.info("[separation] backend=spleeter elapsed=%.1fs result=%s",
                        time.monotonic() - started, res.to_contract_dict())
            return res

        # MDX 主路径
        mdx = self._get_mdx()
        result = mdx.separate(input_path, model=model)

        if result.success:
            logger.info("[separation] backend=mdx elapsed=%.1fs stems=%s real=%s missing=%s",
                        time.monotonic() - started,
                        result.stems, result.real_stems, result.missing_stems)
            return result

        # MDX 失败 → fallback
        if not self.enable_fallback:
            logger.warning("[separation] MDX 失败且已禁用 fallback：%s", result.message)
            return result

        reason = result.message
        logger.warning("[separation] MDX 失败，fallback 到 Spleeter：%s", reason)
        fb = self._get_spleeter().separate(input_path, model="spleeter:4stems")
        fb.fallback_used = True
        fb.fallback_reason = f"MDX 失败：{reason}"
        logger.info("[separation] backend=spleeter(fallback) elapsed=%.1fs stems=%s",
                    time.monotonic() - started, fb.stems)
        return fb

    def separate_4stem(self, input_path: str) -> SeparationResult:
        """显式四轨分离：Spleeter 四轨（当前 POC 阶段唯一完整 4-stem 来源）。

        待第二级分离（instrumental → drums/bass）POC 验证后再切换。
        """
        return self._get_spleeter().separate(input_path, model="spleeter:4stems")

    # ------------------------------------------------------------------

    def get_available_models(self) -> List[str]:
        try:
            return self._get_mdx().get_available_models()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[separation] 获取模型列表失败：%s", exc)
            return [self.mdx_model, "spleeter:4stems"]

    def backend_name(self) -> str:
        return "unified"


# 全局单例（轻量初始化，不加载任何模型）
audio_separator_service = AudioSeparatorService()