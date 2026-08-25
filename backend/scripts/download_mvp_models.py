#!/usr/bin/env python3
"""
MVP 模型自动下载脚本（Kaggle 专用）

- 目标: facebook/musicgen-small + FunAudioLLM/CosyVoice2-0.5B
- 路径: /kaggle/working/models/musicgen-small, /kaggle/working/models/cosyvoice2-0.5b
- Token: 优先 Kaggle Secrets HF_TOKEN，不打印明文
- 重复执行安全，已存在则跳过下载
- 下载前检查磁盘空间

用法（Kaggle Notebook）:
    !python backend/scripts/download_mvp_models.py
    # 或指定根目录:
    # MVP_MODEL_ROOT=/kaggle/working/models python backend/scripts/download_mvp_models.py
"""

import os
import shutil
import sys
from pathlib import Path

# 允许直接运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REQUIRED_SPACE_GB = 5.0  # MVP 总计 ~2.2GB，预留 5GB


def get_hf_token() -> str | None:
    # 1) 标准环境变量
    for key in ["HF_TOKEN", "HUGGINGFACE_HUB_TOKEN", "HF_API_TOKEN"]:
        v = os.getenv(key)
        if v and v.startswith("hf_"):
            return v
    # 2) Kaggle Secrets
    try:
        from kaggle_secrets import UserSecretsClient  # type: ignore

        t = UserSecretsClient().get_secret("HF_TOKEN")
        if t and t.startswith("hf_"):
            return t
    except Exception:
        pass
    return None


def check_disk(path: Path, required_gb: float = REQUIRED_SPACE_GB) -> None:
    total, used, free = shutil.disk_usage(path if path.exists() else path.parent)
    free_gb = free / 1024**3
    print(f"[DISK] {path}: 可用 {free_gb:.2f} GB (需 >= {required_gb} GB)")
    if free_gb < required_gb:
        raise RuntimeError(f"磁盘空间不足: 可用 {free_gb:.2f} GB < {required_gb} GB")


def download_one(repo_id: str, local_dir: Path, token: str | None) -> bool:
    from huggingface_hub import snapshot_download

    if local_dir.exists() and any(local_dir.iterdir()):
        # 简易完整性检查
        has_config = (local_dir / "config.json").exists() or any(local_dir.glob("*.json"))
        if has_config:
            print(f"[SKIP] {repo_id} 已存在于 {local_dir}，跳过下载")
            return True
    print(f"[DOWNLOAD] {repo_id} -> {local_dir}")
    local_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=repo_id, local_dir=str(local_dir), token=token)
    print(f"[PASS] {repo_id} 下载完成")
    return True


def verify_one(name: str, path: Path) -> dict:
    if not path.exists():
        return {"name": name, "status": "FAIL", "files": 0, "size_gb": 0.0}
    files = [f for f in path.rglob("*") if f.is_file()]
    size_gb = sum(f.stat().st_size for f in files) / 1024**3
    status = "PASS" if files and size_gb > 0.1 else "FAIL"
    print(f"\n=== {name} ===")
    print(f"Model download: {status}")
    print(f"Files: {len(files)}")
    for f in sorted(files)[:8]:
        print(f"  {f.relative_to(path)} ({f.stat().st_size / 1024**2:.1f} MB)")
    if len(files) > 8:
        print(f"  ... 共 {len(files)} 文件")
    print(f"Size: {size_gb:.2f} GB")
    return {"name": name, "status": status, "files": len(files), "size_gb": size_gb}


def main() -> None:
    print("=" * 60)
    print("MVP 模型下载: musicgen-small + cosyvoice2-0.5b")
    print("=" * 60)
    from app.config.mvp_models import (
        MUSICGEN_SMALL_ID,
        MUSICGEN_SMALL_DIR,
        COSYVOICE2_ID,
        COSYVOICE2_DIR,
    )

    # 磁盘预检
    check_root = MUSICGEN_SMALL_DIR.parent if MUSICGEN_SMALL_DIR.parent.exists() else Path("/kaggle/working")
    if not check_root.exists():
        check_root = Path.cwd()
    check_disk(check_root, REQUIRED_SPACE_GB)

    token = get_hf_token()
    if token:
        print(f"[TOKEN] 已从 Secrets/环境读取 (长度 {len(token)})")
    else:
        print("[TOKEN] 未找到 HF_TOKEN，将尝试匿名下载（私有模型会失败）")

    # 逐个下载
    mg_ok = False
    cosy_ok = False
    try:
        mg_ok = download_one(MUSICGEN_SMALL_ID, MUSICGEN_SMALL_DIR, token)
    except Exception as e:
        print(f"[FAIL] {MUSICGEN_SMALL_ID}: {e}")
    try:
        cosy_ok = download_one(COSYVOICE2_ID, COSYVOICE2_DIR, token)
    except Exception as e:
        print(f"[FAIL] {COSYVOICE2_ID}: {e}")

    # 验证
    r1 = verify_one("MUSICGEN", MUSICGEN_SMALL_DIR, mg_ok)
    r2 = verify_one("COSYVOICE2", COSYVOICE2_DIR, cosy_ok)

    # 磁盘后检
    total, used, free = shutil.disk_usage(check_root if check_root.exists() else Path.cwd())
    print("\n=== DISK ===")
    print(f"Used: {used / 1024**3:.2f} GB")
    print(f"Free: {free / 1024**3:.2f} GB")
    print(f"Total: {total / 1024**3:.2f} GB")

    if r1["status"] != "PASS" or r2["status"] != "PASS":
        print("\n[RESULT] 部分下载 FAIL，请检查上游日志")
        sys.exit(1)
    print("\n[RESULT] 全部 PASS")


if __name__ == "__main__":
    main()
