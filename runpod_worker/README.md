# RunPod HeartMuLa Worker — 10秒独立 POC

> 独立于 `backend` 生产链路，不修改 `provider_registry.py` / `Modal` / `Fal` / `/health`，不删除 `heartmula_deploy` Kaggle POC，不烘焙 3B 权重

## 文件
- `heartmula_worker.py` — RunPod Serverless handler，输入 `{"input":{"prompt":"...","duration":10}}`，流程：检查 CUDA → `snapshot_download` HeartMuLa-oss-3B/HeartCodec-oss（`HF_TOKEN` 环境变量）到 `$MODEL_CACHE_DIR` 缓存 → `MusicGenerationPipeline.generate(prompt,duration=10)` → 保存 `WAV` 到 `$OUTPUT_DIR` → 返回 `{success,duration,filename,generation_time,gpu_name,cuda_version,torch_version,error}`
- `requirements.txt` — 仅 Worker 依赖，与 `heartmula_deploy/requirements.txt` 完全对齐（`torch` 复用镜像预装 `2.10.0+cu128`），新增 `runpod==1.7.0`
- `Dockerfile` — 独立镜像 `FROM pytorch/pytorch:2.10.0-cuda12.8-cudnn9-devel`，`MODEL_CACHE_DIR=/runpod-volume/pretrained` 运行时下载，不 `COPY` 权重
- `.dockerignore` — 拦截 `pretrained/*.safetensors/*.bin/*.pt/*.ckpt`

## 启动
```bash
# 本地静态检查（无 GPU 仅返回 CUDA 错误，不拉模型）
python runpod_worker/heartmula_worker.py
python -m py_compile runpod_worker/heartmula_worker.py

# Docker 构建（本地验证，不推 RunPod）
docker build -f runpod_worker/Dockerfile -t heartmula-runpod:10s runpod_worker/
# 若需 GPU 本地模拟（需 nvidia-runtime）
docker run --gpus all -e HF_TOKEN=hf_xxx -e MODEL_CACHE_DIR=/tmp/pretrained runpod_worker
```

RunPod 控制台：Template → `heartmula-runpod:10s` → 挂载 Network Volume 至 `/runpod-volume`（缓存模型，避免每次冷启动 12GB 下载）→ 环境变量见下 → Serverless 按需 Worker（非 Always On）→ 测试 `{"input":{"prompt":"A beautiful piano melody","duration":10}}`

## 模型下载
- `huggingface_hub.snapshot_download(repo_id=HeartMuLa/HeartMuLa-oss-3B, local_dir=$MODEL_CACHE_DIR/HeartMuLa-oss-3B)` 与 `HeartCodec-oss` 同理，`token=HF_TOKEN`（严禁硬编码），首次冷启动 ~8-12GB / ~3-5 分钟，温启动命中缓存秒级加载
- 验证文件：`tokenizer.json` `gen_config.json` `config.json`（与 `kaggle_setup.py:222` 一致）
- 与 `heartmula_deploy` 差异：Kaggle 用 `/kaggle/working/pretrained` + `pip --target heartmula_env` 隔离；RunPod 用 `/runpod-volume/pretrained` + 镜像 pip（无 `--target`），均不写 Git

## 环境变量
- `HF_TOKEN`（或 `HUGGINGFACE_TOKEN` / `HF_API_TOKEN`）— 必需，私有仓库鉴权，本地 `.env` / RunPod Secrets 注入，**不写入代码/Dockerfile/Git**
- `MODEL_CACHE_DIR` — 默认 `/runpod-volume/pretrained`（Network Volume），否则 `/tmp/pretrained`
- `HEARTMULA_REPO` / `HEARTCODEC_REPO` — 默认 `HeartMuLa/HeartMuLa-oss-3B` / `HeartMuLa/HeartCodec-oss`，可覆写
- `OUTPUT_DIR` — 默认 `/tmp/heartmula_output`
- 无 `RUNPOD_*` 硬编码；现有 `RUNPOD_ENDPOINT_ID/API_KEY/SMOKE_TEST_TOKEN` 仍由 `backend/app/routers/ai_music.py` Smoke Test 复用

## 当前阶段说明（与 Kaggle 验证一致）
- HeartMuLa：`HeartMuLa/HeartMuLa-oss-3B`
- HeartCodec：`HeartMuLa/HeartCodec-oss`
- 基础镜像：`PyTorch 2.10.0 + CUDA 12.8`（`pytorch/pytorch:2.10.0-cuda12.8-cudnn9-devel`），与 Kaggle `2.10.0+cu128` 完全对齐
- 模型不进入 Docker 镜像，首次启动通过 `HF_TOKEN` 下载模型
- 模型缓存目录：`/runpod-volume/pretrained`（Network Volume 持久化）
- 输出目录：`/tmp/heartmula_output`（Worker 临时目录）
- 当前 Worker 强制只允许 `duration=10`（`handler` 对非10强制修正为10）
- 当前阶段只做 10 秒真实音乐生成验证，不测 5 分钟
- WAV 当前保存在 Worker 临时目录 `/tmp/heartmula_output/heartmula_*.wav`，尚未接入 R2，文件随容器退出丢失
- 因此当前测试目标只是验证 HeartMuLa 能否在 RunPod 上真实生成 WAV，不作为生产音乐 API `/api/v1/ai/generate`

## 显存
- 冷启动加载 `HeartMuLa-oss-3B bf16` + `HeartCodec float32` → `~13-15GB`（与 `kaggle_setup.py:70` 检测一致），10s 推理峰值 `~13.5GB`，温启动复用不翻倍
- 要求 `T4 16GB (sm_75)` 最低，或 `L4/A10G/A100` 更佳；Kaggle 校验 `free >=16GB` 同理适用 RunPod `GPU: NVIDIA L4 / A10`

## 依赖冲突记录
- **无破坏**：Worker 依赖完全隔离 `runpod_worker/requirements.txt`，未写入 `backend/requirements.txt`，`torch` 复用镜像 `2.10.0+cu128` 与 Kaggle 一致，`transformers 4.57` 等锁定一致，已在 `Dockerfile` `RUN python -c "import heartmula_worker"` 静态检查
- 潜在：`bitsandbytes 0.49` 在 `cuda12.8` 需 `libgomp1` 已装；`torchao/torchtune` 与 `torch 2.10` 兼容，Kaggle 路径与 RunPod 一致
- 后端 `/health` 无 `heartlib` 导入，不受影响

## 就绪度
- 静态检查通过，Docker 可本地构建，10s 流程与 `kaggle_generate.py:74 pipeline.generate(duration=10)` 一致，未接入 `provider_registry` / `/api/v1/ai/generate`，按需 Serverless 无长期 GPU 费用 — **已准备好第一次真实 10s RunPod GPU 执行，需你确认后执行 `Endpoint /run` 调用**
