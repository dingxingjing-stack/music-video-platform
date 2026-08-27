"""
Replicate Cog Predictor - HeartMuLa 3B + HeartCodec (Thin Adapter)

Design:
  cog.yaml predict -> predict.py:Predictor -> HeartMuLaLocalService -> HeartMuLa 3B -> HeartCodec -> WAV -> R2 -> URL

Rules:
  - This file is a THIN adapter only. No inference logic duplicated.
  - All generation logic lives in app/services/heartmula_local.py (already verified on Kaggle T4).
  - No Mock. Any GPU/model/CUDA error raises explicit Error.
  - Model weights NEVER in Git/Docker. Downloaded at runtime from HF Hub via snapshot_download.
"""

import os
import tempfile
import uuid
import logging
from pathlib import Path
from cog import BasePredictor, Input, Path as CogPath

logger = logging.getLogger(__name__)


class Predictor(BasePredictor):
    """
    Replicate Cog Predictor for HeartMuLa 3B.

    Lifecycle (Replicate Deployment):
      cog build -> cog push -> Replicate Model -> Deployment (min=0, max=1)
      cold start: setup() loads models (HF Hub download + pipeline) -> predict() reuses
      scale-to-zero: no request -> Worker stopped, next request -> setup() again

    Must use HF Spaces secrets for:
      HF_TOKEN, R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET, CDN_BASE_URL
    """

    def setup(self) -> None:
        """Load model on Worker startup. Runs once per cold start."""
        # Delay imports so cog can import this file even without GPU
        import torch

        # 1) CUDA check - must be explicit error, no Mock
        if not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA unavailable: torch.cuda.is_available() == False. "
                "HeartMuLa requires NVIDIA GPU. Check Dockerfile gpu:true and CUDA 12.4."
            )

        gpu_name = torch.cuda.get_device_name(0)
        vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        logger.info(f"GPU detected: {gpu_name}, VRAM: {vram_gb:.2f} GB, CUDA: {torch.version.cuda}")

        if vram_gb < 14.0:
            raise RuntimeError(f"VRAM insufficient: {vram_gb:.2f} GB < 14.0 GB (T4 16GB required)")

        # 2) Import and initialize HeartMuLaLocalService (lazy_load=True for T4)
        # This handles HF Hub download + HeartMuLaGenPipeline creation
        from app.services.heartmula_local import get_heartmula_local_service, HeartMuLaLocalConfig

        # Use default config (reads HEARTMULA_MODEL_REPO etc from env, lazy_load=True)
        config = HeartMuLaLocalConfig()
        # Enforce T4-safe defaults
        config.lazy_load = True
        config.require_gpu = True

        logger.info(f"Initializing HeartMuLaLocalService: repo={config.model_repo}, codec={config.codec_repo}, version={config.version}")

        # get_heartmula_local_service triggers _validate_environment + _initialize_pipeline
        # This downloads from HF Hub if not cached, verifies *.safetensors, creates pipeline
        self.service = get_heartmula_local_service(config)

        if not self.service._models_loaded:
            raise RuntimeError("HeartMuLa models failed to load (check HF_TOKEN and model repos)")

        # Log memory after load
        stats = self.service.get_memory_stats()
        logger.info(f"HeartMuLa setup complete. Memory stats: {stats}")

    def predict(
        self,
        prompt: str = Input(description="Music description/tags, e.g. 'pop, chinese, female vocal, emotional'", default="pop, emotional"),
        lyrics: str = Input(description="Lyrics text (optional, falls back to prompt)", default=""),
        duration: int = Input(description="Duration in seconds", default=10, ge=10, le=240),
        temperature: float = Input(description="Sampling temperature", default=1.0, ge=0.1, le=2.0),
        top_k: int = Input(description="Top-k sampling", default=50, ge=1, le=250),
        top_p: float = Input(description="Top-p (nucleus) sampling - reserved, currently uses top_k", default=1.0, ge=0.0, le=1.0),
        seed: int = Input(description="Random seed (optional)", default=None),
    ) -> CogPath:
        """
        Run HeartMuLa generation. Returns local file Path (Replicate will upload as output).

        Also uploads to R2 if configured and logs presigned URL, but Cog output is the file itself.
        """
        import torch

        # Validate input
        if not prompt or len(prompt.strip()) < 5:
            raise ValueError("prompt requires >= 5 characters")

        # Optional seed handling (if HeartMuLa supports determinism)
        if seed is not None:
            torch.manual_seed(seed)
            logger.info(f"Seed set: {seed}")

        # 3) Generate via HeartMuLaLocalService (thin delegation)
        # generate_sync returns bytes, we write to temp file for Cog output
        tags = prompt.lower().strip()
        lyrics_text = lyrics.strip() if lyrics else prompt
        max_ms = min(duration * 1000, self.service.config.default_max_audio_length_ms)

        logger.info(f"Generating: prompt='{prompt[:60]}...' duration={duration}s temp={temperature} top_k={top_k}")

        # generate_sync handles temp lyrics/tags files + pipeline + audio validation (48kHz, not silent)
        audio_bytes = self.service.generate_sync(
            lyrics=lyrics_text,
            tags=tags,
            max_audio_length_ms=max_ms,
            topk=top_k,
            temperature=temperature,
            cfg_scale=self.service.config.default_cfg_scale,
        )

        # 4) Write to temp file for Cog output (Replicate will host the file)
        out_path = Path(tempfile.gettempdir()) / f"heartmula_{uuid.uuid4().hex}.wav"
        out_path.write_bytes(audio_bytes)
        logger.info(f"WAV written: {out_path} ({len(audio_bytes)/1024/1024:.2f} MB)")

        # 5) Also upload to R2 if configured (presigned URL for backend/frontend)
        # Do not fail generation if R2 not configured - Cog file output is primary
        r2_url = None
        if os.getenv("R2_ENDPOINT") and os.getenv("R2_ACCESS_KEY_ID"):
            try:
                from app.services.cdn_uploader import cdn_uploader
                import asyncio
                key = f"heartmula/cog/{uuid.uuid4().hex}.wav"
                # upload_private is async, run in new loop if needed
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                # Use sync upload if available, else async
                if hasattr(cdn_uploader, "upload_private"):
                    # Try async
                    import inspect
                    if inspect.iscoroutinefunction(cdn_uploader.upload_private):
                        loop.run_until_complete(cdn_uploader.upload_private(str(out_path), key, "audio/wav"))
                    else:
                        cdn_uploader.upload_private(str(out_path), key, "audio/wav")
                    r2_url = cdn_uploader.get_presigned_download_url(key, expires_in=3600)
                    logger.info(f"R2 uploaded: {r2_url[:80]}...")
            except Exception as e:
                logger.warning(f"R2 upload skipped/failed: {e}")

        # Log for debugging
        logger.info(f"Predict complete: R2={'yes' if r2_url else 'no (Cog file output only)'}")

        return CogPath(str(out_path))
