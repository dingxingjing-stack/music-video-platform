# RunPod Serverless Worker — HeartMuLa 本地推理（GPU）
# 基础镜像：PyTorch 2.4.0 + CUDA 12.4.1。
# 原因：heartlib 声明 torch<2.11,>=2.4（以及 torchaudio<2.11,>=2.4），
#       runpod/pytorch 官方镜像仅在 torch>=2.4 时提供 Python 3.11（无 py3.10 + CUDA 版本），
#       因此基础镜像从 2.2.0-py3.10 升级到 2.4.0-py3.11（heartlib 本身不要求 py3.11，
#       是 runpod/pytorch 镜像 tag 可用性所致）。
# torch 2.4.0 满足 >=2.4,<2.11；torchaudio 2.4.0 / torchvision 0.19.0 均满足 heartlib 约束。
FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

WORKDIR /app

# 系统依赖（torchaudio/librosa/ffmpeg 运行所需）
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# HeartMuLa Worker Python 依赖（含 HeartMuLa service 运行所需）
# requirements.txt 中 torch/torchaudio 为 >=2.2.0（允许保留镜像预装 2.4.0，不会降级）
COPY backend/runpod/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 构建期校验：确认 torch 未被降级且 heartlib 依赖链可导入（无 GPU 不加载权重）
RUN python -c "import torch, torchaudio, transformers, torchtune, vector_quantize_pytorch; \
    print('torch', torch.__version__, 'cuda', torch.version.cuda, 'torchaudio', torchaudio.__version__); \
    assert tuple(int(x) for x in torch.__version__.split('+')[0].split('.')[:2]) >= (2, 4), 'torch downgraded below 2.4'; \
    assert tuple(int(x) for x in torch.__version__.split('+')[0].split('.')[:2]) < (2, 11), 'torch >= 2.11'; \
    import heartlib; \
    from heartlib import HeartMuLaGenPipeline; \
    print('heartlib import OK')"

# 复制 backend 应用包（app/），使 `from app.services.heartmula_service import ...` 可解析。
# worker 只 import heartmula 相关服务；app/services/__init__.py 已惰性化，避免拉入 FastAPI。
COPY backend/app /app/app

# 真实 HeartMuLa Worker handler（替换 smoke test handler）
COPY backend/runpod/handler.py .

# RunPod Serverless 入口
CMD ["python", "-u", "handler.py"]