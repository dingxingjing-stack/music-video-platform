"""PoYoVoiceCloneProvider — PoYo(Suno) 歌唱声音克隆 Provider。

严格按 PoYo 官方 Open API（docs.poyo.ai）已核验的 contract 实现，不猜字段：

统一提交端点：
    POST https://api.poyo.ai/api/generate/submit
    body: { "model": <action>, "input": {...} }   （Bearer token 鉴权）

Voice 轮询端点（Voice 任务必须用此端点取 voice_id/validate_info/is_available）：
    GET  https://api.poyo.ai/api/generate/detail/music?task_id=...

action（model 字段）与 input：
    suno-voice-validate   : { voice_url, vocal_start_s, vocal_end_s, language? }
                            → 完成后 files[0] = { voice_status, validate_info }
    suno-voice-generate   : { task_id, verify_url, voice_name?, style?, singer_skill_level? }
                            → 完成后 files[0] = { voice_status:"success", voice_id }
    suno-voice-check      : { task_id }
                            → 完成后 files[0] = { is_available }
    suno-voice-regenerate : { task_id }
                            → 完成后 files[0] = { voice_status, validate_info }

职责边界：
    - 只负责调用 PoYo 官方 API 一次（提交 + 轮询状态），不做跨 Provider fallback、
      不做无限重试、不重复创建 Voice（exactly-once 由调用方（Router）保证：
      generate 必须持有 validate/regenerate 返回的 task_id 才能提交）。
    - 仅从环境变量 POYO_API_KEY 读 key，绝不落盘/入日志/入源码。
    - 商业授权独立于本类：是否开放给终端用户由上层 VOICE_CLONE_ENABLED + 商务授权决定。
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

POYO_BASE_URL = (os.getenv("POYO_BASE_URL") or "https://api.poyo.ai").rstrip("/")
POYO_VOICE_TIMEOUT_SECONDS = float(os.getenv("POYO_VOICE_TIMEOUT_SECONDS", "300"))
POYO_VOICE_POLL_INTERVAL_SECONDS = float(os.getenv("POYO_VOICE_POLL_INTERVAL_SECONDS", "3"))

# 官方 task 状态（task-management/status.md）
_POLLING_STATUSES = {"not_started", "running"}
_SUCCESS_STATUS = "finished"
_FAILURE_STATUS = "failed"

# 官方支持的语言枚举（voice/validate.md）
SUPPORTED_LANGUAGES = {"en", "zh", "es", "fr", "pt", "de", "ja", "ko", "hi", "ru"}


class PoYoVoiceCloneError(Exception):
    """PoYo Voice Clone 业务错误（携带稳定 message，供 Router 转 HTTP）。"""


def _api_key() -> str:
    key = os.getenv("POYO_API_KEY")
    return (key or "").strip()


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


async def _submit(client: httpx.AsyncClient, api_key: str, model: str, input_data: dict[str, Any]) -> str:
    """提交任务，返回 task_id；提交阶段非 2xx 抛 PoYoVoiceCloneError。"""
    resp = await client.post(
        f"{POYO_BASE_URL}/api/generate/submit",
        headers=_headers(api_key),
        json={"model": model, "input": input_data},
    )
    if resp.status_code >= 400:
        raise PoYoVoiceCloneError(_map_submit_error(resp))
    data = resp.json() if resp.content else {}
    task_id = data.get("data", {}).get("task_id") if isinstance(data.get("data"), dict) else None
    if not task_id:
        raise PoYoVoiceCloneError("PoYo 提交响应缺少 task_id")
    return task_id


async def _poll(client: httpx.AsyncClient, api_key: str, task_id: str, deadline: float) -> dict[str, Any]:
    """轮询 Voice 结果（GET /api/generate/detail/music），返回 data 字典（含 files）。"""
    while time.monotonic() < deadline:
        await asyncio.sleep(POYO_VOICE_POLL_INTERVAL_SECONDS)
        resp = await client.get(
            f"{POYO_BASE_URL}/api/generate/detail/music",
            headers=_headers(api_key),
            params={"task_id": task_id},
        )
        if resp.status_code >= 400:
            raise PoYoVoiceCloneError(_map_submit_error(resp))
        data = resp.json() if resp.content else {}
        d = data.get("data") if isinstance(data.get("data"), dict) else {}
        status = d.get("status")
        if status in _POLLING_STATUSES:
            continue
        if status == _FAILURE_STATUS:
            raise PoYoVoiceCloneError(f"PoYo task failed: {d.get('error_message') or 'unknown'}")
        if status == _SUCCESS_STATUS:
            return d
        # 未知状态：停止，不当作进行态无限轮询
        raise PoYoVoiceCloneError(f"PoYo unknown task status: {status}")
    raise PoYoVoiceCloneError("PoYo voice polling timeout")


def _files_first(data: dict[str, Any]) -> dict[str, Any]:
    files = data.get("files")
    if isinstance(files, list) and files and isinstance(files[0], dict):
        return files[0]
    return {}


def _map_submit_error(resp: httpx.Response) -> str:
    if resp.status_code == 401:
        return "POYO_API_KEY 无效或未授权（401）"
    if resp.status_code == 402 or resp.status_code == 429:
        body = (resp.text or "").lower()
        if any(k in body for k in ("credit", "balance", "insufficient", "quota")):
            return "PoYo 余额/配额不足（402/429）"
        return "PoYo 限流（429）"
    if resp.status_code == 400:
        return "PoYo 请求参数错误（400）"
    if resp.status_code >= 500:
        return f"PoYo 服务异常（{resp.status_code}）"
    return f"PoYo 请求失败（{resp.status_code}）"


class PoYoVoiceCloneProvider:
    """PoYo(Suno) 歌唱声音克隆 Provider。每个方法最多调用 PoYo 一次（提交 + 轮询），无内部重试。"""

    def __init__(self) -> None:
        self._api_key = _api_key()

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=30.0)

    def _deadline(self) -> float:
        return time.monotonic() + POYO_VOICE_TIMEOUT_SECONDS

    async def validate(
        self,
        voice_url: str,
        vocal_start_s: int,
        vocal_end_s: int,
        language: str = "en",
    ) -> dict[str, Any]:
        """第一步：上传参考人声 → 返回 {task_id, validate_info, voice_status}。"""
        if not self.is_configured():
            raise PoYoVoiceCloneError("POYO_API_KEY 未配置")
        if vocal_start_s < 0 or vocal_end_s <= vocal_start_s:
            raise PoYoVoiceCloneError("vocal_start_s/vocal_end_s 无效")
        if language not in SUPPORTED_LANGUAGES:
            raise PoYoVoiceCloneError(f"language 不支持: {language}")
        input_data = {
            "voice_url": voice_url,
            "vocal_start_s": vocal_start_s,
            "vocal_end_s": vocal_end_s,
            "language": language,
        }
        async with self._client() as client:
            task_id = await _submit(client, self._api_key, "suno-voice-validate", input_data)
            data = await _poll(client, self._api_key, task_id, self._deadline())
            f = _files_first(data)
            return {
                "task_id": task_id,
                "validate_info": f.get("validate_info"),
                "voice_status": f.get("voice_status"),
            }

    async def generate(
        self,
        task_id: str,
        verify_url: str,
        voice_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """第二步：用验证短语录音创建 Voice ID → 返回 {voice_id, voice_status}。"""
        if not self.is_configured():
            raise PoYoVoiceCloneError("POYO_API_KEY 未配置")
        if not task_id:
            raise PoYoVoiceCloneError("缺少 validate/regenerate 的 task_id")
        if not verify_url:
            raise PoYoVoiceCloneError("缺少 verify_url（朗读验证短语的录音）")
        input_data: dict[str, Any] = {"task_id": task_id, "verify_url": verify_url}
        if voice_name:
            input_data["voice_name"] = voice_name
        async with self._client() as client:
            gen_task_id = await _submit(client, self._api_key, "suno-voice-generate", input_data)
            data = await _poll(client, self._api_key, gen_task_id, self._deadline())
            f = _files_first(data)
            return {
                "task_id": gen_task_id,
                "voice_id": f.get("voice_id"),
                "voice_status": f.get("voice_status"),
            }

    async def check(self, task_id: str) -> dict[str, Any]:
        """检查已生成的 Voice ID 是否仍可用 → {is_available}。"""
        if not self.is_configured():
            raise PoYoVoiceCloneError("POYO_API_KEY 未配置")
        if not task_id:
            raise PoYoVoiceCloneError("缺少 generate 的 task_id")
        async with self._client() as client:
            t = await _submit(client, self._api_key, "suno-voice-check", {"task_id": task_id})
            data = await _poll(client, self._api_key, t, self._deadline())
            f = _files_first(data)
            return {"task_id": t, "is_available": f.get("is_available")}

    async def regenerate(self, task_id: str) -> dict[str, Any]:
        """验证短语过期/失效时重新索取 → {task_id, validate_info}。"""
        if not self.is_configured():
            raise PoYoVoiceCloneError("POYO_API_KEY 未配置")
        if not task_id:
            raise PoYoVoiceCloneError("缺少 validate 的 task_id")
        async with self._client() as client:
            t = await _submit(client, self._api_key, "suno-voice-regenerate", {"task_id": task_id})
            data = await _poll(client, self._api_key, t, self._deadline())
            f = _files_first(data)
            return {
                "task_id": t,
                "validate_info": f.get("validate_info"),
                "voice_status": f.get("voice_status"),
            }


# 进程内单例（Router 依赖注入用）
poyo_voice_clone_provider = PoYoVoiceCloneProvider()