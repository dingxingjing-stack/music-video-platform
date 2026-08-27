#!/usr/bin/env python3
"""Phase 8: Real Provider Environment Audit - Read-only checks."""
import subprocess
import sys
import os

print("=== Phase 8: Real Provider Environment Audit ===")
print()

results = {}

# 1. NVIDIA GPU detection
print("1. NVIDIA GPU detection:")
try:
    output = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True)
    if output.returncode == 0 and output.stdout.strip():
        gpus = output.stdout.strip().split("\n")
        results["gpu_available"] = True
        results["gpu_count"] = len(gpus)
        print(f"   PASS: {len(gpus)} NVIDIA GPU(s) found")
        for gpu in gpus:
            print(f"     {gpu}")
    else:
        results["gpu_available"] = False
        print("   FAIL: No NVIDIA GPU found")
except Exception as e:
    results["gpu_available"] = False
    print(f"   ERROR: {e}")

# 2. GPU model & memory
print()
print("2. GPU model & memory:")
try:
    output = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
        capture_output=True, text=True
    )
    if output.returncode == 0:
        lines = output.stdout.strip().split("\n")
        if lines and lines[0]:
            parts = lines[0].split(", ")
            results["gpu_model"] = parts[0] if len(parts) > 0 else "Unknown"
            results["gpu_memory"] = parts[1] if len(parts) > 1 else "Unknown"
            print(f"   GPU: {results['gpu_model']}")
            print(f"   Memory: {results['gpu_memory']}")
        else:
            results["gpu_model"] = "Query failed"
            results["gpu_memory"] = "Query failed"
            print("   FAIL: Could not query GPU details")
    else:
        results["gpu_model"] = "Query failed"
        results["gpu_memory"] = "Query failed"
        print("   FAIL: nvidia-smi query failed")
except Exception as e:
    results["gpu_model"] = f"Error: {e}"
    results["gpu_memory"] = f"Error: {e}"
    print(f"   ERROR: {e}")

# 3. NVIDIA Driver / CUDA state
print()
print("3. NVIDIA Driver / CUDA state:")
try:
    output = subprocess.run(["nvidia-smi", "driverVersion"], capture_output=True, text=True)
    if output.returncode == 0:
        results["driver_version"] = output.stdout.strip()
        print(f"   Driver: {results['driver_version']}")
    else:
        results["driver_version"] = "Not available"
        print("   FAIL: Could not detect driver version")
except Exception as e:
    results["driver_version"] = f"Error: {e}"
    print(f"   ERROR: {e}")

# 4. Python version
print()
print("4. Python version:")
py_version = sys.version
results["python_version"] = py_version
print(f"   {py_version}")

# 5. Virtual environment
print()
print("5. Current virtual environment:")
env_result = subprocess.run(
    ["python", "-c", "import os; print(os.environ.get('VENV', 'none'))"],
    capture_output=True, text=True
)
print(f"   VENV env: {env_result.stdout.strip()}")
conda_result = subprocess.run(
    ["python", "-c", "import os; print(os.environ.get('CONDA_PREFIX', 'none'))"],
    capture_output=True, text=True
)
print(f"   CONDA_PREFIX env: {conda_result.stdout.strip()}")
print(f"   python executable: {sys.executable}")

# 6. PyTorch installation
print()
print("6. PyTorch installation:")
try:
    import torch
    results["pytorch_installed"] = True
    print(f"   PASS: PyTorch {torch.__version__} installed")
except ImportError:
    results["pytorch_installed"] = False
    print("   FAIL: PyTorch not installed")

# 7. PyTorch CUDA availability
print()
print("7. PyTorch CUDA availability:")
if results.get("pytorch_installed"):
    try:
        cuda_avail = torch.cuda.is_available()
        results["pytorch_cuda"] = cuda_avail
        print(f"   CUDA available: {cuda_avail}")
        if cuda_avail:
            results["cuda_version"] = torch.cuda.version()
            print(f"   CUDA version: {results['cuda_version']}")
            results["device_count"] = torch.cuda.device_count()
            print(f"   GPU device count: {results['device_count']}")
    except Exception as e:
        results["pytorch_cuda"] = f"Error: {e}"
        print(f"   ERROR: {e}")
else:
    results["pytorch_cuda"] = "PyTorch not installed"
    print("   Skipped: PyTorch not installed")

# 8. httpx installation
print()
print("8. httpx installation:")
try:
    import httpx
    results["httpx_installed"] = True
    print(f"   PASS: httpx {httpx.__version__} installed")
except ImportError:
    results["httpx_installed"] = False
    print("   FAIL: httpx not installed")

# 9. Hugging Face CLI / Hub
print()
print("9. Hugging Face CLI / Hub:")
try:
    output = subprocess.run(["huggingface", "--version"], capture_output=True, text=True)
    if output.returncode == 0:
        results["hf_cli"] = True
        print(f"   PASS: huggingface CLI {output.stdout.strip()}")
    else:
        results["hf_cli"] = False
        print("   FAIL: huggingface CLI not available")
except FileNotFoundError:
    results["hf_cli"] = False
    try:
        from huggingface_hub import HfApi
        results["hf_hub"] = True
        print("   PASS: huggingface_hub Python package available")
    except ImportError:
        results["hf_cli"] = False
        results["hf_hub"] = False
        print("   FAIL: Neither huggingface CLI nor huggingface_hub available")
except Exception as e:
    results["hf_cli"] = False
    print(f"   ERROR: {e}")

# 10. HF_TOKEN / HUGGINGFACE_API credentials
print()
print("10. HF_TOKEN / HUGGINGFACE_API credentials:")
hf_token = subprocess.run(
    ["python", "-c", "import os; print(os.getenv('HF_TOKEN', 'NOT_SET'))"],
    capture_output=True, text=True
)
hf_api_token = subprocess.run(
    ["python", "-c", "import os; print(os.getenv('HUGGINGFACE_API_TOKEN', 'NOT_SET'))"],
    capture_output=True, text=True
)
print(f"   HF_TOKEN: {hf_token.stdout.strip()}")
print(f"   HUGGINGFACE_API_TOKEN: {hf_api_token.stdout.strip()}")
results["hf_token"] = hf_token.stdout.strip()
results["hf_api_token"] = hf_api_token.stdout.strip()

# 11. HeartMuLa model weights needed - read-only check
print()
print("11. HeartMuLa model weights needed:")
try:
    with open("/c/Users/dingx/music-video-platform/backend/app/routers/ai_music.py", "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    if "heartmula" in content.lower():
        results["heartmula_mentioned"] = True
        print("   HeartMuLa referenced in ai_music.py")
    else:
        results["heartmula_mentioned"] = False
        print("   HeartMuLa not referenced in ai_music.py (config check needed)")
except Exception as e:
    results["heartmula_mentioned"] = f"Error: {e}"
    print(f"   ERROR: {e}")

# 12. ACE-Step model weights needed - read-only check
print()
print("12. ACE-Step model weights needed:")
try:
    with open("/c/Users/dingx/music-video-platform/backend/app/routers/ai_music.py", "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    if "ace_step" in content.lower():
        results["ace_step_mentioned"] = True
        print("   ACE-Step referenced in ai_music.py")
    else:
        results["ace_step_mentioned"] = False
        print("   ACE-Step not referenced in ai_music.py (config check needed)")
except Exception as e:
    results["ace_step_mentioned"] = f"Error: {e}"
    print(f"   ERROR: {e}")

# 13. HF ACE-Step model & runtime - read-only check
print()
print("13. HF ACE-Step model & runtime:")
try:
    with open("/c/Users/dingx/music-video-platform/backend/app/routers/ai_music.py", "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    if "hf.space" in content or "HF_TOKEN" in content:
        results["hf_ace_step_configured"] = True
        print("   HF ACE-Step endpoint/configuration found")
    else:
        results["hf_ace_step_configured"] = False
        print("   HF ACE-Step endpoint/configuration not found in ai_music.py")
except Exception as e:
    results["hf_ace_step_configured"] = f"Error: {e}"
    print(f"   ERROR: {e}")

# 14. ACE-Step service endpoint configured - read-only check
print()
print("14. ACE-Step service endpoint configured:")
try:
    with open("/c/Users/dingx/music-video-platform/backend/app/routers/ai_music.py", "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    if "ace_step-ace-step.hf.space" in content:
        results["ace_step_endpoint_configured"] = True
        print("   PASS: ACE-Step endpoint configured in ai_music.py")
    else:
        results["ace_step_endpoint_configured"] = False
        print("   Note: ACE-Step endpoint not explicitly found in ai_music.py")
except Exception as e:
    results["ace_step_endpoint_configured"] = f"Error: {e}"
    print(f"   ERROR: {e}")

# 15. Project requirements / pyproject config
print()
print("15. Project requirements / pyproject config:")
for fname in ["requirements.txt", "pyproject.toml", "setup.py"]:
    path = os.path.join("/c/Users/dingx/music-video-platform", fname)
    if os.path.exists(path):
        results["project_config"] = f"Found: {fname}"
        print(f"   Found: {fname}")
    else:
        results["project_config"] = f"Not found: {fname}"
        print(f"   Not found: {fname}")

print()
print("=== Phase 8 Audit Summary ===")
print(f"GPU Available: {results.get('gpu_available', False)}")
print(f"PyTorch Installed: {results.get('pytorch_installed', False)}")
cuda_status = results.get("pytorch_cuda", "N/A")
print(f"PyTorch CUDA: {cuda_status}")
print(f"httpx Installed: {results.get('httpx_installed', False)}")
hf_status = results.get("hf_cli", results.get("hf_hub", False))
print(f"HF CLI/Hub available: {hf_status}")
print(f"HF_TOKEN set: {results.get('hf_token', 'N/A') != 'NOT_SET'}")
print(f"ACE-Step endpoint configured: {results.get('ace_step_endpoint_configured', False)}")