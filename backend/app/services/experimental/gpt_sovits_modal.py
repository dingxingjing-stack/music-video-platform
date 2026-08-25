"""独立 GPT-SoVITS Modal App — 声音克隆 TTS（零样本 / 少样本）。

与 ACE-Step / Spleeter App 隔离，独占 GPU 镜像（Python 3.11 + PyTorch CUDA）。
web 容器不安装 torch/GPT-SoVITS，仅经 modal.Function.from_name() 调用。

职责：
  1. preload_models()
     - 首次把官方预训练权重（lj1995/GPT-SoVITS，HF `License: mit`）下载进
       共享模型卷 /models/gptsovits/（含 GPT/SoVITS/cnhubert/bert 等，布局与
       HF 仓库一致），只跑一次并 commit。
  2. synthesize_cloned(ref_filename_in_volume, text, language, ...)
     - 以官方 api.py（FastAPI 本地回环 :9880）作为推理后端 —— 直接复用官方
       get_tts_wav() 推理核心，不重写任何模型代码。
     - 参考音频位于共享数据卷 /root/data/refs/，输出写入共享数据卷
       /root/data/generated/ 并 commit，返回 {wav: "xxx.wav"} 文件名映射。

Kaggle 适配：
  - 本文件为 Modal 专用，Kaggle 不下载 GPT-SoVITS 权重（2.5GB），保持远程调用。
  - Kaggle 环境下本模块仅作为文档存档，不在 Kaggle 容器内 import/deploy。
  - 如 Kaggle 误 import，preload_models 已加 Kaggle 环境 guard，禁止写入 /kaggle/working。

推理协议（对齐官方 api.py，2026-07-22 commit d523079）：
  POST http://127.0.0.1:9880/
    {"refer_wav_path", "prompt_text", "prompt_language",
     "text", "text_language", "top_k", "top_p", "temperature", "speed"}
  成功返回 200 + wav 音频流；失败返回 400 + JSON 错误。

License 依据（存档）：
  - 代码：RVC-Boss/GPT-SoVITS MIT License
  - 预训练权重：lj1995/GPT-SoVITS Hugging Face 模型卡显式 `License: mit`
  - 锁定：官方 repo commit d523079fc05d9a8028d6085bffe4a2757c32abb6（main 2026-07-22）

部署：modal deploy gpt_sovits_modal.py::_APP
调用：web 容器经 modal.Function.from_name("avireon-music-platform-gptsovits", "synthesize_cloned")
"""

import os
import subprocess
import time
import uuid

import modal

_APP = modal.App("avireon-music-platform-gptsovits")

_DATA_VOLUME = modal.Volume.from_name("avireon-music-platform-data-v1", create_if_missing=True)
_MODEL_VOLUME = modal.Volume.from_name("avireon-music-platform-models-v1", create_if_missing=True)

_REF_DIR = "/root/data/refs"
_OUT_DIR = "/root/data/generated"
_MODEL_DIR = "/models/gptsovits"

_REPO_URL = "https://github.com/RVC-Boss/GPT-SoVITS"
_REPO_COMMIT = "d523079fc05d9a8028d6085bffe4a2757c32abb6"
_WEIGHTS_REPO = "lj1995/GPT-SoVITS"

_API_PORT = 9880
_API_HEALTH_WAIT = 300  # force rebuild

_IMAGE = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1", "git")
    .run_commands(
        # 锁定官方 GPT-SoVITS 提交（可复现，不追踪 main 漂移）
        f"git init /gpt-sovits && git -C /gpt-sovits remote add origin {_REPO_URL}",
        f"git -C /gpt-sovits fetch --depth 1 origin {_REPO_COMMIT}",
        "git -C /gpt-sovits checkout FETCH_HEAD",
    )
    .run_commands(
        # 官方推理依赖（api.py / GPT_SoVITS 所需）
        "pip install --no-cache-dir -r /gpt-sovits/requirements.txt",
        "pip install --no-cache-dir huggingface_hub",
    )
    .env({"PYTHONIOENCODING": "utf-8"})
)


def _out_dir() -> str:
    os.makedirs(_OUT_DIR, exist_ok=True)
    return _OUT_DIR


def _ref_dir() -> str:
    os.makedirs(_REF_DIR, exist_ok=True)
    return _REF_DIR


@_APP.function(
    image=_IMAGE,
    timeout=60 * 5,
    gpu="T4",
    max_containers=1,
    min_containers=1,
    volumes={"/models": _MODEL_VOLUME, "/root/data": _DATA_VOLUME},
)
def upload_ref_audio(audio_bytes: bytes, voice_id: str) -> str:
    """在容器内直接写参考音频到共享卷 /root/data/refs/{voice_id}.wav，返回文件名。"""
    import os
    fname = f"{voice_id}.wav"
    path = os.path.join(_ref_dir(), fname)
    with open(path, "wb") as f:
        f.write(audio_bytes)
    _DATA_VOLUME.commit()
    print(f"[GPT-SoVITS] uploaded reference audio: {fname}")
    return fname


def _server_env() -> dict:
    """构造官方 api.py 子进程所需环境变量（覆盖默认权重路径）。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["CUDA_VISIBLE_DEVICES"] = "0"
    return env


_api_proc: "subprocess.Popen | None" = None


def _ensure_api_server(ref_path: str, prompt_text: str, prompt_language: str) -> None:
    """以官方 api.py 原样启动本地回环推理服务（每容器单实例，常驻复用）。

    同一容器内只启动一次：warm 容器再次调用直接复用既有子进程，避免端口冲突
    与重复加载模型。启动失败或进程退出则抛异常，由调用方决定重试/降级。
    """
    import httpx

    global _api_proc
    if _api_proc is not None and _api_proc.poll() is None:
        return

    _api_proc = subprocess.Popen(
        [
            "python", "api.py",
            "-s", f"{_MODEL_DIR}/gsv-v4-pretrained/s2v4.pth",
            "-g", f"{_MODEL_DIR}/s1v3.ckpt",
            "-hb", f"{_MODEL_DIR}/chinese-hubert-base",
            "-b", f"{_MODEL_DIR}/chinese-roberta-wwm-ext-large",
            "-d", "cuda",
            "-p", str(_API_PORT),
            "-dr", ref_path,
            "-dt", prompt_text,
            "-dl", prompt_language,
            "-mt", "wav",
            "-st", "int16",
        ],
        cwd="/gpt-sovits",
        env=_server_env(),
    )
    base = f"http://127.0.0.1:{_API_PORT}"
    deadline = time.time() + _API_HEALTH_WAIT
    while time.time() < deadline:
        if _api_proc.poll() is not None:
            raise RuntimeError(f"GPT-SoVITS api.py 启动失败（exit={_api_proc.returncode}）")
        try:
            # 官方 api.py: GET /control?command=restart 返回 200，同时初始化说话人列表
            resp = httpx.get(f"{base}/control", params={"command": "restart"}, timeout=5.0)
            if resp.status_code == 200:
                print(f"[GPT-SoVITS] api.py health check OK")
                return
        except httpx.TransportError:
            pass
        except httpx.HTTPStatusError:
            pass
        time.sleep(2)
    raise RuntimeError(f"GPT-SoVITS api.py 健康检查超时（{_API_HEALTH_WAIT}s）")


def _register_speaker(ref_path: str, prompt_text: str, prompt_language: str, spk: str) -> None:
    """调用 /set_ref_audio 注册说话人（零样本克隆必需）。"""
    import httpx
    base = f"http://127.0.0.1:{_API_PORT}"
    payload = {
        "refer_wav_path": ref_path,
        "prompt_text": prompt_text,
        "prompt_language": prompt_language,
        "spk": spk,
    }
    resp = httpx.post(f"{base}/set_ref_audio", json=payload, timeout=30.0)
    if resp.status_code != 200:
        raise RuntimeError(f"注册说话人失败（HTTP {resp.status_code}）: {resp.text[:300]}")
    print(f"[GPT-SoVITS] registered speaker: {spk}")


@_APP.function(
    image=_IMAGE,
    timeout=60 * 15,
    gpu="T4",
    volumes={"/models": _MODEL_VOLUME, "/root/data": _DATA_VOLUME},
)
def preload_models() -> dict:
    """把官方预训练权重（lj1995/GPT-SoVITS）下载进共享模型卷（只跑一次）。

    Kaggle guard：若误在 Kaggle 环境调用，禁止下载到 /kaggle/working。
    """
    import pathlib

    if pathlib.Path("/kaggle/input").exists() or pathlib.Path("/kaggle/working").exists():
        raise RuntimeError(
            "preload_models is Modal-only — Kaggle must NOT download GPT-SoVITS 2.5GB to /kaggle/working. "
            "Kaggle keeps GPT-SoVITS as Modal remote call."
        )
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=_WEIGHTS_REPO,
        local_dir=_MODEL_DIR,
        local_dir_use_symlinks=False,
    )
    _MODEL_VOLUME.commit()
    print(f"[GPT-SoVITS] preload done: {_MODEL_DIR}")
    return {"model_path": _MODEL_DIR, "weights_repo": _WEIGHTS_REPO}


@_APP.function(
    image=_IMAGE,
    timeout=60 * 45,
    gpu="T4",
    max_containers=1,
    min_containers=1,
    volumes={"/models": _MODEL_VOLUME, "/root/data": _DATA_VOLUME},
)
@modal.concurrent(max_inputs=1)
def synthesize_cloned(
    audio_bytes: bytes,
    voice_id: str,
    text: str,
    language: str,
    prompt_text: str = "",
    prompt_language: str = "",
    speed: float = 1.0,
    out_stem: str = "",
) -> dict:
    """接收音频字节，写入共享卷并执行 GPT-SoVITS 克隆合成（同一容器内完成，避免卷同步延迟）。

    返回 {wav: "xxx.wav"} 文件名映射（位于共享数据卷 generated 目录）。
    失败抛异常，由调用方决定重试/降级。
    """
    import httpx
    import os

    # 写参考音频到共享卷
    fname = f"{voice_id}.wav"
    ref_path = os.path.join(_ref_dir(), fname)
    with open(ref_path, "wb") as f:
        f.write(audio_bytes)
    _DATA_VOLUME.commit()
    print(f"[GPT-SoVITS] uploaded reference audio: {fname}")

    # 参考音频文本（prompt_text）为 GPT-SoVITS 推理必需：由调用方提供
    _ensure_api_server(ref_path, prompt_text or "", prompt_language or "")

    payload = {
        "refer_wav_path": ref_path,
        "prompt_text": prompt_text,
        "prompt_language": prompt_language,
        "text": text,
        "text_language": language,
        "top_k": 15,
        "top_p": 0.6,
        "temperature": 0.6,
        "speed": speed,
        "spk": voice_id,  # 指定说话人，避免默认 'default' 不存在
    }

    base = f"http://127.0.0.1:{_API_PORT}"
    resp = httpx.post(f"{base}/", json=payload, timeout=600.0)
    if resp.status_code != 200:
        raise RuntimeError(f"GPT-SoVITS 合成失败（HTTP {resp.status_code}）: {resp.text[:300]}")

    stem = out_stem or f"clone_{uuid.uuid4().hex[:8]}"
    out_name = f"{stem}.wav"
    with open(os.path.join(_out_dir(), out_name), "wb") as f:
        f.write(resp.content)

    _DATA_VOLUME.commit()
    print(f"[GPT-SoVITS] synthesized {out_name} ({len(resp.content)} bytes)")
    return {"wav": out_name}