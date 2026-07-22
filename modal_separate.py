"""Modal 免费算力 - Demucs 原生 4 轨音频分离 Worker

说明：
- 部署到 Modal 免费的 CPU 算力（每月 $30 额度，2 GB 内存）。
- 接口端点：
    GET  /health      → 健康检查
    POST /separate    → 接收 multipart 音频文件，返回 4 轨 base64

部署：
    1. 注册 https://modal.com（无需绑卡）
    2. pip install modal && modal setup
    3. modal secret create audio-key HF_WORKER_API_KEY=<你的强密钥>
    4. modal deploy modal_separate.py
    5. 记录部署输出的 URL，例如 https://<user>--audio-separation-worker-app.modal.run
"""
import os
import io
import gc
import base64
import tempfile
from pathlib import Path

import modal

image = (
    modal.Image.debian_slim()
    .apt_install(["ffmpeg", "libsndfile1"])
    .pip_install(
        "fastapi==0.115.0",
        "uvicorn==0.30.6",
        "python-multipart==0.0.20",
        "demucs>=4.0.0",
        "torch>=2.0.0,<3.0",
        "soundfile>=0.12.1",
        "torchaudio>=2.0.0",
    )
)

stub = modal.Stub("audio-separation-worker", image=image)

# 全局模型状态（容器内常驻）
MODEL_STATE = {"loaded": False, "model": None}


def load_model_once():
    """首次请求懒加载 demucs 模型，后续请求复用内存中已加载实例"""
    if MODEL_STATE["loaded"]:
        return MODEL_STATE["model"]
    import demucs
    print("[Modal-Worker] 加载 Demucs htdemucs 模型...")
    state = demucs.pretrained.get_model("htdemucs")
    state.eval()
    MODEL_STATE["model"] = state
    MODEL_STATE["loaded"] = True
    print("[Modal-Worker] ✅ 模型就绪")
    return state


@stub.function(
    timeout=300,
    memory=2048,
    cpu=2,
    secrets=[modal.Secret.from_name("audio-key")],
)
@modal.asgi()
def app():
    from fastapi import FastAPI, File, UploadFile, Header, HTTPException
    from fastapi.responses import JSONResponse
    import torch
    import soundfile as sf
    from torchaudio import load as ta_load
    from torchaudio.transforms import Resample
    from demucs.apply import apply_model

    api_key_env = os.getenv("HF_WORKER_API_KEY", "")
    STEM_NAMES = ["vocals", "drums", "bass", "other"]

    fastapi_app = FastAPI(title="Demucs Worker")

    @fastapi_app.get("/health")
    def health():
        return {"status": "ok"}

    @fastapi_app.post("/separate")
    async def separate(
        file: UploadFile = File(...),
        x_api_key: str | None = Header(None, alias="X-API-Key"),
    ):
        # === 1. 鉴权 ===
        if not api_key_env or x_api_key != api_key_env:
            raise HTTPException(status_code=401, detail="Invalid API key")

        # === 2. 加载模型（懒加载） ===
        model = load_model_once()

        # === 3. 写入临时文件 ===
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            inp = td_path / (file.filename or "audio.wav")
            content = await file.read()
            inp.write_bytes(content)

            # === 4. 读取 + 重采样到 44.1kHz ===
            waveform, sr = ta_load(str(inp))
            if waveform.shape[0] == 1:
                waveform = waveform.repeat(2, 1)
            elif waveform.shape[0] > 2:
                waveform = waveform[:2, :]
            if sr != 44100:
                waveform = Resample(sr, 44100)(waveform)
            waveform = waveform.unsqueeze(0)  # (1, 2, samples)

            # === 5. Demucs 推理 ===
            with torch.no_grad():
                sources = apply_model(
                    model, waveform, segment=4, shifts=1, overlap=0.25, split=True
                )
            sources = sources.squeeze(0)  # (4, 2, samples)
            duration = float(waveform.shape[-1] / 44100.0)

            # === 6. 保存为 WAV bytes ===
            stems_bytes = {}
            for i, name in enumerate(STEM_NAMES):
                wav_path = td_path / f"{name}.wav"
                sf.write(
                    str(wav_path),
                    sources[i].mean(dim=0).numpy(),
                    44100,
                    subtype="PCM_16",
                )
                stems_bytes[name] = wav_path.read_bytes()

            # === 7. 返回 JSON（4 轨 base64） ===
            payload = {
                "success": True,
                "duration": duration,
                "stems": {k: base64.b64encode(v).decode("utf-8") for k, v in stems_bytes.items()},
                "message": "Separation succeeded",
            }
            gc.collect()
            return JSONResponse(payload)

    return fastapi_app
