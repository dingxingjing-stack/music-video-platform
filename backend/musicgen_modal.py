"""MusicGen 独立 Modal App — 与 web App 分离，GPU 容器不加载 main.py 的 web 依赖。

部署：modal deploy musicgen_modal.py::_APP
web 容器通过 modal.Function.from_name("avireon-music-platform-musicgen", "musicgen_generate")
调用，结果写入共享数据卷 /root/data/generated/，web 经 /generated 下载。
"""

import modal

_APP = modal.App("avireon-music-platform-musicgen")

_DATA_VOLUME = modal.Volume.from_name("avireon-music-platform-data-v1", create_if_missing=True)
_MODEL_VOLUME = modal.Volume.from_name("avireon-music-platform-models-v1", create_if_missing=True)

_IMAGE = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    .pip_install(
        "torch>=2.3",
        "transformers>=4.44",
        "accelerate>=0.33",
        "soundfile",
        "numpy",
    )
    .env({
        "HF_HOME": "/models/hf",
        "PYTHONIOENCODING": "utf-8",
    })
)


@_APP.function(
    image=_IMAGE,
    gpu="T4",
    timeout=60 * 20,
    max_containers=1,
    volumes={"/models": _MODEL_VOLUME, "/root/data": _DATA_VOLUME},
    env={"GENERATED_DIR": "/root/data/generated"},
)
@modal.concurrent(max_inputs=1)
def musicgen_generate(prompt: str, duration: int = 30) -> str:
    """MusicGen-small 本地生成音乐，写入共享卷，返回相对文件名。"""
    import os
    import uuid
    import torch
    from transformers import AutoProcessor, MusicgenForConditionalGeneration

    os.makedirs("/models/hf", exist_ok=True)
    out_dir = os.getenv("GENERATED_DIR", "/root/data/generated")
    os.makedirs(out_dir, exist_ok=True)

    processor = AutoProcessor.from_pretrained("facebook/musicgen-small")
    model = MusicgenForConditionalGeneration.from_pretrained("facebook/musicgen-small")
    model.to("cuda")
    inputs = processor(text=[prompt], padding=True, return_tensors="pt").to("cuda")
    # MusicGen 32kHz，50 tokens ≈ 1 秒
    max_new_tokens = max(256, int(duration) * 50)
    with torch.no_grad():
        audio = model.generate(**inputs, max_new_tokens=int(max_new_tokens))
    samples = audio[0].cpu().numpy()

    import soundfile as sf
    fname = f"musicgen-{uuid.uuid4().hex[:12]}.wav"
    fpath = os.path.join(out_dir, fname)
    sf.write(fpath, samples[0], samplerate=32000)
    print(f"[MusicGen] wrote {fpath} bytes={os.path.getsize(fpath)}")
    # Modal Volume 写入是最终一致，必须 commit 才能让其他容器立即可见
    _DATA_VOLUME.commit()
    return fname
