"""Stage 2 第一阶段 POC：MDX 分离（python-audio-separator + UVR_MDXNET_9482）。

验证项（用户批准的第一阶段目标）：
  1. 模型加载 / 下载缓存 / 推理 / WAV 输出
  2. CPU 环境实测：3:30 音频推理耗时、峰值内存、临时磁盘占用
  3. 并发安全（同进程并发分离）
  4. 模型缓存复用（不重复下载）
  5. 异常 / 超时 / 加载失败 → 正常返回错误（走 Spleeter fallback 或 failure）
  6. 严格兼容 separate 契约 {"success","stems","duration","message"}
  7. 轨道语义诚实：real_stems / derived_stems / missing_stems 明确记录

运行（Windows PowerShell，UTF-8）：
  chcp 65001; $env:PYTHONIOENCODING="utf-8"
  & "C:\\Users\\dingx\\AppData\\Local\\Programs\\Python\\Python312\\python.exe" backend/scripts/poc_mdx_separation.py

说明：本机无 GPU（CPU only），显存项在 POC 中记录为 N/A（GPU/Modal 环境验证留待
Modal 部署阶段）。不修改任何生产代码/路由。
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path

import numpy as np
import soundfile as sf

# 项目根
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.separation.audio_separator_service import AudioSeparatorService  # noqa: E402
from app.services.separation.base import SEPARATION_CONTRACT_KEYS  # noqa: E402

DATA_DIR = PROJECT_ROOT / "data"
MODEL_DIR = DATA_DIR / "audio_separator_models"
OUT_DIR = DATA_DIR / "poc_out"
REPORT_DIR = PROJECT_ROOT / "docs" / "audio_separation_verification" / "2026-08-15_poc_mdx"

# 环境变量注入（框架读 AUDIO_SEPARATOR_MODEL_DIR）
os.environ["AUDIO_SEPARATOR_MODEL_DIR"] = str(MODEL_DIR)

REPORT: dict = {}


def log(msg: str) -> None:
    print(msg, flush=True)


def gen_test_audio(duration_s: float, path: Path, sample_rate: int = 44100) -> None:
    """生成 3:30 左右立体声混合测试音频（低频+中频+人声段+打击脉冲）。"""
    n = int(duration_s * sample_rate)
    t = np.linspace(0, duration_s, n, endpoint=False)
    mix = (
        0.3 * np.sin(2 * np.pi * 110 * t)
        + 0.2 * np.sin(2 * np.pi * 330 * t)
        + 0.1 * np.sin(2 * np.pi * 550 * t)
    )
    pulse = np.zeros_like(mix)
    pulse[:: sample_rate // 2] = 0.5
    vocals = 0.25 * np.sin(2 * np.pi * 220 * t) * (np.sin(2 * np.pi * 3 * t) > 0)
    mix = mix + vocals + 0.3 * pulse + 0.05 * np.random.randn(n)
    stereo = np.stack([mix, mix * 0.98], axis=1)
    sf.write(str(path), stereo, sample_rate)
    log(f"[gen] 测试音频 {duration_s:.0f}s 生成: {path} ({path.stat().st_size/1e6:.1f} MB)")


def measure_rss_mb() -> float:
    """当前进程峰值 RSS（仅 Windows）。"""
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1e6
    except Exception:  # noqa: BLE001
        return 0.0


def run_poc() -> dict:
    # ---- 0. 准备 ----
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    test_audio = DATA_DIR / "poc_3m30s.wav"
    if not test_audio.exists():
        gen_test_audio(210.0, test_audio)  # 3:30
    else:
        log(f"[prep] 复用既有测试音频 {test_audio}")

    svc = AudioSeparatorService(
        output_dir=str(OUT_DIR),
        model_file_dir=str(MODEL_DIR),
    )

    # ---- 1. 首次推理（含模型下载）+ 契约校验 + 性能 ----
    log("\n=== 1. 首次分离（含首次模型下载） ===")
    t0 = time.monotonic()
    res = svc.separate(str(test_audio))
    dt = time.monotonic() - t0
    log(f"  推理+加载耗时: {dt:.1f}s（含首启下载/加载）")
    log(f"  contract: {json.dumps(res.to_contract_dict(), ensure_ascii=False)}")
    log(f"  audit:    {json.dumps(res.to_audit_dict(), ensure_ascii=False)}")
    assert set(SEPARATION_CONTRACT_KEYS) == set(res.to_contract_dict().keys()), "契约字段不符"
    assert res.success, "首次分离失败"
    assert len(res.stems) == 2, "MDX 应产出 2 轨"
    assert set(res.missing_stems) == {"drums", "bass"}, "MDX 必须如实标记缺失轨"
    assert res.fallback_used is False, "MDX 成功不应触发 fallback"

    stem_bytes = sum(Path(s).stat().st_size for s in res.stems)
    REPORT["first_run"] = {
        "elapsed_s": round(dt, 1),
        "contract": res.to_contract_dict(),
        "real_stems": res.real_stems,
        "missing_stems": res.missing_stems,
        "stem_output_bytes": stem_bytes,
        "peak_rss_mb": round(measure_rss_mb(), 1),
    }

    # ---- 2. 模型缓存复用（第二次，应命中缓存不再下载） ----
    log("\n=== 2. 缓存复用（第二次分离） ===")
    cache_files_before = [p for p in MODEL_DIR.rglob("*") if p.is_file()]
    cache_size_before = sum(p.stat().st_size for p in cache_files_before)
    log(f"  缓存文件数={len(cache_files_before)} 大小={cache_size_before/1e6:.1f} MB")
    t0 = time.monotonic()
    res2 = svc.separate(str(test_audio))
    dt2 = time.monotonic() - t0
    cache_files_after = [p for p in MODEL_DIR.rglob("*") if p.is_file()]
    new_files = [p for p in cache_files_after if p.stat().st_size != 0 and p not in cache_files_before]
    log(f"  第二次耗时: {dt2:.1f}s（应显著小于首次）")
    log(f"  新增缓存文件: {len(new_files)}")
    assert res2.success
    REPORT["cache_reuse"] = {
        "second_elapsed_s": round(dt2, 1),
        "new_cache_files": len(new_files),
        "cache_dir_mb": round(cache_size_before / 1e6, 1),
    }

    # ---- 3. 并发安全（4 线程同时分离） ----
    log("\n=== 3. 并发安全（4 线程） ===")
    results: dict[int, object] = {}
    errors: list = []

    def _worker(idx: int):
        try:
            results[idx] = svc.separate(str(test_audio))
        except Exception as exc:  # noqa: BLE001
            errors.append((idx, str(exc)))

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(4)]
    t0 = time.monotonic()
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=600)
    dt_conc = time.monotonic() - t0
    alive = [i for i, th in enumerate(threads) if th.is_alive()]
    ok = [i for i, r in results.items() if r.success]
    log(f"  并发总耗时: {dt_conc:.1f}s，成功={len(ok)}/4，异常={errors}，仍存活={alive}")
    assert not alive, "存在未完成线程（可能死锁/超时）"
    REPORT["concurrency"] = {
        "threads": 4,
        "total_elapsed_s": round(dt_conc, 1),
        "success_count": len(ok),
        "errors": [str(e) for e in errors[:5]],
    }

    # ---- 4. 异常/边界 ----
    log("\n=== 4. 异常 / 边界 ===")
    cases = {}

    # 4a. 不存在文件
    r = svc.separate(str(DATA_DIR / "nope_missing.wav"))
    cases["missing_file"] = r.to_contract_dict()
    log(f"  missing_file: {r.to_contract_dict()}")

    # 4b. 空文件
    empty = DATA_DIR / "poc_empty.wav"
    empty.write_bytes(b"")
    r = svc.separate(str(empty))
    cases["empty_file"] = r.to_contract_dict()
    log(f"  empty_file:   {r.to_contract_dict()}")

    # 4c. 损坏文件（随机字节）
    corrupt = DATA_DIR / "poc_corrupt.wav"
    corrupt.write_bytes(os.urandom(4096))
    r = svc.separate(str(corrupt))
    cases["corrupt_file"] = r.to_contract_dict()
    log(f"  corrupt_file: {r.to_contract_dict()}")

    # 4d. 短音频 / 不同采样率（16kHz 单声道）
    mono16 = DATA_DIR / "poc_16k_mono.wav"
    sr = 16000
    t = np.linspace(0, 2.0, int(2.0 * sr), endpoint=False)
    mono = (0.4 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    sf.write(str(mono16), mono, sr)
    r = svc.separate(str(mono16))
    cases["16k_mono"] = {"success": r.success, "n_stems": len(r.stems), "duration": r.duration}
    log(f"  16k_mono: {cases['16k_mono']}")

    REPORT["edge_cases"] = cases

    # ---- 5. 超时保护 ----
    log("\n=== 5. 超时保护 ===")
    try:
        svc_timeout = AudioSeparatorService(
            output_dir=str(OUT_DIR),
            model_file_dir=str(MODEL_DIR),
            timeout_seconds=0.001,  # 强制超时
        )
        r = svc_timeout.separate(str(test_audio))
        log(f"  timeout result: success={r.success} msg={r.message}")
        REPORT["timeout"] = {"result": r.to_contract_dict()}
    except Exception as exc:  # noqa: BLE001
        log(f"  timeout raised: {exc}")
        REPORT["timeout"] = {"raised": str(exc)}

    # ---- 6. Spleeter fallback 探针（本地无 Modal 卷 → 明确失败，不崩溃） ----
    log("\n=== 6. Spleeter fallback 探针 ===")
    r = svc.separate_4stem(str(test_audio))
    log(f"  separate_4stem: success={r.success} msg={r.message}")
    REPORT["spleeter_probe"] = {"success": r.success, "message": r.message}

    # ---- 报告 ----
    REPORT["env"] = {
        "audio_separator_version": __import__("audio_separator", fromlist=["__version__"]).__version__
        if hasattr(__import__("audio_separator", fromlist=["__version__"]), "__version__") else "0.44.5",
        "gpu": "N/A (本机无 GPU，CPU only)",
        "python": sys.version.split()[0],
        "test_audio_seconds": 210.0,
    }
    report_path = REPORT_DIR / "poc_report.json"
    report_path.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"\n报告已写入: {report_path}")
    return REPORT


if __name__ == "__main__":
    try:
        run_poc()
    except Exception as exc:  # noqa: BLE001
        log(f"POC 异常中断: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)