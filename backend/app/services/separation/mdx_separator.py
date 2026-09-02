"""MDX 分离 backend — 基于 python-audio-separator（MIT）框架。

本模块只做"调用框架"，不引入 Demucs 权重、不引入 MUSDB18HQ 研究权重。

当前 POC 模型：UVR_MDXNET_9482.onnx（UVR 自训，作者 Anjok07 于 discussion #2307
明确授予商用与再分发许可，需署名）。该模型为 2-stem：vocals / instrumental。

轨道语义（严格区分真实输出与推导，见 base.SeparationResult）：
  - real_stems:   ["vocals", "instrumental"]   ← 模型真实输出
  - derived_stems: ["other"]                   ← instrumental 映射为 other
  - missing_stems: ["drums", "bass"]           ← MDX-Net 不产出，绝不虚假填充
如需 4-stem，必须走第二级分离或 Spleeter fallback（见 audio_separator_service）。

线程安全：单进程内使用全局可重入锁；模型实例懒加载、仅创建一次。
模型缓存：默认目录 AUDIO_SEPARATOR_MODEL_DIR（可用环境变量覆盖），已下载则不重复下载。
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

from .base import (
    SeparationResult,
    SeparatorBackend,
    ensure_input_exists,
    get_duration_seconds,
)

# 默认模型目录：优先环境变量，其次项目 data 目录
_DEFAULT_MODEL_DIR = os.environ.get(
    "AUDIO_SEPARATOR_MODEL_DIR",
    str(Path(__file__).resolve().parents[3] / "data" / "audio_separator_models"),
)

# 默认 POC 模型（UVR_MDXNET_9482：2-stem vocals/instrumental）
_DEFAULT_MDX_MODEL = "UVR_MDXNET_9482.onnx"

# MDX 模型不产出的轨道（不得虚假填充）
_NOT_PRODUCED = ["drums", "bass"]


class MdxSeparator(SeparatorBackend):
    """基于 python-audio-separator 的 MDX 分离 backend。"""

    backend_name = "mdx"

    def __init__(
        self,
        output_dir: Optional[str] = None,
        model_file_dir: Optional[str] = None,
        model_filename: str = _DEFAULT_MDX_MODEL,
        timeout_seconds: Optional[float] = None,
        progress_callback: Optional[Callable[[float], None]] = None,
        sample_rate: int = 44100,
        use_autocast: bool = False,
    ):
        super().__init__(
            output_dir=output_dir,
            timeout_seconds=timeout_seconds,
            progress_callback=progress_callback,
        )
        self.model_file_dir = Path(model_file_dir or _DEFAULT_MODEL_DIR)
        self.model_file_dir.mkdir(parents=True, exist_ok=True)
        self.model_filename = model_filename
        self.sample_rate = sample_rate
        self.use_autocast = use_autocast

        # 框架实例懒加载（全局锁内创建一次）
        self._separator = None
        self._model_loaded = False

    # ------------------------------------------------------------------
    # 懒加载 + 模型实例
    # ------------------------------------------------------------------

    def _get_separator(self):
        """懒加载创建 Separator（线程安全，仅首次创建）。"""
        with self._lock:
            if self._separator is not None:
                return self._separator
            try:
                from audio_separator.separator import Separator
            except ImportError as exc:  # 依赖缺失 → 明确失败而非崩溃
                raise RuntimeError(
                    f"python-audio-separator 未安装（pip install audio-separator）：{exc}"
                ) from exc

            if self.progress_callback:
                self.progress_callback(0.05)

            separator = Separator(
                log_level=30,  # WARNING：抑制 INFO 噪音，保留关键日志
                model_file_dir=str(self.model_file_dir),
                output_dir=str(self.output_dir),
                output_format="WAV",
                sample_rate=self.sample_rate,
                use_autocast=self.use_autocast,
                # MDX 参数：segment_size 越小显存越低；CPU 环境也适用
                mdx_params={
                    "hop_length": 1024,
                    "segment_size": 256,
                    "overlap": 0.25,
                    "batch_size": 1,
                    "enable_denoise": False,
                },
            )

            if self.progress_callback:
                self.progress_callback(0.15)

            # load_model(model_filename=...) 内部完成模型下载（首次）+ 加载
            separator.load_model(model_filename=self.model_filename)

            if self.progress_callback:
                self.progress_callback(0.25)

            self._separator = separator
            self._model_loaded = True
            return separator

    def is_model_loaded(self) -> bool:
        return self._model_loaded

    # ------------------------------------------------------------------
    # 分离
    # ------------------------------------------------------------------

    def separate(self, input_path: str, model: str = "") -> SeparationResult:
        """MDX 2-stem 分离。model 参数允许覆盖 POC 模型（如 MDX23C 对比）。

        线程安全：整个推理过程在可重入锁内串行执行。python-audio-separator 的
        Separator 单实例并非并发安全（共享 output_dir 会写同名文件），因此单进程
        内必须串行；并发请求由上层排队处理（可接受：CPU/单模型推理本身是瓶颈）。
        """
        with self._lock:
            return self._separate_locked(input_path, model)

    def _separate_locked(self, input_path: str, model: str = "") -> SeparationResult:
        err = ensure_input_exists(input_path)
        if err:
            return SeparationResult.failure(err, backend=self.backend_name)

        duration = get_duration_seconds(input_path)
        model_name = model or self.model_filename

        try:
            separator = self._get_separator()
            # 若传入的 model 与初始化时不同，需重新加载（对比测试用）
            if model and model != self.model_filename:
                self.model_filename = model
                self._separator = None
                self._model_loaded = False
                separator = self._get_separator()

            if self.progress_callback:
                self.progress_callback(0.3)

            started = time.monotonic()
            output_files = self._run_with_timeout(separator, input_path)
            elapsed = time.monotonic() - started

            # 框架返回相对文件名（位于 output_dir），统一规整为绝对路径
            stems = []
            for f in output_files or []:
                if not f:
                    continue
                p = Path(f)
                if not p.is_absolute():
                    p = self.output_dir / p
                if p.exists():
                    stems.append(str(p.resolve()))
            if not stems:
                return SeparationResult.failure(
                    "MDX 分离未产出任何轨道文件", backend=self.backend_name,
                    model=model_name, duration=duration,
                )

            # 轨道语义：MDX 2-stem 真实输出 vocals + instrumental
            # 文件名形如 "<base>_(Vocals)_<model>.wav" / "<base>_(Instrumental)_<model>.wav"
            real_stems: List[str] = []
            for s in stems:
                base = os.path.splitext(os.path.basename(s))[0].lower()
                if "_(vocals)_" in base or base.endswith("_(vocals)"):
                    real_stems.append("vocals")
                elif "_(instrumental)_" in base or base.endswith("_(instrumental)") or "_(accompaniment)" in base:
                    real_stems.append("instrumental")
            real_stems = sorted(set(real_stems))
            if not real_stems:
                # 文件名无法识别 → 保守处理：不猜测语义，标记为未知轨道
                real_stems = [f"stem_{i}" for i in range(len(stems))]

            derived = ["other"] if "instrumental" in real_stems else []

            if self.progress_callback:
                self.progress_callback(1.0)

            return SeparationResult(
                success=True,
                stems=stems,
                duration=duration,
                message=f"MDX 分离成功（{model_name}），{len(stems)} 轨真实输出，耗时 {elapsed:.1f}s",
                backend=self.backend_name,
                model=model_name,
                real_stems=real_stems,
                derived_stems=derived,
                missing_stems=list(_NOT_PRODUCED),
            )
        except Exception as exc:  # noqa: BLE001
            return SeparationResult.failure(
                f"MDX 分离失败：{exc}", backend=self.backend_name,
                model=model_name, duration=duration,
            )

    def _run_with_timeout(self, separator, input_path: str) -> List[str]:
        """执行分离并应用超时保护。"""
        timeout = self.timeout_seconds

        def _run():
            return separator.separate(str(input_path))

        if not timeout or timeout <= 0:
            return _run()

        # 在线程中执行以便超时；框架内部可释放（单实例时被 lock 串行）
        result: List[str] = []
        error: List[Exception] = []

        def _target():
            try:
                result.extend(_run() or [])
            except Exception as exc:  # noqa: BLE001
                error.append(exc)

        t = threading.Thread(target=_target, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            raise TimeoutError(f"MDX 分离超过 {timeout}s 未完成")
        if error:
            raise error[0]
        return result

    # ------------------------------------------------------------------

    def get_available_models(self) -> List[str]:
        """返回框架支持的模型文件名列表（仅列出，不下载）。"""
        try:
            sep = self._get_separator()
            models = sep.list_supported_model_files()
            return sorted(models)
        except Exception:  # noqa: BLE001
            return [self.model_filename]

    def get_model_cache_dir(self) -> str:
        return str(self.model_file_dir)