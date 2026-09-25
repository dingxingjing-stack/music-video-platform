"""Lemon Squeezy 集成 —— 阶段一只做「服务端建单」，不发放任何 Credits。

设计前提（全部来自官方文档，逐条可查）：
1. 认证：`Authorization: Bearer {api_key}` + `Accept/Content-Type: application/vnd.api+json`，
   base `https://api.lemonsqueezy.com/v1`。官方明确要求 Key 不得出现在 client-side code，
   所以这里只给后端用，前端永远只拿到一个 checkout_url。
   （docs.lemonsqueezy.com/api/getting-started/requests）
2. 建单：`POST /v1/checkouts`，`store` 与 `variant` 走 JSON:API 的 relationships，
   响应 `data.attributes.url` 就是 Hosted Checkout 链接。
   （docs.lemonsqueezy.com/api/checkouts/create-checkout）
3. 归因：`checkout_data.custom` 是**对象**（官方示例 `{"user_id": 123}`）。本模块只写服务端
   算出的字段（user_id / kind / 条目 id / 积分数），客户端无法指定，因此不存在
   "伪造我是谁、我买了多少" 的入口。
4. 模式：API Key 分 live / test 两套，test key 只碰 test 数据；test mode 不需要商店激活。
   （docs.lemonsqueezy.com/help/getting-started/test-mode）

本阶段刻意**没有**实现 webhook 验签与发放：签名格式虽已核实（`X-Signature` =
对原始 body 的 HMAC-SHA256 hexdigest，无时间戳前缀），但 custom 是否回传到事件里、
以及幂等键设计还没实测，未验证的发放路径一律不存在，比存在但有错更安全。

未配置 LEMONSQUEEZY_API_KEY / LEMONSQUEEZY_STORE_ID / Variant ID 时一律 fail-closed。
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

API_BASE_URL = "https://api.lemonsqueezy.com/v1"
JSONAPI_TYPE = "application/vnd.api+json"

_DETAIL_MAX_CHARS = 200
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.+-]+")

# 内部条目 id → 存放 Lemon Squeezy Variant ID 的环境变量**名字**。
# 这里只映射"哪个条目对应哪个变量"，绝不重复定义价格或积分数量 ——
# 金额与积分的唯一来源仍是 credits_config，避免两处真值漂移。
# Variant 是 LS 的建模单位（product 至少一个 variant，价格挂在 variant 上），
# 且订阅与一次性共用同一机制（variant.is_subscription / interval）。
VARIANT_ENV: dict[str, str] = {
    "credits_200": "LEMONSQUEEZY_VARIANT_ID_CREDITS_200",
    "credits_500": "LEMONSQUEEZY_VARIANT_ID_CREDITS_500",
    "credits_1200": "LEMONSQUEEZY_VARIANT_ID_CREDITS_1200",
    "credits_2800": "LEMONSQUEEZY_VARIANT_ID_CREDITS_2800",
    "starter": "LEMONSQUEEZY_VARIANT_ID_STARTER",
    "basic": "LEMONSQUEEZY_VARIANT_ID_BASIC",
    "pro": "LEMONSQUEEZY_VARIANT_ID_PRO",
    "creator": "LEMONSQUEEZY_VARIANT_ID_CREATOR",
}


class LemonSqueezyError(Exception):
    """Lemon Squeezy 侧错误。对外只暴露机器码与 HTTP 状态，绝不回显密钥或上游原文。"""

    def __init__(self, message: str, *, code: Optional[str] = None,
                 status: Optional[int] = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def api_key() -> str:
    return (os.getenv("LEMONSQUEEZY_API_KEY") or "").strip()


def store_id() -> str:
    return (os.getenv("LEMONSQUEEZY_STORE_ID") or "").strip()


def webhook_secret() -> str:
    """阶段二验签用。本阶段只读不校验，也不得把值传给任何响应/日志。"""
    return (os.getenv("LEMONSQUEEZY_WEBHOOK_SECRET") or "").strip()


def checkout_enabled() -> bool:
    return bool(api_key()) and bool(store_id())


def variant_id_for(item_id: str) -> Optional[str]:
    env = VARIANT_ENV.get(item_id)
    if not env:
        return None
    return (os.getenv(env) or "").strip() or None


def configured_items() -> list[str]:
    """已配好 Variant ID 的条目 —— 前端据此决定购买走哪条链路，不猜。"""
    return [i for i in VARIANT_ENV if variant_id_for(i)]


def describe_ls_error(payload: Any) -> tuple[Optional[str], Optional[str]]:
    """从 LS 的 JSON:API 错误信封里取第一个 (code, 已打码 detail)。

    只取这两个字段。解析失败退化成 (None, None)：诊断信息缺失不能变成新故障源。
    """
    if not isinstance(payload, dict):
        return None, None
    errors = payload.get("errors")
    if not isinstance(errors, list) or not errors:
        return None, None
    first = errors[0]
    if not isinstance(first, dict):
        return None, None

    def _clean(value: Any) -> Optional[str]:
        if not isinstance(value, str) or not value:
            return None
        printable = "".join(ch for ch in value if 0x20 <= ord(ch) < 0x7F)
        cleaned = _EMAIL_RE.sub("[redacted]", printable)[:_DETAIL_MAX_CHARS]
        key = api_key()
        return cleaned.replace(key, "[redacted]") if key and cleaned else cleaned

    return _clean(first.get("code")), _clean(first.get("detail"))


def _scrub(text: str) -> str:
    """最后一道兜底：任何要写日志/抛出的字符串里若混进了 key，就地打码。"""
    key = api_key()
    return text.replace(key, "[redacted]") if key else text


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key()}",
        "Accept": JSONAPI_TYPE,
        "Content-Type": JSONAPI_TYPE,
    }


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except (json.JSONDecodeError, ValueError):
        return None


async def create_checkout(*, variant_id: str, custom: dict[str, Any],
                          redirect_url: Optional[str] = None) -> dict[str, Any]:
    """为某个 Variant 建一张 LS Checkout，返回 {checkout_url}。

    `custom` 必须由调用方（路由）用服务端算出的字段构造；本函数不接收任何来自
    客户端的价格、积分数或 Variant ID —— 那些都在路由层被挡掉了。
    """
    if not api_key():
        raise LemonSqueezyError("LEMONSQUEEZY_API_KEY not configured", code="ls_api_key_missing")
    if not store_id():
        raise LemonSqueezyError("LEMONSQUEEZY_STORE_ID not configured", code="ls_store_id_missing")
    if not variant_id:
        raise LemonSqueezyError("variant id is required", code="ls_variant_missing")

    attributes: dict[str, Any] = {"checkout_data": {"custom": dict(custom)}}
    if redirect_url:
        attributes["product_options"] = {"redirect_url": redirect_url}

    body = {
        "data": {
            "type": "checkouts",
            "attributes": attributes,
            "relationships": {
                "store": {"data": {"type": "stores", "id": store_id()}},
                "variant": {"data": {"type": "variants", "id": variant_id}},
            },
        }
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{API_BASE_URL}/checkouts",
                                     headers=_headers(), json=body)
    except Exception as exc:  # noqa: BLE001 - 网络异常不外泄细节
        logger.warning("Lemon Squeezy checkout create failed (network): %s", type(exc).__name__)
        raise LemonSqueezyError("payment provider unreachable",
                                code="ls_network_error") from exc

    if resp.status_code not in (200, 201):
        code, detail = describe_ls_error(_safe_json(resp))
        logger.warning("Lemon Squeezy 建单被拒 status=%s code=%s detail=%s",
                       resp.status_code, code or "-", detail or "-")
        raise LemonSqueezyError(_scrub(f"payment provider rejected the order (status {resp.status_code})"),
                                code=code or "ls_http_error", status=resp.status_code)

    payload = _safe_json(resp)
    try:
        data = (payload or {}).get("data") or {}
        url = (data.get("attributes") or {}).get("url")
    except AttributeError as exc:
        raise LemonSqueezyError("unexpected response from payment provider",
                                code="ls_bad_response") from exc
    if not url:
        raise LemonSqueezyError("payment provider returned no checkout url",
                                code="ls_no_checkout_url")
    return {"checkout_url": url}
