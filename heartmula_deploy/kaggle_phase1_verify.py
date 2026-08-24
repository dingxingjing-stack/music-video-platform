# 单元格 1：认证与访问验证（不下载模型）
# 在 Kaggle Notebook 中复制运行

import os, sys, subprocess, shutil
from pathlib import Path

print("=" * 60)
print("阶段 1：认证与访问验证")
print("=" * 60)

results = {}

# 1. 从 Kaggle Secrets 读取 HF_TOKEN
print("\n[1] 从 Kaggle Secrets 读取 HF_TOKEN")
try:
    from kaggle_secrets import UserSecretsClient
    secrets = UserSecretsClient()
    hf_token = secrets.get_secret("HF_TOKEN")
    if hf_token and hf_token.startswith("hf_"):
        print(f"  PASS: 从 Secrets 读取成功 (长度 {len(hf_token)})")
        results["secrets_read"] = True
    else:
        print(f"  FAIL: Secrets 中无有效 HF_TOKEN")
        results["secrets_read"] = False
except Exception as e:
    print(f"  FAIL: 读取 Secrets 异常: {e}")
    results["secrets_read"] = False
    hf_token = None

# 2. Hugging Face API 认证测试
print("\n[2] Hugging Face API 认证测试")
if hf_token:
    try:
        from huggingface_hub import HfApi, whoami
        api = HfApi(token=hf_token)
        user_info = whoami(token=hf_token)
        print(f"  PASS: 认证成功，用户: {user_info.get('name', 'unknown')}")
        results["hf_auth"] = True
    except Exception as e:
        print(f"  FAIL: 认证失败: {e}")
        results["hf_auth"] = False
else:
    print(f"  SKIP: 无 Token")
    results["hf_auth"] = False

# 3. 检查 HeartMuLa/HeartMuLa-oss-3B 访问权限
print("\n[3] HeartMuLa/HeartMuLa-oss-3B 访问权限")
if hf_token and results.get("hf_auth"):
    try:
        from huggingface_hub import repo_info
        info = repo_info(repo_id="HeartMuLa/HeartMuLa-oss-3B", token=hf_token, repo_type="model")
        print(f"  PASS: 可访问 (大小: {info.siblings.__len__() if info.siblings else 0} 文件)")
        results["heartmula_access"] = True
    except Exception as e:
        print(f"  FAIL: 无法访问: {e}")
        results["heartmula_access"] = False
else:
    print(f"  SKIP: 认证未通过")
    results["heartmula_access"] = False

# 4. 检查 HeartMuLa/HeartCodec-oss 访问权限
print("\n[4] HeartMuLa/HeartCodec-oss 访问权限")
if hf_token and results.get("hf_auth"):
    try:
        from huggingface_hub import repo_info
        info = repo_info(repo_id="HeartMuLa/HeartCodec-oss", token=hf_token, repo_type="model")
        print(f"  PASS: 可访问 (大小: {info.siblings.__len__() if info.siblings else 0} 文件)")
        results["heartcodec_access"] = True
    except Exception as e:
        print(f"  FAIL: 无法访问: {e}")
        results["heartcodec_access"] = False
else:
    print(f"  SKIP: 认证未通过")
    results["heartcodec_access"] = False

# 5. 磁盘空间
print("\n[5] 磁盘空间检查")
for path_str in ["/kaggle/working", "/kaggle/input"]:
    p = Path(path_str)
    if p.exists():
        total, used, free = shutil.disk_usage(p)
        print(f"  {path_str}: 可用 {free/1024**3:.2f} GB")
    else:
        print(f"  {path_str}: 不存在")
working_free = shutil.disk_usage("/kaggle/working").free / 1024**3
if working_free >= 16:
    print(f"  PASS: /kaggle/working 可用 {working_free:.2f}GB >= 16GB")
    results["disk"] = True
else:
    print(f"  FAIL: /kaggle/working 可用 {working_free:.2f}GB < 16GB")
    results["disk"] = False

# 6. GPU / CUDA
print("\n[6] GPU / CUDA 检查")
try:
    import torch
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        capability = torch.cuda.get_device_capability(0)
        vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
        print(f"  GPU: {gpu_name} (sm_{capability[0]}{capability[1]})")
        print(f"  VRAM: {vram:.2f} GB")
        if capability[0] >= 7:
            print(f"  PASS: GPU 兼容 sm_70+")
            results["gpu"] = True
        else:
            print(f"  FAIL: GPU 架构不兼容")
            results["gpu"] = False
    else:
        print(f"  FAIL: CUDA 不可用")
        results["gpu"] = False
except Exception as e:
    print(f"  FAIL: GPU 检查异常: {e}")
    results["gpu"] = False

# 7. Kaggle CLI
print("\n[7] Kaggle CLI 检查")
try:
    result = subprocess.run(["kaggle", "--version"], capture_output=True, text=True, timeout=10)
    if result.returncode == 0:
        print(f"  PASS: {result.stdout.strip()}")
        results["kaggle_cli"] = True
    else:
        print(f"  FAIL: {result.stderr.strip()}")
        results["kaggle_cli"] = False
except Exception as e:
    print(f"  FAIL: {e}")
    results["kaggle_cli"] = False

# 8. Kaggle Dataset API 权限（列出我的 Dataset）
print("\n[8] Kaggle Dataset API 权限")
if results.get("kaggle_cli"):
    try:
        result = subprocess.run(["kaggle", "datasets", "list", "--mine", "--page-size", "5"], 
                                capture_output=True, text=True, timeout=20)
        if result.returncode == 0:
            print(f"  PASS: 可列出个人 Dataset")
            results["dataset_api"] = True
        else:
            print(f"  FAIL: {result.stderr.strip()}")
            results["dataset_api"] = False
    except Exception as e:
        print(f"  FAIL: {e}")
        results["dataset_api"] = False
else:
    print(f"  SKIP: CLI 不可用")
    results["dataset_api"] = False

# 汇总
print("\n" + "=" * 60)
print("验证汇总")
print("=" * 60)
checks = [
    ("Hugging Face 认证", results.get("hf_auth")),
    ("HeartMuLa-oss-3B 访问", results.get("heartmula_access")),
    ("HeartCodec-oss 访问", results.get("heartcodec_access")),
    ("Kaggle Dataset API", results.get("dataset_api")),
    ("GPU", results.get("gpu")),
    ("磁盘空间", results.get("disk")),
]
all_pass = True
for name, ok in checks:
    status = "PASS" if ok else "FAIL"
    if not ok: all_pass = False
    print(f"  [{status}] {name}")

print(f"\n=== 全部通过: {'是 ✓' if all_pass else '否 ✗'} ===")

if all_pass:
    print("\n>>> 可以进入下一阶段：创建/挂载 Dataset 并下载模型")
else:
    print("\n>>> 请先解决上述 FAIL 项")