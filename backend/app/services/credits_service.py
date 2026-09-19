"""Credits 服务 —— 余额型积分，唯一权威入口。

安全原则：
- 所有 balance 增减只在这里发生，必须写 credits_transactions 账本。
- 余额扣减用条件 UPDATE（WHERE balance >= amount）原子判定，杜绝负余额；
  并发/多进程下由数据库行级锁 + 单条条件更新保证。
- 免费奖励（welcome/email/first_song）用 claimed 标志的 CAS 更新保证「每项仅一次」。
- user_id 全部来自 verified JWT（auth_identity），本服务不校验身份、只按 user_id 落账。
- 与 ai_limits 的"每日次数/成本保护"是两个独立维度，不互相覆盖。
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Optional

from app.db.database import SessionLocal
from app.services.credits_config import (
    FIRST_SONG_BONUS,
    EMAIL_VERIFICATION_BONUS,
    WELCOME_BONUS,
    TRANSACTION_TYPES,
)

# 进程内串行化 SQLite 写事务；生产 PG 由行锁兜底。
# 必须是 RLock：refund_generation_credits 持锁后复用 _apply（同线程二次进入），
# 普通 Lock 会在有实际扣费时自锁死，退款永远不落账。
_DB_LOCK = threading.RLock()


def _ensure_row(user_id: str) -> None:
    """幂等确保 user_credits 存在一行（余额 0，未领取任何奖励）。"""
    from sqlalchemy import text
    sess = None
    try:
        sess = SessionLocal()
        sess.execute(text(
            "INSERT INTO user_credits (user_id, balance, lifetime_earned, lifetime_spent, "
            "welcome_bonus_claimed, email_verification_bonus_claimed, first_song_bonus_claimed) "
            "VALUES (:u, 0, 0, 0, FALSE, FALSE, FALSE) ON CONFLICT(user_id) DO NOTHING"
        ), {"u": user_id})
        sess.commit()
    finally:
        if sess:
            sess.close()


def _apply(user_id: str, amount: int, txn_type: str, reference_id: Optional[str] = None,
           description: Optional[str] = None, require_sufficient: bool = True) -> dict[str, Any]:
    """原子执行一笔账目：扣减（amount<0，要求余额充足）或入账（amount>0）。

    单事务内：写入 transactions + 更新 balance/lifetime；扣减用条件 UPDATE 保证不超扣。
    返回 {"success", "balance", "amount", "error?"}。
    """
    if txn_type not in TRANSACTION_TYPES:
        return {"success": False, "error": f"未知 transaction_type: {txn_type}"}
    sess = None
    try:
        from sqlalchemy import text
        with _DB_LOCK:
            sess = SessionLocal()
            sess.execute(text("BEGIN"))
            _ensure_row(user_id)

            if amount < 0:
                # 条件扣减：余额必须足够，否则 rowcount==0 回滚
                cur = sess.execute(text(
                    "UPDATE user_credits SET balance = balance + :a, lifetime_spent = lifetime_spent + :neg, updated_at = :ts "
                    "WHERE user_id = :u AND balance >= :neg"
                ), {"a": amount, "neg": -amount, "u": user_id, "ts": datetime.now(timezone.utc)})
                if cur.rowcount == 0:
                    sess.rollback()
                    # 读取当前余额返回明确错误
                    _ensure_row(user_id)
                    bal = sess.execute(text("SELECT balance FROM user_credits WHERE user_id=:u"), {"u": user_id}).fetchone()
                    return {"success": False, "error": "余额不足", "balance": int(bal[0]) if bal else 0}
            else:
                sess.execute(text(
                    "UPDATE user_credits SET balance = balance + :a, lifetime_earned = lifetime_earned + :a, updated_at = :ts WHERE user_id = :u"
                ), {"a": amount, "u": user_id, "ts": datetime.now(timezone.utc)})

            # 写账本
            sess.execute(text(
                "INSERT INTO credits_transactions (user_id, amount, transaction_type, reference_id, description, created_at) "
                "VALUES (:u, :a, :t, :r, :d, :ts)"
            ), {"u": user_id, "a": amount, "t": txn_type, "r": reference_id, "d": description,
                "ts": datetime.now(timezone.utc)})

            sess.commit()
            bal = sess.execute(text("SELECT balance FROM user_credits WHERE user_id=:u"), {"u": user_id}).fetchone()
            return {"success": True, "balance": int(bal[0]) if bal else 0, "amount": amount}
    except Exception as e:
        try:
            sess.rollback()
        except Exception:
            pass
        return {"success": False, "error": f"credits 操作失败: {e}"}
    finally:
        if sess:
            sess.close()


def get_balance(user_id: str) -> int:
    """读取余额；无行则视为 0。"""
    from sqlalchemy import text
    sess = None
    try:
        sess = SessionLocal()
        _ensure_row(user_id)
        row = sess.execute(text("SELECT balance FROM user_credits WHERE user_id=:u"), {"u": user_id}).fetchone()
        return int(row[0]) if row else 0
    finally:
        if sess:
            sess.close()


def add_credits(user_id: str, amount: int, txn_type: str, reference_id: Optional[str] = None,
                description: Optional[str] = None) -> dict[str, Any]:
    """入账（正数）。"""
    return _apply(user_id, abs(amount), txn_type, reference_id, description)


def consume_credits(user_id: str, amount: int, reference_id: Optional[str] = None,
                    description: Optional[str] = None) -> dict[str, Any]:
    """扣减（负数），余额不足返回 success=False。"""
    return _apply(user_id, -abs(amount), "generation", reference_id, description)


def refund_credits(user_id: str, amount: int, reference_id: Optional[str] = None,
                   description: Optional[str] = None) -> dict[str, Any]:
    """退款（入账，记录 refund type）。"""
    return _apply(user_id, abs(amount), "refund", reference_id, description)


def reserve_generation_credits(user_id: str, task_id: str, cost: int) -> dict[str, Any]:
    """生成前原子扣减 Credits（reference_id=task_id，写入 generation 流水）。

    余额不足返回 success=False（调用方应拒绝生成、不退 ai_limits 之外的任何东西）。
    """
    return consume_credits(user_id, cost, reference_id=task_id, description=f"generation {task_id}")


def refund_generation_credits(user_id: str, task_id: str) -> dict[str, Any]:
    """生成失败退款 —— 幂等：同一 task_id 只退款一次。

    通过 credits_transactions 中 (reference_id=task_id, transaction_type='refund') 是否已存在
    来判断是否已退过；已退过直接返回 already_refunded=True，绝不重复加回余额。
    """
    from sqlalchemy import text
    sess = None
    try:
        with _DB_LOCK:
            sess = SessionLocal()
            _ensure_row(user_id)
            # 幂等查重：该 task 是否已有 refund 流水
            existing = sess.execute(text(
                "SELECT 1 FROM credits_transactions WHERE user_id=:u AND reference_id=:r AND transaction_type='refund'"
            ), {"u": user_id, "r": task_id}).fetchone()
            if existing:
                return {"success": True, "already_refunded": True}
            # 反查本 task 的 generation 扣费金额（保证退款金额 = 原扣款金额，不多退不少退）
            gen = sess.execute(text(
                "SELECT amount FROM credits_transactions WHERE user_id=:u AND reference_id=:r AND transaction_type='generation' ORDER BY id DESC LIMIT 1"
            ), {"u": user_id, "r": task_id}).fetchone()
            if not gen:
                # 没有 generation 扣费记录 → 无需退款
                return {"success": True, "already_refunded": True, "nothing_to_refund": True}
            cost = abs(int(gen[0]))
            return _apply(user_id, cost, "refund", task_id, f"refund {task_id}")
    except Exception as e:
        return {"success": False, "error": f"退款失败: {e}"}
    finally:
        if sess:
            sess.close()


def _claim_bonus(user_id: str, amount: int, flag_column: str, txn_type: str) -> dict[str, Any]:
    """原子领取一次性奖励：CAS 更新 claimed 标志，rowcount==0 → 已领过。"""
    from sqlalchemy import text
    sess = None
    try:
        with _DB_LOCK:
            sess = SessionLocal()
            _ensure_row(user_id)
            sess.execute(text("BEGIN"))
            cur = sess.execute(text(
                f"UPDATE user_credits SET {flag_column} = TRUE, "
                f"balance = balance + :a, lifetime_earned = lifetime_earned + :a, updated_at = :ts "
                f"WHERE user_id = :u AND {flag_column} = FALSE"
            ), {"a": amount, "u": user_id, "ts": datetime.now(timezone.utc)})
            if cur.rowcount == 0:
                sess.rollback()
                return {"success": False, "already_claimed": True, "error": "该奖励已领取"}
            sess.execute(text(
                "INSERT INTO credits_transactions (user_id, amount, transaction_type, created_at) VALUES (:u, :a, :t, :ts)"
            ), {"u": user_id, "a": amount, "t": txn_type, "ts": datetime.now(timezone.utc)})
            sess.commit()
            bal = sess.execute(text("SELECT balance FROM user_credits WHERE user_id=:u"), {"u": user_id}).fetchone()
            return {"success": True, "already_claimed": False, "balance": int(bal[0]) if bal else 0, "amount": amount}
    except Exception as e:
        try:
            sess.rollback()
        except Exception:
            pass
        return {"success": False, "error": f"领取失败: {e}"}
    finally:
        if sess:
            sess.close()


def claim_welcome_bonus(user_id: str) -> dict[str, Any]:
    return _claim_bonus(user_id, WELCOME_BONUS, "welcome_bonus_claimed", "welcome_bonus")


def claim_email_verification_bonus(user_id: str) -> dict[str, Any]:
    return _claim_bonus(user_id, EMAIL_VERIFICATION_BONUS, "email_verification_bonus_claimed", "email_verification_bonus")


def claim_first_song_bonus(user_id: str) -> dict[str, Any]:
    return _claim_bonus(user_id, FIRST_SONG_BONUS, "first_song_bonus_claimed", "first_song_bonus")


def get_credit_summary(user_id: str) -> dict[str, Any]:
    """聚合返回：余额 + 各项奖励领取状态。"""
    from sqlalchemy import text
    sess = None
    try:
        sess = SessionLocal()
        _ensure_row(user_id)
        row = sess.execute(text(
            "SELECT balance, lifetime_earned, lifetime_spent, welcome_bonus_claimed, "
            "email_verification_bonus_claimed, first_song_bonus_claimed FROM user_credits WHERE user_id=:u"
        ), {"u": user_id}).fetchone()
        if not row:
            return {"balance": 0, "lifetime_earned": 0, "lifetime_spent": 0,
                    "welcome_bonus_claimed": False, "email_verification_bonus_claimed": False,
                    "first_song_bonus_claimed": False}
        return {
            "balance": int(row[0]), "lifetime_earned": int(row[1]), "lifetime_spent": int(row[2]),
            "welcome_bonus_claimed": bool(row[3]), "email_verification_bonus_claimed": bool(row[4]),
            "first_song_bonus_claimed": bool(row[5]),
        }
    finally:
        if sess:
            sess.close()