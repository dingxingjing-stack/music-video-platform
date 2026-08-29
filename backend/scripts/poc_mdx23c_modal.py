"""MDX23C Modal GPU 隔离 POC — 与生产完全隔离，不改任何 app / separation / 测试代码。

背景：MDX23C-8KFFT-InstVoc_HQ（427MB）在本机 CPU 上首次加载+推理 3:30 音频超时，
因此改在 Modal GPU（A10G）上隔离验证，采集与 MDX-Net baseline 可对比的指标。

验证指标：
  - 模型加载时间（首次，含/不含下载）
  - 3:30 音频推理时间
  - GPU VRAM（allocated / reserved / max）
  - RAM（容器内 RSS）
  - 输出 stem 数量（预期 2：vocals + instrumental，因该模型为 2-stem）
  - 输出音频时长 / 采样率 / 文件大小

用法（workdir=backend）：
  python -m modal run scripts/poc_mdx23c_modal.py

不覆盖任何现有报告；结果写入：
  backend/docs/audio_separation_verification/2026-08-15_poc_4stem/mdx23c_modal_gpu_report.json
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import modal

# 只读导入本地路径常量，容器内不使用这些路径
_LOCAL_MODEL_DIR = Path(__file__).resolve().parents[1] / "data" / "audio_separator_models"
_LOCAL_AUDIO = Path(__file__).resolve().parents[1] / "data" / "poc_3m30s.wav"
_REPORT_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "audio_separation_verification"
    / "2026-08-15_poc_4stem"
    / "mdx23c_modal_gpu_report.json"
)

_APP = modal.App("poc-mdx23c-gpu")

_MODEL_VOL = modal.Volume.from_name("poc-mdx23c-gpu-models-v1", create_if_missing=True)
_DATA_VOL = modal.Volume.from_name("poc-mdx23c-gpu-data-v1", create_if_missing=True)

_MODEL_DIR = "/models"
_DATA_DIR = "/data"
_MODEL_FILENAME = "MDX23C-8KFFT-InstVoc_HQ.ckpt"
_MODEL_FILES = [
    "MDX23C-8KFFT-InstVoc_HQ.ckpt",
    "model_2_stem_full_band_8k.yaml",
    "download_checks.json",
    "mdx_model_data.json",
]

_IMAGE = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install(
        "audio-separator==0.44.5",
        "librosa==0.11.0",
        "onnxruntime",
        "audioread",
        "psutil",
        "soundfile",
    )
    .env(
        {
            "AUDIO_SEPARATOR_MODEL_DIR": _MODEL_DIR,
            "PYTHONIOENCODING": "utf-8",
        }
    )
)


@_APP.function(
    image=_IMAGE,
    gpu="A10G",
    timeout=60 * 20,
    max_containers=1,
    volumes={"/models": _MODEL_VOL, "/data": _DATA_VOL},
)
def run_mdx23c() -> dict:
    """在 GPU 容器内加载 MDX23C 并分离 3:30 音频，返回指标。"""
    import psutil
    import soundfile as sf

    rec: dict = {
        "model_name": "MDX23C-8KFFT-InstVoc_HQ",
        "model_type": "MDX23C (2-stem: vocals + instrumental)",
        "gpu": "A10G",
    }

    audio_path = os.path.join(_DATA_DIR, "poc_3m30s.wav")
    if not os.path.exists(audio_path):
        rec["error"] = f"volume 中缺少 {audio_path}"
        return rec
    rec["input_duration_s"] = round(sf.info(audio_path).frames / sf.info(audio_path).samplerate, 2)

    from audio_separator.separator import Separator

    out_dir = os.path.join(_DATA_DIR, "out_mdx23c")
    if os.path.exists(out_dir):
        import shutil

        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    # ---- 模型加载（首次，模型已在 volume，无需下载） ----
    t_all = time.monotonic()
    t0 = time.monotonic()
    sep = Separator(
        log_level=30,
        model_file_dir=_MODEL_DIR,
        output_dir=out_dir,
        output_format="WAV",
        sample_rate=44100,
        mdxc_params={"segment_size": 256, "batch_size": 1, "overlap": 8, "pitch_shift": 0},
    )
    sep.load_model(model_filename=_MODEL_FILENAME)
    rec["model_load_elapsed_s"] = round(time.monotonic() - t0, 1)

    # ---- GPU / RAM 状态 ----
    import torch

    rec["cuda_available"] = bool(torch.cuda.is_available())
    if torch.cuda.is_available():
        rec["gpu_name"] = torch.cuda.get_device_name(0)
        rec["gpu_total_vram_mb"] = round(torch.cuda.get_device_properties(0).total_memory / 1e6, 0)
        rec["vram_after_load_mb"] = round(torch.cuda.memory_allocated() / 1e6, 1)
        rec["vram_reserved_after_load_mb"] = round(torch.cuda.memory_reserved() / 1e6, 1)
    rec["rss_after_load_mb"] = round(psutil.Process().memory_info().rss / 1e6, 1)

    # ---- 推理 3:30 ----
    t0 = time.monotonic()
    try:
        out_files = sep.separate(audio_path)
        rec["separate_return"] = [str(f) for f in (out_files or [])]
        rec["separate_exception"] = None
    except Exception as exc:  # noqa: BLE001
        rec["separate_exception"] = str(exc)
        rec["separate_return"] = None
        out_files = []
    rec["inference_elapsed_s"] = round(time.monotonic() - t0, 1)

    if torch.cuda.is_available():
        rec["vram_peak_allocated_mb"] = round(torch.cuda.max_memory_allocated() / 1e6, 1)
        rec["vram_reserved_peak_mb"] = round(torch.cuda.max_memory_reserved() / 1e6, 1)
    rec["rss_after_inference_mb"] = round(psutil.Process().memory_info().rss / 1e6, 1)
    rec["total_elapsed_s"] = round(time.monotonic() - t_all, 1)

    # ---- 输出文件 ----
    produced = sorted(Path(out_dir).rglob("*.wav"))
    rec["produced_files"] = [p.name for p in produced]
    rec["produced_count"] = len(produced)
    rec["produced_size_mb"] = round(sum(p.stat().st_size for p in produced) / 1e6, 1)
    rec["file_metrics"] = {}
    for p in produced:
        try:
            info = sf.info(str(p))
            rec["file_metrics"][p.name] = {
                "duration_s": round(info.frames / info.samplerate, 2),
                "sr": info.samplerate,
                "channels": info.channels,
                "size_mb": round(p.stat().st_size / 1e6, 1),
            }
        except Exception as exc:  # noqa: BLE001
            rec["file_metrics"][p.name] = {"error": str(exc)}
    rec["output_stem_labels"] = sorted(
        {name.split("_(")[-1].split(")")[0].lower() if "_(" in name else name for name in rec["produced_files"]}
    )
    rec["stable_3m30s"] = rec.get("separate_exception") is None and rec["produced_count"] > 0

    _DATA_VOL.commit()
    return rec


@_APP.local_entrypoint()
def main() -> None:
    """本机入口：上传模型 + 音频到 volume，然后运行 GPU 函数。"""
    import shutil

    # ---- 上传模型文件（幂等：卷根目录已存在则跳过） ----
    try:
        model_dir_entries = {e.path.split("/")[-1] for e in _MODEL_VOL.listdir("/")}
    except Exception:  # noqa: BLE001 目录尚不存在
        model_dir_entries = set()
    with _MODEL_VOL.batch_upload() as batch:
        for name in _MODEL_FILES:
            if name in model_dir_entries:
                print(f"  [skip] /models/{name} (already uploaded)")
                continue
            src = _LOCAL_MODEL_DIR / name
            if src.exists():
                batch.put_file(src, f"/{name}")
                print(f"  [upload] /models/{name} ({src.stat().st_size/1e6:.1f}MB)")

    # ---- 上传测试音频（幂等，卷根目录） ----
    try:
        data_dir_entries = {e.path.split("/")[-1] for e in _DATA_VOL.listdir("/")}
    except Exception:  # noqa: BLE001 目录尚不存在
        data_dir_entries = set()
    with _DATA_VOL.batch_upload() as batch:
        if "poc_3m30s.wav" not in data_dir_entries and _LOCAL_AUDIO.exists():
            batch.put_file(_LOCAL_AUDIO, "/poc_3m30s.wav")
            print(f"  [upload] /data/poc_3m30s.wav ({_LOCAL_AUDIO.stat().st_size/1e6:.1f}MB)")

    # ---- 运行 GPU 函数 ----
    print("\n=== 调用 Modal GPU (A10G) 执行 MDX23C 分离 ===")
    rec = run_mdx23c.remote()

    # ---- 写报告（新文件，不覆盖现有报告） ----
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== 报告已写入: {_REPORT_PATH} ===")

    # ---- 下载输出 wav 到本地（便于比对） ----
    local_out = _LOCAL_MODEL_DIR.parent / "poc_4stem_out" / "mdx23c_modal_gpu"
    local_out.mkdir(parents=True, exist_ok=True)
    for name in rec.get("produced_files", []):
        try:
            with open(local_out / name, "wb") as f:
                _DATA_VOL.read_file_into_fileobj(f"out_mdx23c/{name}", f)
            print(f"  [download] {name} ({local_out.joinpath(name).stat().st_size/1e6:.1f}MB)")
        except Exception as exc:  # noqa: BLE001
            print(f"  [download-fail] {name}: {exc}")

    # ---- 摘要 ----
    print("\n=== 摘要 ===")
    print(json.dumps({k: v for k, v in rec.items() if k != "file_metrics"}, ensure_ascii=False, indent=2))