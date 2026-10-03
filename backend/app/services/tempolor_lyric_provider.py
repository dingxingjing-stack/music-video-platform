"""TempolorLyricProvider — 天谱乐 Lyric v1 歌词生成异步 adapter（P4-B2 Phase B-3）。

官方契约（Phase B-1 FINAL，platform.tianpuyue.cn/docs/464626887e0 / 464626888e0 /
464626889e0，核验日期 2026-10-02）：
- Generate: POST https://api.tianpuyue.cn/open-apis/v1/lyrics/generate
    Authorization: <TEMPOLOR_API_KEY>（裸 Key，无 Bearer 前缀）
    Body: {"prompt": 必需, "song_model": string|null 可选（本阶段默认不发送）,
           "callback_url": 必需}
    200 → {"status": 200000, "message": "success", "request_id": ...,
           "data": {"item_ids": [...]}}
- Query（兜底）: POST https://api.tianpuyue.cn/open-apis/v1/lyrics/query
    Body: {"item_ids": [...]}
    200 → {"status": 200000, ..., "data": {"lyrics": [{"item_id", "status",
           "title", "lyric"}]}}
  官方提示：query 接口有限流，不应高频调用（轮询节奏由 lyrics_engine 约束）。
- Callback：本阶段未实现（B-3 裁定：query 为唯一 Melovar 接入方式）。
  callback_url 仍为官方必填字段——复用 TEMPOLOR_CALLBACK_URL（与 song 生成一致）。

本 adapter 不实现 generate 语义之外的任何重试；失败一律返回 success=False。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

TEMPOLOR_LYRICS_GENERATE_URL = "https://api.tianpuyue.cn/open-apis/v1/lyrics/generate"
TEMPOLOR_LYRICS_QUERY_URL = "https://api.tianpuyue.cn/open-apis/v1/lyrics/query"
TEMPOLOR_SUCCESS_CODE = 200000


class TempolorLyricProvider:
    """天谱乐 Lyric v1（backup）。所有方法永不抛出——失败一律返回 success=False。"""

    name = "tempolor_lyric_v1"

    def _api_key(self) -> str:
        return (os.getenv("TEMPOLOR_API_KEY") or "").strip()

    def _callback_url(self) -> str:
        # 官方必填字段；B-3 裁定不实现 callback 端点——复用与 song 生成相同的
        # 平台级回调地址配置（回调即使投递也不影响 query 兜底路径）。
        return (os.getenv("TEMPOLOR_CALLBACK_URL") or "").strip()

    async def generate(self, prompt: str, timeout: float,
                       song_model: Optional[str] = None) -> Dict[str, Any]:
        """提交歌词生成任务。返回：
        - 成功: {"success": True, "provider", "item_ids": [str, ...]}
        - 失败: {"success": False, "provider", "error": str, "error_code"?: int}
        song_model 默认 None = 不发送该字段（B-3 裁定 4；不得宣称平台缺省行为）。
        """
        api_key = self._api_key()
        if not api_key:
            return {"success": False, "provider": self.name,
                    "error": "TEMPOLOR_API_KEY 未配置"}

        prompt = (prompt or "").strip()
        if not prompt:
            return {"success": False, "provider": self.name,
                    "error": "Tempolor lyrics requires prompt"}

        payload: Dict[str, Any] = {"prompt": prompt}
        # song_model：可选字段；默认不发送（Phase B-3 裁定 4）。
        if song_model:
            payload["song_model"] = song_model

        callback_url = self._callback_url()
        if callback_url:
            payload["callback_url"] = callback_url

        try:
            async with httpx.AsyncClient(timeout=max(1.0, float(timeout))) as client:
                resp = await client.post(
                    TEMPOLOR_LYRICS_GENERATE_URL,
                    headers={"Authorization": api_key,
                             "Content-Type": "application/json"},
                    json=payload,
                )
        except httpx.TimeoutException:
            return {"success": False, "provider": self.name,
                    "error": "Tempolor lyrics generate request timeout"}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "provider": self.name,
                    "error": f"Tempolor lyrics request error: {type(exc).__name__}"}

        if resp.status_code != 200:
            return {"success": False, "provider": self.name,
                    "error": f"Tempolor lyrics HTTP {resp.status_code}"}

        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            return {"success": False, "provider": self.name,
                    "error": "Tempolor lyrics 响应不是合法 JSON"}

        biz = data.get("status") if isinstance(data, dict) else None
        if biz is not None and biz != TEMPOLOR_SUCCESS_CODE:
            result = {"success": False, "provider": self.name,
                      "error": f"Tempolor lyrics 业务错误码 {biz}"}
            if isinstance(biz, int):
                result["error_code"] = biz
            return result

        inner = data.get("data") if isinstance(data, dict) else None
        item_ids = (inner or {}).get("item_ids") if isinstance(inner, dict) else None
        if not isinstance(item_ids, list) or not item_ids:
            return {"success": False, "provider": self.name,
                    "error": "Tempolor lyrics 提交响应缺少 item_ids"}

        return {"success": True, "provider": self.name,
                "item_ids": [str(i) for i in item_ids]}

    async def query(self, item_ids: List[str], timeout: float) -> Dict[str, Any]:
        """查询歌词任务状态。返回：
        - 成功（任一 item 终态 succeeded）:
            {"success": True, "provider", "item_id", "title", "lyric"}
        - 仍在处理: {"success": False, "pending": True, "provider"}
        - 查询失败/畸形: {"success": False, "pending": False, "error"}
        """
        api_key = self._api_key()
        if not api_key:
            return {"success": False, "pending": False, "provider": self.name,
                    "error": "TEMPOLOR_API_KEY 未配置"}
        if not item_ids:
            return {"success": False, "pending": False, "provider": self.name,
                    "error": "item_ids 为空"}

        try:
            async with httpx.AsyncClient(timeout=max(1.0, float(timeout))) as client:
                resp = await client.post(
                    TEMPOLOR_LYRICS_QUERY_URL,
                    headers={"Authorization": api_key,
                             "Content-Type": "application/json"},
                    json={"item_ids": item_ids},
                )
        except httpx.TimeoutException:
            return {"success": False, "pending": True, "provider": self.name,
                    "error": "Tempolor lyrics query timeout"}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "pending": True, "provider": self.name,
                    "error": f"Tempolor lyrics query error: {type(exc).__name__}"}

        if resp.status_code != 200:
            return {"success": False, "pending": True, "provider": self.name,
                    "error": f"Tempolor lyrics query HTTP {resp.status_code}"}

        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            return {"success": False, "pending": True, "provider": self.name,
                    "error": "Tempolor lyrics query 响应不是合法 JSON"}

        biz = data.get("status") if isinstance(data, dict) else None
        if biz is not None and biz != TEMPOLOR_SUCCESS_CODE:
            return {"success": False, "pending": False, "provider": self.name,
                    "error": f"Tempolor lyrics query 业务错误码 {biz}"}

        inner = data.get("data") if isinstance(data, dict) else None
        lyrics_list = (inner or {}).get("lyrics") if isinstance(inner, dict) else None
        if not isinstance(lyrics_list, list) or not lyrics_list:
            return {"success": False, "pending": True, "provider": self.name,
                    "error": "Tempolor lyrics query 响应缺少 lyrics 列表"}

        entry = lyrics_list[0] if isinstance(lyrics_list[0], dict) else {}
        status = str(entry.get("status") or "").lower()
        if status == "failed" or status in ("error", "cancelled"):
            # 终态失败：不再 pending（是否为官方失败枚举之一联调确认）
            return {"success": False, "pending": False, "provider": self.name,
                    "error": f"Tempolor lyrics 任务失败: {status or 'unknown'}"}
        if status != "succeeded":
            return {"success": False, "pending": True, "provider": self.name,
                    "error": f"Tempolor lyrics 任务未完成: {status or 'unknown'}"}

        title = entry.get("title")
        lyric = entry.get("lyric")
        if not isinstance(lyric, str) or not lyric.strip():
            return {"success": False, "pending": False, "provider": self.name,
                    "error": "Tempolor lyrics 任务成功但缺少歌词内容"}

        return {"success": True, "provider": self.name,
                "item_id": str(entry.get("item_id") or ""),
                "title": title if isinstance(title, str) else None,
                "lyric": lyric}
