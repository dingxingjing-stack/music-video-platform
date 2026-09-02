"""ACE-Step 独立 Modal App — 一键完整歌曲生成（四轨分离由独立 Spleeter App 承担）。

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
       - 四轨分离（vocals/drums/bass/other）由独立 Spleeter App 执行
       - ffmpeg 转出 song_full.mp3（完整歌 MP3）
       - 全部写入共享 Volume 并 commit，返回文件名映射
  3. separate_audio(filename_in_volume)
       - 分轨失败后的重试入口：对已生成的完整 WAV 调用独立 Spleeter App 四轨分离

成本保护：
  - 按需 GPU：无 keep_warm，max_containers=1，concurrent=1
  - 单函数超时 600s（与业务侧 MAX_TASK_RUNTIME_SECONDS 一致）
  - 模型权重缓存至共享模型卷（/models/ace-step），冷启动后免重复下载

⚠️ 生成逻辑遵循官方 ACE-Step 推理 API（acestep.inference.generate_music），
   不使用裸 AutoProcessor/AutoModel.generate，也不依赖 HF demo 空间。
"""

import os
import threading
from typing import Optional

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
        # 四轨分离由独立 Spleeter App（spleeter_modal.py）承担，本容器不安装 demucs。
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


def _build_generation_params(
    prompt: str,
    lyrics: str,
    duration: int,
    seed: int = -1,
    reference_audio: Optional[str] = None,
    enable_audio2audio: bool = False,
    reference_strength: float = 0.7,
):
    """构造官方 GenerationParams（不含歌词时自动切为纯器乐）。

    新增 Audio2Audio 支持：
    - reference_audio: base64 编码的参考音频或本地路径
    - enable_audio2audio: 是否启用 Audio2Audio 模式
    - reference_strength: 参考音频强度 (0.0-1.0)
    """
    from acestep.inference import GenerationParams

    return GenerationParams(
        caption=prompt or "",
        lyrics=lyrics or "",
        instrumental=not bool((lyrics or "").strip()),
        duration=float(duration),
        seed=int(seed),
        thinking=True,
        reference_audio=reference_audio,
        enable_audio2audio=enable_audio2audio,
        reference_strength=reference_strength,
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
def generate_full_song(
    prompt: str,
    lyrics: str,
    duration: int = 180,
    reference_audio: Optional[str] = None,
    enable_audio2audio: bool = False,
    reference_strength: float = 0.7,
) -> dict:
    """官方 ACE-Step pipeline 生成完整歌曲 + Spleeter 四轨分离 + MP3 转换。

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
    四轨分离由独立 Spleeter App（spleeter_modal.py）执行。

    新增 Audio2Audio 支持：
    - reference_audio: base64 编码的参考音频或本地路径
    - enable_audio2audio: 是否启用 Audio2Audio 模式
    - reference_strength: 参考音频强度 (0.0-1.0)
    """
    import shutil

    import soundfile as sf

    out_dir = _out_dir()
    full_wav = os.path.join(out_dir, "song_full.wav")
    duration = _clamp_duration(duration)

    dit_handler, llm_handler = _get_handlers()
    from acestep.inference import generate_music

    params = _build_generation_params(
        prompt,
        lyrics,
        duration,
        reference_audio=reference_audio,
        enable_audio2audio=enable_audio2audio,
        reference_strength=reference_strength,
    )
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

    # 关键时序：跨容器 Volume 写必须显式 commit 才对他容器可见。
    # 必须先提交 song_full.wav，Spleeter（独立容器）才能读到它做分轨。
    _DATA_VOLUME.commit()

    stems = _separate_via_spleeter(os.path.basename(full_wav))
    mp3 = _to_mp3(full_wav, os.path.join(out_dir, "song_full.mp3"))

    result_map = {
        "full_wav": "song_full.wav",
        "full_mp3": "song_full.mp3" if mp3 else None,
    }
    # Spleeter 只在成功写出并 commit 后才返回对应 stem；本容器快照可能已过期，
    # 不再用 os.path.exists 复检（会因快照滞后而漏报已存在的文件）。
    for name in ("vocals", "drums", "bass", "other"):
        if name in stems:
            result_map[name] = stems[name]

    _DATA_VOLUME.commit()
    print(f"[ACE-Step] generated {result_map} bytes={os.path.getsize(full_wav)}")
    return result_map


def _separate_via_spleeter(filename_in_volume: str) -> dict:
    """调用独立 Spleeter App 执行四轨分离，返回 {stem_name: filename} 映射。

    ACE-Step 容器不安装 Demucs/Spleeter/TensorFlow，分轨统一由独立 Spleeter App
    （spleeter_modal.py::_APP）在共享数据卷上完成，结果写入 /root/data/generated/。

    失败不阻断歌曲生成：返回空 dict（业务层标记 completed_with_stems_failed，
    可稍后经 retry-stems 用 separate_audio 重试）。
    """
    import modal

    try:
        fn = modal.Function.from_name("avireon-music-platform-spleeter", "separate_audio")
        stems = fn.remote(filename_in_volume)
        return stems if isinstance(stems, dict) else {}
    except Exception as exc:  # noqa: BLE001
        print(f"[Spleeter] 分轨失败（不阻断歌曲生成）: {exc}")
        return {}


@_APP.function(
    image=_IMAGE,
    gpu="L40S",
    timeout=60 * 10,
    max_containers=1,
    volumes={"/models": _MODEL_VOLUME, "/root/data": _DATA_VOLUME},
)
@modal.concurrent(max_inputs=1)
def separate_audio(filename_in_volume: str) -> dict:
    """分轨失败重试入口：转发到独立 Spleeter App 执行四轨分离。

    本容器不安装 Demucs/Spleeter/TensorFlow；四轨分离统一由独立 Spleeter App
    （spleeter_modal.py::_APP，avireon-music-platform-spleeter）承担，避免
    TensorFlow 与 PyTorch/CUDA 环境冲突。返回 {stem_name: "stem_name.wav"}。
    """
    import modal

    fn = modal.Function.from_name("avireon-music-platform-spleeter", "separate_audio")
    return fn.remote(filename_in_volume)


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