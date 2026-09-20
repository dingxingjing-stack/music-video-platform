"""Paddle Billing v2 集成 —— 只服务于"积分补充包"一次性购买。

三件事：
1. `create_checkout_transaction()`：由**服务端**调 Paddle API 建单（POST /transactions），
   把 `custom_data.user_id / pack_id / credits` 写进交易。客户端拿到的只是 transaction_id，
   无法伪造"我是谁 / 我买了多少积分"。
2. `verify_webhook_signature()`：按 Paddle 官方算法验签
   （header `Paddle-Signature: ts=<ts>;h1=<sig>[;h1=<sig2>]`，
   签名串 = `f"{ts}:{raw_body}"`，HMAC-SHA256 hexdigest，常量时间比较，
   多个 h1/多个 secret 全部尝试以支持密钥轮换）。
3. `paddle_config()`：全部凭据来自环境变量，代码里零密钥。

未配置 PADDLE_API_KEY / PADDLE_WEBHOOK_SECRET 时一律 fail-closed（下单 503、回调 503），
绝不因为"没配好"而放行任何发放 Credits 的路径。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

SANDBOX_BASE_URL = "https://sandbox-api.paddle.com"
PRODUCTION_BASE_URL = "https://api.paddle.com"

# 签名串的时间戳最大可接受偏差（秒）。Paddle 官方 SDK 不做时间容差检查，
# 这里额外加一层防重放；设为 0 可关闭。
DEFAULT_WEBHOOK_MAX_AGE = int(os.getenv("PADDLE_WEBHOOK_MAX_AGE_SECONDS", "300"))


class PaddleError(Exception):
    """Paddle 侧错误（对外只暴露类型与安全消息，绝不回显密钥/上游原文）。"""


def paddle_env() -> str:
    return (os.getenv("PADDLE_ENV") or "production").strip().lower()


def api_base_url() -> str:
    return SANDBOX_BASE_URL if paddle_env() in ("sandbox", "staging") else PRODUCTION_BASE_URL


def api_key() -> str:
    return (os.getenv("PADDLE_API_KEY") or "").strip()


def webhook_secrets() -> list[str]:
    """支持逗号分隔的多个 secret（密钥轮换期新旧并存）。"""
    raw = (os.getenv("PADDLE_WEBHOOK_SECRET") or "").strip()
    return [s.strip() for s in raw.split(",") if s.strip()]


def client_token() -> str:
    return (os.getenv("PADDLE_CLIENT_TOKEN") or "").strip()


def checkout_enabled() -> bool:
    return bool(api_key())


def webhook_enabled() -> bool:
    return bool(webhook_secrets())


# ── 凭据形态与 Sandbox / Production 一致性 ───────────────────────────
# Paddle 的 client-side token 前缀标记环境：test_ = Sandbox，live_ = Production。
# 用错会直接导致"在沙箱里刷真实扣款"或反之，因此这里不只告警，而是禁止下单。
def credential_warnings() -> list[str]:
    warnings: list[str] = []
    env = paddle_env()
    token = client_token()
    if token:
        if env == "sandbox" and token.startswith("live_"):
            warnings.append("client_token_is_live_in_sandbox")
        if env == "production" and token.startswith("test_"):
            warnings.append("client_token_is_test_in_production")
    key = api_key()
    # Paddle Billing v2 的真实前缀：沙箱 pdl_sdbx_apikey_、生产 pdl_live_apikey_
    if key and not (key.startswith("pdl_sdbx_apikey_") or key.startswith("pdl_live_apikey_")):
        warnings.append("api_key_format_unexpected")
    if any(not s.startswith("pdl_ntfset_") for s in webhook_secrets()):
        warnings.append("webhook_secret_format_unexpected")
    return warnings


def checkout_blocked_reason() -> Optional[str]:
    """返回禁止下单的原因码；None 表示允许。"""
    warnings = set(credential_warnings())
    if "client_token_is_live_in_sandbox" in warnings:
        return "paddle_env_mismatch_live_token_in_sandbox"
    if "client_token_is_test_in_production" in warnings:
        return "paddle_env_mismatch_test_token_in_production"
    return None


# ── 服务端建单 ────────────────────────────────────────────────────────
async def create_checkout_transaction(*, price_id: str, custom_data: dict[str, Any],
                                      email: Optional[str] = None) -> dict[str, Any]:
    """为一次性积分包或会员订阅创建 Paddle 交易，返回 {transaction_id, checkout_url?}。

    只发送后端算出的 price_id 与 custom_data：身份（user_id）与商品语义（kind）都由
    服务端写入，客户端无法伪造"我是谁 / 我买了什么 / 该发多少积分"。
    """
    key = api_key()
    if not key:
        raise PaddleError("PADDLE_API_KEY not configured")
    if not price_id:
        raise PaddleError("price id is required")

    body: dict[str, Any] = {
        "items": [{"price_id": price_id, "quantity": 1}],
        "custom_data": dict(custom_data),
    }
    if email:
        body["customer"] = {"email": email}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{api_base_url()}/transactions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=body,
            )
    except Exception as exc:  # noqa: BLE001 - 网络异常不外泄细节
        logger.warning("Paddle transaction create failed (network): %s", type(exc).__name__)
        raise PaddleError("payment provider unreachable") from exc

    if resp.status_code not in (200, 201):
        logger.warning("Paddle create returned status %s", resp.status_code)
        raise PaddleError(f"payment provider rejected the order (status {resp.status_code})")

    try:
        data = resp.json().get("data") or {}
    except (json.JSONDecodeError, ValueError) as exc:
        raise PaddleError("unexpected response from payment provider") from exc

    txn_id = data.get("id")
    if not txn_id:
        raise PaddleError("payment provider returned no transaction id")
    return {"transaction_id": txn_id, "checkout_url": data.get("checkout_url")}


async def lookup_user_email(user_id: str) -> Optional[str]:
    """尽力取用户邮箱（Paddle 建 customer 用）。取不到不影响下单。"""
    try:
        from app.services.supabase_service import get_user
        user = get_user(user_id) or {}
        email = user.get("email")
        return email if isinstance(email, str) and email.strip() else None
    except Exception as exc:  # noqa: BLE001 - Supabase 未配置/异常都不阻断
        logger.info("email lookup skipped: %s", type(exc).__name__)
        return None


# ── webhook 验签 ─────────────────────────────────────────────────────
def _parse_signature_header(header: str) -> tuple[Optional[int], list[str]]:
    ts: Optional[int] = None
    hashes: list[str] = []
    for pair in (header or "").split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        key = key.strip()
        if key == "ts":
            try:
                ts = int(value.strip())
            except ValueError:
                ts = None
        elif key == "h1":
            hashes.append(value.strip())
    return ts, hashes


def verify_webhook_signature(raw_body: bytes, signature_header: Optional[str],
                            *, max_age: Optional[int] = None) -> bool:
    """验签 + 时间容差。任何异常/缺配置都返回 False（fail-closed）。"""
    secrets = webhook_secrets()
    if not secrets or not signature_header:
        return False
    ts, hashes = _parse_signature_header(signature_header)
    if ts is None or not hashes:
        return False

    tolerance = DEFAULT_WEBHOOK_MAX_AGE if max_age is None else max_age
    if tolerance and tolerance > 0:
        if abs(time.time() - ts) > tolerance:
            logger.warning("Paddle webhook timestamp outside tolerance (%s s)", tolerance)
            return False

    try:
        body_text = raw_body.decode("utf-8")
    except AttributeError:
        body_text = str(raw_body)

    signed_payload = f"{ts}:{body_text}".encode("utf-8")
    for secret in secrets:
        expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        for received in hashes:
            if hmac.compare_digest(expected, received):
                return True
    return False


def parse_event(payload: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """返回 (event_id, event_type, transaction_dict)。"""
    event_type = str(payload.get("event_type") or payload.get("type") or "")
    event_id = str(payload.get("event_id") or payload.get("id") or "")
    data = payload.get("data")
    if not isinstance(data, dict):
        data = {}
    return event_id, event_type, data


def extract_price_id(transaction: dict[str, Any]) -> Optional[str]:
    items = transaction.get("items") or []
    if not items or not isinstance(items, list):
        return None
    first = items[0] if isinstance(items[0], dict) else {}
    price = first.get("price") if isinstance(first.get("price"), dict) else {}
    return first.get("price_id") or price.get("id")


def extract_transaction_amount(transaction: dict[str, Any]) -> tuple[Optional[int], Optional[str]]:
    """(实收最小货币单位, 币种)。取不到时返回 (None, None)。"""
    for field in ("grand_total", "subtotal", "total"):
        value = transaction.get(field)
        if value not in (None, ""):
            try:
                amount = int(value)
            except (TypeError, ValueError):
                continue
            if amount > 0:
                return amount, str(transaction.get("currency_code") or "").upper() or None
    amounts = transaction.get("amounts") if isinstance(transaction.get("amounts"), dict) else {}
    for field in ("grand_total", "total"):
        try:
            amount = int(amounts.get(field))
        except (TypeError, ValueError):
            continue
        if amount > 0:
            return amount, str(transaction.get("currency_code") or "").upper() or None
    return None, None


def extract_subscription_id(obj: dict[str, Any]) -> Optional[str]:
    """交易/订阅事件里的订阅号。一次性积分包没有该字段 → 返回 None。"""
    for field in ("subscription_id", "id"):
        value = obj.get(field)
        if field == "id" and not str(value or "").startswith("sub_"):
            continue
        if value:
            return str(value)
    return None


def extract_billing_period(obj: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """(周期起点, 周期终点)。Paddle 在不同对象上字段名不同，这里做兼容取值。"""
    for key in ("current_billing_period", "billing_period", "next_billing_at"):
        period = obj.get(key)
        if isinstance(period, dict):
            start = period.get("started_at") or period.get("start") or period.get("date")
            end = period.get("ends_at") or period.get("end")
            if start or end:
                return (str(start) if start else None, str(end) if end else None)
    start = obj.get("current_billing_period_start") or obj.get("billing_period_start")
    end = obj.get("current_billing_period_end") or obj.get("next_bills_at")
    return (str(start) if start else None, str(end) if end else None)


def extract_customer_id(obj: dict[str, Any]) -> Optional[str]:
    """事件对象上的 Paddle customer id（ctre_...）。

    customer.* 事件里主体本身就是客户 → 取 id；交易/订阅事件只取 customer_id，
    且必须带 ctre_ 前缀，避免把 txn_/sub_ 误当客户号写进镜像表。
    """
    value = obj.get("customer_id")
    if value and str(value).startswith("ctre_"):
        return str(value)
    ident = str(obj.get("id") or "")
    return ident if ident.startswith("ctre_") else None


def extract_product_id(obj: dict[str, Any]) -> Optional[str]:
    """订阅首个条目上的 product id（pro_...）。Paddle 一个订阅当前只有一个商品条目。"""
    for item in (obj.get("items") or []):
        if not isinstance(item, dict):
            continue
        price = item.get("price")
        if isinstance(price, dict) and str(price.get("product_id") or "").startswith("pro_"):
            return str(price["product_id"])
        if str(item.get("product_id") or "").startswith("pro_"):
            return str(item["product_id"])
    return None


def extract_scheduled_change(obj: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """(计划中的动作, 生效时间)。Paddle 在 cancel_at_period_end 之前会先挂 scheduled_change。

    镜像这个字段的意义就在于：**有 scheduled_change 不等于已经失去访问权**，
    只有 status 真的变成 canceled 才收回。
    """
    change = obj.get("scheduled_change")
    if not isinstance(change, dict):
        return None, None
    action = change.get("action")
    at = change.get("resume_at") or change.get("effective_from")
    return (str(action) if action else None, str(at) if at else None)


async def create_portal_session(customer_id: str,
                                subscription_ids: Optional[list[str]] = None) -> dict[str, Any]:
    """为客户门户铸造一次性会话，返回 {url, subscription_urls, customer_id}。

    门户由 Paddle 托管，会话是临时凭据 —— 调用方必须已经通过 JWT 确认身份，
    customer_id 只能来自服务端解析结果（见 paddle_mirror.get_customer_id_for_user）。
    """
    key = api_key()
    if not key:
        raise PaddleError("PADDLE_API_KEY not configured")
    if not customer_id or not customer_id.startswith("ctre_"):
        raise PaddleError("invalid customer id")

    body: dict[str, Any] = {}
    if subscription_ids:
        body["subscription_ids"] = list(subscription_ids)

    url = f"{api_base_url()}/customers/{customer_id}/portal-sessions"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers={"Authorization": f"Bearer {key}",
                                                   "Content-Type": "application/json"},
                                     json=body or None)
    except Exception as exc:  # noqa: BLE001 - 网络异常不外泄细节
        logger.warning("Paddle portal session failed (network): %s", type(exc).__name__)
        raise PaddleError("payment provider unreachable") from exc

    if resp.status_code not in (200, 201):
        logger.warning("Paddle portal session returned status %s", resp.status_code)
        raise PaddleError(f"portal session failed ({resp.status_code})")

    try:
        data = resp.json()
    except ValueError:
        raise PaddleError("unexpected portal response")

    # 响应形状：{ id, customer_id, urls: { general: { overview }, subscriptions: [ {id,url} ] } }
    general = ((data.get("urls") or {}).get("general") or {}).get("overview")
    if not general:
        raise PaddleError("portal session missing url")
    return {"url": str(general), "subscription_urls": (data.get("urls") or {}).get("subscriptions") or [],
            "customer_id": str(data.get("customer_id") or customer_id)}
