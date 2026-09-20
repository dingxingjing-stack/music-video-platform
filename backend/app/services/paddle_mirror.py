"""Paddle 客户 / 订阅状态镜像（mirror）+ 付费访问判定。

定位：这是**投影层**，不是发放层。
  - 发放（加积分）在 membership_service / credit_pack_service，幂等锚点各自独立；
  - 本模块只把 Paddle 说过的客户与订阅状态原样落到本地库，供"这个人现在是不是付费
    会员""他的 Paddle customer id 是多少"这类判定使用。

三条硬规则：
  1. 幂等 upsert，键是 Paddle 自己的 id（ctre_ / sub_）。投递是至少一次且可能乱序，
     所以后到的事件用 COALESCE 补字段，绝不把已知值抹成空。
  2. 归属只增不改：一个 customer / subscription 一旦关联到某个 user_id，
     换成别人的请求一律拒绝并记 error —— 宁可状态不更新，也不能把会员搬到别人账上。
  3. 判定访问权只看 status，不看 scheduled_change：计划取消/暂停在真正生效前
     仍然是有效付费会员。

沿用 membership_service 的裸 SQL + _DB_LOCK 写法（同一套 SQLite/Postgres 兼容口径）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text

from app.db.database import SessionLocal
from app.services import credits_service, paddle_service

logger = logging.getLogger(__name__)

# 与 membership_service.ACTIVE_STATUSES 保持同一口径：只有这两个状态给付费访问。
# past_due / paused 不给 —— 沿用本项目既有约定（付款失败即降级，不做宽限）。
GRANTING_STATUSES = ("active", "trialing")

_DB_LOCK = credits_service._DB_LOCK


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mapping(row) -> dict[str, Any]:
    m = row._mapping if hasattr(row, "_mapping") else row
    return {k: m[k] for k in m.keys()}


# ── 客户 ──────────────────────────────────────────────────────────────
def upsert_customer(*, customer_id: str, email: Optional[str] = None,
                    name: Optional[str] = None, status: Optional[str] = None,
                    locale: Optional[str] = None, user_id: Optional[str] = None) -> dict[str, Any]:
    """插入/更新客户镜像行。user_id 只在为空时写入，永不改写已有归属。"""
    if not customer_id:
        return {"action": "skipped", "reason": "missing customer id"}
    with _DB_LOCK:
        sess = SessionLocal()
        try:
            existing = sess.execute(text(
                "SELECT user_id FROM paddle_customers WHERE paddle_customer_id = :c"
            ), {"c": customer_id}).fetchone()
            if existing is None:
                sess.execute(text(
                    "INSERT INTO paddle_customers (paddle_customer_id, user_id, email, name, "
                    "status, locale, created_at, updated_at) "
                    "VALUES (:c, :u, :e, :n, :st, :l, :ts, :ts)"
                ), {"c": customer_id, "u": user_id, "e": email, "n": name,
                    "st": status, "l": locale, "ts": _now()})
                action = "created"
            else:
                cur_user = _mapping(existing)["user_id"]
                if user_id and cur_user and cur_user != user_id:
                    sess.rollback()
                    logger.error("Paddle customer %s already linked to another user; "
                                 "refuse to reassign", customer_id)
                    return {"action": "owner_conflict", "customer_id": customer_id}
                sess.execute(text(
                    "UPDATE paddle_customers SET "
                    "email = COALESCE(:e, email), name = COALESCE(:n, name), "
                    "status = COALESCE(:st, status), locale = COALESCE(:l, locale), "
                    "user_id = COALESCE(user_id, :u), updated_at = :ts "
                    "WHERE paddle_customer_id = :c"
                ), {"e": email, "n": name, "st": status, "l": locale,
                    "u": user_id or cur_user, "ts": _now(), "c": customer_id})
                action = "updated"
            sess.commit()
        except Exception:
            sess.rollback()
            raise
        finally:
            sess.close()
    return {"action": action, "customer_id": customer_id}


def link_user_to_customer(user_id: str, customer_id: Optional[str]) -> bool:
    """交易/订阅事件带 customer_id 时回链归属（幂等，冲突不覆盖）。"""
    if not user_id or not customer_id:
        return False
    return upsert_customer(customer_id=customer_id, user_id=user_id)["action"] != "owner_conflict"


def get_customer_id_for_user(user_id: str) -> Optional[str]:
    """由本地可信数据反查 Paddle customer id（客户门户会话的唯一合法来源）。

    先查客户表归属，再退到订阅镜像 —— 只要此人的任一交易/订阅带过 ctre_，就能拿到。
    """
    sess = SessionLocal()
    try:
        row = sess.execute(text(
            "SELECT paddle_customer_id FROM paddle_customers "
            "WHERE user_id = :u ORDER BY id DESC LIMIT 1"
        ), {"u": user_id}).fetchone()
        if row is not None:
            return str(_mapping(row)["paddle_customer_id"])
        row = sess.execute(text(
            "SELECT paddle_customer_id FROM paddle_subscriptions "
            "WHERE user_id = :u AND paddle_customer_id IS NOT NULL "
            "ORDER BY id DESC LIMIT 1"
        ), {"u": user_id}).fetchone()
        return str(_mapping(row)["paddle_customer_id"]) if row is not None else None
    finally:
        sess.close()


# ── 订阅状态镜像 ───────────────────────────────────────────────────────
def upsert_subscription_state(*, subscription_id: str, status: str,
                              event_type: Optional[str] = None,
                              user_id: Optional[str] = None,
                              customer_id: Optional[str] = None,
                              price_id: Optional[str] = None,
                              product_id: Optional[str] = None,
                              interval: Optional[str] = None,
                              period_start: Optional[str] = None,
                              period_end: Optional[str] = None,
                              cancel_at_period_end: Optional[bool] = None,
                              scheduled_action: Optional[str] = None,
                              scheduled_at: Optional[str] = None) -> dict[str, Any]:
    """按 Paddle 订阅号幂等落状态。空字段用 COALESCE 保留旧值，不抹空。"""
    if not subscription_id:
        return {"action": "skipped", "reason": "missing subscription id"}
    status = str(status or "unknown").lower()
    with _DB_LOCK:
        sess = SessionLocal()
        try:
            existing = sess.execute(text(
                "SELECT user_id FROM paddle_subscriptions WHERE paddle_subscription_id = :s"
            ), {"s": subscription_id}).fetchone()
            params = {"s": subscription_id, "st": status, "ev": event_type, "u": user_id,
                      "c": customer_id, "p": price_id, "pr": product_id, "iv": interval,
                      "ps": period_start, "pe": period_end,
                      "ca": bool(cancel_at_period_end) if cancel_at_period_end is not None else False,
                      "sa": scheduled_action, "sat": scheduled_at, "ts": _now()}
            if existing is None:
                sess.execute(text(
                    "INSERT INTO paddle_subscriptions (paddle_subscription_id, user_id, "
                    "paddle_customer_id, status, price_id, product_id, interval, "
                    "current_period_start, current_period_end, cancel_at_period_end, "
                    "scheduled_change_action, scheduled_change_at, last_event_type, "
                    "created_at, updated_at) VALUES (:s, :u, :c, :st, :p, :pr, :iv, :ps, :pe, "
                    ":ca, :sa, :sat, :ev, :ts, :ts)"
                ), params)
                action = "created"
            else:
                cur_user = _mapping(existing)["user_id"]
                if user_id and cur_user and cur_user != user_id:
                    sess.rollback()
                    logger.error("Paddle subscription %s already owned by another user; "
                                 "refuse to reassign", subscription_id)
                    return {"action": "owner_conflict", "subscription_id": subscription_id}
                sess.execute(text(
                    "UPDATE paddle_subscriptions SET status = :st, "
                    "last_event_type = COALESCE(:ev, last_event_type), "
                    "user_id = COALESCE(user_id, :u), "
                    "paddle_customer_id = COALESCE(:c, paddle_customer_id), "
                    "price_id = COALESCE(:p, price_id), "
                    "product_id = COALESCE(:pr, product_id), "
                    "interval = COALESCE(:iv, interval), "
                    "current_period_start = COALESCE(:ps, current_period_start), "
                    "current_period_end = COALESCE(:pe, current_period_end), "
                    "cancel_at_period_end = :ca, "
                    "scheduled_change_action = :sa, scheduled_change_at = :sat, "
                    "updated_at = :ts WHERE paddle_subscription_id = :s"
                ), params)
                action = "updated"
            sess.commit()
        except Exception:
            sess.rollback()
            raise
        finally:
            sess.close()
    logger.info("Paddle subscription %s mirrored as %s (event=%s scheduled=%s)",
                subscription_id, status, event_type, scheduled_action)
    return {"action": action, "subscription_id": subscription_id, "status": status}


def get_subscription(subscription_id: str) -> Optional[dict[str, Any]]:
    sess = SessionLocal()
    try:
        row = sess.execute(text(
            "SELECT * FROM paddle_subscriptions WHERE paddle_subscription_id = :s"
        ), {"s": subscription_id}).fetchone()
        return _mapping(row) if row is not None else None
    finally:
        sess.close()


def list_user_subscriptions(user_id: str) -> list[dict[str, Any]]:
    sess = SessionLocal()
    try:
        rows = sess.execute(text(
            "SELECT paddle_subscription_id, status, price_id, product_id, interval, "
            "current_period_end, cancel_at_period_end, scheduled_change_action, "
            "scheduled_change_at FROM paddle_subscriptions WHERE user_id = :u ORDER BY id"
        ), {"u": user_id}).fetchall()
        return [_mapping(r) for r in rows]
    finally:
        sess.close()


def has_paid_access(user_id: str) -> bool:
    """当前是否付费会员：只看镜像里的 status，不看 scheduled_change。

    scheduled_change=cancel/pause 只表示"到期后将要"，此刻访问权仍然有效；
    status 真变成 canceled/paused/past_due 才收回。
    """
    if not user_id:
        return False
    placeholders = ", ".join(f"'{s}'" for s in GRANTING_STATUSES)
    sess = SessionLocal()
    try:
        row = sess.execute(text(
            f"SELECT 1 FROM paddle_subscriptions WHERE user_id = :u AND status IN ({placeholders}) "
            "LIMIT 1"
        ), {"u": user_id}).fetchone()
        return row is not None
    except Exception as exc:  # noqa: BLE001
        logger.warning("has_paid_access failed for %s: %s", user_id, exc)
        return False
    finally:
        sess.close()


# ── 事件入口 ───────────────────────────────────────────────────────────
def mirror_from_event(event_type: str, obj: dict[str, Any], *,
                      user_id: Optional[str] = None,
                      price_id: Optional[str] = None) -> dict[str, Any]:
    """webhook 已验签的事件 → 写镜像。返回 {handled, action}，未覆盖的类型 handled=False。

    投影失败绝不影响发放：调用方以 best-effort 方式包裹本函数。
    """
    customer_id = paddle_service.extract_customer_id(obj)
    if event_type.startswith("customer."):
        custom = obj.get("custom_data") if isinstance(obj.get("custom_data"), dict) else {}
        link = user_id or str(custom.get("user_id") or "").strip() or None
        result = upsert_customer(customer_id=customer_id or str(obj.get("id") or ""),
                                 email=obj.get("email"), name=obj.get("name"),
                                 status=obj.get("status"), locale=obj.get("locale"),
                                 user_id=link)
        return {"handled": True, **result}

    subscription_id = paddle_service.extract_subscription_id(obj)
    if not subscription_id:
        # 一次性积分包交易：没有订阅可镜像，只把客户归属链上
        if customer_id and user_id:
            linked = link_user_to_customer(user_id, customer_id)
            return {"handled": True, "action": "linked" if linked else "skipped"}
        return {"handled": False}

    if customer_id and user_id:
        link_user_to_customer(user_id, customer_id)

    period_start, period_end = paddle_service.extract_billing_period(obj)
    scheduled_action, scheduled_at = paddle_service.extract_scheduled_change(obj)
    if event_type.startswith("transaction."):
        # 交易事件上的 status 属于交易本身，不代表订阅状态 → 状态字段留给 subscription.* 覆盖
        status = None
    else:
        status = str(obj.get("status") or "").lower() or None
    if status is None:
        known = get_subscription(subscription_id)
        status = (known or {}).get("status") or "active"

    result = upsert_subscription_state(
        subscription_id=subscription_id, status=status, event_type=event_type,
        user_id=user_id, customer_id=customer_id,
        price_id=price_id or paddle_service.extract_price_id(obj),
        product_id=paddle_service.extract_product_id(obj),
        interval=((obj.get("billing_cycle") or {}).get("interval")
                  if isinstance(obj.get("billing_cycle"), dict) else None),
        period_start=period_start, period_end=period_end,
        cancel_at_period_end=bool(obj.get("cancel_at_period_end")),
        scheduled_action=scheduled_action, scheduled_at=scheduled_at,
    )
    return {"handled": True, **result}
