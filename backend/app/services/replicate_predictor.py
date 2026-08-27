"""
Replicate Predictor for HeartMuLa 3B + HeartCodec

Runs HeartMuLa inference on Replicate's GPU infrastructure.
Uses the existing HeartMuLaLocalService to avoid code duplication.

Deployment:
  - min_instances = 0 (scale-to-zero)
  - max_instances = 1 (single GPU worker)
  - cold start: download models → load → predict
  - subsequent requests: reuse loaded model

Key design:
- Model weights downloaded from HF Hub at startup (not in Docker image)
- Uses existing HeartMuLaLocalService for inference
- Returns real audio via Cloudflare R2 + presigned URLs
- No Mock, no fake audio
- Supports scale-to-zero
"""

import asyncio
import base64
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any

import replicate
from replicate.async_client import ReplicateAsyncClient

from app.services.heartmula_local import (
    HeartMuLaLocalService,
    HeartMuLaLocalConfig,
    HeartMuLaLocalError,
    get_heartmula_local_service,
    is_heartmula_local_available,
)
from app.services.cdn_uploader import cdn_uploader

logger = logging.getLogger(__name__)


# ─── Replicate Predictor ─────────────────────────────────────────────

class HeartMuLaReplicatePredictor(replicate.Predictor):
    """
    Replicate Predictor that runs HeartMuLa 3B + HeartCodec inference.

    Lifecycle:
      - container startup → setup() → download models → load pipeline
      - predict() → generate audio → return dict (NO Mock)
      - container shutdown → clear GPU cache

    The model is loaded ONCE per container instance.
    With scale-to-zero (min_instances=0), the container can be stopped
    entirely between requests. Next request triggers cold start.
    """

    # ─── Class-level state (shared across all instances) ──────────────

    _pipeline_by_gpu: Dict[int, HeartMuLaLocalService] = {}
    _initialized: bool = False

    # ─── Configuration ────────────────────────────────────────────────

    # 默认生成参数
    DEFAULT_TOP_K: int = 50
    DEFAULT_TEMPERATURE: float = 1.0
    DEFAULT_CFG_SCALE: float = 1.5
    MAX_AUDIO_LENGTH_MS: int = 240_000  # 4 分钟

    # Replicate 输出格式
    OUTPUT_SAMPLE_RATE: int = 48_000
    OUTPUT_CHANNELS: int = 2
    OUTPUT_FORMAT: str = "wav"

    # ─── Replicate 环境变量 (必须在 Replicate 部署中设置) ──────────

    # Hugging Face 令牌（用于下载私有模型）
    HF_TOKEN: str = os.getenv("HF_TOKEN", "")

    # HeartMuLa 模型仓库
    HEARTMULA_MODEL_REPO: str = os.getenv(
        "HEARTMULA_MODEL_REPO", "HeartMuLa/HeartMuLa-oss-3B-happy-new-year"
    )

    # HeartCodec 模型仓库
    HEARTCODEC_MODEL_REPO: str = os.getenv(
        "HEARTCODEC_MODEL_REPO", "HeartMuLa/HeartCodec-oss-20260123"
    )

    # 缓存目录 (容器内路径)
    CACHE_DIR: str = "/models/heartmula"

    # R2 配置 (用于上传生成的音频)
    R2_ENDPOINT: str = os.getenv("R2_ENDPOINT", "")
    R2_ACCESS_KEY_ID: str = os.getenv("R2_ACCESS_KEY_ID", "")
    R2_SECRET_ACCESS_KEY: str = os.getenv("R2_SECRET_ACCESS_KEY", "")
    R2_BUCKET: str = os.getenv("R2_BUCKET", "music-audio-storage")
    CDN_BASE_URL: str = os.getenv("CDN_BASE_URL", "")

    # ─── Setup: 在容器启动时运行一次 ──────────────────────────────────

    def setup(self):
        """
        在 Replicate Worker 启动时运行一次。
        - 检查 CUDA
        - 下载模型权重 (HF Hub)
        - 加载 HeartMuLaLocalService (pipeline)
        - 只在 GPU 0 上初始化（单实例设计）
        """
        logger.info("=" * 60)
        logger.info("Replicate Predictor: Container startup (setup)")
        logger.info("=" * 60)

        # 1. 检查 CUDA / GPU
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("❌ CUDA 不可用：Replicate Worker 需要 NVIDIA GPU")

        gpu_id = torch.cuda.current_device()
        gpu_name = torch.cuda.get_device_name(gpu_id)
        vram_gb = torch.cuda.get_device_properties(gpu_id).total_memory / (1024**3)
        logger.info(f"GPU {gpu_id}: {gpu_name}, VRAM: {vram_gb:.2f} GB")

        if vram_gb < 14.0:
            raise RuntimeError(
                f"❌ 显存不足: {vram_gb:.2f} GB (最低 14 GB 推荐，T4 16 GB 标准)"
            )

        # 2. 下载模型权重 (HF Hub)
        logger.info(f"下载 HeartMuLa 模型: {self.HEARTMULA_MODEL_REPO}")
        os.makedirs(self.CACHE_DIR, exist_ok=True)

        from huggingface_hub import snapshot_download

        # 下载 HeartMuLa
        mula_dir = os.path.join(self.CACHE_DIR, "HeartMuLa-oss-3B")
        if not os.path.isdir(mula_dir) or not any(
            mula_dir.glob("*.safetensors")
        ):
            snapshot_download(
                repo_id=self.HEARTMULA_MODEL_REPO,
                local_dir=mula_dir,
                local_dir_use_symlinks=False,
            )
            logger.info("HeartMuLa 权重下载完成")

        # 下载 HeartCodec
        codec_dir = os.path.join(self.CACHE_DIR, "HeartCodec-oss")
        if not os.path.isdir(codec_dir) or not any(codec_dir.glob("*.safetensors")):
            snapshot_download(
                repo_id=self.HEARTCODEC_MODEL_REPO,
                local_dir=codec_dir,
                local_dir_use_symlinks=False,
            )
            logger.info("HeartCodec 权重下载完成")

        # 下载 tokenizer.json 和 gen_config.json
        gen_repo = "HeartMuLa/HeartMuLaGen"
        tokenizer_path = os.path.join(self.CACHE_DIR, "tokenizer.json")
        gen_config_path = os.path.join(self.CACHE_DIR, "gen_config.json")
        if not os.path.exists(tokenizer_path) or not os.path.exists(gen_config_path):
            snapshot_download(
                repo_id=gen_repo,
                local_dir=self.CACHE_DIR,
                local_dir_use_symlinks=False,
                allow_patterns=["tokenizer.json", "gen_config.json"],
            )
            logger.info("tokenizer.json + gen_config.json 下载完成")

        # 3. 初始化 HeartMuLaLocalService (单例，绑定到当前 GPU)
        logger.info("初始化 HeartMuLaLocalService ...")
        config = HeartMuLaLocalConfig(
            model_repo=self.HEARTMULA_MODEL_REPO,
            codec_repo=self.HEARTCODEC_MODEL_REPO,
            version="3B",
            device=f"cuda:{gpu_id}",
            mula_dtype="bfloat16",
            codec_dtype="float32",
            lazy_load=True,  # T4 16GB VRAM 关键策略
            cache_dir=self.CACHE_DIR,
        )

        try:
            pipeline = HeartMuLaLocalService(config)
            HeartMuLaReplicatePredictor._pipeline_by_gpu[gpu_id] = pipeline
            logger.info(
                f"✅ HeartMuLaLocalService 初始化成功 (GPU {gpu_id})"
            )
            # 打印显存状态
            stats = pipeline.get_memory_stats()
            logger.info(f"显存状况: {stats}")
        except HeartMuLaLocalError as e:
            logger.error(f"❌ HeartMuLaLocalService 初始化失败: {e}")
            raise RuntimeError(f"模型初始化失败: {e}")
        except Exception as e:
            logger.exception("❌ 初始化意外错误")
            raise RuntimeError(f"初始化失败: {e}")

        logger.info("=" * 60)
        logger.info("Setup 完成 - 预计可开始接收预测请求")
        logger.info("=" * 60)

    # ─── Predict: 每个请求运行一次 ─────────────────────────────────────

    def predict(
        self,
        # ── 输入参数 (与 Replicate API 匹配) ────────────────────────────
        prompt: str,
        lyrics: Optional[str] = None,
        duration: int = 30,
        temperature: float = 1.0,
        top_k: int = 50,
        top_p: float = 1.0,
        seed: Optional[int] = None,
        # ── 可选的 webhook 回调 ────────────────────────────────────────
        webhook: Optional[str] = None,
        # ── Replicate 自动传递的元数据 ───────────────────────────────────
        version: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Replicate Predictor 的 core 方法。

        每次请求都会运行。模型已在 setup() 中加载一次，此处复用。

        返回 dict，Replicate 会自动将其序列化为 JSON 响应。
        """

        logger.info("=" * 50)
        logger.info(f"Replicate Predictor: generate request")
        logger.info(f"  prompt='{prompt[:60]}...'")
        logger.info(f"  duration={duration}s, temperature={temperature}")
        logger.info(f"  top_k={top_k}, top_p={top_p}")
        if seed is not None:
            logger.info(f"  seed={seed}")

        start_time = time.time()

        try:
            # 1. 获取当前 GPU 的 pipeline (单实例)
            import torch
            gpu_id = torch.cuda.current_device()

            if gpu_id not in HeartMuLaReplicatePredictor._pipeline_by_gpu:
                raise RuntimeError(
                    f"❌ GPU {gpu_id} 上未初始化 Pipeline。"
                    "这不应该发生——确保 setup() 已运行。"
                )

            pipeline = HeartMuLaReplicatePredictor._pipeline_by_gpu[gpu_id]

            # 2. 参数验证
            if not prompt or len(prompt.strip()) < 5:
                raise ValueError("提示词 prompt 至少需要 5 个字符")

            # 2.5. 时长限制
            max_ms = min(duration * 1000, self.MAX_AUDIO_LENGTH_MS)

            # 3. 生成音频 (同步调用，在线程池中避免阻塞)
            loop = asyncio.get_event_loop()

            # 构建歌词和标签
            tags = prompt.lower().strip()
            lyrics_text = lyrics.strip() if lyrics else prompt

            # 在线程池中运行同步生成
            audio_bytes = loop.run_in_executor(
                None,
                self._generate_sync,
                lyrics_text,
                tags,
                max_ms,
                top_k,
                temperature,
                self.DEFAULT_CFG_SCALE,
            )

            # 获取异步结果
            # 注意：run_in_executor 返回 Future，需要 await
            # 但 Replicate Predictor.predict() 是同步的...
            # 我们需要同步获取结果
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    self._generate_sync,
                    lyrics_text,
                    tags,
                    max_ms,
                    top_k,
                    temperature,
                    self.DEFAULT_CFG_SCALE,
                )
                audio_bytes = future.result()

            # 2. 上传到 R2 并获取 presigned URL
            audio_url = asyncio.get_event_loop().run_until_complete(
                self._upload_to_r2(audio_bytes)
            )

            # 3. 获取音频时长
            import torchaudio
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name
            try:
                info = torchaudio.info(tmp_path)
                duration_sec = info.num_frames / info.sample_rate
            finally:
                os.unlink(tmp_path)

            # 4. 构建输出
            generation_time = time.time() - start_time
            result = {
                "success": True,
                "audio_url": audio_url,
                "duration": round(duration_sec, 2),
                "sample_rate": self.OUTPUT_SAMPLE_RATE,
                "channels": self.OUTPUT_CHANNELS,
                "format": self.OUTPUT_FORMAT,
                "generation_time_ms": round(generation_time * 1000),
                "model": "HeartMuLa-oss-3B-happy-new-year",
                "codec": "HeartCodec-oss-20260123",
                "seed": seed,
                "parameters": {
                    "prompt": prompt,
                    "lyrics": lyrics,
                    "duration": duration,
                    "temperature": temperature,
                    "top_k": top_k,
                    "top_p": top_p,
                },
                "metadata": {
                    "gpu": torch.cuda.get_device_name(gpu_id),
                    "vram_gb": round(
                        torch.cuda.get_device_properties(gpu_id).total_memory / (1024**3),
                        2,
                    ),
                },
            }

            logger.info(
                f"✅ 生成完成: {duration_sec:.2f}s, "
                f"用时 {generation_time:.2f}s, "
                f"URL: {audio_url[:80]}..."
            )
            logger.info("=" * 50)

            return result

        except HeartMuLaLocalError as e:
            logger.error(f"❌ 本地推理错误: {e}")
            return {
                "success": False,
                "error": f"本地推理失败: {str(e)}",
                "audio_url": None,
                "duration": None,
                "sample_rate": None,
                "channels": None,
                "format": None,
                "generation_time_ms": round((time.time() - start_time) * 1000),
            }

        except Exception as e:
            logger.exception("❌ 生成过程异常")
            return {
                "success": False,
                "error": f"生成异常: {type(e).__name__}: {str(e)}",
                "audio_url": None,
                "duration": None,
                "sample_rate": None,
                "channels": None,
                "format": None,
                "generation_time_ms": round((time.time() - start_time) * 1000),
            }

    # ─── 辅助: 同步音频生成 ──────────────────────────────────────────

    def _generate_sync(
        self,
        lyrics: str,
        tags: str,
        max_audio_length_ms: int,
        top_k: int,
        temperature: float,
        cfg_scale: float,
    ) -> bytes:
        """同步生成音频字节数据（在线程池中运行）"""
        with torch.no_grad():
            # pipeline 是 HeartMuLaLocalService 实例
            # 它的 generate 方法已在 heartmula_local.py 中定义
            # 我们通过 pipeline 的 generate 方法或直接调用
            # 这里直接使用 pipeline 的属性
            from app.services.heartmula_local import (
                get_heartmula_local_service,
            )

            # 获取当前全局 pipeline
            pipeline = get_heartmula_local_service()

            # 调用 generate_sync 方法
            # 注意：generate_sync 需要 lyrics, tags, max_audio_length_ms
            # 实际 HeartMuLaLocalService.generate_sync 接受这些参数
            result = pipeline.generate_sync(
                lyrics=lyrics,
                tags=tags,
                max_audio_length_ms=max_audio_length_ms,
                top_k=top_k,
                temperature=temperature,
            )

            return result

    # ─── 辅助: R2 上传 ──────────────────────────────────────────────

    async def _upload_to_r2(self, audio_bytes: bytes) -> str:
        """上传音频到 Cloudflare R2 并返回 presigned download URL"""
        import tempfile
        import uuid

        # 生成唯一文件名
        file_id = str(uuid.uuid4())
        key = f"heartmula/replicate/{file_id}.wav"

        # 写入临时文件
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            await cdn_uploader.upload_private(tmp_path, key, "audio/wav")
            presigned_url = cdn_uploader.get_presigned_download_url(
                key, expires_in=3600
            )
            return presigned_url
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    # ─── 类方法: 供 Replicate CLI/HTTP API 调用 ──────────────────────

    @classmethod
    def get_input_schema(cls) -> dict:
        """返回 Replicate API 的输入参数 schema"""
        return {
            "prompt": {
                "type": "string",
                "description": "音乐描述/提示词",
            },
            "lyrics": {
                "type": "string",
                "description": "可选歌词",
            },
            "duration": {
                "type": "number",
                "description": "生成时长(秒)，默认 30s，最大 240s",
                "minimum": 10,
                "maximum": 240,
            },
            "temperature": {
                "type": "number",
                "description": "采样温度 0.1-2.0，默认 1.0",
                "minimum": 0.1,
                "maximum": 2.0,
            },
            "top_k": {
                "type": "integer",
                "description": "Top-k 采样，默认 50",
                "minimum": 1,
                "maximum": 250,
            },
            "top_p": {
                "type": "number",
                "description": "Top-p ( nucleus ) 采样，默认 1.0",
                "minimum": 0.0,
                "maximum": 1.0,
            },
            "seed": {
                "type": "integer",
                "description": "随机种子（可选）",
            },
        }

    @classmethod
    def get_output_schema(cls) -> dict:
        """返回 Replicate API 的输出参数 schema"""
        return {
            "success": {
                "type": "boolean",
                "description": "生成是否成功",
            },
            "audio_url": {
                "type": "string",
                "format": "url",
                "description": "R2 预签名下载 URL",
            },
            "duration": {
                "type": "number",
                "description": "生成音频时长(秒)",
            },
            "sample_rate": {
                "type": "integer",
                "description": "音频采样率",
            },
            "channels": {
                "type": "integer",
                "description": "音频通道数",
            },
            "format": {
                "type": "string",
                "description": "音频格式",
            },
            "error": {
                "type": "string",
                "description": "错误信息（success=False 时存在）",
            },
            "generation_time_ms": {
                "type": "integer",
                "description": "生成耗时(ms)",
            },
            "model": {
                "type": "string",
                "description": "使用的模型名称",
            },
        }