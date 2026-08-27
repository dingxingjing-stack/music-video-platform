"""RunPod Serverless Worker Handler — GPU Smoke Test

最小 GPU Worker：接收 {"input": {...}}，返回成功 JSON，并返回 GPU/CUDA 是否可用。
不下载大型模型，不接通 HeartMuLa/ACE-Step，仅作为 RunPod Serverless 部署验证。
"""

import os
import json
import sys
import traceback
import runpod

# 可选依赖：若未安装则优雅降级
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    torch = None
    TORCH_AVAILABLE = False

try:
    import torchaudio
    TORCHAUDIO_AVAILABLE = True
except ImportError:
    torchaudio = None
    TORCHAUDIO_AVAILABLE = False

try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    librosa = None
    LIBROSA_AVAILABLE = False


def check_gpu() -> dict:
    """检查 GPU/CUDA 可用性，返回详细信息。"""
    info = {
        "cuda_available": False,
        "cuda_version": None,
        "device_count": 0,
        "device_names": [],
        "driver_version": None,
        "torch_version": None,
    }

    if not TORCH_AVAILABLE:
        info["error"] = "torch not installed"
        return info

    info["torch_version"] = torch.__version__
    info["cuda_available"] = torch.cuda.is_available()

    if torch.cuda.is_available():
        info["cuda_version"] = torch.version.cuda
        info["device_count"] = torch.cuda.device_count()
        for i in range(torch.cuda.device_count()):
            info["device_names"].append(torch.cuda.get_device_name(i))
        # 尝试获取驱动版本（可能不可用）
        try:
            import subprocess
            result = subprocess.run(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"], 
                                   capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                info["driver_version"] = result.stdout.strip().split("\n")[0]
        except Exception:
            pass

    return info


def handler(job: dict) -> dict:
    """
    RunPod Serverless 标准 handler 入口。
    
    期望输入格式：
    {
        "input": {
            "prompt": "optional test prompt",
            "duration": 30,
            "test_mode": "smoke"
        }
    }
    
    返回格式：
    {
        "success": true,
        "output": {
            "gpu_info": {...},
            "test_result": "smoke test passed",
            "message": "RunPod Serverless worker is healthy"
        }
    }
    """
    try:
        # 解析输入
        job_input = job.get("input", {}) if isinstance(job, dict) else {}
        
        # 可选参数
        test_prompt = job_input.get("prompt", "test")
        duration = job_input.get("duration", 30)
        test_mode = job_input.get("test_mode", "smoke")
        
        # 核心检查：GPU/CUDA 可用性
        gpu_info = check_gpu()
        
        # 环境信息
        env_info = {
            "python_version": sys.version,
            "torch_available": TORCH_AVAILABLE,
            "torchaudio_available": TORCHAUDIO_AVAILABLE,
            "librosa_available": LIBROSA_AVAILABLE,
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES", "not_set"),
        }
        
        # 简单的推理测试（如果 CUDA 可用）
        inference_test = None
        if TORCH_AVAILABLE and torch.cuda.is_available():
            try:
                device = torch.device("cuda")
                x = torch.randn(2, 2, device=device)
                y = x @ x.T  # 简单矩阵乘法
                inference_test = {
                    "status": "success",
                    "device": str(device),
                    "test_tensor_shape": list(y.shape),
                }
            except Exception as e:
                inference_test = {"status": "failed", "error": str(e)}
        else:
            inference_test = {"status": "skipped", "reason": "CUDA not available or torch not installed"}
        
        # 组装输出
        output = {
            "gpu_info": gpu_info,
            "env_info": env_info,
            "inference_test": inference_test,
            "test_input": {
                "prompt": test_prompt,
                "duration": duration,
                "test_mode": test_mode,
            },
            "message": "RunPod Serverless worker smoke test completed",
        }
        
        return {
            "success": True,
            "output": output,
        }
        
    except Exception as e:
        # 捕获所有异常，返回标准错误格式
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


# RunPod Serverless 入口点 (module-level for static analysis detection)
runpod.serverless.start({"handler": handler})