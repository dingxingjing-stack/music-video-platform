"""Stage 2「4-stem 模型对比 POC」— MDX-Net baseline vs MDX23C vs Mega 53-Stems。

用法：
  python scripts/poc_4stem_compare.py <mdx23c|mega53> [--skip-extra]
    --skip-extra  跳过并发(4×重型模型)与失败行为阶段，仅采集核心推理指标

每一阶段完成后即时写入 poc_4stem_report.json，可断点续跑。
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path

import psutil
import soundfile as sf

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
MODEL_DIR = DATA_DIR / "audio_separator_models"
OUT_BASE = DATA_DIR / "poc_4stem_out"
REPORT_DIR = PROJECT_ROOT / "docs" / "audio_separation_verification" / "2026-08-15_poc_4stem"

os.environ["AUDIO_SEPARATOR_MODEL_DIR"] = str(MODEL_DIR)

TEST_AUDIO = DATA_DIR / "poc_3m30s.wav"

REPORT: dict = {}


def log(msg: str) -> None:
    print(msg, flush=True)


def ram_gb() -> dict:
    vm = psutil.virtual_memory()
    return {"total_gb": round(vm.total / 1e9, 1), "avail_gb": round(vm.available / 1e9, 1)}


def rss_mb() -> float:
    return psutil.Process().memory_info().rss / 1e6


def cpu_pct() -> float:
    try:
        return psutil.Process().cpu_percent(interval=None)
    except Exception:  # noqa: BLE001
        return 0.0


def measure_wav(pa):
    try:
        import numpy as np
        info = sf.info(str(pa))
        y, sr = sf.read(str(pa), always_2d=True)
        rms = float(np.sqrt(np.mean(y ** 2)))
        peak = float(np.max(np.abs(y)))
        return {
            "duration": round(info.frames / info.samplerate, 2),
            "sr": info.samplerate,
            "channels": info.channels,
            "rms": round(rms, 4),
            "peak": round(peak, 4),
            "size_mb": round(pa.stat().st_size / 1e6, 1),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def stem_label(path: Path) -> str:
    b = path.stem.lower()
    for stem in ("vocals", "drums", "bass", "other", "instrumental", "lead-vocal", "back-vocal", "vocal"):
        if f"({stem})" in b or f"_{stem}_" in b or b.endswith(f"_{stem}") or b.endswith(f"({stem})"):
            return stem
    return b


def save() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    p = REPORT_DIR / "poc_4stem_report.json"
    p.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"  [保存] {p}")


def run_model(model_name: str, model_filename: str, out_subdir: str, skip_extra: bool) -> dict:
    log(f"\n{'='*70}\n### 模型: {model_name} ({model_filename})\n{'='*70}")
    out_dir = OUT_BASE / out_subdir
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rec = {"model_name": model_name, "model_filename": model_filename, "ram": ram_gb()}
    t_all = time.monotonic()

    from audio_separator.separator import Separator

    # ---- 首次下载 + 加载 ----
    t0 = time.monotonic()
    sep = Separator(
        log_level=30, model_file_dir=str(MODEL_DIR), output_dir=str(out_dir),
        output_format="WAV", sample_rate=44100,
        mdx_params={"hop_length": 1024, "segment_size": 256, "overlap": 0.25, "batch_size": 1, "enable_denoise": False},
        mdxc_params={"segment_size": 256, "batch_size": 1, "overlap": 8, "pitch_shift": 0},
    )
    sep.load_model(model_filename=model_filename)
    rec["first_load_elapsed_s"] = round(time.monotonic() - t0, 1)
    rec["rss_after_load_mb"] = round(rss_mb(), 1)
    log(f"  首次加载(含下载): {rec['first_load_elapsed_s']}s  RSS={rss_mb():.0f}MB")
    save()

    # ---- 推理（核心） ----
    base_rss = rss_mb()
    t0 = time.monotonic()
    try:
        out_files = sep.separate(str(TEST_AUDIO))
        rec["separate_return"] = [str(f) for f in (out_files or [])]
        rec["separate_exception"] = None
    except Exception as exc:  # noqa: BLE001
        rec["separate_exception"] = str(exc)
        rec["separate_return"] = None
        log(f"  separate 异常: {exc}")
        out_files = []
    rec["inference_elapsed_s"] = round(time.monotonic() - t0, 1)
    rec["peak_rss_mb"] = round(rss_mb(), 1)
    rec["rss_delta_mb"] = round(rss_mb() - base_rss, 1)
    rec["cpu_pct_sample"] = round(cpu_pct(), 1)
    rec["total_elapsed_s"] = round(time.monotonic() - t_all, 1)

    produced = sorted(out_dir.rglob("*.wav"))
    rec["produced_files"] = [p.name for p in produced]
    rec["produced_count"] = len(produced)
    rec["produced_size_mb"] = round(sum(p.stat().st_size for p in produced) / 1e6, 1)
    rec["file_metrics"] = {stem_label(p): measure_wav(p) for p in produced}
    rec["output_stem_labels"] = sorted({stem_label(p) for p in produced})
    rec["stable_3m30s"] = rec.get("separate_exception") is None and len(produced) > 0
    log(f"  推理: {rec['inference_elapsed_s']}s  RSS+{rec['rss_delta_mb']:.0f}MB  输出 {len(produced)} 文件")
    save()

    # ---- 缓存后第二次（仅加载+推理） ----
    if rec.get("separate_exception") is None:
        t0 = time.monotonic()
        sep2 = Separator(
            log_level=30, model_file_dir=str(MODEL_DIR), output_dir=str(out_dir),
            output_format="WAV", sample_rate=44100,
            mdx_params={"hop_length": 1024, "segment_size": 256, "overlap": 0.25, "batch_size": 1, "enable_denoise": False},
            mdxc_params={"segment_size": 256, "batch_size": 1, "overlap": 8, "pitch_shift": 0},
        )
        sep2.load_model(model_filename=model_filename)
        rec["cached_load_elapsed_s"] = round(time.monotonic() - t0, 1)
        t0 = time.monotonic()
        try:
            sep2.separate(str(TEST_AUDIO))
            rec["cached_infer_elapsed_s"] = round(time.monotonic() - t0, 1)
            rec["cached_infer_error"] = None
        except Exception as exc:  # noqa: BLE001
            rec["cached_infer_elapsed_s"] = None
            rec["cached_infer_error"] = str(exc)
        log(f"  缓存后加载: {rec['cached_load_elapsed_s']}s  缓存后推理: {rec['cached_infer_elapsed_s']}s")
        save()

    # ---- 并发行为（仅并发 2 线程，避免资源爆炸） ----
    if not skip_extra and rec.get("separate_exception") is None:
        log("  并发行为（2 线程，各独立 Separator，同 output_dir）...")
        results, errors = {}, []

        def _worker(i):
            try:
                s = Separator(
                    log_level=40, model_file_dir=str(MODEL_DIR), output_dir=str(out_dir),
                    output_format="WAV", sample_rate=44100,
                    mdx_params={"hop_length": 1024, "segment_size": 256, "overlap": 0.25, "batch_size": 1},
                    mdxc_params={"segment_size": 256, "batch_size": 1, "overlap": 8},
                )
                s.load_model(model_filename=model_filename)
                results[i] = len(s.separate(str(TEST_AUDIO)))
            except Exception as exc:  # noqa: BLE001
                errors.append((i, str(exc)))

        t0 = time.monotonic()
        ths = [threading.Thread(target=_worker, args=(i,)) for i in range(2)]
        for th in ths:
            th.start()
        for th in ths:
            th.join(timeout=1200)
        alive = [i for i, th in enumerate(ths) if th.is_alive()]
        rec["concurrency"] = {
            "threads": 2,
            "total_elapsed_s": round(time.monotonic() - t0, 1),
            "success_count": sum(1 for v in results.values() if isinstance(v, int)),
            "errors": [str(e) for e in errors[:5]],
            "still_alive": alive,
        }
        log(f"  并发: 成功={rec['concurrency']['success_count']}/2 存活={alive} 错误={errors[:3]}")
        save()

    # ---- 失败行为 ----
    if not skip_extra:
        log("  失败行为（空文件 / 缺失文件）...")
        empty = DATA_DIR / "poc_empty4.wav"
        empty.write_bytes(b"")
        try:
            s = Separator(log_level=50, model_file_dir=str(MODEL_DIR), output_dir=str(out_dir),
                          output_format="WAV", sample_rate=44100)
            s.load_model(model_filename=model_filename)
            r_empty = s.separate(str(empty))
            rec["failure_empty"] = "ok" if not r_empty else f"returned {r_empty}"
        except Exception as exc:  # noqa: BLE001
            rec["failure_empty"] = f"exception: {exc}"
        try:
            r_missing = s.separate(str(DATA_DIR / "nope_missing.wav"))
            rec["failure_missing"] = "ok" if not r_missing else f"returned {r_missing}"
        except Exception as exc:  # noqa: BLE001
            rec["failure_missing"] = f"exception: {exc}"
        log(f"  failure_empty={rec['failure_empty']}  failure_missing={rec['failure_missing']}")
        save()

    log(f"  实际输出 {len(produced)} 个文件: {[p.name for p in produced]}")
    log(f"  stem labels: {rec['output_stem_labels']}")
    return rec


MODELS = {
    "mdx23c": ("MDX23C-8KFFT-InstVoc_HQ", "MDX23C-8KFFT-InstVoc_HQ.ckpt", "mdx23c"),
    "mega53": ("MVSep Mega 53-Stems v1.0.21", "mvsep_mega_model_bs_roformer_53_stems_v1.ckpt", "mega53"),
}


def main() -> None:
    global REPORT
    REPORT = {"env": {"gpu": "N/A (CPU only)", "python": sys.version.split()[0], **ram_gb()}}

    only = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in MODELS else None
    skip_extra = "--skip-extra" in sys.argv

    report_path = REPORT_DIR / "poc_4stem_report.json"
    if report_path.exists():
        try:
            REPORT.update(json.loads(report_path.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            pass

    if "baseline_mdxnet" not in REPORT:
        baseline_path = PROJECT_ROOT / "docs" / "audio_separation_verification" / "2026-08-15_poc_mdx" / "poc_report.json"
        if baseline_path.exists():
            REPORT["baseline_mdxnet"] = json.loads(baseline_path.read_text(encoding="utf-8"))["first_run"]
            REPORT["baseline_mdxnet"]["model_name"] = "UVR_MDXNET_9482.onnx (MDX-Net, 2-stem)"
        else:
            REPORT["baseline_mdxnet"] = {"note": "baseline 报告缺失，按用户给定的固定 baseline 数据记录"}

    keys = [only] if only else list(MODELS.keys())
    for key in keys:
        if key in REPORT and "inference_elapsed_s" in REPORT[key]:
            log(f"跳过已完成模型 {key}（断点续跑）")
            continue
        name, filename, subdir = MODELS[key]
        REPORT[key] = run_model(name, filename, subdir, skip_extra)
        save()

    log(f"\n最终报告: {report_path}")


if __name__ == "__main__":
    main()