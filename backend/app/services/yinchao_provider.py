"""YinchaoProvider — 音潮开放平台（open.yinchaoyongxian.com）音乐生成 Provider。

Phase：将已通过真实 Render → 音潮 V4.0 测试的音潮 API，正式接入 Provider fallback 链。

职责边界（严格，与 MurekaProvider 一致）：
- 只负责音潮官方 API 两段式调用：
    POST /api/v1/song/generate       → 提交，拿到 task_id
    GET  /api/v1/task/query?task_id= → 轮询，直到终态 → 下载音频
- 失败/未知状态一律返回 success=False，交由上层 ProviderRegistry.fallback_chain()
  与 ai_music.py 依次接管（Yinchao → Mureka → RunPod/Fal）。
- **不 reserve / 不 refund / 不修改 quota**（额度全在上层 ai_limits）。
- **不实现跨 Provider fallback**。
- **不发送 duration、不映射 lyrics**（音潮 V4.0 generate 无 duration；本阶段固定
  task_type="normal" 由音潮自动写词，不强行注入 lyrics）。
- 不把音潮第三方 audio_url 返回给前端；本地下载后仅暴露 _local_path 给上层 R2 流程。

本文件不依赖 yinchao_test.py；二者各自独立。
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
YINCHAO_BASE_URL = (os.getenv("YINCHAO_API_BASE_URL") or "https://open.yinchaoyongxian.com").rstrip("/")
YINCHAO_TIMEOUT_SECONDS = float(os.getenv("YINCHAO_TIMEOUT_SECONDS", "240"))
YINCHAO_POLL_INTERVAL_SECONDS = float(os.getenv("YINCHAO_POLL_INTERVAL_SECONDS", "3"))

# 官方 task 状态（choices[0].status；来自真实 API 实测）
_POLLING_STATUSES = {"pending", "running", "stream"}
_SUCCESS_STATUSES = {"done"}
_FAILURE_STATUSES = {"fail"}


def local_dir() -> str:
    """与 mureka_provider / runpod_client / fal_client 一致的生成目录（GENERATED_DIR）。"""
    return os.getenv(
        "GENERATED_DIR",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "generated"),
    )


def _download_audio(url: str, dest_dir: Optional[str] = None) -> Optional[str]:
    """下载音潮音频 URL 到本地生成目录，返回本地绝对路径；失败返回 None。

    不假设文件格式，按 URL 后缀保留真实扩展名；不把一种格式改名成另一种。
    """
    dest = Path(dest_dir or local_dir())
    dest.mkdir(parents=True, exist_ok=True)
    suffix = ".mp3"
    if url:
        low = url.lower().split("?")[0]
        for ext in (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"):
            if low.endswith(ext):
                suffix = ext
                break
    out_path = dest / f"yinchao_{int(time.time() * 1000)}{suffix}"
    try:
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            resp = client.get(url)
        if resp.status_code != 200:
            logger.warning("[yinchao] 音频下载失败: HTTP %s", resp.status_code)
            return None
        data = resp.content
        if not data or len(data) < 1000:
            logger.warning("[yinchao] 音频过小或为空 (%d bytes)", len(data) if data else 0)
            return None
        out_path.write_bytes(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[yinchao] 音频下载异常: %s", exc)
        return None
    logger.info("[yinchao] 音频已下载: %s (%d bytes)", out_path, out_path.stat().st_size)
    return str(out_path)


class YinchaoProvider(BaseProvider):
    """音潮开放平台 API Provider（text_to_music，生产 PRIMARY 候选）。"""

    name = "yinchao"
    provider_type = "api"
    capabilities = ["text_to_music"]
    # 音潮 V4.0 generate 无 duration 参数，不声明 max_duration（保留基类默认 0）。
    gpu = "yinchao-cloud"
    production = True

    # ── 内部工具 ────────────────────────────────────────────

    def _api_key(self) -> str:
        """惰性读取 API Key（缺 Key 不崩溃，返回空串交由 generate 判空）。"""
        key = os.getenv("YINCHAO_API_KEY")
        if key and key.strip():
            return key.strip()
        try:
            from app.core.secrets import get_secret
            v = get_secret("YINCHAO_API_KEY", required=False)
            return (v or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    async def health_check(self) -> dict:
        return {"healthy": bool(self._api_key()), "provider": self.name}

    # ── 主逻辑 ──────────────────────────────────────────────

    async def generate(self, request: dict) -> dict:
        """调用音潮生成歌曲；失败一律返回 success=False，由上层 fallback 接管。"""
        api_key = self._api_key()
        if not api_key:
            return {"success": False, "error": "YINCHAO_API_KEY is not configured", "provider": self.name}

        prompt = (request.get("prompt") or "").strip()
        if not prompt:
            return {"success": False, "error": "Yinchao requires prompt", "provider": self.name}

        # 音潮请求体固定字段；不映射 lyrics / 忽略 duration（见模块 docstring）
        payload: dict[str, Any] = {
            "model": "v4.0",
            "task_type": "normal",
            "prompt": prompt,
            "n": 1,
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        submit_url = f"{YINCHAO_BASE_URL}/api/v1/song/generate"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # 1) 提交
                resp = await client.post(submit_url, headers=headers, json=payload)
                if resp.status_code != 200:
                    return self._map_submit_error(resp)

                data = resp.json() if resp.content else {}
                task_id = data.get("id") if isinstance(data, dict) else None
                if not task_id:
                    logger.warning("[yinchao] 提交响应缺少 id: %s", str(data)[:300])
                    return {"success": False, "error": "Yinchao 提交响应缺少 task id", "provider": self.name}

                logger.info("[yinchao] task=%s 已提交", task_id)

                # 2) 轮询
                query_url = f"{YINCHAO_BASE_URL}/api/v1/task/query"
                deadline = time.monotonic() + YINCHAO_TIMEOUT_SECONDS
                while time.monotonic() < deadline:
                    await asyncio.sleep(YINCHAO_POLL_INTERVAL_SECONDS)
                    q = await client.get(query_url, params={"task_id": task_id}, headers=headers)
                    if q.status_code != 200:
                        logger.warning("[yinchao] query HTTP %s", q.status_code)
                        continue
                    qd = q.json() if q.content else {}
                    choices = qd.get("choices") if isinstance(qd, dict) else None
                    choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
                    status = choice.get("status")

                    if status in _SUCCESS_STATUSES:
                        audio_url = choice.get("audio_url")
                        if not audio_url:
                            return {"success": False, "error": "Yinchao response contains no downloadable audio URL", "provider": self.name}
                        local_path = await asyncio.to_thread(_download_audio, audio_url)
                        if not local_path:
                            return {"success": False, "error": "Yinchao 音频下载失败", "provider": self.name}
                        fname = os.path.basename(local_path)
                        return {
                            "success": True,
                            "volume_files": {
                                # 音潮实际返回 mp3：full_mp3/full_wav 均指向真实文件，
                                # 不伪造 WAV、不改扩展名；上层 _upload_and_finalize 优先用 _local_path。
                                "full_mp3": fname,
                                "full_wav": fname,
                                "_local_path": local_path,
                                "_yinchao_url": audio_url,
                            },
                            "provider": self.name,
                        }

                    if status in _FAILURE_STATUSES:
                        err_code = choice.get("error_code")
                        err = choice.get("error") or "task failed"
                        logger.warning("[yinchao] task=%s fail code=%s error=%s", task_id, err_code, err)
                        return {
                            "success": False,
                            "error": f"Yinchao task failed ({err_code} {err})" if err_code else f"Yinchao task failed: {err}",
                            "provider": self.name,
                        }

                    if status in _POLLING_STATUSES:
                        continue

                    # 未知 status：停止轮询，不当作进行态（与 MurekaProvider 同策略）
                    logger.warning("[yinchao] task=%s 未知 status=%s → 停止轮询", task_id, status)
                    return {"success": False, "error": f"Yinchao unknown task status: {status}", "provider": self.name}

                return {"success": False, "error": "Yinchao polling timeout", "provider": self.name}

        except httpx.TimeoutException:
            return {"success": False, "error": "Yinchao request timeout", "provider": self.name}
        except Exception as exc:  # noqa: BLE001
            # 绝不把 API Key / Authorization 写入日志；exc 本身不含 Key
            logger.warning("[yinchao] 生成异常: %s", exc)
            return {"success": False, "error": f"Yinchao generation error: {exc}", "provider": self.name}

    def _map_submit_error(self, resp: httpx.Response) -> dict:
        """把提交阶段 HTTP 错误映射为 provider failure（不内部无限 retry，不泄露 Secret）。"""
        err = f"Yinchao submit HTTP {resp.status_code}"
        try:
            body = resp.text[:300]
        except Exception:  # noqa: BLE001
            body = ""
        if resp.status_code == 401:
            err = "YINCHAO_API_KEY 无效或未授权（401）"
        elif resp.status_code == 400:
            err = "Yinchao 请求参数错误（400）"
        elif resp.status_code == 403:
            err = "Yinchao 区域/权限限制（403）"
        elif resp.status_code == 402:
            err = "Yinchao 余额不足（402）"
        elif resp.status_code == 429:
            low = body.lower()
            if any(k in low for k in ("quota", "credit", "balance", "余额", "额度")):
                err = "Yinchao 配额耗尽（429 quota）"
            else:
                err = "Yinchao 限流（429 rate limit）"
        elif resp.status_code == 503:
            err = "Yinchao 引擎过载（503）"
        # 不把完整 body 写日志（可能含敏感内容），只记录状态码
        logger.warning("[yinchao] submit 失败 http=%s", resp.status_code)
        return {"success": False, "error": err, "provider": self.name}