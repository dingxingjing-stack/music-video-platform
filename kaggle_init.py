"""
Kaggle Notebook 初始化逻辑 — 严格 Dataset 模式

职责：
  1. 统一 HF/Torch 缓存到 /kaggle/working/cache（避免 ~/.cache 双份）
  2. 磁盘检查：总/已用/剩余 + Dataset/缓存大小
  3. HeartMuLa 3B 严格检查：/kaggle/input/heartmula-3b 必须完整（config.json + *.safetensors），
     否则直接抛 HeartMuLaDatasetError，不回落到 /kaggle/working，不自动下载
  4. 禁止 working 下出现 HeartMuLa 权重（安全修正）
  5. ASR small 缓存检查，已存在则跳过下载，仅允许 small
  6. 环境 guard：HEARTCODEC_LOCAL_MODE=false, GPT-SoVITS/ACE-Step 保持 Modal 远程

使用（Kaggle notebook）：
  import kaggle_init
  kaggle_init.setup()  # 或在 cell 顶部 `import kaggle_init; kaggle_init.setup()`
"""

from __future__ import annotations

import os
import pathlib


def _is_kaggle() -> bool:
    return pathlib.Path("/kaggle/input").exists() or pathlib.Path("/kaggle/working").exists()


def setup(
    heartmula_dataset: str = "/kaggle/input/heartmula-3b",
    cache_root: str = "/kaggle/working/cache",
) -> dict:
    """执行 Kaggle 初始化（严格 Dataset 模式），返回状态 dict。

    - HeartMuLa 不存在/不完整 → 抛 HeartMuLaDatasetError（不下载，不回落）
    - working 下检测到 HeartMuLa 权重 → 抛 HeartMuLaDatasetError
    """
    hf_home = os.getenv("HF_HOME", "")
    torch_home = os.getenv("TORCH_HOME", "")
    if _is_kaggle():
        hf_home = f"{cache_root}/hf"
        torch_home = f"{cache_root}/torch"
        os.environ["KAGGLE_CACHE_ROOT"] = cache_root
        os.environ["HF_HOME"] = hf_home
        os.environ["HF_HUB_CACHE"] = f"{hf_home}/hub"
        os.environ["TORCH_HOME"] = torch_home
        os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")
        pathlib.Path(hf_home).mkdir(parents=True, exist_ok=True)
        pathlib.Path(torch_home).mkdir(parents=True, exist_ok=True)
        pathlib.Path(f"{cache_root}/hf").mkdir(parents=True, exist_ok=True)
        pathlib.Path("/kaggle/working/output").mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("VOICE_CLONE_ASR_MODEL", "small")
        os.environ.setdefault("HEARTCODEC_LOCAL_MODE", "false")
        os.environ.setdefault("HEARTMULA_KAGGLE_DATASET_PATH", heartmula_dataset)

    result: dict = {
        "is_kaggle": _is_kaggle(),
        "hf_home": os.getenv("HF_HOME", hf_home),
        "torch_home": os.getenv("TORCH_HOME", torch_home),
        "heartmula_dataset": heartmula_dataset,
        "heartmula_available": False,
        "asr_small_cached": False,
        "disk": {},
    }

    try:
        import shutil as _sh

        for p in ["/kaggle/working", "/kaggle/input", cache_root]:
            pp = pathlib.Path(p)
            if pp.exists():
                usage = _sh.disk_usage(str(pp))
                result["disk"][p] = {
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                }
    except Exception:
        pass

    # 严格禁止 working 下出现 HeartMuLa 权重
    try:
        from backend.app.services.heartmula_service import assert_no_heartmula_working_download

        assert_no_heartmula_working_download()
    except ImportError:
        for p in [
            pathlib.Path("/kaggle/working/heartmula-3b"),
            pathlib.Path("/kaggle/working/cache/hf/hub/models--HeartMuLa-3b"),
            pathlib.Path("/kaggle/working/models/heartmula"),
        ]:
            if p.exists():
                raise RuntimeError(f"[HeartMuLa 安全] 禁止路径存在: {p} — 请清理并改用 Dataset。")

    # HeartMuLa 严格校验：Kaggle 下不存在/不完整直接抛错（不回落，不下载）
    if _is_kaggle():
        try:
            from backend.app.services.heartmula_service import require_heartmula_dataset, is_heartmula_dataset_available

            # require 会抛 HeartMuLaDatasetError
            require_heartmula_dataset(heartmula_dataset)
            result["heartmula_available"] = True
        except Exception as exc:
            # 严格模式：直接抛出，不吞错
            raise
    else:
        try:
            from backend.app.services.heartmula_service import is_heartmula_dataset_available  # type: ignore

            result["heartmula_available"] = is_heartmula_dataset_available(heartmula_dataset)
        except Exception:
            p = pathlib.Path(heartmula_dataset)
            result["heartmula_available"] = p.is_dir() and (p / "config.json").exists() and any(p.glob("*.safetensors"))

    try:
        from backend.app.services.experimental.asr_client import is_asr_model_cached  # type: ignore

        result["asr_small_cached"] = is_asr_model_cached("small", result["hf_home"] or hf_home)
    except Exception:
        for cand in [
            pathlib.Path(hf_home) / "hub/models--Systran--faster-whisper-small",
            pathlib.Path(hf_home) / "models--Systran--faster-whisper-small",
        ]:
            if cand.exists() and any(cand.iterdir()):
                result["asr_small_cached"] = True
                break

    print(f"[kaggle_init] is_kaggle={result['is_kaggle']}")
    print(f"[kaggle_init] HF_HOME={result['hf_home']}")
    for k, v in result["disk"].items():
        print(f"[kaggle_init] disk {k}: total {v['total_gb']}GB used {v['used_gb']}GB free {v['free_gb']}GB")
    print(f"[kaggle_init] HeartMuLa Dataset {heartmula_dataset}: {'FOUND' if result['heartmula_available'] else 'NOT FOUND'}")
    print(f"[kaggle_init] ASR small cached: {result['asr_small_cached']}")
    print("[kaggle_init] STRICT: HeartMuLa missing -> error (no fallback, no download to working)")
    return result


if __name__ == "__main__":
    setup()
