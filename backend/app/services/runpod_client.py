"""RunPod Serverless 客户端 — 用于生产环境音乐生成。

基于 RunPod Serverless REST API（https://api.runpod.ai/v2），不依赖 runpod SDK。
支持：
- RUNPOD_API_KEY（Bearer token 认证）
- RUNPOD_ENDPOINT_ID（Serverless Endpoint ID，如 abc123）
- RUNPOD_TIMEOUT 默认 300s
- RUNPOD_POLL_INTERVAL 默认 2s

认证：Header `Authorization: Bearer $RUNPOD_API_KEY`
官方文档：https://docs.runpod.io/serverless
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

# 默认模型：文本生成音乐；可通过 RUNPOD_ENDPOINT_ID 配置
# 示例 Endpoint ID 格式：abc123xyz
DEFAULT_ENDPOINT = ""
RUNPOD_BASE = "https://api.runpod.ai/v2"


def _resolve_runpod_api_key() -> Optional[str]:
    # 优先级：进程 env RUNPOD_API_KEY > secrets.local.json
    v = os.getenv("RUNPOD_API_KEY")
    if v and v.strip():
        return v.strip()
    try:
        v2 = get_secret("RUNPOD_API_KEY")
        if v2 and v2.strip():
            return v2.strip()
    except Exception:
        pass
    return None


def _resolve_endpoint_id() -> str:
    return (os.getenv("RUNPOD_ENDPOINT_ID") or "").strip()


def _resolve_timeout() -> float:
    try:
        return float(os.getenv("RUNPOD_TIMEOUT", "300"))
    except Exception:
        return 300.0


def _resolve_poll_interval() -> float:
    try:
        return float(os.getenv("RUNPOD_POLL_INTERVAL", "2"))
    except Exception:
        return 2.0


def local_dir() -> str:
    return os.getenv("GENERATED_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "generated"))


class RunPodError(Exception):
    pass


class RunPodAuthError(RunPodError):
    pass


class RunPodTimeoutError(RunPodError):
    pass


async def _download_to_generated(url: str, dest_dir: Optional[str] = None) -> str:
    """下载 RunPod 媒体 URL 到 GENERATED_DIR，返回本地路径。"""
    dest = Path(dest_dir or local_dir())
    dest.mkdir(parents=True, exist_ok=True)
    # 保留原始后缀，RunPod 通常返回 .wav / .mp3 / .flac
    suffix = ".wav"
    if url:
        low = url.lower().split("?")[0]
        for ext in (".wav", ".mp3", ".flac", ".ogg", ".m4a"):
            if low.endswith(ext):
                suffix = ext
                break
    out_path = dest / f"runpod_{int(time.time()*1000)}{suffix}"
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            raise RunPodError(f"下载 RunPod 音频失败: HTTP {resp.status_code}")
        data = resp.content
        if not data or len(data) < 1000:
            raise RunPodError(f"下载的音频过小或为空 ({len(data) if data else 0} bytes)")
        out_path.write_bytes(data)
    logger.info("[runpod] 音频已下载: %s (%d bytes)", out_path, out_path.stat().st_size)
    return str(out_path)


async def generate_via_runpod(
    prompt: str,
    lyrics: str = "",
    duration: int = 30,
    reference_audio_b64: Optional[str] = None,
    enable_audio2audio: bool = False,
) -> dict | None:
    """调用 RunPod Serverless 生成音乐，返回 volume_files 兼容结构；失败返回 None。

    volume_files 形如 {"full_wav": "<本地绝对路径或文件名>", "full_mp3": "..."}
    调用方（ai_music._upload_and_finalize）会经 download_file 取回本地文件
    并上传 R2。由于 RunPod 已直接给出可下载 URL，我们在此直接下载到 GENERATED_DIR，
    使得后续 download_file 的本地命中路径生效，不依赖 Modal Volume。
    """
    api_key = _resolve_runpod_api_key()
    if not api_key:
        logger.warning("[runpod] 未配置 RUNPOD_API_KEY，跳过 RunPod 生成")
        return None

    endpoint_id = _resolve_endpoint_id()
    if not endpoint_id:
        logger.warning("[runpod] 未配置 RUNPOD_ENDPOINT_ID，跳过 RunPod 生成")
        return None

    timeout = _resolve_timeout()
    poll_interval = _resolve_poll_interval()

    # 组合 prompt + lyrics；RunPod 模型通常接受 prompt 文本
    final_prompt = prompt.strip()
    if lyrics and lyrics.strip():
        # 避免超长 prompt 截断（保守截断）
        lyric_snippet = lyrics.strip()[:800]
        final_prompt = f"{final_prompt}. Lyrics: {lyric_snippet}" if final_prompt else lyric_snippet

    # duration 限制
    seconds_total = max(10, min(int(duration) if duration else 30, 180))

    # RunPod Serverless async endpoint: POST /v2/{endpoint_id}/run
    submit_url = f"{RUNPOD_BASE}/{endpoint_id}/run"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    # 输入 payload：根据模型要求构建
    # 假设模型接受 prompt, duration, 等参数
    payload: dict = {
        "input": {
            "prompt": final_prompt,
            "duration": int(seconds_total),
            "steps": 100,
        }
    }
    # lyrics 支持
    if lyrics and lyrics.strip():
        payload["input"]["lyrics"] = lyrics.strip()[:800]
    # audio-to-audio 支持
    if enable_audio2audio and reference_audio_b64:
        if reference_audio_b64.startswith("http"):
            payload["input"]["audio_url"] = reference_audio_b64
        elif reference_audio_b64.startswith("data:"):
            payload["input"]["audio_url"] = reference_audio_b64
        else:
            payload["input"]["audio_url"] = f"data:audio/wav;base64,{reference_audio_b64}"

    logger.info("[runpod] 提交队列: endpoint=%s prompt_len=%d duration=%ds", endpoint_id, len(final_prompt), int(seconds_total))

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. submit
        try:
            resp = await client.post(submit_url, headers=headers, json=payload)
        except Exception as exc:
            logger.warning("[runpod] 提交异常: %s", exc)
            return None

        if resp.status_code == 401:
            raise RunPodAuthError("RUNPOD_API_KEY 无效或未授权（401）")
        if resp.status_code == 429:
            logger.warning("[runpod] 队列限流 429")
            return None
        if resp.status_code not in (200, 201, 202):
            logger.warning("[runpod] 提交失败: HTTP %s body=%s", resp.status_code, resp.text[:500])
            return None

        try:
            data = resp.json()
        except Exception:
            logger.warning("[runpod] 提交响应非 JSON: %s", resp.text[:500])
            return None

        request_id = data.get("id") or data.get("request_id")
        if not request_id:
            logger.warning("[runpod] 提交响应缺 request_id: %s", str(data)[:800])
            return None

        status_url = f"{RUNPOD_BASE}/{endpoint_id}/status/{request_id}"
        logger.info("[runpod] 已入队 request_id=%s", request_id)

        # 2. poll status
        deadline = time.monotonic() + timeout
        last_status = None
        while time.monotonic() < deadline:
            await asyncio.sleep(poll_interval)
            try:
                s_resp = await client.get(status_url, headers=headers)
            except Exception as exc:
                logger.warning("[runpod] status 轮询异常: %s", exc)
                continue
            if s_resp.status_code == 404:
                logger.warning("[runpod] status 404，request_id 可能过期: %s", request_id)
                return None
            if s_resp.status_code not in (200, 202):
                logger.warning("[runpod] status 失败 %s: %s", s_resp.status_code, s_resp.text[:500])
                continue
            try:
                s_data = s_resp.json()
            except Exception:
                continue
            status = s_data.get("status")
            last_status = status
            if status in ("COMPLETED", "COMPLETED ", "completed", "succeeded"):
                break
            if status in ("FAILED", "failed", "error"):
                logger.warning("[runpod] 任务失败: %s", str(s_data)[:800])
                return None
            # IN_QUEUE / IN_PROGRESS 继续轮询
            qp = s_data.get("queue_position")
            if qp is not None:
                logger.info("[runpod] 队列中 position=%s status=%s", qp, status)

        else:
            logger.warning("[runpod] 轮询超时 %ds (last_status=%s)", timeout, last_status)
            return None

        # 3. get result
        result_url = f"{RUNPOD_BASE}/{endpoint_id}/result/{request_id}"
        try:
            r_resp = await client.get(result_url, headers=headers)
        except Exception as exc:
            logger.warning("[runpod] result 拉取异常: %s", exc)
            return None
        if r_resp.status_code != 200:
            logger.warning("[runpod] result 失败 %s: %s", r_resp.status_code, r_resp.text[:800])
            return None
        try:
            r_data = r_resp.json()
        except Exception:
            logger.warning("[runpod] result 非 JSON: %s", r_resp.text[:500])
            return None

        # 解析音频 URL：适配多种模型输出
        audio_url = None
        # RunPod result 通常包装为 {"output": {...}} 或直接 {...}
        payload_data = r_data.get("output") if isinstance(r_data.get("output"), dict) else r_data
        candidates = []
        for key in ("audio_file", "audio", "audio_url", "output", "file", "url"):
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
            logger.warning("[runpod] result 未找到音频 URL: %s", str(r_data)[:2000])
            return None
        audio_url = candidates[0]
        if "soundhelix" in audio_url.lower():
            logger.warning("[runpod] 拒绝 soundhelix 假音频: %s", audio_url)
            return None

        # 4. 下载到 GENERATED_DIR
        try:
            local_path = await _download_to_generated(audio_url)
        except Exception as exc:
            logger.warning("[runpod] 音频下载失败: %s", exc)
            return None

        fname = os.path.basename(local_path)
        # 返回 volume_files 兼容结构；额外字段供日志/审计
        return {"full_wav": fname, "full_mp3": fname, "_local_path": local_path, "_runpod_url": audio_url, "_request_id": request_id}