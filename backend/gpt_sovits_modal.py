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
_API_HEALTH_WAIT = 180

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
            resp = httpx.get(f"{base}/control", params={"command": "restart"}, timeout=2.0)
            if resp.status_code == 200:
                return
        except httpx.TransportError:
            time.sleep(2)
    raise RuntimeError(f"GPT-SoVITS api.py 健康检查超时（{_API_HEALTH_WAIT}s）")


@_APP.function(
    image=_IMAGE,
    timeout=60 * 15,
    gpu="T4",
    volumes={"/models": _MODEL_VOLUME, "/root/data": _DATA_VOLUME},
)
def preload_models() -> dict:
    """把官方预训练权重（lj1995/GPT-SoVITS）下载进共享模型卷（只跑一次）。"""
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
    timeout=60 * 15,
    gpu="T4",
    max_containers=1,
    volumes={"/models": _MODEL_VOLUME, "/root/data": _DATA_VOLUME},
)
@modal.concurrent(max_inputs=1)
def synthesize_cloned(
    ref_filename_in_volume: str,
    text: str,
    language: str,
    prompt_text: str = "",
    prompt_language: str = "",
    speed: float = 1.0,
    out_stem: str = "",
) -> dict:
    """对共享卷中已有的参考音频执行 GPT-SoVITS 克隆合成。

    返回 {wav: "xxx.wav"} 文件名映射（位于共享数据卷 generated 目录）。
    失败抛异常，由调用方决定重试/降级。
    """
    import httpx

    ref_path = os.path.join(_ref_dir(), os.path.basename(ref_filename_in_volume))
    if not os.path.exists(ref_path):
        raise FileNotFoundError(f"volume 中不存在参考音频 {ref_filename_in_volume}")

    # 参考音频文本（prompt_text）为 GPT-SoVITS 推理必需：由调用方提供
    # 参考音频的转写文本；未提供时交由 api.py 使用启动时预设的默认参考。
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