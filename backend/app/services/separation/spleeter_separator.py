"""Spleeter backend — 包装现有 Modal Spleeter 实现（不修改现有代码）。

调用现有 `app.services.audio_separation_service.demucs_service`（懒加载版），
该实例是生产在用的 Modal Spleeter 四轨分离（vocals/drums/bass/other），
保持其行为完全不变，仅作为统一接口的 fallback backend。

Spleeter 许可（存档）：代码 MIT（deezer/spleeter）；预训练权重 MIT，Deezer
issue #259 确认商用；spleeter==2.4.2 + tensorflow==2.12.1 固定版本，Python 3.11。
"""

from __future__ import annotations

from typing import Callable, List, Optional

from .base import (
    STEM_NAMES,
    SeparationResult,
    SeparatorBackend,
    ensure_input_exists,
    get_duration_seconds,
)


class SpleeterSeparator(SeparatorBackend):
    """包装现有 Modal Spleeter 的 fallback backend（四轨）。"""

    backend_name = "spleeter"

    def __init__(
        self,
        output_dir: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        progress_callback: Optional[Callable[[float], None]] = None,
        spleeter_service=None,
    ):
        super().__init__(
            output_dir=output_dir,
            timeout_seconds=timeout_seconds,
            progress_callback=progress_callback,
        )
        if spleeter_service is None:
            from app.services.audio_separation_service import demucs_service
            spleeter_service = demucs_service
        self._service = spleeter_service

    def separate(self, input_path: str, model: str = "spleeter:4stems") -> SeparationResult:
        """调用现有 Modal Spleeter，返回统一契约结果。"""
        err = ensure_input_exists(input_path)
        if err:
            return SeparationResult.failure(err, backend=self.backend_name)

        duration = get_duration_seconds(input_path)

        try:
            result = self._service.separate(
                input_path,
                model=model,
                progress_callback=self.progress_callback,
            )
            success = bool(result.get("success"))
            stems = [str(s) for s in result.get("stems", []) if s]
            message = result.get("message", "")

            # Spleeter 真实产出四轨（若服务缺轨，如实记录）
            real = [s for s in STEM_NAMES if any(f"\\{s}.wav" in p.lower() or f"/{s}.wav" in p.lower() or p.lower().endswith(f"{s}.wav") for p in stems)]
            if not real and success:
                real = list(STEM_NAMES[: len(stems)])

            return SeparationResult(
                success=success,
                stems=stems,
                duration=float(result.get("duration") or duration),
                message=message or ("Spleeter 分离成功" if success else "Spleeter 分离失败"),
                backend=self.backend_name,
                model=model,
                real_stems=real,
                derived_stems=[],
                missing_stems=[s for s in STEM_NAMES if s not in real],
            )
        except Exception as exc:  # noqa: BLE001
            return SeparationResult.failure(
                f"Spleeter 分离失败：{exc}", backend=self.backend_name, duration=duration,
            )

    def get_available_models(self) -> List[str]:
        try:
            return self._service.get_available_models()
        except Exception:  # noqa: BLE001
            return ["spleeter:4stems"]