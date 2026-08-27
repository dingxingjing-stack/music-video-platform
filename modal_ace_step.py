"""
ACE-Step Modal Deployment - Minimal L40S Configuration
- Only ACE-Step music generation
- No HeartMuLa, HeartCodec, MusicGen, Demucs, UVR
- Model weights cached in Modal Volume
- Scale-to-zero with 5 min idle timeout
"""

import modal
import os

# ============================================================
# Image Definition - Pre-install ACE-Step dependencies
# ============================================================
ace_step_image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("git")
    .pip_install([
        "git+https://github.com/ace-step/ACE-Step.git@1bee4c9f5b43e30995f8d4d33b3919197ce1bd68",
        "torch==2.5.1",
        "torchaudio==2.5.1",
        "transformers>=4.40.0",
        "accelerate>=0.30.0",
        "safetensors>=0.4.0",
        "huggingface_hub[hf_transfer]>=0.23.0",
        "fastapi>=0.109.0",
        "httpx>=0.27.0",
        "python-multipart>=0.0.6",
        "numpy",
        "scipy",
        "soundfile",
    ])
    .env({
        "HF_HUB_ENABLE_HF_TRANSFER": "1",
        "HF_HOME": "/models",
        "TORCH_HOME": "/models",
    })
)

# ============================================================
# Modal App & Volume for model persistence
# ============================================================
app = modal.App("ace-step-music", image=ace_step_image)

# Persistent volume for model weights (~6-8GB)
model_volume = modal.Volume.from_name("ace-step-models", create_if_missing=True)

# HF Token secret (create in Modal Dashboard: modal secret create hf-token HF_TOKEN=xxx)
hf_secret = modal.Secret.from_name("hf-token")

# ============================================================
# ACE-Step Pipeline Singleton (loaded once per container)
# ============================================================
class ACEStepPipeline:
    _instance = None
    _pipeline = None
    
    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        from acestep.pipeline_ace_step import ACEStepPipeline as ACEPipeline
        import torch
        
        print("[ACE-Step] Initializing pipeline...")
        # Initialize pipeline with model cache directory
        self.pipeline = ACEPipeline(
            checkpoint_dir="/models/checkpoints",
            persistent_storage_path="/models",
            device_id=0,
            dtype="bfloat16",
            cpu_offload=False,
            quantized=False,
        )
        print("[ACE-Step] Loading model checkpoints...")
        self.pipeline.load_checkpoint()
        print("[ACE-Step] Model loaded successfully")
    
    def generate(self, prompt: str, lyrics: str, duration: int, style: str,
                 cfg_scale: float = 7.0, steps: int = 25, 
                 bpm: int = None, key: str = None, vocal_type: str = "auto"):
        """Text-to-music generation using __call__ method"""
        # Map our parameters to ACE-Step's __call__ signature
        # Note: style parameter is not directly supported, we embed it in prompt
        enhanced_prompt = f"{style} music, {prompt}" if style and style != "auto" else prompt
        
        result = self.pipeline(
            prompt=prompt if prompt else "",
            lyrics=lyrics if lyrics else "",
            audio_duration=float(duration),
            infer_step=steps,
            guidance_scale=cfg_scale,
            task="text2music",
            audio2audio_enable=False,
            format="wav",
            batch_size=1,
        )
        return result
    
    def continue_audio(self, reference_audio_path: str, prompt: str, lyrics: str,
                       duration: int, style: str, cfg_scale: float = 7.0,
                       steps: int = 25, reference_start_sec: float = 0.0,
                       reference_duration_sec: float = None,
                       continuation_mode: str = "extend"):
        """Audio-to-audio continuation"""
        result = self.pipeline(
            prompt=prompt if prompt else "",
            lyrics=lyrics if lyrics else "",
            audio_duration=float(duration),
            infer_step=steps,
            guidance_scale=cfg_scale,
            task="audio2audio",
            audio2audio_enable=True,
            ref_audio_input=reference_audio_path,
            format="wav",
            batch_size=1,
        )
        return result

# ============================================================
# Helper: Download reference audio from URL
# ============================================================
async def download_reference_audio(url: str) -> str:
    import httpx
    import tempfile
    import uuid
    
    tmp_path = f"/tmp/ref_{uuid.uuid4().hex}.wav"
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        with open(tmp_path, "wb") as f:
            f.write(resp.content)
    return tmp_path

# ============================================================
# Health Check Endpoint
# ============================================================
@app.function(
    gpu="L40S",
    timeout=60,
    scaledown_window=300,
)
@modal.fastapi_endpoint(method="GET", docs=True)
def health():
    return {
        "healthy": True,
        "model": "ace-step",
        "version": "1.0",
        "max_duration_single": 180,
    }

# ============================================================
# Main Generation Endpoint
# ============================================================
@app.function(
    gpu="L40S",
    timeout=300,
    volumes={"/models": model_volume},
    secrets=[hf_secret],
    scaledown_window=300,
    max_containers=4,
)
@modal.fastapi_endpoint(method="POST", docs=True)
async def generate(request: dict):
    """
    Request body:
    {
        "prompt": "upbeat pop song",
        "lyrics": "[Verse]...\n[Chorus]...",
        "duration": 180,
        "style": "pop",
        "cfg_scale": 7.0,
        "steps": 25,
        "bpm": 120,
        "key": "C",
        "vocal_type": "auto",
        "seed": 42
    }
    """
    import torch
    import torchaudio
    import tempfile
    import uuid
    import base64
    
    # Lazy load pipeline
    pipeline = ACEStepPipeline.get()
    
    # Extract parameters
    prompt = request.get("prompt", "")
    lyrics = request.get("lyrics", "")
    duration = min(request.get("duration", 180), 180)  # Cap at 180s per generation
    style = request.get("style", "pop")
    cfg_scale = request.get("cfg_scale", 7.0)
    steps = request.get("steps", 25)
    bpm = request.get("bpm")
    key = request.get("key")
    vocal_type = request.get("vocal_type", "auto")
    seed = request.get("seed")
    
    if seed is not None:
        torch.manual_seed(seed)
    
    print(f"[Generate] prompt='{prompt[:50]}...' duration={duration}s style={style}")
    
    # Generate audio - pipeline.generate returns a list of output paths (strings)
    result = pipeline.generate(
        prompt=prompt,
        lyrics=lyrics,
        duration=duration,
        style=style,
        cfg_scale=cfg_scale,
        steps=steps,
        bpm=bpm,
        key=key,
        vocal_type=vocal_type,
    )
    
    # Result is a list of output file paths (strings)
    if isinstance(result, list) and len(result) > 0:
        output_path = result[0]
    elif isinstance(result, str):
        output_path = result
    else:
        raise RuntimeError(f"Unexpected result type: {type(result)}")
    
    # Read the generated file as base64
    with open(output_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode()
    
    # Cleanup temp file
    try:
        os.unlink(output_path)
    except:
        pass
    
    return {
        "audio_b64": audio_b64,
        "duration": duration,
        "sample_rate": 44100,
        "channels": 2,
        "format": "wav",
    }

# ============================================================
# Audio2Audio Continuation Endpoint
# ============================================================
@app.function(
    gpu="L40S",
    timeout=300,
    volumes={"/models": model_volume},
    secrets=[hf_secret],
    scaledown_window=300,
    max_containers=4,
)
@modal.fastapi_endpoint(method="POST", docs=True)
async def continue_audio(request: dict):
    """
    Request body:
    {
        "reference_audio_url": "https://.../source.wav",
        "reference_audio_b64": "base64...",  # 或者直接传音频 base64（推荐，无需外部 URL）
        "prompt": "continue with bridge",
        "lyrics": "[Bridge]...",
        "duration": 30,
        "style": "pop",
        "cfg_scale": 7.0,
        "steps": 25,
        "reference_start_sec": 0.0,
        "reference_duration_sec": 30.0,
        "continuation_mode": "extend"  # extend, vary, style_transfer
    }
    """
    import torch
    import torchaudio
    import tempfile
    import uuid
    import base64
    
    pipeline = ACEStepPipeline.get()
    
    # 支持两种参考音频来源：base64 直接传 或 URL 下载
    reference_audio_b64 = request.get("reference_audio_b64")
    reference_audio_url = request.get("reference_audio_url")
    if not reference_audio_b64 and not reference_audio_url:
        return {"error": "reference_audio_b64 or reference_audio_url required"}
    
    if reference_audio_b64:
        audio_data = base64.b64decode(reference_audio_b64)
        ref_path = f"/tmp/ref_{uuid.uuid4().hex}.wav"
        with open(ref_path, "wb") as f:
            f.write(audio_data)
    else:
        ref_path = await download_reference_audio(reference_audio_url)
    
    try:
        prompt = request.get("prompt", "")
        lyrics = request.get("lyrics", "")
        duration = min(request.get("duration", 30), 180)
        style = request.get("style", "pop")
        cfg_scale = request.get("cfg_scale", 7.0)
        steps = request.get("steps", 25)
        reference_start_sec = request.get("reference_start_sec", 0.0)
        reference_duration_sec = request.get("reference_duration_sec")
        continuation_mode = request.get("continuation_mode", "extend")
        
        print(f"[Continue] ref_len={len(base64.b64decode(reference_audio_b64)) if reference_audio_b64 else reference_audio_url} duration={duration}s mode={continuation_mode}")
        
        # continue_audio 返回输出 wav 路径列表（与 generate 相同）
        result = pipeline.continue_audio(
            reference_audio_path=ref_path,
            prompt=prompt,
            lyrics=lyrics,
            duration=duration,
            style=style,
            cfg_scale=cfg_scale,
            steps=steps,
            reference_start_sec=reference_start_sec,
            reference_duration_sec=reference_duration_sec,
            continuation_mode=continuation_mode,
        )
        
        if isinstance(result, list) and len(result) > 0:
            output_path = result[0]
        elif isinstance(result, str):
            output_path = result
        else:
            # 兼容：可能是 tensor
            tmp_path = f"/tmp/continue_{uuid.uuid4().hex}.wav"
            torchaudio.save(tmp_path, result.cpu(), 44100)
            output_path = tmp_path
        
        with open(output_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()
        
        try:
            os.unlink(output_path)
        except:
            pass
        
        return {
            "audio_b64": audio_b64,
            "duration": duration,
            "sample_rate": 44100,
            "channels": 2,
            "format": "wav",
        }
    finally:
        try:
            os.unlink(ref_path)
        except:
            pass

# ============================================================
# Stem Separation Endpoint (placeholder - requires Demucs)
# ============================================================
@app.function(
    gpu="L40S",
    timeout=180,
    volumes={"/models": model_volume},
    secrets=[hf_secret],
    scaledown_window=300,
)
@modal.fastapi_endpoint(method="POST", docs=True)
async def separate(request: dict):
    """
    Stem separation - returns dict with vocals/drums/bass/other URLs
    Note: Requires Demucs installation. Returns placeholder for now.
    """
    return {
        "error": "Stem separation not implemented in minimal deployment. Requires Demucs.",
        "vocals": None,
        "drums": None,
        "bass": None,
        "other": None,
    }

# ============================================================
# Local test entry point
# ============================================================
if __name__ == "__main__":
    import modal
    modal.run(app.generate)