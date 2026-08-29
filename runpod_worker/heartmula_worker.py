#!/usr/bin/env python3
"""
RunPod Serverless Worker — HeartMuLa 10s POC
独立于 backend 生产链路，不修改 provider_registry / Modal / Fal / /health

输入:
  {"input": {"prompt": "...", "duration": 10}}

流程:
  1. 检查 CUDA
  2. 下载/加载 HeartMuLa-oss-3B (HF_TOKEN via env, 运行时缓存)
  3. 加载 HeartCodec-oss
  4. CUDA 推理 MusicGenerationPipeline.generate(prompt, duration=10)
  5. 保存 WAV
  6. 返回 {success, duration, filename, generation_time, gpu_name, cuda_version, torch_version, error}

模型权重运行时缓存至 $MODEL_CACHE_DIR (默认 /runpod-volume/pretrained，fallback /tmp/pretrained)，不提交 Git
官方运行: runpod.serverless.start({"handler": handler})
"""

import os
import sys
import time
import traceback
from pathlib import Path
from typing import Dict, Any, Optional

# 全局缓存（冷启动加载一次，温启动复用）
_MULAR = None
_CODEC = None
_PIPELINE = None
_DEVICE = None
_MODEL_LOADED = False

# 模型仓库（与 heartmula_deploy/kaggle_setup.py:28 保持一致，不硬编码 Token）
HEARTMULA_REPO = os.getenv("HEARTMULA_REPO", "HeartMuLa/HeartMuLa-oss-3B")
HEARTCODEC_REPO = os.getenv("HEARTCODEC_REPO", "HeartMuLa/HeartCodec-oss")
# 运行时缓存目录：RunPod Network Volume 优先，否则 /tmp
MODEL_CACHE_DIR = Path(os.getenv("MODEL_CACHE_DIR", "/runpod-volume/pretrained"))
if not MODEL_CACHE_DIR.exists():
    # fallback 到容器本地临时目录（需 HF_TOKEN 每次冷启动重新下载）
    MODEL_CACHE_DIR = Path(os.getenv("HF_CACHE_TMP", "/tmp/pretrained"))
HEARTMULA_DIR = MODEL_CACHE_DIR / "HeartMuLa-oss-3B"
HEARTCODEC_DIR = MODEL_CACHE_DIR / "HeartCodec-oss"
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/tmp/heartmula_output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 延迟导入 runpod（本地静态检查无 runpod 包时不报错）
try:
    import runpod
except ImportError:
    runpod = None  # type: ignore


def _get_versions() -> Dict[str, str]:
    """返回 torch / cuda 版本信息（不依赖 GPU）"""
    try:
        import torch
        cuda_ver = torch.version.cuda or "n/a"
        torch_ver = torch.__version__
    except Exception as e:
        cuda_ver = f"error:{e}"
        torch_ver = "unknown"
    return {"cuda_version": cuda_ver, "torch_version": torch_ver}


def _check_cuda() -> Dict[str, Any]:
    """检查 CUDA 可用性，返回 gpu_name / cuda_version / torch_version"""
    vers = _get_versions()
    try:
        import torch
        if not torch.cuda.is_available():
            return {"ok": False, "error": "CUDA not available (torch.cuda.is_available()==False)", **vers, "gpu_name": None}
        gpu_name = torch.cuda.get_device_name(0)
        # sm_70 检查（与 kaggle_setup.py:76 一致）
        cap = torch.cuda.get_device_capability(0)
        if cap[0] < 7:
            return {"ok": False, "error": f"GPU {gpu_name} sm_{cap[0]}{cap[1]} < sm_70", **vers, "gpu_name": gpu_name}
        return {"ok": True, "gpu_name": gpu_name, **vers}
    except Exception as e:
        return {"ok": False, "error": f"CUDA check failed: {e}", **vers, "gpu_name": None}


def _ensure_models():
    """下载/加载模型（仅第一次冷启动执行），使用 HF_TOKEN 环境变量，不写入代码"""
    global _MULAR, _CODEC, _PIPELINE, _DEVICE, _MODEL_LOADED
    if _MODEL_LOADED and _MULAR is not None and _CODEC is not None and _PIPELINE is not None:
        return

    # 1. 检查 CUDA（必须）
    cuda_info = _check_cuda()
    if not cuda_info["ok"]:
        raise RuntimeError(cuda_info["error"])
    _DEVICE = "cuda"
    gpu_name = cuda_info["gpu_name"]
    print(f"[HeartMuLa] CUDA OK: {gpu_name} {cuda_info['cuda_version']} torch {cuda_info['torch_version']}")

    # 2. 准备 HF Token（严禁硬编码）
    hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN") or os.getenv("HF_API_TOKEN")
    if hf_token:
        print(f"[HeartMuLa] HF_TOKEN present (len {len(hf_token)})")
    else:
        print("[HeartMuLa] HF_TOKEN not set — 尝试匿名下载（私有仓库需 Token）")

    # 3. snapshot_download（运行时缓存，不烘焙）
    from huggingface_hub import snapshot_download

    MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dl_kwargs = {"local_dir_use_symlinks": False}
    if hf_token:
        dl_kwargs["token"] = hf_token  # type: ignore

    if not HEARTMULA_DIR.exists():
        print(f"[HeartMuLa] snapshot_download {HEARTMULA_REPO} -> {HEARTMULA_DIR}")
        snapshot_download(repo_id=HEARTMULA_REPO, local_dir=str(HEARTMULA_DIR), **dl_kwargs)
    else:
        print(f"[HeartMuLa] cache hit {HEARTMULA_DIR}")

    if not HEARTCODEC_DIR.exists():
        print(f"[HeartMuLa] snapshot_download {HEARTCODEC_REPO} -> {HEARTCODEC_DIR}")
        snapshot_download(repo_id=HEARTCODEC_REPO, local_dir=str(HEARTCODEC_DIR), **dl_kwargs)
    else:
        print(f"[HeartMuLa] cache hit {HEARTCODEC_DIR}")

    # 4. 验证关键文件（与 kaggle_setup.py:222 一致）
    for p in [HEARTMULA_DIR / "tokenizer.json", HEARTMULA_DIR / "gen_config.json", HEARTCODEC_DIR / "config.json"]:
        if not p.exists():
            print(f"[HeartMuLa] WARN missing {p} (可能影响加载)")

    # 5. 加载模型（与 kaggle_generate.py:42 一致）
    # 强制路径无特殊处理 — RunPod 镜像已 pip 安装 heartlib
    from heartlib.heartmula import HeartMuLa
    from heartlib.heartcodec import HeartCodec
    from heartlib.pipelines import MusicGenerationPipeline

    import torch

    print(f"[HeartMuLa] loading HeartMuLa {HEARTMULA_DIR} -> {_DEVICE}")
    _MULAR = HeartMuLa.from_pretrained(str(HEARTMULA_DIR)).to(_DEVICE)
    _MULAR.eval()
    print("[HeartMuLa] HeartMuLa loaded")

    print(f"[HeartMuLa] loading HeartCodec {HEARTCODEC_DIR} -> {_DEVICE}")
    _CODEC = HeartCodec.from_pretrained(str(HEARTCODEC_DIR)).to(_DEVICE)
    _CODEC.eval()
    print("[HeartMuLa] HeartCodec loaded")

    try:
        _PIPELINE = MusicGenerationPipeline(model=_MULAR, codec=_CODEC, device=_DEVICE)
        print("[HeartMuLa] MusicGenerationPipeline created")
    except Exception as e:
        print(f"[HeartMuLa] Pipeline create failed, fallback manual: {e}")
        _PIPELINE = None
        raise RuntimeError(f"MusicGenerationPipeline init failed: {e}")

    _MODEL_LOADED = True
    print("[HeartMuLa] models ready")


def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    RunPod 官方 handler 签名: handler(event) -> dict
    event = {"input": {"prompt": str, "duration": int}} 或 {"prompt": ...} (兼容)
    返回: {success, duration, filename, generation_time, gpu_name, cuda_version, torch_version, error}
    """
    start_total = time.monotonic()
    # 解析输入（兼容 event\input 或 顶层）
    inp = event.get("input") if isinstance(event.get("input"), dict) else event
    prompt = (inp.get("prompt") or inp.get("text") or "").strip() if isinstance(inp, dict) else ""
    duration = inp.get("duration", 10) if isinstance(inp, dict) else 10
    try:
        duration = int(duration)
    except Exception:
        duration = 10
    # 仅验证 10 秒（阶段一约束）
    if duration != 10:
        print(f"[HeartMuLa] WARN duration={duration} !=10, 强制 10（阶段一仅验证 10s）")
        duration = 10
    if not prompt or len(prompt) < 3:
        prompt = "A beautiful piano melody, peaceful and emotional"

    vers = _get_versions()
    cuda_check = _check_cuda()
    if not cuda_check["ok"]:
        return {
            "success": False,
            "duration": duration,
            "filename": None,
            "generation_time": round(time.monotonic() - start_total, 2),
            "gpu_name": cuda_check.get("gpu_name"),
            "cuda_version": cuda_check.get("cuda_version", vers["cuda_version"]),
            "torch_version": cuda_check.get("torch_version", vers["torch_version"]),
            "error": cuda_check["error"],
        }

    gpu_name = cuda_check["gpu_name"]
    cuda_ver = cuda_check["cuda_version"]
    torch_ver = cuda_check["torch_version"]

    # 加载模型（冷启动）
    try:
        _ensure_models()
        assert _PIPELINE is not None
        assert _DEVICE == "cuda"
    except Exception as e:
        tb = traceback.format_exc()[-2000:]
        return {
            "success": False,
            "duration": duration,
            "filename": None,
            "generation_time": round(time.monotonic() - start_total, 2),
            "gpu_name": gpu_name,
            "cuda_version": cuda_ver,
            "torch_version": torch_ver,
            "error": f"model load failed: {e}\n{tb}",
        }

    # 推理
    import torch
    gen_start = time.monotonic()
    try:
        with torch.no_grad():
            # 与 kaggle_generate.py:74 保持一致
            output = _PIPELINE.generate(
                prompt=prompt,
                duration=duration,
                temperature=1.0,
                top_k=250,
                top_p=0.95,
            )
        gen_time = round(time.monotonic() - gen_start, 2)
        total_time = round(time.monotonic() - start_total, 2)

        if output is None:
            raise RuntimeError("pipeline.generate returned None")

        # 保存 WAV（与 kaggle_generate.py:89 一致，路径改为 OUTPUT_DIR）
        # output: torch.Tensor [channels, samples] 或 [1, channels, samples]
        try:
            import torchaudio
        except ImportError:
            import soundfile as sf  # fallback
            torchaudio = None  # type: ignore

        ts = int(time.time() * 1000)
        filename = f"heartmula_{ts}_{duration}s.wav"
        out_path = OUTPUT_DIR / filename
        # 归一化维度
        wav = output
        if wav.ndim == 3 and wav.shape[0] == 1:
            wav = wav.squeeze(0)  # [1,C,T] -> [C,T]
        # 确保 [C,T]
        if wav.ndim == 1:
            wav = wav.unsqueeze(0)
        wav_cpu = wav.detach().cpu()
        # torchaudio 需要 [C,T]，soundfile 需要 [T,C]
        sr = 44100  # HeartMuLa 默认 44.1k
        # 尝试从 pipeline/codec 读取真实 sr，若失败用 44100
        try:
            sr = getattr(_CODEC, "sample_rate", 44100) or 44100
        except Exception:
            pass

        if torchaudio is not None:
            torchaudio.save(str(out_path), wav_cpu, sample_rate=sr)
        else:
            import soundfile as sf
            # [C,T] -> [T,C]
            sf.write(str(out_path), wav_cpu.t().numpy(), sr)

        print(f"[HeartMuLa] saved {out_path} shape {tuple(wav_cpu.shape)} sr {sr} gen {gen_time}s total {total_time}s")
        return {
            "success": True,
            "duration": duration,
            "filename": str(out_path),
            "generation_time": gen_time,
            "total_time": total_time,
            "gpu_name": gpu_name,
            "cuda_version": cuda_ver,
            "torch_version": torch_ver,
            "sample_rate": sr,
            "shape": list(wav_cpu.shape),
            "error": None,
        }
    except Exception as e:
        tb = traceback.format_exc()[-2500:]
        gen_time = round(time.monotonic() - gen_start, 2)
        total_time = round(time.monotonic() - start_total, 2)
        return {
            "success": False,
            "duration": duration,
            "filename": None,
            "generation_time": gen_time,
            "total_time": total_time,
            "gpu_name": gpu_name,
            "cuda_version": cuda_ver,
            "torch_version": torch_ver,
            "error": f"generate failed: {type(e).__name__}: {e}\n{tb}",
        }


# 本地直接运行：python runpod_worker/heartmula_worker.py （不启动 serverless，用于静态检查）
if __name__ == "__main__":
    import json
    # 简单本地自检（无 GPU 时仅检查 CUDA 错误返回）
    demo = {"input": {"prompt": "A beautiful piano melody", "duration": 10}}
    print("本地 handler 自检（不依赖 RunPod）:")
    print(json.dumps(handler(demo), indent=2, ensure_ascii=False))
else:
    # RunPod Serverless 官方启动（仅在 RunPod 环境 import runpod 成功时）
    if runpod is not None:
        # 按官方文档：runpod.serverless.start({"handler": handler})
        try:
            runpod.serverless.start({"handler": handler})
        except Exception as e:
            print(f"[HeartMuLa] runpod.serverless.start failed: {e}", file=sys.stderr)
            raise
