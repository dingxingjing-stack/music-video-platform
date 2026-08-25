"""
Kaggle T4 16GB 从零部署脚本 — 严格 Dataset 模式
顺序：A -> M，不跳步，不自动下载 HeartMuLa 到 /kaggle/working

执行：
  Kaggle Notebook 首 cell: !python kaggle_deploy.py
  或分步在 Notebook 中按 cell 顺序执行（见 kaggle_notebook.ipynb）

安全约束：
  - HeartMuLa 3B 必须且仅 /kaggle/input/heartmula-3b Dataset，缺失/不完整直接报错，不回落、不下载
  - 禁止任何 HeartMuLa 权重出现在 /kaggle/working
  - ASR 仅 faster-whisper-small（~250MB int8），禁止 large-v3
  - GPT-SoVITS / ACE-Step 保持 Modal 远程，不在 Kaggle 下载
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys


def section(title: str):
    print(f"\n{'='*60}\n{title}\n{'='*60}")


def run(cmd, check=True, shell=False):
    print(f"$ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    if shell:
        return subprocess.run(cmd, shell=True, check=check)
    return subprocess.run(cmd, check=check)


# A. 检查 Kaggle T4 GPU / CUDA
def step_a_gpu():
    section("A. 检查 Kaggle T4 GPU / CUDA")
    try:
        import subprocess as sp
        r = sp.run(["nvidia-smi"], capture_output=True, text=True, timeout=10)
        print(r.stdout[:2000] if r.returncode == 0 else r.stderr[:2000])
        if r.returncode != 0:
            print("WARNING: nvidia-smi 不可用（可能是 CPU 环境）— 需确认 Kaggle 加速器已选 T4 x2")
    except Exception as e:
        print(f"nvidia-smi 检查失败: {e}")
    # also check /proc
    if pathlib.Path("/proc/driver/nvidia/version").exists():
        print(pathlib.Path("/proc/driver/nvidia/version").read_text()[:500])
    print("期望: Tesla T4 16GB x1, CUDA 12.4, Driver >= 550")


# B. 检查 /kaggle/working 剩余空间
def step_b_disk():
    section("B. 检查 /kaggle/working 剩余空间")
    for p in ["/kaggle/working", "/kaggle/input", "/kaggle/working/cache"]:
        pp = pathlib.Path(p)
        if pp.exists():
            u = shutil.disk_usage(str(pp))
            print(f"{p}: total {u.total/1024**3:.2f}GB used {u.used/1024**3:.2f}GB free {u.free/1024**3:.2f}GB")
            # also df -h
            try:
                r = subprocess.run(["df", "-h", str(pp)], capture_output=True, text=True, timeout=5)
                print(r.stdout)
            except Exception:
                pass
    avail = shutil.disk_usage("/kaggle/working").free / 1024**3 if pathlib.Path("/kaggle/working").exists() else 0
    if avail < 2:
        print("WARNING: /kaggle/working 剩余 <2GB，需清理 cache/output")
    else:
        print(f"OK: working 剩余 {avail:.2f}GB")


# C. 检查 /kaggle/input/heartmula-3b（严格 — 仅 Kaggle 报错，本地仅警告）
def step_c_heartmula_dataset():
    section("C. 检查 /kaggle/input/heartmula-3b（严格 Dataset）")
    from backend.app.services.heartmula_service import require_heartmula_dataset, assert_no_heartmula_working_download, is_heartmula_dataset_available, _is_kaggle_env

    # 禁止 working 下出现权重（仅 Kaggle 生效）
    try:
        assert_no_heartmula_working_download()
        print("OK: /kaggle/working 无 HeartMuLa 权重（安全）")
    except Exception as e:
        print(f"ERROR: {e}")
        raise

    # 严格检查 Dataset — Kaggle 下必须存在，本地仅警告
    if _is_kaggle_env():
        try:
            path = require_heartmula_dataset()
            print(f"OK: HeartMuLa Dataset 完整: {path}")
            p = pathlib.Path(path)
            print(f"  config.json: {(p/'config.json').exists()}")
            print(f"  safetensors: {list(p.glob('*.safetensors'))[:3]}")
            for sub in p.iterdir():
                if sub.is_dir():
                    print(f"  sub {sub.name}: config {(sub/'config.json').exists()} safetensors {len(list(sub.glob('*.safetensors')))}")
        except Exception as e:
            print(str(e))
            print("请在 Kaggle Notebook 右侧 Add data 挂载 HeartMuLa-3B Dataset 到 /kaggle/input/heartmula-3b 后重试。")
            raise
    else:
        # 本地开发：仅检查，不阻断
        available = is_heartmula_dataset_available()
        print(f"本地环境: HeartMuLa Dataset available={available}（Kaggle 严格校验仅在 Kaggle 生效，本地走 API）")
        if not available:
            print("提示: 本地无需 Dataset，生产走 HEARTMULA_API_URL；Kaggle 则必须挂载 Dataset")


# D. 设置 HF_HOME / TORCH_HOME
def step_d_cache_env():
    section("D. 设置 HF_HOME / TORCH_HOME（统一缓存）")
    # 仅 Kaggle 才使用 /kaggle/working/cache；本地 dry-run 不创建 /kaggle 目录
    is_kaggle = pathlib.Path("/kaggle/input").exists() or pathlib.Path("/kaggle/working").exists()
    if is_kaggle:
        cache_root = "/kaggle/working/cache"
        hf_home = f"{cache_root}/hf"
        torch_home = f"{cache_root}/torch"
        os.environ["KAGGLE_CACHE_ROOT"] = cache_root
        os.environ["HF_HOME"] = hf_home
        os.environ["HF_HUB_CACHE"] = f"{hf_home}/hub"
        os.environ["TORCH_HOME"] = torch_home
        for p in [hf_home, torch_home, f"{cache_root}/hf", "/kaggle/working/output"]:
            pathlib.Path(p).mkdir(parents=True, exist_ok=True)
    else:
        # 本地 dry-run：使用临时统一缓存，不污染 /kaggle
        cache_root = os.getenv("KAGGLE_CACHE_ROOT", str(pathlib.Path.home() / ".cache" / "huggingface"))
        hf_home = os.getenv("HF_HOME", cache_root)
        torch_home = os.getenv("TORCH_HOME", str(pathlib.Path.home() / ".cache" / "torch"))
        os.environ.setdefault("KAGGLE_CACHE_ROOT", cache_root)
        os.environ.setdefault("HF_HOME", hf_home)
        os.environ.setdefault("HF_HUB_CACHE", f"{hf_home}/hub")
        os.environ.setdefault("TORCH_HOME", torch_home)
        print(f"本地 dry-run: 未创建 /kaggle/working，使用 HF_HOME={hf_home}")
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ.setdefault("VOICE_CLONE_ASR_MODEL", "small")
    os.environ.setdefault("HEARTCODEC_LOCAL_MODE", "false")
    os.environ.setdefault("HEARTMULA_KAGGLE_DATASET_PATH", "/kaggle/input/heartmula-3b")
    for k in ["HF_HOME", "HF_HUB_CACHE", "TORCH_HOME", "KAGGLE_CACHE_ROOT", "VOICE_CLONE_ASR_MODEL", "HEARTCODEC_LOCAL_MODE", "HEARTMULA_KAGGLE_DATASET_PATH"]:
        print(f"{k}={os.environ.get(k)}")
    print("OK: 统一缓存已设置，避免 ~/.cache 双份")


# E. 安装 requirements-kaggle.txt（本脚本默认 dry-run，需显式 --install 才执行）
def step_e_install(dry_run=True):
    section("E. 安装 requirements-kaggle.txt")
    req = pathlib.Path("requirements-kaggle.txt")
    if not req.exists():
        req = pathlib.Path("/kaggle/working/requirements-kaggle.txt")
    print(f"requirements: {req} exists={req.exists()}")
    if dry_run:
        print("DRY-RUN: 未执行 pip install。如需安装，请运行: pip install -r requirements-kaggle.txt")
        print("本次按用户要求不执行大规模 pip install，仅展示将安装内容：")
        if req.exists():
            print(req.read_text(encoding="utf-8")[:2000])
        return
    run([sys.executable, "-m", "pip", "install", "-r", str(req)])


# F. 检查 PyTorch CUDA
def step_f_torch_cuda():
    section("F. 检查 PyTorch CUDA")
    import torch
    print(f"torch {torch.__version__}")
    print(f"cuda available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"device count: {torch.cuda.device_count()}")
        for i in range(torch.cuda.device_count()):
            print(f"  {i}: {torch.cuda.get_device_name(i)}")
        print(f"cuda version: {torch.version.cuda}")
    else:
        print("WARNING: CUDA 不可用 — Kaggle 需启用 GPU 加速器")


# G. 检查 faster-whisper-small 是否已缓存
def step_g_asr_cache():
    section("G. 检查 faster-whisper-small 是否已缓存")
    from backend.app.services.experimental.asr_client import is_asr_model_cached, ASR_CACHE_DIR, ASR_MODEL
    hf_home = os.getenv("HF_HOME", ASR_CACHE_DIR)
    cached = is_asr_model_cached("small", hf_home)
    print(f"ASR_MODEL={ASR_MODEL} (期望 small)")
    print(f"HF_HOME={hf_home}")
    print(f"small cached: {cached}")
    if ASR_MODEL != "small":
        print("ERROR: ASR_MODEL 必须为 small（安全约束），请设置 VOICE_CLONE_ASR_MODEL=small")
        raise RuntimeError("ASR_MODEL must be small")
    return cached


# H. 如果没有，只允许下载 small（dry-run 默认不下载）
def step_h_download_small(dry_run=True):
    section("H. 如未缓存，仅允许下载 small（禁止 large-v3）")
    from backend.app.services.experimental.asr_client import ASR_CACHE_DIR
    cached = step_g_asr_cache()  # 复用检查
    if cached:
        print("SKIP: small 已缓存，无需下载")
        return
    if dry_run:
        print(f"DRY-RUN: 将下载 Systran/faster-whisper-small (~250MB int8) 到 {ASR_CACHE_DIR}")
        print("实际下载仅在首次转写时由 WhisperModel(download_root=...) 触发，不在此处批量下载")
        print("禁止下载 large-v3（1.5GB）")
        return
    # 实际触发下载（仅 small）
    print("Downloading small...")
    from faster_whisper import WhisperModel
    WhisperModel("small", device="cpu", compute_type="int8", download_root=ASR_CACHE_DIR)
    print("OK: small 下载完成")


# I. 检查 HeartMuLa Dataset，不允许下载（严格 — 仅 Kaggle 阻断）
def step_i_heartmula_strict():
    section("I. 检查 HeartMuLa Dataset（严格，不允许下载）")
    from backend.app.services.heartmula_service import require_heartmula_dataset, assert_no_heartmula_working_download, _is_kaggle_env, is_heartmula_dataset_available
    assert_no_heartmula_working_download()
    if _is_kaggle_env():
        path = require_heartmula_dataset()  # 缺失直接抛错（Kaggle）
        print(f"OK: {path} 完整，禁止任何下载到 /kaggle/working")
    else:
        available = is_heartmula_dataset_available()
        print(f"本地环境: HeartMuLa available={available}（Kaggle 严格校验仅在 Kaggle 生效）")
    print("约束: 本项目不含 HeartMuLa snapshot_download，任何自动下载均被禁止")


# J. 检查 R2 配置
def step_j_r2():
    section("J. 检查 R2 配置")
    keys = ["R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "R2_PUBLIC_DOMAIN"]
    missing = []
    for k in keys:
        v = os.getenv(k, "")
        print(f"{k}={'SET' if v else 'NOT SET'}")
        if not v and k in ["R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"]:
            missing.append(k)
    if missing:
        print(f"WARNING: R2 配置缺失 {missing} — 上传/下载将失败，请配置 Secrets")
    else:
        print("OK: R2 配置完整")


# K. 检查 Modal API 配置
def step_k_modal():
    section("K. 检查 Modal API 配置")
    # ACE-Step 走 Modal 远程，GPT-SoVITS 也走 Modal
    for k in ["ACE_STEP_MODAL_URL", "ACE_STEP_GENERATE_URL", "ACE_STEP_CONTINUE_URL", "ACE_STEP_HEALTH_URL", "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"]:
        v = os.getenv(k, "")
        print(f"{k}={'SET' if v else 'NOT SET'}")
    # 也检查 heartmula/heartcodec API
    for k in ["HEARTMULA_API_URL", "HEARTMULA_API_KEY", "HEARTCODEC_API_URL", "HEARTCODEC_API_KEY"]:
        v = os.getenv(k, "")
        print(f"{k}={'SET' if v else 'NOT SET'}")
    print("说明: ACE-Step/GPT-SoVITS 保持 Modal 远程，不在 Kaggle 下载权重")


# L. 启动 FastAPI
def step_l_fastapi(dry_run=True):
    section("L. 启动 FastAPI")
    if dry_run:
        print("DRY-RUN: 未实际启动。Kaggle 中启动命令：")
        print("  uvicorn backend.main:app --host 0.0.0.0 --port 8000 &")
        return None
    import subprocess as sp
    proc = sp.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"])
    print(f"Started uvicorn pid={proc.pid}")
    return proc


# M. 执行 health/API/AI 服务连接测试
def step_m_health():
    section("M. 执行 health/API/AI 服务连接测试")
    import time
    import httpx
    base = os.getenv("FASTAPI_BASE_URL", "http://127.0.0.1:8000")
    # 等待 FastAPI 就绪
    for i in range(10):
        try:
            r = httpx.get(f"{base}/health", timeout=5.0)
            print(f"GET /health {r.status_code}: {r.text[:500]}")
            break
        except Exception as e:
            print(f"  retry {i}: {e}")
            time.sleep(1)
    else:
        print("WARNING: /health 不可用 — 请确认 FastAPI 已启动")
        return
    # services status
    try:
        r = httpx.get(f"{base}/api/v1/services/status", timeout=5.0)
        print(f"GET /api/v1/services/status {r.status_code}: {r.text[:1000]}")
    except Exception as e:
        print(f"services/status 失败: {e}")
    # ACE-Step Modal health（若配置）
    ace_health = os.getenv("ACE_STEP_HEALTH_URL") or (os.getenv("ACE_STEP_MODAL_URL", "") + "/health" if os.getenv("ACE_STEP_MODAL_URL") else "")
    if ace_health:
        try:
            r = httpx.get(ace_health, timeout=10.0)
            print(f"ACE-Step Modal {ace_health} {r.status_code}: {r.text[:500]}")
        except Exception as e:
            print(f"ACE-Step Modal 不可用: {e}")
    else:
        print("ACE-Step Modal URL 未配置 — 跳过")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true", help="实际执行 pip install")
    ap.add_argument("--download-small", action="store_true", help="实际下载 small")
    ap.add_argument("--start-server", action="store_true", help="实际启动 FastAPI")
    args = ap.parse_args()

    step_a_gpu()
    step_b_disk()
    step_c_heartmula_dataset()
    step_d_cache_env()
    step_e_install(dry_run=not args.install)
    step_f_torch_cuda()
    step_g_asr_cache()
    step_h_download_small(dry_run=not args.download_small)
    step_i_heartmula_strict()
    step_j_r2()
    step_k_modal()
    step_l_fastapi(dry_run=not args.start_server)
    step_m_health()
    print("\nAll steps done (strict mode).")
