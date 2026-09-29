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

本模块现在包含 webhook 的**验签与解析**（P2-1），但**仍然没有任何发放路径**：
2026-09-25 用完全隔离的 Test Mode 接收端实测过真实 payload 后，签名算法、
`meta.custom_data` 回传、`meta.webhook_id` 跨重试稳定性都已确认；而 Credits 发放
涉及资金，必须在验签→幂等→台账三层都落地并测过之后才允许存在。

未配置 LEMONSQUEEZY_API_KEY / LEMONSQUEEZY_STORE_ID / Variant ID 时一律 fail-closed。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from sqlalchemy.exc import IntegrityError

from app.db import database as db
from app.db.database import LemonSqueezyPurchase
from app.services import credits_service
from app.services.credits_config import CREDIT_PACKS, CREDIT_PACK_CURRENCY

logger = logging.getLogger(__name__)

API_BASE_URL = "https://api.lemonsqueezy.com/v1"
JSONAPI_TYPE = "application/vnd.api+json"

_DETAIL_MAX_CHARS = 200
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.+-]+")

# 本项目用户主身份 = Supabase auth.users.id（verified JWT 的 sub），规范形态是 UUID。
# 只用于"拒绝明显不合法的归因目标"，不用于查用户是否存在（那是 add_credits 的事）。
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_USER_ID_MAX_LEN = 255                     # 与 user_credits.user_id 列宽一致

# X-Signature 是 HMAC-SHA256 的 hex digest ⇒ 恰好 64 个十六进制字符。
# 先按形状挡掉畸形头，避免把垃圾字符串喂进 compare_digest。
_SIGNATURE_HEX_LEN = 64
_HEX_CHARS = frozenset("0123456789abcdef")

# ── Webhook 事件名与对象类型（2026-09-25 真实 Test Mode 投递实测）──────────
LS_OBJECT_ORDER = "orders"
LS_OBJECT_SUBSCRIPTION = "subscriptions"
LS_OBJECT_INVOICE = "subscription-invoices"

LS_EVENT_ORDER_CREATED = "order_created"
LS_EVENT_ORDER_REFUNDED = "order_refunded"
LS_EVENT_SUBSCRIPTION_CREATED = "subscription_created"
LS_EVENT_SUBSCRIPTION_UPDATED = "subscription_updated"
LS_EVENT_SUBSCRIPTION_CANCELLED = "subscription_cancelled"
LS_EVENT_SUBSCRIPTION_PAYMENT_SUCCESS = "subscription_payment_success"
LS_EVENT_SUBSCRIPTION_PAYMENT_RECOVERED = "subscription_payment_recovered"
LS_EVENT_SUBSCRIPTION_PAYMENT_FAILED = "subscription_payment_failed"
LS_EVENT_SUBSCRIPTION_PAYMENT_REFUNDED = "subscription_payment_refunded"

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


def webhook_enabled() -> bool:
    """Webhook 是否可用（secret 已配）。

    必须与建单能力分开判断：一条"能收钱但回调恒 503"的链路等于收了钱不发积分，
    是本仓已知最伤口碑的故障形态，因此这里要能被上层单独识别并 fail-closed。
    """
    return bool(webhook_secret())


def checkout_enabled() -> bool:
    """能否建单。

    刻意把 `webhook_enabled()` 纳入：LS 的 Webhook 在 secret 缺失时是 503（fail-closed），
    若此时仍允许建单，用户会完成付款而积分永远不到账。宁可整条链路关闭、让前端
    回落到 Paddle，也不制造"付了钱没东西"的订单。
    """
    return bool(api_key()) and bool(store_id()) and webhook_enabled()


def variant_id_for(item_id: str) -> Optional[str]:
    env = VARIANT_ENV.get(item_id)
    if not env:
        return None
    return (os.getenv(env) or "").strip() or None


def configured_items() -> list[str]:
    """已配好 Variant ID 的条目 —— 前端据此决定购买走哪条链路，不猜。"""
    return [i for i in VARIANT_ENV if variant_id_for(i)]


def item_id_for_variant(variant_id: Optional[str | int]) -> Optional[str]:
    """Variant ID → 内部条目 id（`VARIANT_ENV` 的反向查询）。

    回调里没有"我们自己的条目 id"，只有 LS 的 variant；发放前必须用它交叉校验
    custom 声明的条目，防止"便宜的档配贵的积分"或后台换 variant 后串档。
    真值仍然只有 `credits_config` —— 这里只反查 id，不返回任何价格/积分。
    """
    wanted = _txt(variant_id)
    if not wanted:
        return None
    for item_id, env in VARIANT_ENV.items():
        if (os.getenv(env) or "").strip() == wanted:
            return item_id
    return None


# ── Webhook 验签 ────────────────────────────────────────────────────────
def verify_webhook_signature(raw_body: bytes, signature: Optional[str]) -> bool:
    """校验 Lemon Squeezy 的 `X-Signature`。任何异常/缺配置都返回 False（fail-closed）。

    算法（实测确认，与 Paddle **完全不同**，不得复用 paddle_service 的验签）：
        X-Signature = hexdump( HMAC-SHA256(LEMONSQUEEZY_WEBHOOK_SECRET, 原始请求体字节) )

    三条纪律：
    1. 输入必须是**原始 body 字节**。`request.json()` 之后再 `json.dumps` 会得到
       不同的字节（键序/空白/转义），实测必然验签失败 —— 所以这里绝不重新序列化。
    2. LS 头里**没有时间戳、没有 nonce**，因此不做任何 tolerance / max_age /
       重放窗口判断；防重放靠 `meta.webhook_id` 的投递层幂等（P2-3）。
    3. 失败只返回布尔，不回显期望值、长度或算法细节，避免给探测者反馈。
    """
    secret = webhook_secret()
    if not secret or not signature:
        return False

    received = signature.strip().lower()
    if len(received) != _SIGNATURE_HEX_LEN or not set(received) <= _HEX_CHARS:
        return False

    if isinstance(raw_body, (bytes, bytearray)):
        body = bytes(raw_body)
    elif isinstance(raw_body, str):
        body = raw_body.encode("utf-8")
    else:
        return False

    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received)


# ── Webhook payload 解析 ────────────────────────────────────────────────
# 以下字段路径全部来自 2026-09-25 真实 Test Mode 投递，不是文档推测：
#   meta: test_mode / event_name / custom_data / webhook_id
#   data.type / data.id / data.attributes
# 实测的"不存在"同样重要：invoice 对象没有 product_id / variant_id / order_id /
# quantity；subscription 与 invoice 都没有 interval / current_period_start。
# 所以本结构**不提供** interval 字段 —— 计费周期只能由服务端配置/台账决定。
@dataclass(frozen=True)
class LsOrderItem:
    """`data.attributes.first_order_item`（实测是扁平对象，不是 JSON:API 包裹）。"""
    id: str
    order_id: str
    product_id: str
    variant_id: str
    price_id: str
    price_cents: Optional[int]
    quantity: Optional[int]
    test_mode: bool


@dataclass(frozen=True)
class LsEvent:
    """一条已解析的 LS webhook 事件。字段只从实测存在的路径取值。"""
    # ── 投递与归因 ─────────────────────────────────────────────
    delivery_id: str        # meta.webhook_id —— 跨重试稳定，P2-3 的幂等锚点
    event_name: str         # meta.event_name
    object_type: str        # data.type
    object_id: str          # data.id
    test_mode: bool         # meta.test_mode 严格 is True（缺失即 False，不猜）
    custom: dict[str, Any]  # meta.custom_data —— 服务端建单时写入的原样回传
    kind: str               # custom.kind：credit_pack | membership（我们自己的标记）
    user_id: str            # custom.user_id（实测为 string）
    # ── 通用对象字段 ───────────────────────────────────────────
    store_id: str
    customer_id: str
    currency: str
    status: str
    total_cents: Optional[int]
    subtotal_cents: Optional[int]
    tax_cents: Optional[int]
    discount_cents: Optional[int]
    refunded: bool
    refunded_amount_cents: Optional[int]
    identifier: str         # orders：对外 uuid（= my-orders 页面段）
    order_number: str
    created_at: str
    updated_at: str
    # ── 身份链（按对象类型分别取，取不到就是空串）──────────────
    order_id: str           # orders→data.id；subscriptions→attributes.order_id；invoice 无
    invoice_id: str         # subscription-invoices→data.id；其余为空
    subscription_id: str    # subscriptions→data.id；invoice→attributes.subscription_id
    order_item_id: str
    product_id: str         # invoice 实测无 ⇒ 空串，绝不猜
    variant_id: str         # 同上
    price_id: str
    quantity: Optional[int]
    billing_reason: str     # invoice：initial / renewal / …
    renews_at: str
    ends_at: str
    # ── 原始明细（orders 才有）─────────────────────────────────
    order_item: Optional[LsOrderItem]


_EMPTY_EVENT = LsEvent(
    delivery_id="", event_name="", object_type="", object_id="", test_mode=False,
    custom={}, kind="", user_id="", store_id="", customer_id="", currency="",
    status="", total_cents=None, subtotal_cents=None, tax_cents=None,
    discount_cents=None, refunded=False, refunded_amount_cents=None, identifier="",
    order_number="", created_at="", updated_at="", order_id="", invoice_id="",
    subscription_id="", order_item_id="", product_id="", variant_id="", price_id="",
    quantity=None, billing_reason="", renews_at="", ends_at="", order_item=None,
)


def _txt(value: Any) -> str:
    """JSON:API 的 id 是字符串、attributes 里的 id 是整数；统一成 str 再比较。"""
    return "" if value is None else str(value).strip()


def _cents(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _parse_order_item(raw: Any) -> Optional[LsOrderItem]:
    item = _dict(raw)
    if not item:
        return None
    return LsOrderItem(
        id=_txt(item.get("id")), order_id=_txt(item.get("order_id")),
        product_id=_txt(item.get("product_id")), variant_id=_txt(item.get("variant_id")),
        price_id=_txt(item.get("price_id")), price_cents=_cents(item.get("price")),
        quantity=_cents(item.get("quantity")), test_mode=item.get("test_mode") is True,
    )


def parse_webhook_event(payload: Any) -> LsEvent:
    """把已验签的 LS payload 解析成 LsEvent。**永不抛异常**：形状不对就返回空事件，
    由调用方按"无 delivery_id ⇒ 不处理只 ack"处置（避免 500 → LS 无限重投）。
    """
    if not isinstance(payload, dict):
        return _EMPTY_EVENT

    meta = _dict(payload.get("meta"))
    data = _dict(payload.get("data"))
    attrs = _dict(data.get("attributes"))
    custom = _dict(meta.get("custom_data"))
    object_type = _txt(data.get("type"))
    object_id = _txt(data.get("id"))

    order_item = _parse_order_item(attrs.get("first_order_item"))

    product_id = variant_id = price_id = ""
    quantity = _cents(attrs.get("quantity"))
    if object_type == LS_OBJECT_ORDER and order_item is not None:
        product_id, variant_id, price_id = order_item.product_id, order_item.variant_id, order_item.price_id
        quantity = order_item.quantity if quantity is None else quantity
    elif object_type == LS_OBJECT_SUBSCRIPTION:
        product_id = _txt(attrs.get("product_id"))
        variant_id = _txt(attrs.get("variant_id"))
        sub_item = _dict(attrs.get("first_subscription_item"))
        price_id = _txt(sub_item.get("price_id"))
        if quantity is None:
            quantity = _cents(sub_item.get("quantity"))
    # LS_OBJECT_INVOICE 与未知类型：刻意什么都不填 —— 实测这些字段在 invoice 里不存在，
    # 需要 variant/price/plan 的调用方必须回台账反查（P2-5/P2-6）。

    if object_type == LS_OBJECT_ORDER:
        order_id, subscription_id = object_id, _txt(attrs.get("subscription_id"))
    elif object_type == LS_OBJECT_SUBSCRIPTION:
        order_id, subscription_id = _txt(attrs.get("order_id")), object_id
    else:
        order_id, subscription_id = _txt(attrs.get("order_id")), _txt(attrs.get("subscription_id"))

    return LsEvent(
        delivery_id=_txt(meta.get("webhook_id")),
        event_name=_txt(meta.get("event_name")),
        object_type=object_type,
        object_id=object_id,
        test_mode=meta.get("test_mode") is True,
        custom=custom,
        kind=_txt(custom.get("kind")),
        user_id=_txt(custom.get("user_id")),
        store_id=_txt(attrs.get("store_id")),
        customer_id=_txt(attrs.get("customer_id")),
        currency=_txt(attrs.get("currency")),
        status=_txt(attrs.get("status")),
        total_cents=_cents(attrs.get("total")),
        subtotal_cents=_cents(attrs.get("subtotal")),
        tax_cents=_cents(attrs.get("tax")),
        discount_cents=_cents(attrs.get("discount_total")),
        refunded=attrs.get("refunded") is True,
        refunded_amount_cents=_cents(attrs.get("refunded_amount")),
        identifier=_txt(attrs.get("identifier")),
        order_number=_txt(attrs.get("order_number")),
        order_id=order_id,
        invoice_id=object_id if object_type == LS_OBJECT_INVOICE else "",
        subscription_id=subscription_id,
        order_item_id=_txt(attrs.get("order_item_id")),
        product_id=product_id,
        variant_id=variant_id,
        price_id=price_id,
        quantity=quantity,
        billing_reason=_txt(attrs.get("billing_reason")),
        renews_at=_txt(attrs.get("renews_at")),
        ends_at=_txt(attrs.get("ends_at")),
        created_at=_txt(attrs.get("created_at")),
        updated_at=_txt(attrs.get("updated_at")),
        order_item=order_item,
    )


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


# ── Credit Pack 一次性履约（P2-4）──────────────────────────────────────
# 结果状态与 HTTP 语义（沿用本项目 Paddle 回调既有口径，不新造一套）：
#   granted / already_processed → 200：钱已落账或已处理过，绝不再发
#   ignored                     → 200：结构性不可履约（不是我们的商品 / 不是 pack /
#                                     订单状态未到 paid / 生产环境收到 test 事件）
#   rejected                    → 400：金额、币种、数量、身份、串档不符。宁可让 LS
#                                     重投 3 次后停在失败投递列表，也不静默吞掉一笔钱
#   error                       → 500：台账或发放本身失败 ⇒ 必须重投补发
GRANTED = "granted"
ALREADY_PROCESSED = "already_processed"
IGNORED = "ignored"
REJECTED = "rejected"
ERROR = "error"

# 实测：一笔付清的 LS order 其 attributes.status == "paid"。
# 其它取值（pending / refunded / failed / expired …）一律不履约 —— 不猜语义。
LS_ORDER_STATUS_PAID = "paid"


@dataclass(frozen=True)
class LsFulfillmentResult:
    """履约结论。`code` 只放机器码，绝不放 payload 片段。"""
    status: str
    code: str = ""
    credits: int = 0


def is_production() -> bool:
    """动态读取，便于测试 monkeypatch（与 ai_music.py 同一约定）。"""
    return (os.getenv("ENVIRONMENT") or "development").strip().lower() == "production"


def pack_truth_for_item(item_id: Optional[str]) -> Optional[dict[str, Any]]:
    """内部条目 id → 履约真值（credits / price_cents / currency）。

    与 credits_config.get_credit_packs() 的区别是刻意的：那个函数按
    **PADDLE_PRICE_ID_*** 过滤，LS 侧的开关是 LEMONSQUEEZY_VARIANT_ID_*。
    数值本身仍只有一个来源（CREDIT_PACKS + CREDIT_PACK_CURRENCY），
    cents 用与既有一致的 round(price_usd * 100) 换算，比较时只用整数。
    """
    if not item_id:
        return None
    pack = next((p for p in CREDIT_PACKS if p["id"] == item_id), None)
    if pack is None:
        return None
    return {
        "id": pack["id"],
        "credits": int(pack["credits"]),
        "price_cents": round(float(pack["price_usd"]) * 100),
        "currency": CREDIT_PACK_CURRENCY,
    }


def _valid_user_id(user_id: str) -> bool:
    """只接受我们自己签发进 custom 的那种身份：规范 UUID 形态的字符串。

    不接受 email、不接受 LS 的 customer_id —— 见 webhook 归因约定。
    形态不符即视为不可归因，宁可拒发也不把钱落到别人头上。
    """
    if not user_id or len(user_id) > _USER_ID_MAX_LEN:
        return False
    return bool(_UUID_RE.match(user_id))


def _claim_purchase(event: LsEvent, user_id: str, pack: dict[str, Any]) -> str:
    """以 ls_order_id 的数据库 UNIQUE 抢占本单处理权。claimed / duplicate / error。"""
    sess = None
    try:
        sess = db.SessionLocal()
        sess.add(LemonSqueezyPurchase(
            ls_order_id=event.order_id,
            ls_event_id=event.delivery_id or None,
            user_id=user_id,
            test_mode=event.test_mode,
            product_id=event.product_id or None,
            variant_id=event.variant_id or None,
            price_id=event.price_id or None,
            quantity=event.quantity,
            currency=event.currency or None,
            subtotal_cents=event.subtotal_cents,
            tax_cents=event.tax_cents,
            discount_cents=event.discount_cents,
            total_cents=event.total_cents,
            refunded_amount_cents=event.refunded_amount_cents,
        ))
        sess.commit()
        return "claimed"
    except IntegrityError:
        if sess is not None:
            sess.rollback()
        return "duplicate"
    except Exception as exc:  # noqa: BLE001 - 只记异常类型，绝不记 payload
        if sess is not None:
            sess.rollback()
        logger.error("Lemon Squeezy purchase claim failed for order %s: %s",
                     event.order_id, type(exc).__name__)
        return "error"
    finally:
        if sess is not None:
            sess.close()


def _release_purchase(ls_order_id: str) -> None:
    """发放失败时释放占位，让 LS 重投还能补发（与 Paddle 侧同一语义）。"""
    sess = None
    try:
        sess = db.SessionLocal()
        sess.query(LemonSqueezyPurchase).filter_by(ls_order_id=ls_order_id).delete()
        sess.commit()
    except Exception as exc:  # noqa: BLE001
        if sess is not None:
            sess.rollback()
        logger.error("could not release Lemon Squeezy claim for order %s: %s",
                     ls_order_id, type(exc).__name__)
    finally:
        if sess is not None:
            sess.close()


def fulfill_credit_pack_order(event: LsEvent) -> LsFulfillmentResult:
    """一次性 Credit Pack 的唯一履约入口。

    只认 `order_created` + `custom.kind == "credit_pack"`。subscription、invoice、
    refund、membership 在本函数里一律 ignored —— 它们属于 P2-5/P2-6/P2-7。

    发放数量只来自 pack_truth_for_item()（即 credits_config），payload 里的
    custom.credits / attributes.total / variant_name 一律不作为"发多少"的依据；
    它们只用于"这单是不是它声称的那一单"的交叉校验。
    """
    if event.object_type != LS_OBJECT_ORDER or event.event_name != LS_EVENT_ORDER_CREATED:
        return LsFulfillmentResult(IGNORED, "not_a_pack_order")
    if event.kind != "credit_pack":
        return LsFulfillmentResult(IGNORED, "not_credit_pack")

    # Test / Live 隔离：test 事件在生产环境绝不换成真实 Credits。
    if is_production() and event.test_mode:
        logger.error("Refusing to fulfil LS test-mode order %s in production", event.order_id)
        return LsFulfillmentResult(IGNORED, "test_mode_in_production")

    if not event.order_id:
        return LsFulfillmentResult(REJECTED, "missing_order_id")
    if event.status != LS_ORDER_STATUS_PAID:
        return LsFulfillmentResult(IGNORED, f"status:{event.status or 'unknown'}")

    # variant → 条目：唯一由服务端配置决定的商品身份。
    item_id = item_id_for_variant(event.variant_id)
    if not item_id:
        logger.info("Lemon Squeezy order %s variant %s is not a configured pack; ignored",
                    event.order_id, event.variant_id or "-")
        return LsFulfillmentResult(IGNORED, "unconfigured_variant")

    declared = str(event.custom.get("pack_id") or "").strip()
    if declared != item_id:
        # custom 声明的档位与 variant 反查出的档位不一致 = 串档，必须停。
        logger.error("Lemon Squeezy order %s declares pack %s but variant %s maps to %s",
                     event.order_id, declared or "-", event.variant_id, item_id)
        return LsFulfillmentResult(REJECTED, "pack_id_mismatch")

    pack = pack_truth_for_item(item_id)
    if pack is None:
        return LsFulfillmentResult(IGNORED, "unknown_pack")

    if not _valid_user_id(event.user_id):
        logger.error("Lemon Squeezy order %s has no usable custom_data.user_id", event.order_id)
        return LsFulfillmentResult(REJECTED, "invalid_user_id")

    if event.quantity != 1:
        logger.error("Lemon Squeezy order %s quantity=%s (expected exactly 1) — refusing",
                     event.order_id, event.quantity)
        return LsFulfillmentResult(REJECTED, "unexpected_quantity")

    if not event.currency or event.currency != pack["currency"]:
        logger.error("Lemon Squeezy order %s currency %s != configured %s — refusing",
                     event.order_id, event.currency or "-", pack["currency"])
        return LsFulfillmentResult(REJECTED, "currency_not_supported")

    if event.total_cents != pack["price_cents"]:
        # 整数分比较；不做汇率换算、不从 tax/discount 反推。
        # 注意：这是"实收必须等于标价"的严格口径 —— 一旦 LS 对某国买家在标价之上
        # 另计销售税，total 就会大于标价而被本条拒掉。该口径待你确认（见 P2-4 报告）。
        logger.error("Lemon Squeezy order %s total %s != configured price %s for pack %s "
                     "— refusing", event.order_id, event.total_cents,
                     pack["price_cents"], pack["id"])
        return LsFulfillmentResult(REJECTED, "amount_mismatch")

    claim = _claim_purchase(event, event.user_id, pack)
    if claim == "duplicate":
        logger.info("Lemon Squeezy order %s already processed → skip grant", event.order_id)
        return LsFulfillmentResult(ALREADY_PROCESSED, "already_processed")
    if claim == "error":
        return LsFulfillmentResult(ERROR, "claim_failed")

    try:
        result = credits_service.add_credits(
            event.user_id, pack["credits"], "purchase",
            reference_id=f"ls:order:{event.order_id}",
            description=f"credit pack {pack['id']}",
        )
    except Exception as exc:  # noqa: BLE001 - 发放抛异常同样必须释放占位，否则重投被自己挡住
        _release_purchase(event.order_id)
        logger.error("Lemon Squeezy credit grant raised for order %s: %s",
                     event.order_id, type(exc).__name__)
        return LsFulfillmentResult(ERROR, "grant_failed")
    if not result.get("success"):
        _release_purchase(event.order_id)
        logger.error("Lemon Squeezy credit grant failed for order %s: %s",
                     event.order_id, result.get("error") or "unknown")
        return LsFulfillmentResult(ERROR, "grant_failed")

    logger.info("Granted %s Lemon Squeezy pack credits to %s (pack %s, order %s, test=%s)",
                pack["credits"], event.user_id, pack["id"], event.order_id, event.test_mode)
    return LsFulfillmentResult(GRANTED, "granted", pack["credits"])
