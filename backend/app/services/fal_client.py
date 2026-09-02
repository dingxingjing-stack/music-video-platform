"""Fal.ai 队列客户端 — 用于生产环境音乐生成。

基于 REST Queue API（https://queue.fal.run），不依赖 fal-client SDK。
支持：
- FAL_KEY（官方）或 FAL_API_KEY（兼容）双键读取
- FAL_MODEL 可配置（默认 fal-ai/stable-audio）
- 队列提交 -> 轮询 status -> 拉取 result -> 下载音频到 GENERATED_DIR

认证：Header `Authorization: Key $FAL_KEY`
官方推荐环境变量名即 FAL_KEY，本项目同时兼容 FAL_API_KEY。
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

import httpx

from app.core.secrets import get_secret

logger = logging.getLogger(__name__)

# 默认模型：文本生成音乐；可通过 FAL_MODEL 覆盖为其它 fal 音乐模型
# 常见：fal-ai/stable-audio / fal-ai/stable-audio-3 / fal-ai/musicgen 等
DEFAULT_MODEL = "fal-ai/stable-audio"
QUEUE_BASE = "https://queue.fal.run"


def _resolve_fal_key() -> Optional[str]:
    # 优先级：进程 env FAL_KEY > FAL_API_KEY > secrets.local.json
    for k in ("FAL_KEY", "FAL_API_KEY"):
        v = os.getenv(k)
        if v and v.strip():
            return v.strip()
        try:
            v2 = get_secret(k)
            if v2 and v2.strip():
                return v2.strip()
        except Exception:
            pass
    return None


def _resolve_model() -> str:
    return (os.getenv("FAL_MODEL") or os.getenv("FAL_MUSIC_MODEL") or DEFAULT_MODEL).strip()


def _resolve_timeout() -> float:
    try:
        return float(os.getenv("FAL_TIMEOUT", "300"))
    except Exception:
        return 300.0


def _resolve_poll_interval() -> float:
    try:
        return float(os.getenv("FAL_POLL_INTERVAL", "2"))
    except Exception:
        return 2.0


def local_dir() -> str:
    return os.getenv("GENERATED_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "generated"))


class FalQueueError(Exception):
    pass


class FalAuthError(FalQueueError):
    pass


async def _download_to_generated(url: str, dest_dir: Optional[str] = None) -> str:
    """下载 fal 媒体 URL 到 GENERATED_DIR，返回本地路径。"""
    dest = Path(dest_dir or local_dir())
    dest.mkdir(parents=True, exist_ok=True)
    # 保留原始后缀，fal 通常返回 .wav / .mp3 / .flac
    suffix = ".wav"
    if url:
        low = url.lower().split("?")[0]
        for ext in (".wav", ".mp3", ".flac", ".ogg", ".m4a"):
            if low.endswith(ext):
                suffix = ext
                break
    out_path = dest / f"fal_{int(time.time()*1000)}{suffix}"
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            raise FalQueueError(f"下载 fal 音频失败: HTTP {resp.status_code}")
        data = resp.content
        if not data or len(data) < 1000:
            raise FalQueueError(f"下载的音频过小或为空 ({len(data) if data else 0} bytes)")
        out_path.write_bytes(data)
    logger.info("[fal] 音频已下载: %s (%d bytes)", out_path, out_path.stat().st_size)
    return str(out_path)


async def generate_via_fal(
    prompt: str,
    lyrics: str = "",
    duration: int = 30,
    reference_audio_b64: Optional[str] = None,
    enable_audio2audio: bool = False,
) -> dict | None:
    """调用 fal 队列生成音乐，返回 volume_files 兼容结构；失败返回 None。

    volume_files 形如 {"full_wav": "<本地绝对路径或文件名>", "full_mp3": "..."}
    调用方（ai_music._upload_and_finalize）会经 ace_step_download 取回本地文件
    并上传 R2。由于 fal 已直接给出可下载 URL，我们在此直接下载到 GENERATED_DIR，
    使得后续 download_file 的本地命中路径生效，不依赖 Modal Volume。
    """
    fal_key = _resolve_fal_key()
    if not fal_key:
        logger.warning("[fal] 未配置 FAL_KEY / FAL_API_KEY，跳过 fal 生成")
        return None

    model = _resolve_model()
    timeout = _resolve_timeout()
    poll_interval = _resolve_poll_interval()

    # 组合 prompt + lyrics；fal stable-audio 仅接受 prompt 文本
    final_prompt = prompt.strip()
    if lyrics and lyrics.strip():
        # 避免超长 prompt 截断（fal 上下文限制约 500 字符，此处保守截断）
        lyric_snippet = lyrics.strip()[:800]
        final_prompt = f"{final_prompt}. Lyrics: {lyric_snippet}" if final_prompt else lyric_snippet

    # seconds_total 限制：stable-audio 默认 30s，范围 10-120s 较安全
    seconds_total = max(10, min(int(duration) if duration else 30, 180))
    # 部分模型最大 47s，超长时截断并在日志告警
    if seconds_total > 95 and model == "fal-ai/stable-audio":
        logger.warning("[fal] 模型 %s 建议 <=95s，请求 %ds 将被截断为 95s", model, seconds_total)
        seconds_total = 95

    submit_url = f"{QUEUE_BASE}/{model}"
    headers = {"Authorization": f"Key {fal_key}", "Content-Type": "application/json"}

    # 输入 payload 按模型区分；stable-audio 必需 prompt + seconds_total
    payload: dict = {"prompt": final_prompt, "seconds_total": seconds_total, "steps": 100}
    # audio-to-audio 扩展：若提供参考音频（base64 data-uri 或 URL），部分 fal 模型支持 audio_url
    if enable_audio2audio and reference_audio_b64:
        # 若是 base64，尝试转为 data URI
        if reference_audio_b64.startswith("http"):
            payload["audio_url"] = reference_audio_b64
        elif reference_audio_b64.startswith("data:"):
            # fal 支持 data URI 直传
            payload["audio_url"] = reference_audio_b64
        else:
            # 裸 base64 -> 包装为 data URI
            payload["audio_url"] = f"data:audio/wav;base64,{reference_audio_b64}"

    logger.info("[fal] 提交队列: model=%s prompt_len=%d duration=%ds", model, len(final_prompt), seconds_total)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. submit
        try:
            resp = await client.post(submit_url, headers=headers, json=payload)
        except Exception as exc:
            logger.warning("[fal] 提交异常: %s", exc)
            return None

        if resp.status_code == 401:
            raise FalAuthError("FAL_KEY 无效或未授权（401）")
        if resp.status_code == 429:
            logger.warning("[fal] 队列限流 429")
            return None
        if resp.status_code not in (200, 201, 202):
            logger.warning("[fal] 提交失败: HTTP %s body=%s", resp.status_code, resp.text[:500])
            return None

        try:
            data = resp.json()
        except Exception:
            logger.warning("[fal] 提交响应非 JSON: %s", resp.text[:500])
            return None

        request_id = data.get("request_id") or data.get("requestId") or data.get("requestId".lower())
        # 兼容部分模型直接同步返回（subscribe 风格）
        if not request_id:
            # 若直接返回 audio_file，则视为同步完成
            maybe_url = None
            if isinstance(data, dict):
                af = data.get("audio_file") or data.get("audio") or data.get("audio_url")
                if isinstance(af, dict):
                    maybe_url = af.get("url")
                elif isinstance(af, str) and af.startswith("http"):
                    maybe_url = af
            if maybe_url:
                try:
                    local_path = await _download_to_generated(maybe_url)
                    fname = os.path.basename(local_path)
                    return {"full_wav": fname, "full_mp3": fname, "_local_path": local_path, "_fal_url": maybe_url}
                except Exception as exc:
                    logger.warning("[fal] 同步结果下载失败: %s", exc)
                    return None
            logger.warning("[fal] 提交响应缺 request_id: %s", str(data)[:800])
            return None

        status_url = f"{QUEUE_BASE}/{model}/requests/{request_id}/status"
        result_url = f"{QUEUE_BASE}/{model}/requests/{request_id}"
        logger.info("[fal] 已入队 request_id=%s", request_id)

        # 2. poll status
        deadline = time.monotonic() + timeout
        last_status = None
        while time.monotonic() < deadline:
            await asyncio.sleep(poll_interval)
            try:
                s_resp = await client.get(status_url, headers=headers, params={"logs": "0"})
            except Exception as exc:
                logger.warning("[fal] status 轮询异常: %s", exc)
                continue
            if s_resp.status_code == 404:
                logger.warning("[fal] status 404，request_id 可能过期: %s", request_id)
                return None
            if s_resp.status_code not in (200, 202):
                logger.warning("[fal] status 失败 %s: %s", s_resp.status_code, s_resp.text[:500])
                continue
            try:
                s_data = s_resp.json()
            except Exception:
                continue
            status = s_data.get("status") or s_data.get("state")
            last_status = status
            if status in ("COMPLETED", "COMPLETED ", "completed"):
                break
            if status in ("FAILED", "failed"):
                logger.warning("[fal] 任务失败: %s", str(s_data)[:800])
                return None
            # IN_QUEUE / IN_PROGRESS 继续轮询
            # 可选：打印 queue_position
            qp = s_data.get("queue_position")
            if qp is not None:
                logger.info("[fal] 队列中 position=%s status=%s", qp, status)

        else:
            logger.warning("[fal] 轮询超时 %ds (last_status=%s)", timeout, last_status)
            return None

        # 3. get result
        try:
            r_resp = await client.get(result_url, headers=headers)
        except Exception as exc:
            logger.warning("[fal] result 拉取异常: %s", exc)
            return None
        if r_resp.status_code != 200:
            logger.warning("[fal] result 失败 %s: %s", r_resp.status_code, r_resp.text[:800])
            return None
        try:
            r_data = r_resp.json()
        except Exception:
            logger.warning("[fal] result 非 JSON: %s", r_resp.text[:500])
            return None

        # 解析音频 URL：适配多种模型输出
        audio_url = None
        # 队列 result 通常包装为 {"data": {...}} 或直接 {...}
        payload_data = r_data.get("data") if isinstance(r_data.get("data"), dict) else r_data
        candidates = []
        for key in ("audio_file", "audio", "audio_url", "output", "file"):
            v = payload_data.get(key)
            if isinstance(v, dict) and v.get("url"):
                candidates.append(v["url"])
            elif isinstance(v, str) and v.startswith("http"):
                candidates.append(v)
            elif isinstance(v, list) and v:
                for item in v:
                    if isinstance(item, dict) and item.get("url"):
                        candidates.append(item["url"])
                    elif isinstance(item, str) and item.startswith("http"):
                        candidates.append(item)
        # 兜底：深度搜索第一个 http url
        if not candidates:
            import re
            m = re.search(r"https://[^\"]+\.(?:wav|mp3|flac|ogg|m4a)", str(r_data))
            if m:
                candidates.append(m.group(0))
        if not candidates:
            # 记录完整 result 供排查（截断）
            logger.warning("[fal] result 未找到音频 URL: %s", str(r_data)[:2000])
            return None
        audio_url = candidates[0]
        if "soundhelix" in audio_url.lower():
            logger.warning("[fal] 拒绝 soundhelix 假音频: %s", audio_url)
            return None

        # 4. 下载到 GENERATED_DIR
        try:
            local_path = await _download_to_generated(audio_url)
        except Exception as exc:
            logger.warning("[fal] 音频下载失败: %s", exc)
            return None

        fname = os.path.basename(local_path)
        # 返回 Modal 兼容的 volume_files；额外字段供日志/审计
        return {"full_wav": fname, "full_mp3": fname, "_local_path": local_path, "_fal_url": audio_url, "_request_id": request_id}
