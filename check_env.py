"""Check current environment status for Phase 7/8"""
import os
import sys

print("=" * 60)
print("ENVIRONMENT CHECK")
print("=" * 60)

# PyTorch and CUDA
print("\n--- PyTorch & CUDA ---")
import torch
print(f"PyTorch version: {torch.__version__}")
cuda_available = hasattr(torch, 'cuda') and torch.cuda.is_available()
print(f"CUDA available: {cuda_available}")
if cuda_available:
    print(f"CUDA device count: {torch.cuda.device_count()}")
    for i in range(torch.cuda.device_count()):
        print(f"  Device {i}: {torch.cuda.get_device_name(i)}")
else:
    print("CUDA not available - CPU only environment")

# HF Token
print("\n--- Hugging Face Token ---")
hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_TOKEN")
print(f"HF_TOKEN env var: {'SET' if hf_token else 'NOT SET'}")
if hf_token:
    print(f"Token preview: {hf_token[:20]}...")

# Check for model directories
print("\n--- Model Cache Check ---")
import glob

# Check for HeartMuLa models
hl_models = glob.glob("/root/.cache/huggingface/hub/models--HeartMuLa*")
print(f"HeartMuLa model cache: {len(hl_models)} directories found")

# Check for HF ACE-Step related
hf_models = glob.glob("/root/.cache/huggingface/hub/models--*ace_step*")
print(f"ACE-Step related models: {len(hf_models)} directories found")

# Check project directories
print("\n--- Project Directories ---")
be_dir = "backend/app"
if os.path.exists(be_dir):
    print(f"backend dir exists: YES")
    routers_dir = os.path.join(be_dir, "routers")
    if os.path.exists(routers_dir):
        print(f"routers dir contents: {os.listdir(routers_dir)}")
else:
    print(f"backend dir exists: NO")

# Check Modal
print("\n--- Modal Check ---")
try:
    import modal
    print("Modal importable: YES")
except ImportError:
    print("Modal importable: NO (not installed)")

# Check if we can access Hugging Face
print("\n--- Hugging Face Access ---")
try:
    import httpx
    token = os.getenv("HF_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    # Just check if httpx works
    print(f"httpx available: YES")
    print(f"Can import httpx: YES")
except Exception as e:
    print(f"httpx error: {e}")

print("\n" + "=" * 60)