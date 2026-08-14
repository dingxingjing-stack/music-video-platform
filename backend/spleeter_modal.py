"""独立 Spleeter Modal App — 音频四轨分离（vocals/drums/bass/other）。

与 ACE-Step 生成 App（ace_step_modal.py）完全隔离，独立镜像（Python 3.11 +
Spleeter 2.4.2 + TensorFlow 2.12.1），避免 TensorFlow 与 PyTorch/CUDA 在
同一容器内共存导致的依赖冲突。web 容器不安装 Spleeter/TensorFlow。

职责：
  1. preload_models()
     - 首次把官方 Spleeter 4stems 预训练权重下载进共享模型卷 /models/spleeter/
  2. separate_audio(filename_in_volume)
     - 对共享数据卷 /root/data/generated/ 中的完整 WAV 执行 Spleeter 4stems 分离
     - 输出 vocals.wav / drums.wav / bass.wav / other.wav（与 Demucs 输出协议一致）
     - 写入共享数据卷并 commit，返回 {stem_name: "stem_name.wav"} 文件名映射

License 依据（存档）：
  - 代码：MIT License（https://github.com/deezer/spleeter/blob/master/LICENSE）
  - 预训练权重：MIT。JOSS 论文（doi:10.21105/joss.02154）明确
    "source code and pre-trained models are distributed under an MIT license"；
    Deezer 官方 issue #259 确认 "commercial use is fine"。
  - 固定版本：spleeter==2.4.2（PyPI，2025-04-03），tensorflow==2.12.1
  - Python 约束：spleeter requires_python >=3.8,<3.12，故镜像用 3.11

部署：modal deploy spleeter_modal.py::_APP
调用：web 容器经 modal.Function.from_name("avireon-music-platform-spleeter", "separate_audio")
"""

import os
import shutil

import modal

_APP = modal.App("avireon-music-platform-spleeter")

_DATA_VOLUME = modal.Volume.from_name("avireon-music-platform-data-v1", create_if_missing=True)
_MODEL_VOLUME = modal.Volume.from_name("avireon-music-platform-models-v1", create_if_missing=True)

_GENERATED_DIR = "/root/data/generated"
_MODEL_DIR = "/models/spleeter"
_STEM_NAMES = ["vocals", "drums", "bass", "other"]

_IMAGE = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install(
        "spleeter==2.4.2",
        "tensorflow==2.12.1",
    )
    .env({
        "SPLEETER_MODEL_PATH": _MODEL_DIR,
        "PYTHONIOENCODING": "utf-8",
    })
)


def _out_dir() -> str:
    os.makedirs(_GENERATED_DIR, exist_ok=True)
    return _GENERATED_DIR


def _get_separator():
    """惰性初始化 Spleeter Separator（每容器仅一次），禁用多进程规避容器内不稳定。"""
    from spleeter.separator import Separator

    return Separator("spleeter:4stems", multiprocess=False)


@_APP.function(
    image=_IMAGE,
    timeout=60 * 10,
    volumes={"/models": _MODEL_VOLUME},
)
def preload_models() -> dict:
    """把官方 Spleeter 4stems 预训练权重下载进共享模型卷（只跑一次）。"""
    sep = _get_separator()
    _MODEL_VOLUME.commit()
    print(f"[Spleeter] preload done: {_MODEL_DIR}")
    return {"model_path": _MODEL_DIR, "model_id": sep._model_id}


@_APP.function(
    image=_IMAGE,
    timeout=60 * 10,
    max_containers=1,
    volumes={"/models": _MODEL_VOLUME, "/root/data": _DATA_VOLUME},
)
@modal.concurrent(max_inputs=1)
def separate_audio(filename_in_volume: str) -> dict:
    """对共享卷中已有的完整 WAV 执行 Spleeter 4stems 四轨分离。

    返回 {stem_name: f"{stem_name}.wav"} 文件名映射（全部位于共享数据卷）。
    分离失败抛异常，由调用方决定重试/降级。
    """
    out_dir = _out_dir()
    src = os.path.join(out_dir, os.path.basename(filename_in_volume))
    if not os.path.exists(src):
        raise FileNotFoundError(f"volume 中不存在 {filename_in_volume}")

    track_dir = os.path.join(out_dir, "spleeter_out")
    if os.path.exists(track_dir):
        shutil.rmtree(track_dir)
    os.makedirs(track_dir, exist_ok=True)

    sep = _get_separator()
    # Spleeter 4stems 输出目录结构为 <out>/<track>/<stem>.wav
    sep.separate_to_file(src, track_dir)
    for name in _STEM_NAMES:
        src_stem = os.path.join(track_dir, os.path.splitext(os.path.basename(src))[0], f"{name}.wav")
        dst_stem = os.path.join(out_dir, f"{name}.wav")
        if os.path.exists(src_stem):
            if os.path.exists(dst_stem):
                os.remove(dst_stem)
            shutil.move(src_stem, dst_stem)
    shutil.rmtree(track_dir, ignore_errors=True)

    result = {}
    for name in _STEM_NAMES:
        if os.path.exists(os.path.join(out_dir, f"{name}.wav")):
            result[name] = f"{name}.wav"

    _DATA_VOLUME.commit()
    print(f"[Spleeter] separated {result}")
    return result