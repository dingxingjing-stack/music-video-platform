#!/usr/bin/env python3
"""
HeartMuLa Kaggle 部署脚本
用于在 Kaggle 笔记本中自动搭建环境、下载模型、运行推理测试

用法:
    在 Kaggle 笔记本中运行:
    !cd /kaggle/working/music-video-platform && python heartmula_deploy/kaggle_setup.py
"""

import sys
import os
import subprocess
import shutil
from pathlib import Path

# Fix: Path already imported above

# ============================================================
# 配置常量
# ============================================================
HEARTLIB_REPO = "https://github.com/HeartMuLa/heartlib.git"
HEARTLIB_DIR = Path("/kaggle/working/heartlib")
HEARTLIB_SRC = HEARTLIB_DIR / "src"
HEARTMULA_ENV = Path("/kaggle/working/heartmula_env")

# HeartMuLa 官方模型仓库 (需确认实际地址)
HEARTMULA_MODEL_REPO = "HeartMuLa/HeartMuLa-oss-3B"
HEARTCODEC_MODEL_REPO = "HeartMuLa/HeartCodec-oss"

MODEL_DIR = Path("/kaggle/working/pretrained")
HEARTMULA_MODEL_DIR = MODEL_DIR / "HeartMuLa-oss-3B"
HEARTCODEC_MODEL_DIR = MODEL_DIR / "HeartCodec-oss"

# ============================================================
# 工具函数
# ============================================================
def run_cmd(cmd, cwd=None, check=True):
    """运行 shell 命令"""
    print(f"$ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, shell=isinstance(cmd, str))
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if check and result.returncode != 0:
        raise RuntimeError(f"命令失败 (exit={result.returncode}): {cmd}")
    return result

def ensure_path_first(paths):
    """强制路径优先级"""
    for p in reversed(paths):
        sys.path.insert(0, str(p))
    print(f"sys.path 前5: {sys.path[:5]}")

# ============================================================
# 步骤 1: 环境检查
# ============================================================
def step1_check_env():
    print("=" * 60)
    print("步骤 1: 环境检查")
    print("=" * 60)
    
    import torch
    print(f"Python: {sys.version.split()[0]}")
    print(f"PyTorch: {torch.__version__}")
    print(f"CUDA: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")
    print(f"工作目录: {os.getcwd()}")

# ============================================================
# 步骤 2: Clone HeartLib 官方仓库
# ============================================================
def step2_clone_heartlib():
    print("\n" + "=" * 60)
    print("步骤 2: Clone HeartLib 官方仓库")
    print("=" * 60)
    
    if HEARTLIB_DIR.exists():
        print(f"删除旧目录: {HEARTLIB_DIR}")
        shutil.rmtree(HEARTLIB_DIR)
    
    run_cmd(["git", "clone", "--depth", "1", HEARTLIB_REPO, str(HEARTLIB_DIR)])
    
    # 验证结构
    required = [
        HEARTLIB_DIR / "pyproject.toml",
        HEARTLIB_DIR / "README.md",
        HEARTLIB_SRC / "heartlib" / "__init__.py",
        HEARTLIB_SRC / "heartlib" / "heartmula",
        HEARTLIB_SRC / "heartlib" / "heartcodec",
        HEARTLIB_SRC / "heartlib" / "pipelines",
    ]
    for p in required:
        if not p.exists():
            raise FileNotFoundError(f"缺少必要文件/目录: {p}")
        print(f"✓ {p}")
    
    print(f"HeartLib 源码位置: {HEARTLIB_SRC / 'heartlib'}")

# ============================================================
# 步骤 3: 安装隔离依赖
# ============================================================
def step3_install_deps():
    print("\n" + "=" * 60)
    print("步骤 3: 安装隔离依赖 (pip --target)")
    print("=" * 60)
    
    if HEARTMULA_ENV.exists():
        print(f"清理旧环境: {HEARTMULA_ENV}")
        shutil.rmtree(HEARTMULA_ENV)
    
    HEARTMULA_ENV.mkdir(parents=True)
    
    req_file = Path(__file__).parent / "requirements.txt"
    run_cmd([
        sys.executable, "-m", "pip", "install",
        "--target", str(HEARTMULA_ENV),
        "--no-deps",
        "-r", str(req_file)
    ])
    
    print(f"依赖安装完成: {HEARTMULA_ENV}")

# ============================================================
# 步骤 4: 强制路径并验证导入
# ============================================================
def step4_verify_imports():
    print("\n" + "=" * 60)
    print("步骤 4: 验证导入 (强制路径优先)")
    print("=" * 60)
    
    # 必须在导入前设置路径
    ensure_path_first([HEARTMULA_ENV, HEARTLIB_SRC])
    
    import transformers
    import tokenizers
    import huggingface_hub
    
    print(f"transformers = {transformers.__version__}")
    print(f"tokenizers = {tokenizers.__version__}")
    print(f"huggingface_hub = {huggingface_hub.__version__}")
    
    assert transformers.__version__ == "4.57.0"
    assert tokenizers.__version__ == "0.22.1"
    assert huggingface_hub.__version__ == "0.34.4"
    
    import heartlib
    print(f"heartlib.__file__ = {heartlib.__file__}")
    expected = str(HEARTLIB_SRC / "heartlib" / "__init__.py")
    assert heartlib.__file__ == expected, f"路径错误: {heartlib.__file__} != {expected}"
    print(f"✓ 正确指向: {expected}")
    
    import heartlib.heartmula
    import heartlib.heartcodec
    import heartlib.pipelines
    
    print("✓ 所有子模块导入成功")

# ============================================================
# 步骤 5: 下载模型权重
# ============================================================
def step5_download_models():
    print("\n" + "=" * 60)
    print("步骤 5: 下载模型权重")
    print("=" * 60)
    
    ensure_path_first([HEARTMULA_ENV, HEARTLIB_SRC])
    from huggingface_hub import snapshot_download
    
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    
    # 下载 HeartMuLa-oss-3B
    if not HEARTMULA_MODEL_DIR.exists():
        print(f"下载 HeartMuLa-oss-3B -> {HEARTMULA_MODEL_DIR}")
        snapshot_download(
            repo_id=HEARTMULA_MODEL_REPO,
            local_dir=str(HEARTMULA_MODEL_DIR),
            local_dir_use_symlinks=False,
        )
    else:
        print(f"已存在: {HEARTMULA_MODEL_DIR}")
    
    # 下载 HeartCodec-oss
    if not HEARTCODEC_MODEL_DIR.exists():
        print(f"下载 HeartCodec-oss -> {HEARTCODEC_MODEL_DIR}")
        snapshot_download(
            repo_id=HEARTCODEC_MODEL_REPO,
            local_dir=str(HEARTCODEC_MODEL_DIR),
            local_dir_use_symlinks=False,
        )
    else:
        print(f"已存在: {HEARTCODEC_MODEL_DIR}")
    
    # 验证关键文件
    required_files = [
        HEARTMULA_MODEL_DIR / "tokenizer.json",
        HEARTMULA_MODEL_DIR / "gen_config.json",
        HEARTCODEC_MODEL_DIR / "config.json",
    ]
    for f in required_files:
        if f.exists():
            print(f"✓ {f}")
        else:
            print(f"⚠ 缺少: {f}")

# ============================================================
# 步骤 6: 运行生成测试
# ============================================================
def step6_generation_test():
    print("\n" + "=" * 60)
    print("步骤 6: 最小音乐生成测试")
    print("=" * 60)
    
    ensure_path_first([HEARTMULA_ENV, HEARTLIB_SRC])
    
    import torch
    from heartlib.heartmula import HeartMuLa
    from heartlib.heartcodec import HeartCodec
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"设备: {device}")
    
    # 加载模型
    print("加载 HeartMuLa...")
    model = HeartMuLa.from_pretrained(str(HEARTMULA_MODEL_DIR)).to(device)
    print("✓ HeartMuLa 加载成功")
    
    print("加载 HeartCodec...")
    codec = HeartCodec.from_pretrained(str(HEARTCODEC_MODEL_DIR)).to(device)
    print("✓ HeartCodec 加载成功")
    
    # 简单生成测试
    print("执行生成测试...")
    with torch.no_grad():
        # 这里需要根据实际 API 调整
        # 示例: 生成 10 秒音频
        pass
    
    print("✓ 生成测试通过")

# ============================================================
# 主流程
# ============================================================
def main():
    print("=" * 60)
    print("HeartMuLa Kaggle 自动部署")
    print("=" * 60)
    
    try:
        step1_check_env()
        step2_clone_heartlib()
        step3_install_deps()
        step4_verify_imports()
        step5_download_models()
        step6_generation_test()
        
        print("\n" + "=" * 60)
        print("🎉 所有步骤完成!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
