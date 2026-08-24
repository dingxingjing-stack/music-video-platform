# HeartMuLa Kaggle 部署 - 笔记本单元格版本
# 复制以下代码到 Kaggle 笔记本单元格中运行
# 注意: 笔记本中使用 ! 前缀运行 shell 命令

# ============================================================
# 单元格 1: 环境检查 + Clone HeartLib
# ============================================================
import sys, os, subprocess, shutil
from pathlib import Path

HEARTLIB_DIR = Path("/kaggle/working/heartlib")
HEARTLIB_SRC = HEARTLIB_DIR / "src"
HEARTMULA_ENV = Path("/kaggle/working/heartmula_env")

# 清理旧目录
if HEARTLIB_DIR.exists():
    shutil.rmtree(HEARTLIB_DIR)

# Clone 官方仓库 (笔记本中用: !git clone ...)
# !git clone --depth 1 https://github.com/HeartMuLa/heartlib.git /kaggle/working/heartlib
subprocess.run(["git", "clone", "--depth", "1", "https://github.com/HeartMuLa/heartlib.git", "/kaggle/working/heartlib"], check=True)

# 验证
for p in [
    HEARTLIB_DIR / "pyproject.toml",
    HEARTLIB_DIR / "README.md",
    HEARTLIB_SRC / "heartlib" / "__init__.py",
    HEARTLIB_SRC / "heartlib" / "heartmula",
    HEARTLIB_SRC / "heartlib" / "heartcodec",
    HEARTLIB_SRC / "heartlib" / "pipelines",
]:
    assert p.exists(), f"缺失: {p}"
    print(f"✓ {p}")

print("HeartLib clone 完成")


# ============================================================
# 单元格 2: 安装隔离依赖
# ============================================================
import sys, subprocess, shutil
from pathlib import Path

HEARTMULA_ENV = Path("/kaggle/working/heartmula_env")

if HEARTMULA_ENV.exists():
    shutil.rmtree(HEARTMULA_ENV)
HEARTMULA_ENV.mkdir(parents=True)

requirements = """
transformers==4.57.0
tokenizers==0.22.1
huggingface-hub==0.34.4
tqdm==4.67.1
numpy==2.0.2
torch==2.13.0+cu121
torchaudio==2.13.0+cu121
einops==0.8.0
safetensors==0.4.3
"""

req_file = HEARTMULA_ENV / "requirements.txt"
req_file.write_text(requirements.strip())

# 笔记本中用: !pip install --target /kaggle/working/heartmula_env --no-deps -r /kaggle/working/heartmula_env/requirements.txt
subprocess.run([
    sys.executable, "-m", "pip", "install",
    "--target", "/kaggle/working/heartmula_env",
    "--no-deps",
    "-r", "/kaggle/working/heartmula_env/requirements.txt"
], check=True)

print("依赖安装完成")


# ============================================================
# 单元格 3: 强制路径 + 验证导入
# ============================================================
import sys
from pathlib import Path

HEARTMULA_ENV = Path("/kaggle/working/heartmula_env")
HEARTLIB_SRC = Path("/kaggle/working/heartlib/src")

# 必须在所有 import 之前
sys.path.insert(0, str(HEARTMULA_ENV))
sys.path.insert(0, str(HEARTLIB_SRC))

import transformers, tokenizers, huggingface_hub
print(f"transformers = {transformers.__version__}")
print(f"tokenizers = {tokenizers.__version__}")
print(f"huggingface_hub = {huggingface_hub.__version__}")

assert transformers.__version__ == "4.57.0"
assert tokenizers.__version__ == "0.22.1"
assert huggingface_hub.__version__ == "0.34.4"

import heartlib
print(f"heartlib.__file__ = {heartlib.__file__}")
assert heartlib.__file__ == "/kaggle/working/heartlib/src/heartlib/__init__.py"

import heartlib.heartmula
import heartlib.heartcodec
import heartlib.pipelines

print("✅ 所有导入验证通过")


# ============================================================
# 单元格 4: 下载模型权重
# ============================================================
from huggingface_hub import snapshot_download
from pathlib import Path

MODEL_DIR = Path("/kaggle/working/pretrained")
MODEL_DIR.mkdir(exist_ok=True)

HEARTMULA_MODEL_DIR = MODEL_DIR / "HeartMuLa-oss-3B"
HEARTCODEC_MODEL_DIR = MODEL_DIR / "HeartCodec-oss"

# 下载 HeartMuLa-oss-3B
if not HEARTMULA_MODEL_DIR.exists():
    snapshot_download(
        repo_id="HeartMuLa/HeartMuLa-oss-3B",
        local_dir=str(HEARTMULA_MODEL_DIR),
        local_dir_use_symlinks=False,
    )
    print(f"✓ HeartMuLa 下载完成: {HEARTMULA_MODEL_DIR}")
else:
    print(f"已存在: {HEARTMULA_MODEL_DIR}")

# 下载 HeartCodec-oss
if not HEARTCODEC_MODEL_DIR.exists():
    snapshot_download(
        repo_id="HeartMuLa/HeartCodec-oss",
        local_dir=str(HEARTCODEC_MODEL_DIR),
        local_dir_use_symlinks=False,
    )
    print(f"✓ HeartCodec 下载完成: {HEARTCODEC_MODEL_DIR}")
else:
    print(f"已存在: {HEARTCODEC_MODEL_DIR}")

# 验证关键文件
for f in [
    HEARTMULA_MODEL_DIR / "tokenizer.json",
    HEARTMULA_MODEL_DIR / "gen_config.json",
    HEARTCODEC_MODEL_DIR / "config.json",
]:
    print(f"{'✓' if f.exists() else '✗'} {f}")


# ============================================================
# 单元格 5: GPU 生成测试
# ============================================================
import torch
from pathlib import Path

# 再次确保路径
import sys
sys.path.insert(0, "/kaggle/working/heartmula_env")
sys.path.insert(0, "/kaggle/working/heartlib/src")

from heartlib.heartmula import HeartMuLa
from heartlib.heartcodec import HeartCodec

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"设备: {device}")

MODEL_DIR = Path("/kaggle/working/pretrained")

# 加载模型
mular = HeartMuLa.from_pretrained(str(MODEL_DIR / "HeartMuLa-oss-3B")).to(device)
codec = HeartCodec.from_pretrained(str(MODEL_DIR / "HeartCodec-oss")).to(device)

print("✓ 模型加载成功")

# 尝试生成 (根据官方 API 调整)
with torch.no_grad():
    try:
        # 这里需要根据实际 HeartMuLa API 调整
        # 示例调用:
        # output = mular.generate(prompt="peaceful piano", duration=10)
        # wav = codec.decode(output)
        print("请根据官方 API 文档/示例填入生成代码")
    except Exception as e:
        print(f"生成测试: {e}")

print("测试完成")
