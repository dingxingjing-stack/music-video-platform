"""
本地 MusicGen-Small 推理服务（Kaggle T4 专用）

- 模型: facebook/musicgen-small (300M, 1GB, MIT)
- 路径: /kaggle/working/models/musicgen-small (优先) 或 HF cache
- 不依赖 HF Space，本地 torch 直接推理
- 与现有 HF Space 版 MusicGenService (factory: music) 共存，互不影响
- 生产默认仍为 Modal ACE-Step，本文件为实验/本地路径 provider
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

import torch

from app.config.mvp_models import MUSICGEN_SMALL_DIR, MUSICGEN_SMALL_ID, resolve_musicgen_dir


class MusicGenSmallLocalService:
    """Kaggle 本地 MusicGen-Small。首次调用时延迟加载模型到 GPU。"""

    def __init__(
        self,
        model_dir: Optional[Path] = None,
        device: Optional[str] = None,
    ) -> None:
        self.model_dir = model_dir or resolve_musicgen_dir()
        self.model_id = MUSICGEN_SMALL_ID
        # T4 优先 cuda，否则 cpu
        if device:
            self.device = device
        else:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._processor = None
        self._model = None

    def is_available(self) -> bool:
        return self.model_dir.exists() and any(self.model_dir.iterdir())

    def _lazy_load(self):
        if self._model is not None:
            return
        from transformers import AutoProcessor, MusicgenForConditionalGeneration

        local_only = self.model_dir.exists()
        src = str(self.model_dir) if local_only else self.model_id
        # AutoProcessor 会从本地或 HF 拉取
        self._processor = AutoProcessor.from_pretrained(src, local_files_only=local_only)
        self._model = MusicgenForConditionalGeneration.from_pretrained(
            src, local_files_only=local_only
        )
        self._model.to(self.device)
        self._model.eval()

    @torch.no_grad()
    def generate(
        self,
        prompt: str,
        duration: float = 10.0,
        temperature: float = 1.0,
        top_k: int = 250,
        guidance_scale: float = 3.0,
        output_path: Optional[Path] = None,
    ) -> Path:
        """
        同步生成 WAV。
        - duration: 秒，MusicGen-small 原生 30s 内
        - 返回输出文件 Path
        """
        if not prompt:
            raise ValueError("prompt 不能为空")
        duration = max(1.0, min(float(duration), 30.0))
        self._lazy_load()
        assert self._processor is not None and self._model is not None

        inputs = self._processor(text=[prompt], padding=True, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        # MusicGen 以 token 数控制时长，约 50 token/秒
        max_new_tokens = int(duration * 50)

        audio_values = self._model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_k=top_k,
            guidance_scale=guidance_scale,
            do_sample=True,
        )

        # 采样率 32000 (MusicGen) 或 44100 取决于 processor
        sample_rate = getattr(self._processor, "sampling_rate", 32000)
        if hasattr(self._processor, "feature_extractor") and hasattr(
            self._processor.feature_extractor, "sampling_rate"
        ):
            sample_rate = self._processor.feature_extractor.sampling_rate

        import soundfile as sf

        out_path = output_path or Path(f"/tmp/musicgen_small_{int(time.time()*1000)}.wav")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # audio_values: [1, channels, samples] -> [channels, samples]
        wav = audio_values[0].cpu().float().numpy()
        # 转为 [samples, channels] 以兼容 soundfile
        if wav.ndim == 2:
            wav = wav.T
        sf.write(str(out_path), wav, sample_rate)
        return out_path

    def health(self) -> dict:
        total, used, free = 0, 0, 0
        try:
            import shutil

            total, used, free = shutil.disk_usage(self.model_dir if self.model_dir.exists() else Path.cwd())
        except Exception:
            pass
        return {
            "model_id": self.model_id,
            "model_dir": str(self.model_dir),
            "exists": self.is_available(),
            "device": self.device,
            "cuda": torch.cuda.is_available(),
            "free_gb": free / 1024**3 if free else 0,
        }
