# RunPod HeartMuLa 独立镜像（不修改 backend/Dockerfile，不烘焙 3B 权重）
# 基础镜像：PyTorch 官方 2.10.0 + CUDA 12.8 + cuDNN9（与 Kaggle 2.10.0+cu128 完全对齐，sm_70+ 兼容）
# 权重运行时经 HF_TOKEN snapshot_download 至 /runpod-volume/pretrained（Network Volume 缓存）
# 官方 tag 已验证存在：pytorch/pytorch:2.10.0-cuda12.8-cudnn9-devel
FROM pytorch/pytorch:2.10.0-cuda12.8-cudnn9-devel

WORKDIR /app

# 系统依赖（与 heartmula_deploy 一致，补充 libsndfile/ffmpeg 用于音频保存）
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libsndfile1 \
    ffmpeg \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 复制 Worker 代码与独立 requirements（不复制 backend，避免污染）
COPY requirements.txt /app/requirements.txt
COPY heartmula_worker.py /app/heartmula_worker.py

# 安装依赖（不重装 torch/torchaudio，利用镜像预装的 cu128 版本；其余按 heartmula_deploy 锁定，pip 不会降级 torch 2.10）
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# 模型缓存目录（RunPod Network Volume 挂载点，首次冷启动下载，后续温启动复用）
# 严禁 COPY 模型权重；运行时 HF_TOKEN 注入
ENV MODEL_CACHE_DIR=/runpod-volume/pretrained
ENV OUTPUT_DIR=/tmp/heartmula_output
ENV HEARTMULA_REPO=HeartMuLa/HeartMuLa-oss-3B
ENV HEARTCODEC_REPO=HeartMuLa/HeartCodec-oss
ENV PYTHONUNBUFFERED=1

# 预创建目录（权限）
RUN mkdir -p /runpod-volume/pretrained /tmp/heartmula_output

# 静态检查：验证 heartmula_worker 可 import（无 GPU 时 handler 仅返回 CUDA 错误，不拉模型）
RUN python -c "import heartmula_worker; print('static check ok', heartmula_worker.HEARTMULA_REPO)"

# RunPod Serverless 入口（官方）：python -u heartmula_worker.py
CMD ["python", "-u", "/app/heartmula_worker.py"]
