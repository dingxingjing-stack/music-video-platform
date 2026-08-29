"""Mega 53 (BS-RoFormer, 53 stems) Modal GPU 隔离 POC — 与生产完全隔离。

背景：
  Mega 53 = ZFTurbo/Music-Source-Separation-Training v1.0.21 发布的 53-stem 模型
  （mvsep_mega_model_bs_roformer_53_stems_v1.ckpt, 1368.9MB）。官方明确说明：
    - BS-RoFormer 架构，num_stems=53，建议 >=16GB VRAM
    - stems 不求和为原曲（含重叠信息）
    - 单 stem 质量低于专项模型
  audio-separator 0.44.5 内置清单不含该模型，因此本 POC 在 Modal 镜像内
  clone 官方 repo，使用官方 utils/settings.get_model_from_config + 官方
  bs_roformer 模型类直接加载 ckpt + yaml 推理（不修改任何 site-packages /
  app / separation / 测试代码）。

验证指标：
  - 模型加载时间（首次，含 torch.load + load_state_dict）
  - 3:30 音频推理时间
  - GPU VRAM（allocated / reserved / max）
  - RAM（容器内 RSS）
  - 输出 stem 数量（预期 53）
  - 是否存在 vocals / drums / bass / other 四类（记录标签）
  - 每个 stem 音频规格（时长 / 采样率 / 通道 / 大小）
  - 是否稳定完成 3:30

结论字段：
  meets_4stem_requirement: 是否满足"独立 4-stem (vocals/drums/bass/other)"。
  若 Mega 53 不是原生独立 4-stem，明确标记 False，不做后处理伪造。

用法（workdir=backend）：
  python -m modal run scripts/poc_mega53_modal.py

不覆盖任何现有报告；结果写入：
  backend/docs/audio_separation_verification/2026-08-15_poc_4stem/mega53_modal_gpu_report.json
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
    / "mega53_modal_gpu_report.json"
)

_APP = modal.App("poc-mega53-gpu")

_MODEL_VOL = modal.Volume.from_name("poc-mega53-gpu-models-v1", create_if_missing=True)
_DATA_VOL = modal.Volume.from_name("poc-mega53-gpu-data-v1", create_if_missing=True)

_MODEL_DIR = "/models"
_DATA_DIR = "/data"
_CKPT_FILENAME = "mvsep_mega_model_bs_roformer_53_stems_v1.ckpt"
_YAML_FILENAME = "mvsep_mega_model_bs_roformer_53_stems.yaml"
_MODEL_FILES = [_CKPT_FILENAME, _YAML_FILENAME]

# 关键 stems（含 drums/bass/vocals/other 代表），用于本地下载比对
_DOWNLOAD_STEMS = [
    "lead-vocal", "vocal", "back-vocal",
    "drums", "kick", "snare", "hh", "toms",
    "bass", "double-bass",
    "accordion", "piano", "guitar",
]

_IMAGE = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "ffmpeg", "libsndfile1")
    .pip_install(
        "torch",
        "torchaudio",
        "numpy",
        "librosa==0.11.0",
        "soundfile",
        "ml-collections",
        "omegaconf",
        "pyyaml",
        "tqdm",
        "einops",
        "rotary-embedding-torch",
        "beartype",
        "matplotlib",
        "psutil",
        "packaging",
    )
    .run_commands(
        [
            "git clone --depth 1 https://github.com/ZFTurbo/Music-Source-Separation-Training /msst"
        ]
    )
    .env(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
    )
)


@_APP.function(
    image=_IMAGE,
    gpu="A10G",
    timeout=60 * 50,
    max_containers=1,
    volumes={"/models": _MODEL_VOL, "/data": _DATA_VOL},
)
def run_mega53() -> dict:
    """在 GPU 容器内用官方 Mega 53 (BS-RoFormer) 分离 3:30 音频，返回指标。"""
    import sys

    sys.path.insert(0, "/msst")

    import numpy as np
    import psutil
    import soundfile as sf
    import torch
    from argparse import Namespace
    from utils.model_utils import bigshifts_wrapper, load_start_checkpoint
    from utils.settings import get_model_from_config

    rec: dict = {
        "model_name": "Mega 53",
        "model_type": "BS-RoFormer (53 stems)",
        "gpu": "A10G",
    }

    audio_path = os.path.join(_DATA_DIR, "poc_3m30s.wav")
    if not os.path.exists(audio_path):
        rec["error"] = f"volume 中缺少 {audio_path}"
        return rec

    ckpt_path = os.path.join(_MODEL_DIR, _CKPT_FILENAME)
    yaml_path = os.path.join(_MODEL_DIR, _YAML_FILENAME)
    if not os.path.exists(ckpt_path) or not os.path.exists(yaml_path):
        rec["error"] = f"volume 中缺少 {_CKPT_FILENAME} 或 {_YAML_FILENAME}"
        return rec

    rec["input_duration_s"] = round(sf.info(audio_path).frames / sf.info(audio_path).samplerate, 2)

    out_dir = os.path.join(_DATA_DIR, "out_mega53")
    if os.path.exists(out_dir):
        import shutil

        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"

    # ---- 模型加载（首次：get_model_from_config + torch.load + load_state_dict） ----
    t_all = time.monotonic()
    t0 = time.monotonic()
    try:
        model, config = get_model_from_config("bs_roformer", yaml_path)
        rec["arch_stems"] = int(config.model.num_stems)
        rec["arch_instruments"] = list(config.training.instruments)
        rec["arch_instruments_count"] = len(rec["arch_instruments"])
        checkpoint = torch.load(ckpt_path, weights_only=False, map_location="cpu")
        args = Namespace(
            start_check_point="",
            model_type="bs_roformer",
            lora_checkpoint_loralib=None,
            lora_checkpoint_peft=None,
            load_only_compatible_weights=False,
        )
        load_start_checkpoint(args, model, checkpoint, type_="inference")
        model = model.to(device)
        model.eval()
        rec["model_load_elapsed_s"] = round(time.monotonic() - t0, 1)
        rec["model_load_exception"] = None
    except Exception as exc:  # noqa: BLE001
        rec["model_load_elapsed_s"] = round(time.monotonic() - t0, 1)
        rec["model_load_exception"] = str(exc)
        rec["stable_3m30s"] = False
        _DATA_VOL.commit()
        return rec

    # ---- GPU / RAM 状态（加载后） ----
    rec["cuda_available"] = bool(torch.cuda.is_available())
    if torch.cuda.is_available():
        rec["gpu_name"] = torch.cuda.get_device_name(0)
        rec["gpu_total_vram_mb"] = round(torch.cuda.get_device_properties(0).total_memory / 1e6, 0)
        rec["vram_after_load_mb"] = round(torch.cuda.memory_allocated() / 1e6, 1)
        rec["vram_reserved_after_load_mb"] = round(torch.cuda.memory_reserved() / 1e6, 1)
    rec["rss_after_load_mb"] = round(psutil.Process().memory_info().rss / 1e6, 1)

    # ---- 推理 3:30 ----
    import librosa

    try:
        mix, sr = librosa.load(audio_path, sr=44100, mono=False)
        if mix.ndim == 1:
            mix = np.expand_dims(mix, axis=0)
    except Exception as exc:  # noqa: BLE001
        rec["separate_exception"] = f"librosa.load failed: {exc}"
        rec["stable_3m30s"] = False
        _DATA_VOL.commit()
        return rec

    t0 = time.monotonic()
    try:
        waveforms = bigshifts_wrapper(
            config,
            model,
            mix,
            torch.device(device),
            model_type="bs_roformer",
            pbar=True,
            bigshifts=1,
        )
        rec["separate_exception"] = None
        rec["returned_stem_count"] = len(waveforms)
        rec["returned_stem_labels"] = sorted(waveforms.keys())
    except Exception as exc:  # noqa: BLE001
        rec["separate_exception"] = str(exc)
        waveforms = {}
    rec["inference_elapsed_s"] = round(time.monotonic() - t0, 1)

    if torch.cuda.is_available():
        rec["vram_peak_allocated_mb"] = round(torch.cuda.max_memory_allocated() / 1e6, 1)
        rec["vram_reserved_peak_mb"] = round(torch.cuda.max_memory_reserved() / 1e6, 1)
    rec["rss_after_inference_mb"] = round(psutil.Process().memory_info().rss / 1e6, 1)
    rec["total_elapsed_s"] = round(time.monotonic() - t_all, 1)

    # ---- 保存输出 ----
    produced = []
    for instr, wav in waveforms.items():
        name = f"poc_3m30s__{instr}__Mega53.wav"
        path = os.path.join(out_dir, name)
        try:
            sf.write(path, wav.T, 44100, subtype="FLOAT")
            produced.append(path)
        except Exception as exc:  # noqa: BLE001
            rec.setdefault("write_errors", {})[instr] = str(exc)

    rec["produced_files"] = [os.path.basename(p) for p in produced]
    rec["produced_count"] = len(produced)
    rec["produced_size_mb"] = round(sum(os.path.getsize(p) for p in produced) / 1e6, 1)

    rec["file_metrics"] = {}
    for p in produced:
        try:
            info = sf.info(p)
            rec["file_metrics"][os.path.basename(p)] = {
                "duration_s": round(info.frames / info.samplerate, 2),
                "sr": info.samplerate,
                "channels": info.channels,
                "size_mb": round(os.path.getsize(p) / 1e6, 1),
            }
        except Exception as exc:  # noqa: BLE001
            rec["file_metrics"][os.path.basename(p)] = {"error": str(exc)}

    # ---- 4-stem 判定（如实记录，不后处理伪造） ----
    labels = set(rec.get("returned_stem_labels") or rec.get("arch_instruments") or [])
    vocals_candidates = {"vocal", "lead-vocal", "back-vocal"}
    drums_candidates = {"drums", "kick", "snare", "hh", "toms", "congas", "percussion", "timpani", "triangle"}
    bass_candidates = {"bass", "double-bass"}
    rec["has_vocals"] = bool(labels & vocals_candidates)
    rec["has_drums"] = bool(labels & drums_candidates)
    rec["has_bass"] = bool(labels & bass_candidates)
    rec["has_other"] = "other" in labels
    rec["native_single_stem_vocals"] = "vocals" in labels
    rec["native_single_stem_drums"] = "drums" in labels
    rec["native_single_stem_bass"] = "bass" in labels
    rec["meets_4stem_requirement"] = (
        "vocals" in labels and "drums" in labels and "bass" in labels and "other" in labels
    )
    rec["stems_sum_to_mix"] = False  # 官方声明：stems 不求和为原曲
    rec["official_notes"] = (
        "Mega 53 官方说明：内存密集(建议>=16GB VRAM)；单 stem 质量低于专项模型；"
        "stems 不求和为原曲，含重叠信息；默认返回全部 stems，过滤空 stem 为后续工作。"
    )
    rec["stable_3m30s"] = rec.get("separate_exception") is None and rec["produced_count"] > 0

    _DATA_VOL.commit()
    return rec


@_APP.local_entrypoint()
def main() -> None:
    """本机入口：上传模型 + 音频到 volume，然后运行 GPU 函数。"""
    # ---- 上传 Mega 53 模型文件（幂等：卷根目录已存在则跳过） ----
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
    print("\n=== 调用 Modal GPU (A10G) 执行 Mega 53 (53 stems) 分离 ===")
    rec = run_mega53.remote()

    # ---- 写报告（新文件，不覆盖现有报告） ----
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== 报告已写入: {_REPORT_PATH} ===")

    # ---- 下载关键 stems 到本地（便于比对） ----
    local_out = _LOCAL_MODEL_DIR.parent / "poc_4stem_out" / "mega53_modal_gpu"
    local_out.mkdir(parents=True, exist_ok=True)
    stem_by_label = {}
    for name in rec.get("produced_files", []):
        stem = name.replace("poc_3m30s__", "").replace("__Mega53.wav", "")
        stem_by_label[stem] = name
    for stem in _DOWNLOAD_STEMS:
        name = stem_by_label.get(stem)
        if not name:
            continue
        try:
            with open(local_out / name, "wb") as f:
                _DATA_VOL.read_file_into_fileobj(f"out_mega53/{name}", f)
            print(f"  [download] {name} ({local_out.joinpath(name).stat().st_size/1e6:.1f}MB)")
        except Exception as exc:  # noqa: BLE001
            print(f"  [download-fail] {name}: {exc}")

    # ---- 摘要 ----
    keys = [
        "model_name", "model_type", "gpu", "input_duration_s",
        "model_load_elapsed_s", "inference_elapsed_s", "total_elapsed_s",
        "cuda_available", "gpu_name", "gpu_total_vram_mb",
        "vram_after_load_mb", "vram_reserved_after_load_mb",
        "vram_peak_allocated_mb", "vram_reserved_peak_mb",
        "rss_after_load_mb", "rss_after_inference_mb",
        "returned_stem_count", "returned_stem_labels",
        "produced_count", "produced_size_mb",
        "has_vocals", "has_drums", "has_bass", "has_other",
        "native_single_stem_vocals", "native_single_stem_drums", "native_single_stem_bass",
        "meets_4stem_requirement", "stems_sum_to_mix", "stable_3m30s",
        "separate_exception", "model_load_exception", "error",
    ]
    print("\n=== 摘要 ===")
    print(json.dumps({k: rec.get(k) for k in keys if k in rec}, ensure_ascii=False, indent=2))