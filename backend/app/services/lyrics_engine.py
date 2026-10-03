"""LyricsEngine — Lyrics 双 Provider 编排（P4-B2 Phase B-3）。

流程（B-2 Design Revision 锁定）：

    Yinchao Lyrics primary（同步，单次）
        ↓ failure
    TemPolor Lyric v1 generate（异步提交）
        ↓
    /lyrics/query 轮询（短退避，遵守官方限流）
        ↓
    success / 全局 45s hard deadline 到期 → 失败

约束：
- TOTAL REQUEST DEADLINE = 45s（T0 起），任何 HTTP/睡眠/轮询不得越过；
  各子请求 timeout 动态受剩余预算约束（不是独立累加）。
- 同一 Provider 失败不自动重试（授权范围外）。
- 不实现 callback（B-3 裁定 1）；/lyrics/query 为唯一 Melovar 接入方式
  （「query 为交付事实源」是 Melovar 内部架构决策，非 TemPolor 官方保证）。
- 零持久化、零 Credits 交互。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Optional

from app.services.tempolor_lyric_provider import TempolorLyricProvider
from app.services.yinchao_lyric_provider import YinchaoLyricProvider

DEADLINE_SECONDS = 45.0          # 全局 hard deadline（B-3 裁定 3：45s，不提高 nginx 超时）
YINCHAO_TIMEOUT_CAP = 20.0       # Yinchao 单次 timeout 上限
TEMPOLOR_SUBMIT_TIMEOUT_CAP = 15.0
TEMPOLOR_QUERY_TIMEOUT_CAP = 10.0
QUERY_BACKOFF_SCHEDULE = (5.0, 10.0, 15.0, 15.0)  # 短退避序列（秒），服从剩余预算
MIN_TAIL_BUDGET = 2.0            # 尾部预留：低于该剩余预算即停止发起新请求


@dataclass
class UnifiedLyricResult:
    """双 Provider 统一内部结构（运行时 only，零持久化）。"""
    provider: str                     # "yinchao_lyric" | "tempolor_lyric_v1" | ""
    title: Optional[str]
    lyric: str
    item_id: Optional[str]            # TemPolor 专用；Yinchao 为 None
    status: str                       # "succeeded" | "failed"
    error: Optional[str]              # 失败原因（脱敏，不含 Key）
    fallback_used: bool               # primary 失败后由 backup 产出 = True
    elapsed_sec: float


def _fail(error: str, *, provider: str = "", fallback_used: bool = False,
          elapsed: float = 0.0, title: Optional[str] = None) -> UnifiedLyricResult:
    return UnifiedLyricResult(provider=provider, title=title, lyric="",
                              item_id=None, status="failed", error=error,
                              fallback_used=fallback_used, elapsed_sec=round(elapsed, 2))


class LyricsEngine:
    """Lyrics 双 Provider 编排器。generate() 永不抛出。"""

    def __init__(self, yinchao: Optional[YinchaoLyricProvider] = None,
                 tempolor: Optional[TempolorLyricProvider] = None,
                 deadline_seconds: float = DEADLINE_SECONDS):
        self._yinchao = yinchao or YinchaoLyricProvider()
        self._tempolor = tempolor or TempolorLyricProvider()
        self._deadline_seconds = float(deadline_seconds)

    async def generate(self, prompt: str) -> UnifiedLyricResult:
        t0 = time.monotonic()
        deadline = t0 + self._deadline_seconds

        def remaining() -> float:
            return deadline - time.monotonic()

        # ── 1° Yinchao primary（同步）────────────────────────────────
        y_timeout = max(1.0, min(YINCHAO_TIMEOUT_CAP, remaining()))
        y = await self._yinchao.generate(prompt, timeout=y_timeout)
        elapsed = time.monotonic() - t0
        if y.get("success"):
            return UnifiedLyricResult(
                provider=y["provider"], title=y.get("title"),
                lyric=y["lyric"], item_id=None, status="succeeded",
                error=None, fallback_used=False, elapsed_sec=round(elapsed, 2))
        y_error = y.get("error") or "unknown"

        # ── 2° TemPolor backup（异步提交 + query 轮询）────────────────
        # 剩余预算不足以完成「提交 + 至少一轮查询」时直接超时失败
        if remaining() <= TEMPOLOR_SUBMIT_TIMEOUT_CAP + MIN_TAIL_BUDGET:
            return _fail("歌词生成超时，请稍后重试",
                         fallback_used=True, elapsed=time.monotonic() - t0)

        t_timeout = min(TEMPOLOR_SUBMIT_TIMEOUT_CAP, max(1.0, remaining() - MIN_TAIL_BUDGET))
        t = await self._tempolor.generate(prompt, timeout=t_timeout,
                                          song_model=None)  # B-3 裁定 4：默认不发送
        elapsed = time.monotonic() - t0
        if not t.get("success"):
            t_error = t.get("error") or "unknown"
            return _fail(f"歌词生成失败（primary: {y_error[:80]}；backup: {t_error[:80]}）",
                         fallback_used=True, elapsed=time.monotonic() - t0)

        item_ids = t.get("item_ids") or []

        # ── query 轮询（短退避，服从剩余预算与官方限流）────────────────
        for backoff in QUERY_BACKOFF_SCHEDULE:
            sleep_for = min(backoff, max(0.0, remaining() - MIN_TAIL_BUDGET))
            if sleep_for <= 0:
                break
            await asyncio.sleep(sleep_for)
            if remaining() <= MIN_TAIL_BUDGET:
                break

            q_timeout = min(TEMPOLOR_QUERY_TIMEOUT_CAP, max(1.0, remaining() - MIN_TAIL_BUDGET))
            q = await self._tempolor.query(item_ids, timeout=q_timeout)

            if q.get("success"):
                return UnifiedLyricResult(
                    provider=q["provider"], title=q.get("title"),
                    lyric=q["lyric"], item_id=q.get("item_id"),
                    status="succeeded", error=None, fallback_used=True,
                    elapsed_sec=round(time.monotonic() - t0, 2))
            # pending → 继续轮询；非 pending 的失败（业务错/畸形）→ 提前终止
            if not q.get("pending", True):
                return _fail(q.get("error") or "Tempolor lyrics query failed",
                             fallback_used=True, elapsed=time.monotonic() - t0)

        # 全局 deadline 到期
        return _fail("歌词生成超时，请稍后重试", fallback_used=True,
                     elapsed=time.monotonic() - t0)


# 模块级单例（lyric_service 等调用方 import 使用；测试可对实例属性打桩）
lyrics_engine = LyricsEngine()
