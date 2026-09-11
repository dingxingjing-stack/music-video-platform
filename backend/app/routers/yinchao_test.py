"""音潮（Yinchao）连通性测试端点 —— 临时、隔离、默认关闭、仅测试。

用途单一：验证「本后端（如 Render 生产环境）→ 音潮开放平台」的完整链路。
绝不属于生产用户音乐生成流程。

安全门控（双重）：
1. 总开关：环境变量 ENABLE_YINCHAO_TEST == "true" 才启用；否则直接 404。
2. Token：请求头 X-Yinchao-Test-Token 必须等于环境变量 YINCHAO_TEST_TOKEN；否则 403。
默认关闭：ENABLE_YINCHAO_TEST 缺失/非 "true" 时端点对外表现为 404。

不输出/记录：完整 API Key、完整 Authorization、完整 audio_url（若含签名 token）。
"""

from __future__ import annotations

import asyncio
import os
import time

import httpx
from fastapi import APIRouter, Header, HTTPException

router = APIRouter(prefix="/api/v1/ai/test", tags=["yinchao-test"])

YINCHAO_BASE = (os.getenv("YINCHAO_API_BASE_URL") or "https://open.yinchaoyongxian.com").rstrip("/")
POLL_INTERVAL = 3
POLL_TIMEOUT = 240


def _enabled() -> bool:
    return (os.getenv("ENABLE_YINCHAO_TEST") or "").strip().lower() == "true"


def _token_ok(header: str | None) -> bool:
    expected = (os.getenv("YINCHAO_TEST_TOKEN") or "").strip()
    if not expected:
        return False
    return header == expected


@router.get("/yinchao")
async def yinchao_connectivity_test(x_yinchao_test_token: str | None = Header(default=None)):
    """执行一次音潮 V4.0 最小生成，验证完整链路。受 ENABLE_YINCHAO_TEST + token 双重门控。"""
    # 门控 1：总开关（未开启 → 404，不暴露端点存在性）
    if not _enabled():
        raise HTTPException(status_code=404, detail="Not Found")

    # 门控 2：token
    if not _token_ok(x_yinchao_test_token):
        raise HTTPException(status_code=403, detail="Forbidden")

    # Step 1：Key 检查（绝不输出 Key）
    key = (os.getenv("YINCHAO_API_KEY") or "").strip()
    if not key:
        return {
            "success": False,
            "provider": "yinchao",
            "task_id": None,
            "status": "error",
            "error_code": "NO_KEY",
            "error": "YINCHAO_API_KEY is not configured",
        }

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "v4.0",
        "task_type": "normal",
        "prompt": "一首轻快的中文流行歌曲，主题是夏日海边的回忆，女声演唱，现代流行音乐风格",
        "n": 1,
    }

    started = time.monotonic()

    # Step 2：提交生成
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(f"{YINCHAO_BASE}/api/v1/song/generate", headers=headers, json=payload)
            if r.status_code != 200:
                return {
                    "success": False,
                    "provider": "yinchao",
                    "task_id": None,
                    "status": "submit_fail",
                    "error_code": f"HTTP_{r.status_code}",
                    "error": (r.text or "")[:300],
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                }
            data = r.json() if r.content else {}
            task_id = data.get("id") if isinstance(data, dict) else None
            if not task_id:
                return {
                    "success": False,
                    "provider": "yinchao",
                    "task_id": None,
                    "status": "submit_fail",
                    "error_code": "NO_TASK_ID",
                    "error": "generate returned no task id",
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                }

            # Step 3/4：轮询
            deadline = time.monotonic() + POLL_TIMEOUT
            final_status = None
            final_choice: dict = {}
            while time.monotonic() < deadline:
                await asyncio.sleep(POLL_INTERVAL)
                q = await client.get(
                    f"{YINCHAO_BASE}/api/v1/task/query", params={"task_id": task_id}, headers=headers
                )
                if q.status_code != 200:
                    continue
                qd = q.json() if q.content else {}
                choices = qd.get("choices") if isinstance(qd, dict) else None
                choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
                status = choice.get("status")
                if status in ("done", "fail"):
                    final_status = status
                    final_choice = choice
                    break

            elapsed = round(time.monotonic() - started, 2)

            # Step 5：结果
            if final_status == "done":
                title = final_choice.get("title") or ""
                duration = final_choice.get("duration") or 0
                audio_url = final_choice.get("audio_url") or ""
                audio_available = bool(audio_url)
                # 仅在服务端做一次 HEAD 探测，不把完整 URL 返回给调用者
                if audio_available:
                    try:
                        hr = await client.head(audio_url, timeout=30, follow_redirects=True)
                        audio_available = hr.status_code == 200
                    except Exception:
                        audio_available = False
                return {
                    "success": True,
                    "provider": "yinchao",
                    "task_id": task_id,
                    "status": "done",
                    "title": title,
                    "duration": duration,
                    "audio_url_available": audio_available,
                    "elapsed_seconds": elapsed,
                }

            if final_status == "fail":
                return {
                    "success": False,
                    "provider": "yinchao",
                    "task_id": task_id,
                    "status": "fail",
                    "error_code": final_choice.get("error_code") or "FAIL",
                    "error": (final_choice.get("error") or "task failed"),
                    "elapsed_seconds": elapsed,
                }

            # 超时
            return {
                "success": False,
                "provider": "yinchao",
                "task_id": task_id,
                "status": "timeout",
                "error_code": "TIMEOUT",
                "error": f"task not terminal within {POLL_TIMEOUT}s",
                "elapsed_seconds": elapsed,
            }
    except httpx.TimeoutException:
        return {
            "success": False,
            "provider": "yinchao",
            "task_id": None,
            "status": "network_error",
            "error_code": "TIMEOUT",
            "error": "request timeout",
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
    except Exception as e:  # noqa: BLE001
        return {
            "success": False,
            "provider": "yinchao",
            "task_id": None,
            "status": "network_error",
            "error_code": type(e).__name__,
            "error": str(e)[:300],
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }