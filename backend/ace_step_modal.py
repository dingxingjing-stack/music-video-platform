"""ACE-Step + Demucs 独立 Modal App — 一键完整歌曲生成 + 自动四轨分轨。

与 web App（main.py）分离，GPU 容器不加载 web 依赖。部署：
    modal deploy ace_step_modal.py::_APP
web 容器通过 modal.Function.from_name("avireon-music-platform-acestep", ...)
调用，结果写入共享数据卷 /root/data/generated/，web 经文件下载 API 取回并上传 R2。

职责：
  1. preload_models()
       - 首次把 ACE-Step 权重下载进共享模型卷 /models/ace-step/
       - DiT（acestep-v15-turbo）+ VAE + Qwen3-Embedding-0.6B + 5Hz-LM-4B
  2. generate_full_song(prompt, lyrics, duration)
       - 官方 acestep 包 pipeline（AceStepHandler + LLMHandler + generate_music）
       - 整曲生成（acestep-v15-turbo + acestep-5Hz-lm-4B，LM backend=pt）
       - Demucs htdemucs GPU 四轨分离（vocals/drums/bass/other）
       - ffmpeg 转出 song_full.mp3（完整歌 MP3）
       - 全部写入共享 Volume 并 commit，返回文件名映射
  3. separate_audio(filename_in_volume)
       - 分轨失败后的重试入口：对已生成的完整 WAV 单独跑 Demucs

成本保护：
  - 按需 GPU：无 keep_warm，max_containers=1，concurrent=1
  - 单函数超时 600s（与业务侧 MAX_TASK_RUNTIME_SECONDS 一致）
  - 模型权重缓存至共享模型卷（/models/ace-step），冷启动后免重复下载

⚠️ 生成逻辑遵循官方 ACE-Step 推理 API（acestep.inference.generate_music），
   不使用裸 AutoProcessor/AutoModel.generate，也不依赖 HF demo 空间。
"""

import os
import threading

import modal

_APP = modal.App("avireon-music-platform-acestep")

_DATA_VOLUME = modal.Volume.from_name("avireon-music-platform-data-v1", create_if_missing=True)
_MODEL_VOLUME = modal.Volume.from_name("avireon-music-platform-models-v1", create_if_missing=True)

_ACE_STEP_REPO = "https://github.com/ace-step/ACE-Step-1.5.git"
_ACE_STEP_SRC = "/opt/ace-step"
_ACE_STEP_CONFIG = "acestep-v15-turbo"          # 官方合并仓内的 DiT 配置子目录
_ACE_STEP_LM = os.getenv("ACESTEP_LM_MODEL_PATH", "acestep-5Hz-lm-4B")
_ACE_STEP_LM_BACKEND = os.getenv("ACESTEP_LM_BACKEND", "pt")  # "vllm"（nano-vllm）或 "pt"
_CHECKPOINTS_DIR = "/models/ace-step"
_GENERATED_DIR = "/root/data/generated"

_IMAGE = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg", "git")
    .run_commands(
        f"git clone --depth 1 {_ACE_STEP_REPO} {_ACE_STEP_SRC}",
        "pip install --no-cache-dir uv",
        f"cd {_ACE_STEP_SRC} && uv pip install --system --no-cache /opt/ace-step",
        "pip install --no-cache-dir 'demucs>=4.0.0'",
    )
    .env({
        "ACESTEP_CHECKPOINTS_DIR": _CHECKPOINTS_DIR,
        "ACESTEP_INIT_LLM": "true",
        "HF_HOME": "/models/hf",
        "PYTHONIOENCODING": "utf-8",
        "TOKENIZERS_PARALLELISM": "false",
    })
)

_handlers_lock = threading.Lock()
_handlers: tuple | None = None


def _out_dir() -> str:
    os.makedirs(_GENERATED_DIR, exist_ok=True)
    return _GENERATED_DIR


def _clamp_duration(duration: int | None) -> int:
    """业务侧上限 MAX_AUDIO_DURATION_SECONDS=180，此处仅做防御性钳制（官方支持 10~600）。"""
    if not duration or int(duration) <= 0:
        return 180
    return max(10, min(int(duration), 600))


def _build_generation_params(prompt: str, lyrics: str, duration: int, seed: int = -1):
    """构造官方 GenerationParams（不含歌词时自动切为纯器乐）。"""
    from acestep.inference import GenerationParams

    return GenerationParams(
        caption=prompt or "",
        lyrics=lyrics or "",
        instrumental=not bool((lyrics or "").strip()),
        duration=float(duration),
        seed=int(seed),
        thinking=True,
    )


def _build_generation_config():
    from acestep.inference import GenerationConfig

    return GenerationConfig(batch_size=1, audio_format="wav", use_random_seed=True)


def _get_handlers():
    """惰性初始化 DiT 与 5Hz-LM（每容器仅一次），线程安全。"""
    global _handlers
    if _handlers is None:
        with _handlers_lock:
            if _handlers is None:
                from acestep.handler import AceStepHandler
                from acestep.llm_inference import LLMHandler

                dit_handler = AceStepHandler()
                status, ok = dit_handler.initialize_service(
                    project_root=_ACE_STEP_SRC,
                    config_path=_ACE_STEP_CONFIG,
                    device="cuda",
                )
                if not ok:
                    raise RuntimeError(f"ACE-Step DiT 初始化失败: {status}")

                llm_handler = LLMHandler()
                status, ok = llm_handler.initialize(
                    checkpoint_dir=_CHECKPOINTS_DIR,
                    lm_model_path=_ACE_STEP_LM,
                    backend=_ACE_STEP_LM_BACKEND,
                    device="cuda",
                )
                if not ok:
                    raise RuntimeError(f"ACE-Step LM 初始化失败: {status}")

                _handlers = (dit_handler, llm_handler)
    return _handlers


@_APP.function(
    image=_IMAGE,
    timeout=60 * 60,
    volumes={"/models": _MODEL_VOLUME},
)
def preload_models() -> dict:
    """把 ACE-Step 权重下载进共享模型卷（只跑一次，B1 冒烟前执行）。"""
    from acestep.model_downloader import ensure_lm_model, ensure_main_model

    ok, msg = ensure_main_model(_CHECKPOINTS_DIR, prefer_source="huggingface")
    if not ok:
        raise RuntimeError(f"主模型下载失败: {msg}")
    ok, msg = ensure_lm_model(_ACE_STEP_LM, _CHECKPOINTS_DIR, prefer_source="huggingface")
    if not ok:
        raise RuntimeError(f"LM 模型下载失败: {msg}")

    _MODEL_VOLUME.commit()
    print(f"[ACE-Step] preload done: {_CHECKPOINTS_DIR}")
    return {"checkpoints": _CHECKPOINTS_DIR}


@_APP.function(
    image=_IMAGE,
    gpu="L40S",
    timeout=60 * 10,
    max_containers=1,
    volumes={"/models": _MODEL_VOLUME, "/root/data": _DATA_VOLUME},
)
@modal.concurrent(max_inputs=1)
def generate_full_song(prompt: str, lyrics: str, duration: int = 180) -> dict:
    """官方 ACE-Step pipeline 生成完整歌曲 + Demucs 四轨分离 + MP3 转换。

    返回文件名映射（全部位于共享 Volume /root/data/generated/）：
        {
          "full_mp3": "song_full.mp3",
          "full_wav": "song_full.wav",
          "vocals": "vocals.wav",
          "drums": "drums.wav",
          "bass": "bass.wav",
          "other": "other.wav",
        }
    分轨失败时仅返回 full_wav/full_mp3（stems 缺失），由业务层标记
    completed_with_stems_failed，并可用 separate_audio 重试。
    """
    import shutil

    import soundfile as sf

    out_dir = _out_dir()
    full_wav = os.path.join(out_dir, "song_full.wav")
    duration = _clamp_duration(duration)

    dit_handler, llm_handler = _get_handlers()
    from acestep.inference import generate_music

    params = _build_generation_params(prompt, lyrics, duration)
    config = _build_generation_config()
    result = generate_music(dit_handler, llm_handler, params, config, save_dir=out_dir)

    if not result or not getattr(result, "success", False) or not getattr(result, "audios", []):
        raise RuntimeError(getattr(result, "error", None) or "ACE-Step 未生成音频")

    audio = result.audios[0]
    src = audio.get("path") or ""
    if not src or not os.path.exists(src):
        tensor = audio.get("tensor")
        if tensor is None:
            raise RuntimeError("ACE-Step 未返回音频文件")
        arr = tensor.detach().float().cpu().numpy()
        sf.write(
            full_wav,
            arr.T if arr.ndim == 2 else arr,
            samplerate=int(audio.get("sample_rate") or 44100),
        )
    else:
        shutil.move(src, full_wav)

    stems = _separate_to_dir(full_wav, out_dir)
    mp3 = _to_mp3(full_wav, os.path.join(out_dir, "song_full.mp3"))

    result_map = {
        "full_wav": "song_full.wav",
        "full_mp3": "song_full.mp3" if mp3 else None,
    }
    for name in ("vocals", "drums", "bass", "other"):
        if name in stems and os.path.exists(stems[name]):
            result_map[name] = f"{name}.wav"

    _DATA_VOLUME.commit()
    print(f"[ACE-Step] generated {result_map} bytes={os.path.getsize(full_wav)}")
    return result_map


@_APP.function(
    image=_IMAGE,
    gpu="L40S",
    timeout=60 * 10,
    max_containers=1,
    volumes={"/models": _MODEL_VOLUME, "/root/data": _DATA_VOLUME},
)
@modal.concurrent(max_inputs=1)
def separate_audio(filename_in_volume: str) -> dict:
    """对共享卷中已有的完整 WAV 执行 Demucs 四轨分离（分轨失败重试入口）。"""
    out_dir = _out_dir()
    src = os.path.join(out_dir, os.path.basename(filename_in_volume))
    if not os.path.exists(src):
        raise FileNotFoundError(f"volume 中不存在 {filename_in_volume}")
    stems = _separate_to_dir(src, out_dir)
    result = {}
    for name in ("vocals", "drums", "bass", "other"):
        if name in stems and os.path.exists(stems[name]):
            result[name] = f"{name}.wav"
    _DATA_VOLUME.commit()
    print(f"[Demucs] separated {result}")
    return result


def _separate_to_dir(wav_path: str, out_dir: str) -> dict:
    """GPU 运行 Demucs htdemucs，返回 {stem_name: output_path}。"""
    from demucs.api import Separator

    separator = Separator(model="htdemucs", device="cuda", segment=7.8)
    _wav, sources = separator.separate_audio_file(wav_path)
    # sources: {stem_name: (channels, samples) tensor}，htdemucs 顺序为
    # drums/bass/other/vocals，此处按逻辑名取
    names = ["vocals", "drums", "bass", "other"]
    paths: dict[str, str] = {}
    for name in names:
        tensor = sources.get(name)
        if tensor is None:
            continue
        path = os.path.join(out_dir, f"{name}.wav")
        _save_tensor(tensor, path)
        paths[name] = path
    return paths


def _save_tensor(tensor, path: str) -> None:
    import torch

    arr = tensor.detach().float().cpu()
    if arr.ndim == 2:
        arr = arr.numpy().T  # (channels, samples) -> (samples, channels)
    else:
        arr = arr.numpy()
    import soundfile as sf

    sf.write(path, arr, samplerate=44100)


def _to_mp3(wav_path: str, mp3_path: str):
    import subprocess

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-qscale:a", "2", mp3_path],
            check=True,
            capture_output=True,
        )
        return mp3_path if os.path.exists(mp3_path) else None
    except Exception as exc:  # noqa: BLE001
        print(f"[ffmpeg] mp3 转换失败（不阻断主流程）: {exc}")
        return None