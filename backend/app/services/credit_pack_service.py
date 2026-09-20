"""积分补充包发放账本 —— Paddle webhook 唯一写入点。

幂等策略（claim → grant → 失败则释放 claim）：
1. 先以 `paddle_transaction_id`（数据库 UNIQUE）插入一条购买记录抢占处理权；
   冲突 ⇒ 该交易此前已处理 ⇒ 直接返回 already_processed，绝不二次加 Credits。
2. 抢占成功后再调 credits_service 加积分；若加积分失败，删掉刚插入的占位记录并
   抛出异常，让 Paddle 按其重试机制重投 webhook（而不是把用户的钱吞在"已处理"状态里）。

与会员体系零耦合：只写 user_credits / credits_transactions / credit_pack_purchases，
不碰 subscription、beta_users.daily_credits_limit、会员等级或到期时间。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal
from app.services import credits_service

logger = logging.getLogger(__name__)

_DB_LOCK = credits_service._DB_LOCK  # 与 Credits 账本共用同一把进程内锁（SQLite 写入串行化）


def _now() -> datetime:
    return datetime.now(timezone.utc)


def find_purchase(transaction_id: str) -> Optional[dict[str, Any]]:
    sess = SessionLocal()
    try:
        row = sess.execute(text(
            "SELECT user_id, pack_id, credits, paddle_price_id, status FROM credit_pack_purchases "
            "WHERE paddle_transaction_id = :t"
        ), {"t": transaction_id}).fetchone()
        if row is None:
            return None
        m = row._mapping if hasattr(row, "_mapping") else row
        return {"user_id": m["user_id"], "pack_id": m["pack_id"], "credits": m["credits"],
                "paddle_price_id": m["paddle_price_id"], "status": m["status"]}
    finally:
        sess.close()


def list_purchases(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    sess = SessionLocal()
    try:
        rows = sess.execute(text(
            "SELECT pack_id, credits, paddle_price_id, currency, amount_cents, status, created_at "
            "FROM credit_pack_purchases WHERE user_id = :u ORDER BY id DESC LIMIT :n"
        ), {"u": user_id, "n": limit}).fetchall()
        out = []
        for row in rows:
            m = row._mapping if hasattr(row, "_mapping") else row
            out.append({k: m[k] for k in ("pack_id", "credits", "paddle_price_id",
                                          "currency", "amount_cents", "status", "created_at")})
        return out
    except Exception as exc:  # noqa: BLE001 - 查询失败不影响主流程
        logger.warning("list_purchases failed for %s: %s", user_id, exc)
        return []
    finally:
        sess.close()


def grant_pack_credits(*, transaction_id: str, user_id: str, pack: dict[str, Any],
                       price_id: str, event_id: Optional[str] = None,
                       currency: Optional[str] = None,
                       amount_cents: Optional[int] = None) -> dict[str, Any]:
    """幂等发放。返回 {"status": "granted"|"already_processed", ...}。

    积分数量只取自 `pack`（后端 Price ID → 配置的映射），调用方无法从外部指定。
    """
    if not transaction_id:
        raise ValueError("transaction_id is required")
    if not user_id:
        raise ValueError("user_id is required")
    credits = int(pack["credits"])

    with _DB_LOCK:
        sess = SessionLocal()
        claimed = False
        try:
            sess.execute(text(
                "INSERT INTO credit_pack_purchases "
                "(user_id, paddle_transaction_id, paddle_event_id, paddle_price_id, pack_id, credits, "
                " currency, amount_cents, status, created_at, updated_at) "
                "VALUES (:u, :t, :e, :p, :k, :c, :cu, :a, 'completed', :ts, :ts)"
            ), {"u": user_id, "t": transaction_id, "e": event_id, "p": price_id, "k": pack["id"],
                "c": credits, "cu": currency, "a": amount_cents, "ts": _now()})
            sess.commit()
            claimed = True
        except IntegrityError:
            sess.rollback()
            existing = find_purchase(transaction_id)
            logger.info("Paddle transaction %s already processed (credits=%s) → skip grant",
                        transaction_id, (existing or {}).get("credits"))
            return {"status": "already_processed", "transaction_id": transaction_id,
                    "credits": 0, "existing": existing}
        finally:
            sess.close()

        # 抢占成功 → 真正加积分。失败则释放占位，交给 Paddle 重投。
        result = credits_service.add_credits(
            user_id, credits, "purchase",
            reference_id=transaction_id,
            description=f"credit pack {pack['id']}",
        )
        if not result.get("success"):
            release = SessionLocal()
            try:
                release.execute(text("DELETE FROM credit_pack_purchases WHERE paddle_transaction_id = :t"),
                                {"t": transaction_id})
                release.commit()
            except Exception:  # noqa: BLE001
                release.rollback()
                logger.error("could not release claim for %s; manual reconcile needed", transaction_id)
            finally:
                release.close()
            logger.error("credit grant failed for transaction %s: %s", transaction_id, result.get("error"))
            raise RuntimeError(result.get("error") or "credit grant failed")

    logger.info("Granted %s credits to %s for pack %s (txn %s)", credits, user_id, pack["id"], transaction_id)
    return {"status": "granted", "transaction_id": transaction_id, "credits": credits,
            "balance": result.get("balance")}
