#!/usr/bin/env bash
# Kaggle T4 16GB + 19.5GB working 启动前环境初始化与磁盘检查（严格 Dataset 模式）
# 规则：
#   - HeartMuLa 3B 必须且仅从 /kaggle/input/heartmula-3b Dataset 加载
#   - 不存在/不完整（缺 config.json 或 *.safetensors）→ 直接报错，不回落到 /kaggle/working，不自动下载
#   - 禁止任何 HeartMuLa 权重出现在 /kaggle/working（安全修正）
set -euo pipefail

echo "=========================================="
echo "Kaggle Setup — Music Video Platform (STRICT Dataset)"
echo "Date: $(date -u)"
echo "=========================================="

# --- 1. 统一缓存（避免 ~/.cache 与 /kaggle/working/cache 双份）---
export KAGGLE_CACHE_ROOT="/kaggle/working/cache"
export HF_HOME="${KAGGLE_CACHE_ROOT}/hf"
export HF_HUB_CACHE="${HF_HOME}/hub"
export TORCH_HOME="${KAGGLE_CACHE_ROOT}/torch"
export HF_HUB_ENABLE_HF_TRANSFER="${HF_HUB_ENABLE_HF_TRANSFER:-1}"
export PYTHONIOENCODING="utf-8"

mkdir -p "${HF_HOME}" "${TORCH_HOME}" "/kaggle/working/cache/hf" "/kaggle/working/output"

echo "[Cache] HF_HOME=${HF_HOME}"
echo "[Cache] TORCH_HOME=${TORCH_HOME}"
echo "[Cache] HF_HUB_ENABLE_HF_TRANSFER=${HF_HUB_ENABLE_HF_TRANSFER}"

# --- 2. 磁盘检查（总/已用/剩余 + 主要模型缓存大小）---
echo ""
echo "--- B. Disk Check (/kaggle/working) ---"
if command -v df >/dev/null 2>&1; then
  df -h /kaggle/working || df -h
fi
if command -v du >/dev/null 2>&1; then
  echo ""
  echo "Cache sizes:"
  du -sh "${KAGGLE_CACHE_ROOT}" 2>/dev/null || echo "  (cache not yet created)"
  du -sh "${HF_HOME}" 2>/dev/null || true
  du -sh "/kaggle/input" 2>/dev/null | head -n 20 || true
fi

# --- 3. HeartMuLa 严格检查（不回落，不下载）---
echo ""
echo "--- C/I. HeartMuLa Dataset STRICT check (/kaggle/input/heartmula-3b) ---"
HEARTMULA_DATASET="/kaggle/input/heartmula-3b"
if [ ! -d "${HEARTMULA_DATASET}" ]; then
  echo "ERROR: HeartMuLa Dataset NOT FOUND at ${HEARTMULA_DATASET}"
  echo "  必须在 Kaggle Notebook 右侧 Add data 挂载 HeartMuLa-3B Dataset 到 /kaggle/input/heartmula-3b"
  echo "  禁止自动下载到 /kaggle/working（6.5GB 会占满 19.5GB working）"
  echo "  请挂载后重新运行此脚本。"
  exit 1
fi
echo "  Found: ${HEARTMULA_DATASET}"
ls -lh "${HEARTMULA_DATASET}" | head -n 20
if [ ! -f "${HEARTMULA_DATASET}/config.json" ]; then
  # 也检查子目录形式
  if ls "${HEARTMULA_DATASET}"/*/config.json >/dev/null 2>&1; then
    echo "  -> config.json found in subdirectory (Kaggle dataset nesting) — OK"
  else
    echo "ERROR: ${HEARTMULA_DATASET}/config.json 缺失 — Dataset 不完整"
    echo "  禁止回落到 /kaggle/working，不自动下载。请检查 Dataset 内容。"
    exit 1
  fi
else
  echo "  -> config.json OK"
fi
if ! ls "${HEARTMULA_DATASET}"/*.safetensors >/dev/null 2>&1 && ! ls "${HEARTMULA_DATASET}"/*/  *.safetensors >/dev/null 2>&1 2>/dev/null; then
  # 检查子目录
  if ls "${HEARTMULA_DATASET}"/*/*.safetensors >/dev/null 2>&1; then
    echo "  -> *.safetensors found in subdirectory — OK"
  else
    echo "ERROR: ${HEARTMULA_DATASET}/*.safetensors 缺失 — Dataset 不完整"
    echo "  禁止回落到 /kaggle/working，不自动下载。请确保 Dataset 包含权重。"
    exit 1
  fi
else
  echo "  -> *.safetensors OK"
fi
# 禁止 working 下出现 HeartMuLa 权重
if [ -d "/kaggle/working/heartmula-3b" ] || [ -d "/kaggle/working/cache/hf/hub/models--HeartMuLa-3b" ] || [ -d "/kaggle/working/models/heartmula" ]; then
  echo "ERROR: 检测到 /kaggle/working 下存在 HeartMuLa 权重（禁止）— 请删除："
  ls -ld /kaggle/working/heartmula-3b 2>/dev/null || true
  ls -ld /kaggle/working/cache/hf/hub/models--HeartMuLa* 2>/dev/null || true
  ls -ld /kaggle/working/models/heartmula 2>/dev/null || true
  echo "  HeartMuLa 必须仅通过 /kaggle/input/heartmula-3b Dataset 挂载"
  exit 1
fi
echo "  -> HeartMuLa STRICT OK (Dataset 完整，working 无副本)"

# ASR small 缓存提示（不强制失败）
echo ""
echo "--- G/H. ASR small cache check ---"
if [ -d "${HF_HOME}/hub/models--Systran--faster-whisper-small" ] || [ -d "${HF_HOME}/models--Systran--faster-whisper-small" ]; then
  echo "  ASR small cached: YES ($(du -sh ${HF_HOME}/*small* 2>/dev/null | head -n 5))"
else
  echo "  ASR small cached: NO — 首次转写时仅允许下载 small (~250MB int8) 到 ${HF_HOME}"
  echo "  (large-v3 禁止下载)"
fi

echo ""
echo "--- Env guards (STRICT) ---"
echo "HEARTMULA_KAGGLE_DATASET_PATH=${HEARTMULA_KAGGLE_DATASET_PATH:-/kaggle/input/heartmula-3b} (STRICT: missing -> error, no fallback)"
echo "VOICE_CLONE_ASR_MODEL=${VOICE_CLONE_ASR_MODEL:-small} (only small allowed)"
echo "HEARTCODEC_LOCAL_MODE=${HEARTCODEC_LOCAL_MODE:-false} (must be false)"
echo "GPT-SoVITS / ACE-Step : Modal remote only — Kaggle will NOT download"

# --- 空间预警 ---
if command -v df >/dev/null 2>&1; then
  avail_kb=$(df -k /kaggle/working 2>/dev/null | awk 'NR==2 {print $4}')
  if [ -n "${avail_kb}" ] && [ "${avail_kb}" -lt 2097152 ]; then
    echo ""
    echo "WARNING: /kaggle/working remaining <2GB — consider clearing /kaggle/working/cache or output"
  fi
fi

echo ""
echo "Setup done. Next: pip install -r requirements-kaggle.txt (if needed) then start backend."
echo "=========================================="
