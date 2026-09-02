"""
MVP 模型路径与配置

- MusicGen-small: facebook/musicgen-small (~1GB, 300M, MIT)
- CosyVoice2-0.5B: FunAudioLLM/CosyVoice2-0.5B (~1.2GB, 0.5B, Apache 2.0)
- 统一本地路径: /kaggle/working/models/{musicgen-small,cosyvoice2-0.5b}
- Kaggle 时通过 HF_TOKEN 下载，权重不入库
"""

from pathlib import Path
import os

# 基础模型根目录，可通过环境变量覆盖
MODEL_ROOT = Path(os.getenv("MVP_MODEL_ROOT", "/kaggle/working/models"))

MUSICGEN_SMALL_ID = "facebook/musicgen-small"
MUSICGEN_SMALL_DIR = MODEL_ROOT / "musicgen-small"

COSYVOICE2_ID = "FunAudioLLM/CosyVoice2-0.5B"
COSYVOICE2_DIR = MODEL_ROOT / "cosyvoice2-0.5b"

# 本地开发回退目录
LOCAL_FALLBACK_ROOT = Path(__file__).resolve().parents[3] / "models"


def resolve_musicgen_dir() -> Path:
    for p in [MUSICGEN_SMALL_DIR, LOCAL_FALLBACK_ROOT / "musicgen-small"]:
        if p.exists():
            return p
    return MUSICGEN_SMALL_DIR


def resolve_cosyvoice_dir() -> Path:
    for p in [COSYVOICE2_DIR, LOCAL_FALLBACK_ROOT / "cosyvoice2-0.5b"]:
        if p.exists():
            return p
    return COSYVOICE2_DIR


def model_status() -> dict:
    return {
        "musicgen_small": {
            "id": MUSICGEN_SMALL_ID,
            "dir": str(MUSICGEN_SMALL_DIR),
            "exists": MUSICGEN_SMALL_DIR.exists(),
        },
        "cosyvoice2": {
            "id": COSYVOICE2_ID,
            "dir": str(COSYVOICE2_DIR),
            "exists": COSYVOICE2_DIR.exists(),
        },
        "model_root": str(MODEL_ROOT),
    }
