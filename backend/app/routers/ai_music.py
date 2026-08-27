"""AI 音乐生成路由（异步任务架构）—— 公测商业版

POST /api/v1/ai/generate               提交生成任务，立即返回 task_id
GET  /api/v1/ai/task/{id}              轮询任务状态，completed 时返回可播放 URL
GET  /api/v1/ai/task/{id}/download     授权下载（完整歌/分轨，预签名 URL）
POST /api/v1/ai/task/{id}/retry-stems  分轨失败重试
GET  /api/v1/ai/limits                 额度/成本保护状态

生成链（无 MusicGen 商业兜底）：
  Agnes 优化 prompt/歌词
    -> ACE-Step 1.5 (Modal GPU，整曲生成) + Spleeter 四轨分轨（独立 Modal App） + MP3
    -> HF ACE-Step 兜底（真实音频，无 mock 假音频）
    -> 明确报错（失败自动重试 1 次后仍失败则失败）

额度与成本保护（提交前原子预留，GPU 启动前扣减，失败回退）：
  - 每用户每日 1 首 / 每月 15 首 / 全平台每日 30 首（集中配置见 ai_limits.py）
  - 每用户同时仅 1 个任务（task_store 锁），单任务超时 10 分钟

下载安全（公测最小增强）：
  - job 绑定创建者（X-User-ID 头），下载端校验 job 存在 / 归属 / 已完成 / 文件属于 job
  - IDOR 防护：A 无法通过改 job_id 下载 B 的音频
  - Modal 内部路径与对象存储公网 URL 均不暴露；下载仅返回短期预签名 URL（10 分钟）
  - 记录下载审计（user_id / job_id / file_type / 时间 / IP）+ 每用户限流
"""

import asyncio
import json
import os
import time
import httpx
from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from app.services.agnes_music_service import agnes_service, AgnesSongRequest
from app.services.ace_step_client import (
    separate_only as ace_step_separate,
    download_file as ace_step_download,
    QueueFullError,
)
from app.services.provider_registry import get_provider_registry, gpu_rate_usd_per_sec
from app.services.ai_limits import (
    MAX_AUDIO_DURATION_SECONDS,
    MAX_AUTO_RETRIES,
    MAX_TASK_RUNTIME_SECONDS,
    reserve_generation,
    refund_generation,
    generation_usage_status,
    check_and_log_download,
    budget_hard_stop_reached,
)
from app.services import task_store
from app.services.cdn_uploader import cdn_uploader

router = APIRouter(prefix="/api/v1/ai", tags=["ai-music"])

HF_FALLBACK_ENABLED = os.getenv("HF_FALLBACK", "true").lower() in ("1", "true", "yes")

# 下载文件白名单：逻辑名 -> (manifest 键, 是否分轨)
DOWNLOAD_FILES = {
    "full": ("full_mp3", False),
    "full_wav": ("full_wav", False),
    "vocals": ("vocals", True),
    "drums": ("drums", True),
    "bass": ("bass", True),
    "other": ("other", True),
}
# Provider 选择与注册见 app/services/provider_registry.py（唯一 production = modal_ace_step）。


# 最大歌曲时长硬限制（秒）—— 后端硬限制，不可绕过
MAX_SONG_DURATION_SECONDS = 270

# 参考音频默认截取长度（秒）
REFERENCE_SECONDS = 30


async def _try_hf_ace_step_fallback(
    prompt: str,
    lyrics: str,
    duration: int,
    reference_audio_b64: Optional[str] = None,
    enable_audio2audio: bool = False,
    reference_strength: float = 0.7,
) -> Optional[str]:
    """HF ACE-Step Space 兜底（Gradio 5 API）：仅接受真实音频 URL，禁止 mock/假音频（SoundHelix）。
    
    新增支持 Audio2Audio 参数：
    - enable_audio2audio: 是否启用 Audio2Audio
    - reference_audio_b64: base64 编码的参考音频
    - reference_strength: 参考音频强度 (0.0-1.0)
    """
    if not HF_FALLBACK_ENABLED:
        return None

    hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")
    if not hf_token:
        print("[HF 兜底] 未配置 HF_TOKEN / HUGGINGFACE_TOKEN，跳过")
        return None

    # Gradio 5 协议：POST /gradio_api/call/__call__ -> event_id -> GET SSE 轮询
    base_url = "https://ace-step-ace-step.hf.space"
    api_url = f"{base_url}/gradio_api/call/__call__"
    headers = {"Authorization": f"Bearer {hf_token}", "Content-Type": "application/json"}

    # 22 个 positional parameters（顺序必须与当前 LIVE API 一致）
    # 参数 19/20/21 现在支持 Audio2Audio
    data = [
        float(duration),          # 1  Audio Duration
        prompt,                   # 2  Tags
        lyrics or "",             # 3  Lyrics
        50,                       # 4  Infer Steps
        15.0,                     # 5  Guidance Scale
        "euler",                  # 6  Scheduler Type
        "apg",                    # 7  CFG Type
        10.0,                     # 8  Granularity Scale
        None,                     # 9  manual seeds (default None)
        0.5,                      # 10 Guidance Interval
        0.0,                      # 11 Guidance Interval Decay
        3.0,                      # 12 Min Guidance Scale
        True,                     # 13 use ERG for tag
        False,                    # 14 use ERG for lyric
        True,                     # 15 use ERG for diffusion
        None,                     # 16 OSS Steps
        0.0,                      # 17 Guidance Scale Text
        0.0,                      # 18 Guidance Scale Lyric
        enable_audio2audio,       # 19 Enable Audio2Audio
        0.7,                      # 20 Refer audio strength
        reference_audio_b64,      # 21 Reference Audio (Audio2Audio)
        "none",                   # 22 Lora Name or Path
    ]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(api_url, headers=headers, json={"data": data})
            if response.status_code != 200:
                print(f"[HF 兜底] ACE-Step Space 提交失败: HTTP {response.status_code}")
                return None
            resp_data = response.json()
            event_id = (resp_data or {}).get("event_id")
            if not event_id:
                print("[HF 兜底] ACE-Step Space 未返回 event_id")
                return None

            # SSE 轮询直到 event: complete / event: error
            poll_url = f"{api_url}/{event_id}"
            async with client.stream("GET", poll_url, headers=headers, timeout=300.0) as stream:
                current_event = None
                async for line in stream.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("event:"):
                        current_event = line[len("event:"):].strip()
                    elif line.startswith("data:"):
                        payload_text = line[len("data:"):].strip()
                        if current_event == "error":
                            print(f"[HF 兜底] ACE-Step Space 返回 error 事件: {payload_text[:200]}")
                            return None
                        if current_event == "complete":
                            try:
                                payload = json.loads(payload_text)
                            except Exception as exc:
                                print(f"[HF 兜底] SSE complete 事件解析失败: {exc}")
                                return None
                            # Gradio 5 complete 事件 data 是顶层 JSON 数组（兼容 dict 包装）
                            items = payload if isinstance(payload, list) else (payload.get("data") if isinstance(payload, dict) else None)
                            if isinstance(items, list):
                                for item in items:
                                    url = None
                                    if isinstance(item, dict):
                                        url = item.get("url") or item.get("name")
                                    elif isinstance(item, str) and item.startswith("http"):
                                        url = item
                                    if url and url.startswith("http") and "soundhelix.com" not in url:
                                        return url
                            print("[HF 兜底] ACE-Step Space complete 事件未返回可用音频 URL")
                            return None
        print("[HF 兜底] ACE-Step Space SSE 流结束但未收到 complete 事件")
        return None
    except Exception as e:  # noqa: BLE001
        print(f"[HF 兜底] 异常: {type(e).__name__}: {e}")
        return None


class GenerateRequest(BaseModel):
    """AI 生成请求"""
    prompt: str
    style: str = "pop"
    duration: Optional[int] = None
    lyrics: Optional[str] = None
    type: str = "song"
    user_id: Optional[str] = None  # 兼容旧调用；优先使用 X-User-ID 请求头


class GenerateResponse(BaseModel):
    """AI 生成响应（提交成功即返回）"""
    success: bool
    task_id: Optional[str] = None
    status_url: Optional[str] = None
    error: Optional[str] = None


class TaskResponse(BaseModel):
    """任务状态查询响应"""
    task_id: str
    state: str          # 对外终态始终为 pending/processing/completed/failed/cancelled
    progress: int
    audio_url: Optional[str] = None
    video_url: Optional[str] = None
    ai_provider: Optional[str] = None
    error: Optional[str] = None
    stems: Optional[dict] = None
    stems_state: Optional[str] = None   # ok / failed / skipped
    retries: Optional[int] = 0
    stem_retries: Optional[int] = 0


def _log_generation_cost(task_id: str, user_key: str, provider, result: str, total_duration_ms: int, retries: int):
    """记录生成成本观测（估算口径：实测容器时长 × GPU 单价）。失败不影响生成主流程。"""
    try:
        task_store.log_generation_cost(
            task_id=task_id,
            user_key=user_key,
            provider=provider.name,
            gpu=provider.gpu,
            result=result,
            container_duration_ms=total_duration_ms,
            retries=retries,
            estimated_cost_usd=round(
                total_duration_ms / 1000.0 * gpu_rate_usd_per_sec(provider.gpu), 8,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[CostLog] log_generation_cost failed: {exc}")


async def _run_generation(task_id: str, request: GenerateRequest, user_key: str):
    """后台执行完整生成链路：Agnes -> ACE-Step(Modal) -> HF(ACE-Step) -> 报错。"""
    try:
        task_store.update(task_id, state="processing", progress=10)

        agnes_request = AgnesSongRequest(
            prompt=request.prompt,
            style=request.style,
            duration=request.duration or 180,
            type=request.type,
            lyrics=request.lyrics,
        )
        agnes_result = await agnes_service.generate_song(agnes_request)

        ai_provider = "agnes" if agnes_result.optimized_prompt and agnes_result.optimized_prompt != request.prompt else "gemini"
        task_store.update(task_id, progress=25, ai_provider=f"{ai_provider}")

        final_prompt = agnes_result.optimized_prompt or request.prompt
        lyrics = request.lyrics or agnes_result.generated_lyrics or final_prompt
        duration = min(request.duration or 180, MAX_AUDIO_DURATION_SECONDS)

        # ── Modal ACE-Step (GPU) ── 经 ProviderRegistry 选择；失败自动重试 MAX_AUTO_RETRIES 次
        task_store.update(task_id, state="generating", progress=40)
        provider = get_provider_registry().select()
        volume_result: Optional[dict] = None
        retries_used = 0
        total_duration_ms = 0
        for attempt in range(1 + MAX_AUTO_RETRIES):
            retries_used = attempt
            t0 = time.monotonic()
            try:
                gen_result = await provider.generate(
                    {
                        "prompt": final_prompt,
                        "lyrics": lyrics,
                        "duration": duration,
                        "reference_audio": None,  # 当前不支持 Audio2Audio，保留接口兼容
                        "enable_audio2audio": False,
                        "reference_strength": 0.7,
                    },
                )
                total_duration_ms += int((time.monotonic() - t0) * 1000)
            except QueueFullError:
                total_duration_ms += int((time.monotonic() - t0) * 1000)
                raise
            volume_result = gen_result.get("volume_files") if gen_result and gen_result.get("success") else None
            if volume_result:
                break
            task_store.update(task_id, retries=attempt, error=f"ACE-Step 第 {attempt} 次尝试失败，自动重试")

        if volume_result:
            task_store.update(
                task_id, state="uploading", progress=75,
                volume_files=volume_result, ai_provider=f"{ai_provider}+acestep",
            )
            _log_generation_cost(task_id, user_key, provider, "success", total_duration_ms, retries_used)
            await _upload_and_finalize(task_id, volume_result)
            return

        # GPU 尝试失败：先记录成本观测，再走 HF 兜底
        _log_generation_cost(task_id, user_key, provider, "failed", total_duration_ms, retries_used)

        # ── HF ACE-Step 兜底（真实音频，无 mock）──
        task_store.update(task_id, state="generating", progress=55)
        hf_audio = await _try_hf_ace_step_fallback(final_prompt, lyrics, duration)
        if hf_audio:
            task_store.update(
                task_id, state="completed", progress=100,
                audio_url=hf_audio, stems_state="skipped", ai_provider=f"{ai_provider}+hf",
            )
            return

        task_store.update(
            task_id, state="failed",
            error="音乐生成失败：ACE-Step(Modal) 与 HF 兜底均不可用（请检查 Modal 部署 / HF_TOKEN 配置）",
        )
        refund_generation(user_key)
    except QueueFullError as e:
        _log_generation_cost(task_id, user_key, provider, "queue_full", total_duration_ms, retries_used)
        task_store.update(task_id, state="failed", error=str(e))
        refund_generation(user_key)
    except HTTPException:
        task_store.update(task_id, state="failed", error="请求参数错误")
        refund_generation(user_key)
    except asyncio.TimeoutError:
        task_store.update(task_id, state="failed", error="生成超时，请稍后重试")
        refund_generation(user_key)
    except Exception as e:  # noqa: BLE001
        import traceback
        print(f"[generate 未捕获异常] {type(e).__name__}: {e}")
        traceback.print_exc()
        task_store.update(task_id, state="failed", error=f"{type(e).__name__}: {e}")
        refund_generation(user_key)
    finally:
        task_store.release_lock_for_task(task_id)


async def _upload_and_finalize(task_id: str, volume_result: dict):
    """把生成产物取回本地、上传 R2 私有，写回任务元数据。

    兼容两种来源：
    - Modal 共享卷（volume_result 含末尾文件名，需 ace_step_download）
    - Fal（volume_result 含 _local_path 已在 GENERATED_DIR，download 直接命中本地）
    """
    import tempfile

    tmp_dir = tempfile.mkdtemp(prefix="acestep_")
    files_local: dict = {}

    # 优先使用 fal 已下载的本地路径（_local_path）
    if volume_result.get("_local_path") and os.path.exists(volume_result["_local_path"]):
        lp = volume_result["_local_path"]
        # 统一映射为 full_wav / full_mp3
        files_local["full_wav"] = lp
        files_local["full_mp3"] = lp
        # 若额外携带 _local_path 对应的 stems，也一并处理（当前 fal 无分轨）
    else:
        # full_wav 必需；full_mp3 可选（Modal 端可能转换失败）
        full_wav_name = volume_result.get("full_wav")
        if not full_wav_name:
            raise RuntimeError("ACE-Step/Fal 未返回完整歌曲文件")
        path = await ace_step_download(full_wav_name, tmp_dir)
        if not path:
            # fal 场景：尝试直接把文件名当本地路径（GENERATED_DIR 命中）
            alt = os.path.join(tmp_dir, os.path.basename(full_wav_name))
            # 也尝试 GENERATED_DIR
            from app.services.fal_client import local_dir as fal_local_dir
            alt2 = os.path.join(fal_local_dir(), os.path.basename(full_wav_name))
            if os.path.exists(alt2):
                path = alt2
            elif os.path.exists(alt):
                path = alt
            else:
                raise RuntimeError(f"下载 {full_wav_name} 失败")
        files_local["full_wav"] = path

        mp3_name = volume_result.get("full_mp3")
        if mp3_name and mp3_name != volume_result.get("full_wav"):
            p = await ace_step_download(mp3_name, tmp_dir)
            if p:
                files_local["full_mp3"] = p

    for logical in ("vocals", "drums", "bass", "other"):
        name = volume_result.get(logical)
        if not name:
            continue
        # 若是 fal 场景的本地路径，已在上一步处理；此处仅处理额外 stems
        if os.path.exists(name):
            files_local[logical] = name
            continue
        p = await ace_step_download(name, tmp_dir)
        if p:
            files_local[logical] = p

    manifest = await cdn_uploader.upload_music_package(task_id, files_local)

    stems_ok = all(s in manifest for s in ("vocals", "drums", "bass", "other"))
    state = "completed" if stems_ok else "completed_with_stems_failed"
    task_store.update(
        task_id,
        state=state,
        progress=100,
        download=manifest,
        stems_state="ok" if stems_ok else "failed",
        audio_url=_sign_for_playback(task_id, "full_mp3", manifest),
    )


def _sign_for_playback(task_id: str, logical: str, manifest: Optional[dict]) -> Optional[str]:
    """为任务返回的可播放 URL 签发短期预签名 URL（仅 backend 侧可生成）。"""
    if not manifest:
        return None
    key = manifest.get(logical)
    if not key:
        key = manifest.get("full_wav")
    if not key:
        return None
    try:
        return cdn_uploader.get_presigned_download_url(key, expires_in=600)
    except Exception:  # noqa: BLE001
        return None


def _stems_signed(task_id: str, manifest: Optional[dict]) -> Optional[dict]:
    """为 4 分轨签发短期预签名 URL（播放用）。"""
    if not manifest:
        return None
    out = {}
    for logical in ("vocals", "drums", "bass", "other"):
        key = manifest.get(logical)
        if key:
            try:
                out[logical] = cdn_uploader.get_presigned_download_url(key, expires_in=600)
            except Exception:  # noqa: BLE001
                continue
    return out or None


async def _run_with_timeout(task_id: str, request: GenerateRequest, user_key: str):
    """包一层超时（单任务最大 10 分钟），超时自动标记 failed 并回退额度。"""
    try:
        await asyncio.wait_for(
            _run_generation(task_id, request, user_key),
            timeout=MAX_TASK_RUNTIME_SECONDS,
        )
    except asyncio.TimeoutError:
        task_store.update(task_id, state="failed", error="生成超时，请稍后重试")
        refund_generation(user_key)
        task_store.release_lock_for_task(task_id)


@router.post("/generate", response_model=GenerateResponse)
async def generate_music(
    request: Request,
    req: GenerateRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """提交 AI 音乐生成任务，立即返回 task_id。

    用户绑定优先级：X-User-ID 请求头 > 请求体 user_id > 客户端 IP。
    job 在创建时即绑定该 user_key，下载/重试均以此归属校验。
    """
    if not req.prompt or len(req.prompt.strip()) < 5:
        raise HTTPException(status_code=400, detail="提示词至少需要 5 个字符")

    user_key = x_user_id or req.user_id or (request.client.host if request.client else None)
    if task_store.is_user_busy(user_key):
        return GenerateResponse(
            success=False,
            error="您有一个生成任务正在进行中，请完成后再试",
        )

    # 原子预留额度（GPU 启动前扣减）—— 不可通过重复 POST / 改 localStorage 绕过
    reserved = reserve_generation(user_key)
    if not reserved["success"]:
        # GPU 预算硬停线：达到 FAL_BUDGET_DAILY 后在 GPU 启动前返回 429（与 retry-stems 一致，兼容旧 MODAL_BUDGET_DAILY）
        if "预算" in reserved["error"]:
            return JSONResponse(
                status_code=429,
                content=GenerateResponse(success=False, error=reserved["error"]).model_dump(),
            )
        return GenerateResponse(success=False, error=reserved["error"])

    task_id = task_store.new_task(user_key=user_key)
    if not task_store.acquire_lock(user_key, task_id):
        task_store.delete(task_id)
        refund_generation(user_key)
        return GenerateResponse(
            success=False,
            error="您有一个生成任务正在进行中，请完成后再试",
        )

    asyncio.create_task(_run_with_timeout(task_id, req, user_key))
    return GenerateResponse(
        success=True,
        task_id=task_id,
        status_url=f"/api/v1/ai/task/{task_id}",
    )


@router.get("/task/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """轮询任务状态；completed 时返回可播放 URL 与分轨。

    带 X-User-ID 时做归属校验；不带时保持向后兼容（公测安全限制，见 ai_limits 说明）。
    """
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    user_key = task.get("user_key")
    if x_user_id and user_key and x_user_id != user_key:
        raise HTTPException(status_code=403, detail="无权访问该任务")

    state = task["state"]
    audio_url = task.get("audio_url")
    stems_state = task.get("stems_state")
    if state in ("completed", "completed_with_stems_failed"):
        manifest = task.get("download")
        if manifest:
            audio_url = audio_url or _sign_for_playback(task_id, "full_mp3", manifest)

    return TaskResponse(
        task_id=task["task_id"],
        state="completed" if state == "completed_with_stems_failed" else state,
        progress=task["progress"],
        audio_url=audio_url,
        video_url=task.get("video_url"),
        ai_provider=task.get("ai_provider"),
        error=task.get("error"),
        stems=_stems_signed(task_id, task.get("download")) if state in ("completed", "completed_with_stems_failed") else None,
        stems_state=stems_state,
        retries=task.get("retries", 0),
        stem_retries=task.get("stem_retries", 0),
    )


@router.get("/task/{task_id}/download")
async def download_file(
    request: Request,
    task_id: str,
    file: str = "full",
    fmt: str = "mp3",
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """授权下载：完整歌（mp3/wav）与 4 分轨。返回短期预签名 URL。

    校验（全部通过才签发）：job 存在 -> 归属当前用户 -> 已完成 -> 文件属于该 job。
    用户 A 无法通过修改 job_id 下载用户 B 的音频（IDOR 防护）。
    """
    if file not in DOWNLOAD_FILES:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {file}")

    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    user_key = task.get("user_key")
    if not x_user_id or not user_key or x_user_id != user_key:
        raise HTTPException(status_code=403, detail="无权访问该任务（需 X-User-ID 且归属匹配）")

    if task["state"] not in ("completed", "completed_with_stems_failed"):
        raise HTTPException(status_code=409, detail="任务尚未完成")

    manifest_key, is_stem = DOWNLOAD_FILES[file]
    if file == "full" and fmt == "wav":
        manifest_key = "full_wav"
    if is_stem and task.get("stems_state") != "ok":
        raise HTTPException(status_code=409, detail="该任务分轨未生成，请先重试分轨")

    manifest = task.get("download") or {}
    key = manifest.get(manifest_key)
    if not key:
        raise HTTPException(status_code=404, detail="文件不存在（可能未生成 MP3）")

    ip = request.client.host if request else ""
    if not check_and_log_download(
        user_key,
        task_id,
        f"{file}:{fmt}",
        ip,
    ):
        raise HTTPException(status_code=429, detail="下载过于频繁，请稍后再试")

    expires_in = 600
    return {
        "url": cdn_uploader.get_presigned_download_url(key, expires_in=expires_in),
        "expires_in": expires_in,
        "file": file,
        "format": fmt,
    }


@router.post("/task/{task_id}/retry-stems")
async def retry_stems(
    task_id: str,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """分轨失败重试：对已生成的完整 WAV 重新执行四轨分离（独立 Spleeter App）。"""
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    user_key = task.get("user_key")
    if not x_user_id or not user_key or x_user_id != user_key:
        raise HTTPException(status_code=403, detail="无权访问该任务")

    if task["state"] not in ("completed", "completed_with_stems_failed"):
        raise HTTPException(status_code=409, detail="任务状态不允许重试分轨")
    if task.get("stems_state") == "ok":
        raise HTTPException(status_code=409, detail="分轨已生成，无需重试")

    # GPU 预算硬停线：达到后不启动分轨（重试分轨同样消耗算力，不允许绕过预算）
    if budget_hard_stop_reached():
        raise HTTPException(status_code=429, detail="今日 GPU 预算已用尽，请明天再试")

    volume_files = task.get("volume_files") or {}
    full_wav = volume_files.get("full_wav")
    if not full_wav:
        raise HTTPException(status_code=409, detail="缺少完整 WAV（无法重试分轨）")

    if task_store.is_user_busy(user_key):
        raise HTTPException(status_code=429, detail="您有任务正在进行中，请稍后再试")

    # 重试次数上限（不重复扣生成额度）— 兼容 PG 返回 None
    if (task.get("stem_retries") or 0) >= MAX_AUTO_RETRIES:
        raise HTTPException(
            status_code=429,
            detail=f"分轨重试次数已达上限（{MAX_AUTO_RETRIES} 次），请稍后再试",
        )

    # 借用同一任务槽位（不重复扣额度，分轨免费）
    task_store.update(task_id, stem_retries=(task.get("stem_retries") or 0) + 1)
    asyncio.create_task(_run_retry_stems(task_id, user_key, full_wav))
    return {"success": True, "task_id": task_id}


async def _run_retry_stems(task_id: str, user_key: str, full_wav: str):
    try:
        task_store.update(task_id, state="separating", progress=85)
        stems = await ace_step_separate(full_wav)
        if not stems:
            task_store.update(task_id, state="completed_with_stems_failed", progress=100, error="分轨重试失败")
            return

        import tempfile
        tmp_dir = tempfile.mkdtemp(prefix="acestep_retry_")
        files_local = {}
        for logical in ("vocals", "drums", "bass", "other"):
            name = stems.get(logical)
            if not name:
                continue
            p = await ace_step_download(name, tmp_dir)
            if p:
                files_local[logical] = p

        manifest = dict((task_store.get(task_id) or {}).get("download") or {})
        added = await cdn_uploader.upload_music_package(task_id, files_local)
        manifest.update(added)

        ok = all(s in manifest for s in ("vocals", "drums", "bass", "other"))
        task_store.update(
            task_id, state="completed" if ok else "completed_with_stems_failed",
            progress=100, download=manifest,
            stems_state="ok" if ok else "failed",
            error=None,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[retry-stems 异常] {type(e).__name__}: {e}")
        task_store.update(task_id, state="completed_with_stems_failed", progress=100, error=f"分轨重试失败: {e}")
    finally:
        task_store.release_lock_for_task(task_id)


@router.get("/limits")
async def get_limits(x_user_id: str = Header(None, alias="X-User-ID")):
    """查询用户额度与全局成本保护状态。"""
    return await generation_usage_status(x_user_id)


@router.get("/tasks")
async def list_user_tasks_endpoint(x_user_id: str = Header(None, alias="X-User-ID")):
    """查询当前用户的所有生成任务。

    仅返回当前归属用户的任务，使用 X-User-ID 进行归属校验。
    返回任务基本信息：id, state, progress, audio_url, stems_state, created_at, updated_at。
    """
    from app.services.task_store import list_user_tasks

    user_key = x_user_id
    if not user_key:
        return {"tasks": [], "count": 0}

    tasks = list_user_tasks(user_key)
    return {"tasks": tasks, "count": len(tasks)}


@router.get("/task/{task_id}/delete")
async def delete_user_task(
    task_id: str,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """删除用户的生成任务。

    1. 验证任务归属：仅当前用户可删除自己的任务
    2. 清理 R2 对象（完整音频 + 4 个分轨）
    3. 清理 SQLite 任务记录和锁
    4. 删除失败时返回明确错误，不报告成功
    """
    import json
    import boto3
    from botocore.config import Config
    from fastapi import HTTPException

    # Step 1: 获取任务信息以验证归属
    from app.services.task_store import get_task as task_store_get

    task = task_store_get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 验证用户归属：task.user_key 必须与 X-User-ID 匹配
    user_key = task.get("user_key")
    if not user_key or user_key != x_user_id:
        raise HTTPException(status_code=403, detail="无权删除他人的任务")

    # Step 2: 尝试删除 R2 对象（经 r2_config 统一）
    from app.services.r2_config import get_r2_account_id, get_r2_access_key, get_r2_secret_key, get_r2_bucket
    r2_account_id = get_r2_account_id()
    r2_access_key = get_r2_access_key()
    r2_secret_key = get_r2_secret_key()
    r2_bucket = get_r2_bucket()

    r2_deleted = True
    r2_errors = []

    if r2_account_id and r2_access_key and r2_secret_key and r2_bucket:
        try:
            s3_client = boto3.client(
                's3',
                endpoint_url="https://{}.r2.cloudflarestorage.com".format(r2_account_id),
                aws_access_key_id=r2_access_key,
                aws_secret_access_key=r2_secret_key,
                config=Config(signature_version='s3v4'),
                region_name='auto',
            )

            # 要删除的 R2 对象键
            keys_to_delete = []
            # full_mp3
            if task.get("download"):
                try:
                    download = json.loads(task.get("download", "{}"))
                    if "full_mp3" in download:
                        keys_to_delete.append("music/{}/full_mp3.mp3".format(task_id))
                except (json.JSONDecodeError, TypeError):
                    pass
            # full_wav
            full_wav = task.get("volume_files", {})
            if full_wav and "full_wav" in full_wav:
                keys_to_delete.append("music/{}/{}".format(task_id, full_wav["full_wav"]))
            # 4 个分轨
            for stem in ["vocals", "drums", "bass", "other"]:
                stem_name = task.get("volume_files", {}).get(stem)
                if stem_name:
                    keys_to_delete.append("music/{}/{}".format(task_id, stem_name))

            # 执行删除
            for key in keys_to_delete:
                try:
                    s3_client.delete_object(Bucket=r2_bucket, Key=key)
                except Exception as e:
                    r2_errors.append("{}: {}".format(key, str(e)))
                    r2_deleted = False
        except Exception as e:
            r2_deleted = False
            r2_errors.append(str(e))
    else:
        r2_deleted = False
        r2_errors.append("R2 配置不完整")

    # Step 3: 只有 R2 删除全部成功才删除 SQLite 记录
    if r2_deleted:
        try:
            from app.services.task_store import delete as task_store_delete
            task_store_delete(task_id)
            return {"success": True, "detail": "任务删除成功"}
        except Exception as e:
            raise HTTPException(status_code=500, detail="删除数据库记录失败: {}".format(str(e)))
    else:
        # R2 删除失败，不删除数据库记录，返回错误
        error_detail = "任务删除失败: R2 对象删除"
        if r2_errors:
            error_detail += ": " + "; ".join(r2_errors[:3])
        raise HTTPException(status_code=500, detail=error_detail)

@router.get("/styles")
async def list_styles():
    """获取支持的音乐风格"""
    return {
        "styles": [
            {"value": "pop", "label": "流行", "description": "主流流行音乐"},
            {"value": "rock", "label": "摇滚", "description": "摇滚乐"},
            {"value": "electronic", "label": "电子", "description": "电子音乐"},
            {"value": "hip-hop", "label": "嘻哈", "description": "嘻哈/说唱"},
            {"value": "r&b", "label": "R&B", "description": "节奏布鲁斯"},
            {"value": "jazz", "label": "爵士", "description": "爵士乐"},
            {"value": "classical", "label": "古典", "description": "古典音乐"},
            {"value": "ambient", "label": "氛围", "description": "氛围音乐"},
            {"value": "cinematic", "label": "电影配乐", "description": "电影原声"},
            {"value": "lo-fi", "label": "Lo-Fi", "description": "低保真音乐"},
        ]
    }