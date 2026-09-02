"""
HF Space ZeroGPU - MusicGen-Small MVP

- Model: facebook/musicgen-small (300M, MIT) via transformers
- Runtime: Gradio 4 + ZeroGPU (large 48GB, RTX Pro 6000 Blackwell)
- Pattern: model.to('cuda') at module level (emulated), @spaces.GPU for inference
- CosyVoice2: BLOCKED stub this phase (do not install cosyvoice)
"""

import spaces
import gradio as gr
import torch
import soundfile as sf
import tempfile
from pathlib import Path

from transformers import AutoProcessor, MusicgenForConditionalGeneration

MODEL_ID = "facebook/musicgen-small"

# 顶层加载（ZeroGPU 仿真 CUDA，不占实时 GPU；@spaces.GPU 内为真 CUDA）
# 避免重复下载：from_pretrained 走 HF Hub 缓存（~/.cache/huggingface）
processor = AutoProcessor.from_pretrained(MODEL_ID)
model = MusicgenForConditionalGeneration.from_pretrained(MODEL_ID)
model.to("cuda")
model.eval()


@spaces.GPU(duration=60)
def generate(prompt: str, duration: float = 10.0, temperature: float = 1.0, top_k: int = 250):
    """MusicGen 推理，duration 1-30s，返回 wav 路径供 Gradio Audio 展示"""
    if not prompt or not prompt.strip():
        raise gr.Error("prompt 不能为空")
    duration = max(1.0, min(float(duration), 30.0))
    # 50 token/秒 估算
    max_new_tokens = int(duration * 50)
    inputs = processor(text=[prompt.strip()], padding=True, return_tensors="pt")
    inputs = {k: v.to("cuda") for k, v in inputs.items()}
    with torch.no_grad():
        audio_values = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=float(temperature),
            top_k=int(top_k),
            guidance_scale=3.0,
            do_sample=True,
        )
    # 采样率
    sample_rate = getattr(processor, "sampling_rate", 32000)
    if hasattr(processor, "feature_extractor") and hasattr(processor.feature_extractor, "sampling_rate"):
        sample_rate = processor.feature_extractor.sampling_rate
    wav = audio_values[0].cpu().float().numpy()
    if wav.ndim == 2:
        wav = wav.T
    out = Path(tempfile.gettempdir()) / f"musicgen_{int(torch.cuda.Event().elapsed_time(torch.cuda.Event()) if False else 0)}.wav"
    # 用临时文件避免并发覆盖
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    sf.write(tmp.name, wav, sample_rate)
    return tmp.name


def health():
    return {"status": "ok", "model": MODEL_ID, "cuda": torch.cuda.is_available()}


# Gradio UI
with gr.Blocks(title="MVP MusicGen-Small ZeroGPU") as demo:
    gr.Markdown("# 🎵 MVP MusicGen-Small (ZeroGPU)\n`facebook/musicgen-small` via transformers — CosyVoice2 本阶段 BLOCKED")
    with gr.Row():
        prompt = gr.Textbox(label="Prompt", placeholder="upbeat pop piano, cheerful", lines=2)
        duration = gr.Slider(1, 30, value=10, step=1, label="Duration (s)")
    temp = gr.Slider(0.5, 1.5, value=1.0, step=0.1, label="Temperature")
    topk = gr.Slider(10, 500, value=250, step=10, label="top_k")
    btn = gr.Button("Generate", variant="primary")
    out_audio = gr.Audio(label="Output", type="filepath")
    btn.click(fn=generate, inputs=[prompt, duration, temp, topk], outputs=out_audio)
    gr.Examples(examples=[["upbeat pop piano, cheerful", 10, 1.0, 250]], inputs=[prompt, duration, temp, topk], outputs=out_audio, fn=generate, cache_examples=False)

if __name__ == "__main__":
    demo.launch()
