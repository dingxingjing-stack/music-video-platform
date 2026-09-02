"""
本地 CosyVoice2-0.5B 推理服务（Kaggle T4 专用）

- 模型: FunAudioLLM/CosyVoice2-0.5B (0.5B, 1.2GB, Apache 2.0)
- 路径: /kaggle/working/models/cosyvoice2-0.5b
- 能力: TTS + 零样本声音克隆（3-10s 参考音频）+ 跨语言 (9 语 18 方言)
- 与现有 GPT-SoVITS Space 版共存，本地路径不影响生产
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import torch

from app.config.mvp_models import COSYVOICE2_DIR, COSYVOICE2_ID, resolve_cosyvoice_dir


class CosyVoice2LocalService:
    """Kaggle 本地 CosyVoice2-0.5B，延迟加载。"""

    def __init__(
        self,
        model_dir: Optional[Path] = None,
        device: Optional[str] = None,
    ) -> None:
        self.model_dir = model_dir or resolve_cosyvoice_dir()
        self.model_id = COSYVOICE2_ID
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._cosy = None

    def is_available(self) -> bool:
        return self.model_dir.exists() and any(self.model_dir.iterdir())

    def _lazy_load(self):
        if self._cosy is not None:
            return
        # CosyVoice 官方包名为 cosyvoice；若未安装，提示安装
        try:
            from cosyvoice.cli.cosyvoice import CosyVoice2  # type: ignore
        except ImportError as e:
            raise ImportError(
                "未安装 cosyvoice。Kaggle 中运行: pip install cosyvoice  # 或 fun-cosyvoice"
            ) from e
        # CosyVoice2 构造参数可能随版本变化，优先本地目录
        local_only = self.model_dir.exists()
        src = str(self.model_dir) if local_only else self.model_id
        # 兼容不同签名：尝试常用构造
        try:
            self._cosy = CosyVoice2(src, load_jit=False, load_trt=False, fp16=torch.cuda.is_available())
        except TypeError:
            self._cosy = CosyVoice2(src)

    @torch.no_grad()
    def tts(
        self,
        text: str,
        reference_audio: Optional[Path | str] = None,
        reference_text: Optional[str] = None,
        output_path: Optional[Path] = None,
    ) -> Path:
        """
        文本转语音（支持零样本克隆）。
        - text: 目标文本（中/英/葡等）
        - reference_audio: 克隆参考音频路径（3-10s，wav），为 None 时使用默认音色
        - reference_text: 参考音频对应文本（可选，提升相似度）
        """
        if not text:
            raise ValueError("text 不能为空")
        self._lazy_load()
        assert self._cosy is not None
        out_path = output_path or Path(f"/tmp/cosyvoice2_{int(time.time()*1000)}.wav")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # 统一调用：优先零样本，否则普通 TTS
        # 不同版本 API 差异较大，做两级适配
        try:
            if reference_audio:
                # 常见签名: inference_zero_shot(text, prompt_text, prompt_speech_16k)
                import torchaudio

                wav, sr = torchaudio.load(str(reference_audio))
                if wav.shape[0] > 1:
                    wav = wav.mean(dim=0, keepdim=True)
                if sr != 16000:
                    wav = torchaudio.functional.resample(wav, sr, 16000)
                wav = wav.to(self.device)
                # 尝试零样本接口
                if hasattr(self._cosy, "inference_zero_shot"):
                    result = self._cosy.inference_zero_shot(
                        text, reference_text or "", wav.squeeze(0)
                    )
                elif hasattr(self._cosy, "inference_cross_lingual"):
                    result = self._cosy.inference_cross_lingual(text, wav.squeeze(0))
                else:
                    result = self._cosy.inference_sft(text)
            else:
                # 无参考音色，使用 SFT
                if hasattr(self._cosy, "inference_sft"):
                    result = self._cosy.inference_sft(text)
                else:
                    result = self._cosy.inference_zero_shot(text, "", None)  # type: ignore
        except Exception as e:
            raise RuntimeError(f"CosyVoice2 推理失败: {e}") from e

        # result 可能是 dict 含 tts_speech 或直接为 tensor
        import soundfile as sf

        wav_out = None
        sr_out = 22050
        if isinstance(result, dict):
            wav_out = result.get("tts_speech")
            sr_out = result.get("tts_speech_rate", sr_out) or sr_out
        else:
            wav_out = result
        if wav_out is None:
            raise RuntimeError("CosyVoice2 未返回音频")

        # 转 numpy
        if torch.is_tensor(wav_out):
            wav_out = wav_out.cpu().float().numpy()
        # 兼容 [T] 或 [1, T]
        if wav_out.ndim == 2 and wav_out.shape[0] == 1:
            wav_out = wav_out[0]
        sf.write(str(out_path), wav_out, sr_out)
        return out_path

    def health(self) -> dict:
        import shutil

        try:
            total, used, free = shutil.disk_usage(self.model_dir if self.model_dir.exists() else Path.cwd())
        except Exception:
            free = 0
        return {
            "model_id": self.model_id,
            "model_dir": str(self.model_dir),
            "exists": self.is_available(),
            "device": self.device,
            "cuda": torch.cuda.is_available(),
            "free_gb": free / 1024**3 if free else 0,
        }
