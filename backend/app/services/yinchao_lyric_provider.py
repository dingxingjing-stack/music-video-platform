"""YinchaoLyricProvider — 音潮歌词生成同步 adapter（P4-B2 Phase B-3）。

官方契约（Phase B-1 Resolution ④，platform.yinchaoyongxian.com/docs/guides/generate-lyric
与 docs/api-reference/lyric/lyric-generate-post，核验日期 2026-10-02）：
- POST https://open.yinchaoyongxian.com/api/v1/lyric/generate
- Authorization: Bearer <YINCHAO_API_KEY>
- Request Body（application/json）: {"prompt": string}——唯一字段，官方标注长度 1–2000
- 同步返回 200: {"title": string, "lyric": string}

本 adapter 不实现轮询/callback（Yinchao Lyrics 为同步接口）；
不发送 prompt 以外的任何字段（官方未定义 model/language/style 参数）。
超时/预算由调用方（lyrics_engine）以 timeout 参数动态约束（45s 全局 hard deadline）。
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx

YINCHAO_LYRIC_URL = "https://open.yinchaoyongxian.com/api/v1/lyric/generate"


class YinchaoLyricProvider:
    """音潮歌词生成（primary）。generate() 永不抛出——失败一律返回 success=False。"""

    name = "yinchao_lyric"

    def _api_key(self) -> str:
        return (os.getenv("YINCHAO_API_KEY") or "").strip()

    async def generate(self, prompt: str, timeout: float) -> Dict[str, Any]:
        """同步生成歌词。返回：
        - 成功: {"success": True, "provider", "title": str|None, "lyric": str}
        - 失败: {"success": False, "provider", "error": str}（error 脱敏，不含 Key）
        """
        api_key = self._api_key()
        if not api_key:
            return {"success": False, "provider": self.name,
                    "error": "YINCHAO_API_KEY 未配置"}

        prompt = (prompt or "").strip()
        if not prompt:
            return {"success": False, "provider": self.name,
                    "error": "Yinchao lyrics requires prompt"}

        try:
            async with httpx.AsyncClient(timeout=max(1.0, float(timeout))) as client:
                resp = await client.post(
                    YINCHAO_LYRIC_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"prompt": prompt},
                )
        except httpx.TimeoutException:
            return {"success": False, "provider": self.name,
                    "error": "Yinchao lyrics request timeout"}
        except Exception as exc:  # noqa: BLE001
            # 不把 API Key 写入日志/错误信息
            return {"success": False, "provider": self.name,
                    "error": f"Yinchao lyrics request error: {type(exc).__name__}"}

        if resp.status_code != 200:
            return {"success": False, "provider": self.name,
                    "error": f"Yinchao lyrics HTTP {resp.status_code}"}

        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            return {"success": False, "provider": self.name,
                    "error": "Yinchao lyrics 响应不是合法 JSON"}

        if not isinstance(data, dict):
            return {"success": False, "provider": self.name,
                    "error": "Yinchao lyrics 响应结构异常"}

        title = data.get("title")
        lyric = data.get("lyric")
        if not isinstance(lyric, str) or not lyric.strip():
            return {"success": False, "provider": self.name,
                    "error": "Yinchao lyrics 响应缺少歌词内容"}

        return {
            "success": True,
            "provider": self.name,
            "title": title if isinstance(title, str) else None,
            "lyric": lyric,
        }
