"""会员订阅状态与月度积分发放（Paddle Recurring）。

与积分补充包的关系：
- 共用同一套用户身份（verified auth.users.id）与同一套积分账本（user_credits /
  credits_transactions），不另建用户系统、不另建积分系统。
- 完全独立于 credit_pack_purchases：买包只加积分，绝不写这张表；
  订阅只改等级/到期时间并按周期发放，绝不因为"买过一次包"而产生订阅。

幂等：每个计费周期只发一次月度积分。锚点存在 user_memberships.last_granted_period_start
（值为 Paddle 的周期起点，取不到周期时退化为该周期的 transaction id —— 续费必然产生新
transaction id，因此同样唯一）。用 CAS 更新锚点，rowcount==1 才发放；发放失败则把锚点
退回原值，让 Paddle 重投时还能补发。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text

from app.db.database import SessionLocal
from app.services import credits_service

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("active", "trialing")
_DB_LOCK = credits_service._DB_LOCK          # RLock：可与 credits_service 内部同名锁嵌套


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_membership(subscription_id: str) -> Optional[dict[str, Any]]:
    sess = SessionLocal()
    try:
        row = sess.execute(text("SELECT * FROM user_memberships WHERE paddle_subscription_id = :s"),
                           {"s": subscription_id}).fetchone()
        if row is None:
            return None
        m = row._mapping if hasattr(row, "_mapping") else row
        return {k: m[k] for k in m.keys() if k != "id"}
    finally:
        sess.close()


def get_user_id_for_subscription(subscription_id: str) -> Optional[str]:
    """续费事件里没有 custom_data 时的身份回退来源（由首开事件写入）。"""
    sess = SessionLocal()
    try:
        row = sess.execute(text("SELECT user_id FROM user_memberships WHERE paddle_subscription_id = :s"),
                           {"s": subscription_id}).fetchone()
        if row is None:
            return None
        m = row._mapping if hasattr(row, "_mapping") else row
        return m["user_id"]
    finally:
        sess.close()


def get_active_membership(user_id: str) -> Optional[dict[str, Any]]:
    """用户当前有效会员（等级 + 到期时间）。无有效订阅返回 None。"""
    sess = SessionLocal()
    try:
        placeholders = ", ".join(f"'{s}'" for s in ACTIVE_STATUSES)
        row = sess.execute(text(
            "SELECT plan_id, status, interval, credits_per_month, current_period_start, "
            "current_period_end, cancel_at_period_end, paddle_subscription_id "
            f"FROM user_memberships WHERE user_id = :u AND status IN ({placeholders}) "
            "ORDER BY COALESCE(current_period_end, '') DESC, id DESC LIMIT 1"
        ), {"u": user_id}).fetchone()
        if row is None:
            return None
        m = row._mapping if hasattr(row, "_mapping") else row
        return {k: m[k] for k in m.keys()}
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_active_membership failed for %s: %s", user_id, exc)
        return None
    finally:
        sess.close()


def upsert_subscription(*, subscription_id: str, user_id: str, plan: dict[str, Any],
                        status: str = "active", period_start: Optional[str] = None,
                        period_end: Optional[str] = None,
                        cancel_at_period_end: bool = False) -> dict[str, Any]:
    """插入或更新订阅行（等级/周期/状态跟随 Paddle）。"""
    with _DB_LOCK:
        sess = SessionLocal()
        try:
            existing = sess.execute(text(
                "SELECT user_id, plan_id FROM user_memberships WHERE paddle_subscription_id = :s"
            ), {"s": subscription_id}).fetchone()
            if existing is None:
                sess.execute(text(
                    "INSERT INTO user_memberships (user_id, paddle_subscription_id, plan_id, "
                    "paddle_price_id, status, interval, credits_per_month, current_period_start, "
                    "current_period_end, cancel_at_period_end, created_at, updated_at) "
                    "VALUES (:u, :s, :p, :pi, :st, :iv, :c, :ps, :pe, :ca, :ts, :ts)"
                ), {"u": user_id, "s": subscription_id, "p": plan["id"],
                    "pi": plan.get("paddle_price_id"), "st": status,
                    "iv": plan.get("interval", "month"),
                    "c": plan["credits_per_month"], "ps": period_start, "pe": period_end,
                    "ca": bool(cancel_at_period_end), "ts": _now()})
                action = "created"
            else:
                m = existing._mapping if hasattr(existing, "_mapping") else existing
                if m["user_id"] != user_id:
                    # 订阅归属被改写 = 严重异常，宁可不动也不要把会员挪给别人
                    sess.rollback()
                    logger.error("subscription %s already owned by another user; refuse to reassign",
                                 subscription_id)
                    raise ValueError("subscription owner mismatch")
                sess.execute(text(
                    "UPDATE user_memberships SET plan_id=:p, paddle_price_id=:pi, status=:st, "
                    "interval=:iv, credits_per_month=:c, "
                    "current_period_start=COALESCE(:ps, current_period_start), "
                    "current_period_end=COALESCE(:pe, current_period_end), "
                    "cancel_at_period_end=:ca, updated_at=:ts WHERE paddle_subscription_id=:s"
                ), {"p": plan["id"], "pi": plan.get("paddle_price_id"), "st": status,
                    "iv": plan.get("interval", "month"), "c": plan["credits_per_month"],
                    "ps": period_start, "pe": period_end, "ca": bool(cancel_at_period_end),
                    "ts": _now(), "s": subscription_id})
                action = "updated"
            sess.commit()
        except Exception:
            sess.rollback()
            raise
        finally:
            sess.close()
    logger.info("Membership %s for %s: plan=%s status=%s period_end=%s",
                action, user_id, plan["id"], status, period_end)
    return {"action": action, "subscription_id": subscription_id, "plan_id": plan["id"],
            "status": status}


def grant_period_credits(*, subscription_id: str, user_id: str, plan: dict[str, Any],
                         anchor: str) -> dict[str, Any]:
    """本周期发放月度积分（幂等）。anchor = 周期起点或该周期的 transaction id。"""
    credits = int(plan["credits_per_month"])
    with _DB_LOCK:
        sess = SessionLocal()
        try:
            cur = sess.execute(text(
                "UPDATE user_memberships SET last_granted_period_start = :a, updated_at = :ts "
                "WHERE paddle_subscription_id = :s "
                "AND (last_granted_period_start IS NULL OR last_granted_period_start <> :a)"
            ), {"a": anchor, "ts": _now(), "s": subscription_id})
            if cur.rowcount == 0:
                sess.rollback()
                logger.info("Period %s of subscription %s already granted → skip",
                            anchor, subscription_id)
                return {"status": "already_granted", "credits": 0}
            sess.commit()
        except Exception:
            sess.rollback()
            raise
        finally:
            sess.close()

        result = credits_service.add_credits(
            user_id, credits, "subscription_grant",
            reference_id=f"pdl:{subscription_id}:{anchor}",
            description=f"membership {plan['id']} monthly credits",
        )
        if not result.get("success"):
            # 锚点退回，交给 Paddle 重投补发，绝不把周期吞成"已发但未到账"
            rollback = SessionLocal()
            try:
                rollback.execute(text(
                    "UPDATE user_memberships SET last_granted_period_start = NULL "
                    "WHERE paddle_subscription_id = :s AND last_granted_period_start = :a"
                ), {"s": subscription_id, "a": anchor})
                rollback.commit()
            except Exception:  # noqa: BLE001
                rollback.rollback()
                logger.error("could not roll back grant anchor for %s/%s", subscription_id, anchor)
            finally:
                rollback.close()
            raise RuntimeError(result.get("error") or "subscription grant failed")

    logger.info("Granted %s monthly credits to %s (plan %s, anchor %s)",
                credits, user_id, plan["id"], anchor)
    return {"status": "granted", "credits": credits, "balance": result.get("balance")}
