"""MurekaProvider — Mureka 官方 API（api.mureka.ai）音乐生成 Provider。

Phase API-2B：在现有 Provider 架构中新增 MurekaProvider 作为生产 PRIMARY。

职责边界（严格）：
- 只负责 Mureka 官方 API 两段式调用：
    POST /v1/song/generate        → 提交，拿到 task_id
    GET  /v1/song/query/{task_id} → 轮询，直到终态 → 下载音频
- 失败/未知状态一律返回 success=False，交由上层 ProviderRegistry.fallback_chain()
  与 ai_music.py 依次接管 RunPod → Fal → HF。
- **不 reserve / 不 refund / 不修改 quota**（额度全在上层 ai_limits）。
- **不实现跨 Provider fallback**（严禁在 Provider 内部接 RunPod）。
- **不发送 duration**（官方 /v1/song/generate 未确认该字段）。

本文件不引用 legacy mureka_service.py / inference/mureka.py，二者继续保留。
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from app.services.provider_registry import BaseProvider

logger = logging.getLogger(__name__)

# ── 环境变量（不做模块级 required，避免缺 Key 导致启动失败）──
MUREKA_BASE_URL = (os.getenv("MUREKA_BASE_URL") or "https://api.mureka.ai").rstrip("/")
MUREKA_MODEL = os.getenv("MUREKA_MODEL", "auto")
MUREKA_TIMEOUT_SECONDS = float(os.getenv("MUREKA_TIMEOUT_SECONDS", "300"))
MUREKA_POLL_INTERVAL_SECONDS = float(os.getenv("MUREKA_POLL_INTERVAL_SECONDS", "3"))

# 提示词官方上限（超出安全的截断，不违反合同）
PROMPT_MAX_CHARS = 1024
LYRICS_MAX_CHARS = 5000

# 官方 task 状态全集（权威来源 platform.mureka.ai/docs）
_POLLING_STATUSES = {"preparing", "queued", "running", "streaming"}
_SUCCESS_STATUSES = {"succeeded"}
_FAILURE_STATUSES = {"failed", "timeouted", "cancelled"}


def local_dir() -> str:
    """与 runpod_client/fal_client 一致的生成目录（GENERATED_DIR）。"""
    return os.getenv(
        "GENERATED_DIR",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "generated"),
    )


def _download_audio(url: str, dest_dir: Optional[str] = None) -> Optional[str]:
    """下载 Mureka 音频 URL 到 GENERATED_DIR，返回本地绝对路径；失败返回 None。

    不假设文件一定是 WAV/MP3，按 URL 后缀保留扩展名；不把一种格式改名成另一种。
    """
    dest = Path(dest_dir or local_dir())
    dest.mkdir(parents=True, exist_ok=True)
    suffix = ".wav"
    if url:
        low = url.lower().split("?")[0]
        for ext in (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"):
            if low.endswith(ext):
                suffix = ext
                break
    out_path = dest / f"mureka_{int(time.time() * 1000)}{suffix}"
    try:
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            resp = client.get(url)
        if resp.status_code != 200:
            logger.warning("[mureka] 音频下载失败: HTTP %s", resp.status_code)
            return None
        data = resp.content
        if not data or len(data) < 1000:
            logger.warning("[mureka] 音频过小或为空 (%d bytes)", len(data) if data else 0)
            return None
        out_path.write_bytes(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[mureka] 音频下载异常: %s", exc)
        return None
    logger.info("[mureka] 音频已下载: %s (%d bytes)", out_path, out_path.stat().st_size)
    return str(out_path)


def _extract_audio_url(data: dict) -> Optional[str]:
    """防御性解析 Mureka 成功任务的音频下载 URL。

    仅支持当前已知候选字段（wav_url / audio_url / url），不臆造官方合同字段；
    choices[] 内部精确嵌套留待真实响应进一步确认，这里做多层级兜底。
    找不到可下载 URL 返回 None。
    """
    if not isinstance(data, dict):
        return None

    # 1) 顶层字段
    for key in ("wav_url", "audio_url", "url"):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()

    # 2) data 嵌套对象
    inner = data.get("data")
    if isinstance(inner, dict):
        for key in ("wav_url", "audio_url", "url"):
            v = inner.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()

    # 3) choices / songs 数组第一个元素
    for list_key in ("choices", "songs"):
        items = data.get(list_key)
        if not isinstance(items, list) or not items:
            continue
        first = items[0]
        if not isinstance(first, dict):
            continue
        for key in ("wav_url", "audio_url", "url", "song_url", "mp3_url"):
            v = first.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        # 嵌套 audio / urls 对象兜底
        nested = first.get("audio") or first.get("urls") or first.get("song_urls")
        if isinstance(nested, dict):
            for key in ("wav_url", "audio_url", "url", "wav", "mp3"):
                v = nested.get(key)
                if isinstance(v, str) and v.strip():
                    return v.strip()

    return None


class MurekaProvider(BaseProvider):
    """Mureka 官方 API Provider（生产 PRIMARY，PHASE API-2B）。"""

    name = "mureka"
    provider_type = "api"
    capabilities = ["lyrics_to_music"]
    # 官方 /v1/song/generate 无 duration 参数，不声明 max_duration（保留基类默认 0）。
    gpu = "mureka"
    production = True

    # ── 内部工具 ────────────────────────────────────────────

    def _api_key(self) -> str:
        """惰性读取 API Key（缺 Key 不崩溃，返回空串交由 generate 判空）。"""
        key = os.getenv("MUREKA_API_KEY")
        if key and key.strip():
            return key.strip()
        try:
            from app.core.secrets import get_secret
            v = get_secret("MUREKA_API_KEY", required=False)
            return (v or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    async def health_check(self) -> dict:
        return {"healthy": bool(self._api_key()), "provider": self.name}

    # ── 主逻辑 ──────────────────────────────────────────────

    async def generate(self, request: dict) -> dict:
        """调用 Mureka 生成歌曲；失败返回 success=False，由上层 fallback 接管。"""
        api_key = self._api_key()
        if not api_key:
            return {"success": False, "error": "MUREKA_API_KEY 未配置", "provider": self.name}

        # ── 输入转换：只提取 Mureka 真正支持的字段 ──
        lyrics = (request.get("lyrics") or "").strip()
        if not lyrics:
            return {"success": False, "error": "Mureka requires lyrics", "provider": self.name}
        lyrics = lyrics[:LYRICS_MAX_CHARS]

        prompt = (request.get("prompt") or "").strip()
        prompt = prompt[:PROMPT_MAX_CHARS]

        model = (request.get("model") or MUREKA_MODEL) or "auto"

        # 第一版固定 n=1，不扩展成本（官方 n 最大 3，但默认请求 1 首）
        payload: dict[str, Any] = {
            "lyrics": lyrics,
            "model": model,
            "prompt": prompt,
            "n": 1,
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        submit_url = f"{MUREKA_BASE_URL}/v1/song/generate"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # 1) 提交
                resp = await client.post(submit_url, headers=headers, json=payload)
                trace_id: Optional[str] = None
                if resp.status_code != 200:
                    return self._map_submit_error(resp)

                data = resp.json() if resp.content else {}
                trace_id = data.get("trace_id")
                mureka_task_id = data.get("id") or data.get("task_id")
                if not mureka_task_id:
                    logger.warning("[mureka] 提交响应缺少 id/task_id: %s", str(data)[:300])
                    return {"success": False, "error": "Mureka 提交响应缺少 task id", "provider": self.name}

                logger.info("[mureka] task=%s trace=%s 已提交", mureka_task_id, trace_id)

                # 2) 轮询
                query_url = f"{MUREKA_BASE_URL}/v1/song/query/{mureka_task_id}"
                deadline = time.monotonic() + MUREKA_TIMEOUT_SECONDS
                while time.monotonic() < deadline:
                    await asyncio.sleep(MUREKA_POLL_INTERVAL_SECONDS)
                    q = await client.get(query_url, headers=headers)
                    if q.status_code != 200:
                        return {"success": False, "error": f"Mureka query HTTP {q.status_code}", "provider": self.name}
                    qdata = q.json() if q.content else {}
                    status = qdata.get("status")
                    logger.info("[mureka] task=%s trace=%s status=%s", mureka_task_id, trace_id, status)

                    if status in _SUCCESS_STATUSES:
                        audio_url = _extract_audio_url(qdata)
                        if not audio_url:
                            return {"success": False, "error": "Mureka response contains no downloadable audio URL", "provider": self.name}
                        local_path = await asyncio.to_thread(_download_audio, audio_url)
                        if not local_path:
                            return {"success": False, "error": "Mureka 音频下载失败", "provider": self.name}
                        fname = os.path.basename(local_path)
                        return {
                            "success": True,
                            "volume_files": {
                                "full_wav": fname,
                                "full_mp3": fname,
                                "_local_path": local_path,
                                "_mureka_url": audio_url,
                                "_trace_id": trace_id,
                            },
                            "provider": self.name,
                        }

                    if status in _FAILURE_STATUSES:
                        return {"success": False, "error": f"Mureka task {status}: {mureka_task_id}", "provider": self.name}

                    if status in _POLLING_STATUSES:
                        continue

                    # 未知 status：记录并停止轮询，绝不当作进行态无限轮询
                    logger.warning(
                        "[mureka] 未知 status task=%s trace=%s status=%s → 停止轮询",
                        mureka_task_id, trace_id, status,
                    )
                    return {
                        "success": False,
                        "error": f"Mureka unknown task status: {status}",
                        "provider": self.name,
                    }

                return {"success": False, "error": "Mureka polling timeout", "provider": self.name}

        except httpx.TimeoutException:
            return {"success": False, "error": "Mureka request timeout", "provider": self.name}
        except Exception as exc:  # noqa: BLE001
            logger.warning("[mureka] 生成异常: %s", exc)
            return {"success": False, "error": f"Mureka generation error: {exc}", "provider": self.name}

    def _map_submit_error(self, resp: httpx.Response) -> dict:
        """把提交阶段 HTTP 错误映射为 provider failure（区分 quota，不做内部无限 retry）。"""
        err = f"Mureka submit HTTP {resp.status_code}"
        try:
            body = resp.text[:300]
        except Exception:  # noqa: BLE001
            body = ""
        if resp.status_code == 401:
            err = "MUREKA_API_KEY 无效或未授权（401）"
        elif resp.status_code == 400:
            err = "Mureka 请求参数错误（400）"
        elif resp.status_code == 403:
            err = "Mureka 区域/权限限制（403）"
        elif resp.status_code == 429:
            low = body.lower()
            if any(k in low for k in ("quota", "credit", "billing", "balance")):
                err = "Mureka 配额耗尽（429 quota）"
            else:
                err = "Mureka 限流（429 rate limit）"
        elif resp.status_code == 503:
            err = "Mureka 引擎过载（503）"
        logger.warning("[mureka] %s body=%s", err, body)
        return {"success": False, "error": err, "provider": self.name}