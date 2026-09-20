"""任务终态化与孤儿对账（P0-3 / P0-4 / F9）。

单一退款出口：任何"任务不会再前进"的判定都必须走 finalize_stale_task()，
由它做状态 CAS 翻转 + Credits 幂等退款 + 日额度幂等退款 + 释放用户锁。

F9 例外（已交付不得判失败）：state='separating' 是 retry_stems 从 completed 借用的
重试槽位（ai_music.retry_stems → try_transition_state），此时主音频早已交付
（audio_url 或 download 清单非空）。这类任务只能收敛为 completed_with_stems_failed
并释放锁，绝不写 failed、绝不退 Credits、绝不退日额度 —— 否则用户既白拿一首歌、
又会从 Library 里丢掉它。未交付任务的行为完全不变。

Exactly-once 依据：
- ai_tasks.state 的 CAS 更新（WHERE state IN 活跃态）保证退款动作只发生一次；
- ai_limits.refund_generation(task_id=...) 自身用 ai_tasks.refunded_at 抢占；
- credits_service.refund_generation_credits(task_id=...) 自身用流水查重。

退款权重读自 ai_tasks.generation_quota_weight（建任务时与 reserve_generation 同步写入），
不在此处重新推断 duration；该列为 NULL 的旧任务按保守值 1 退（宁可少退不多退）。

前提：进程内只有一个 uvicorn 实例（生产 Render 为单进程，backend/Dockerfile 未使用
--workers）。若将来横向扩容，启动期 reconcile_active() 会把其它实例正在跑的任务
判为孤儿，届时必须改为「心跳 + 实例归属」后才能启用。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

def _get_session():
    """复用 task_store 的会话来源（含测试临时库覆盖），保证开发与测试同一条路径。"""
    from app.services import task_store
    return task_store._get_session()


ACTIVE_STATES = ("pending", "processing", "generating", "separating", "uploading")
# 常量子句：text() 不能把 tuple 直接绑进 IN，这里内联固定字面量（无任何外部输入）
_STATE_LIST = "(" + ", ".join(f"'{s}'" for s in ACTIVE_STATES) + ")"

# retry_stems 借用的重试槽位状态：只有它可能是"已交付但仍活跃"的
STEMS_RETRY_STATE = "separating"
# 主音频已交付、仅缺分轨的项目既有终态
DELIVERED_STEMS_FAILED_STATE = "completed_with_stems_failed"

# 超过该秒数仍未推进即视为孤儿（与 ai_limits.TASK_TIMEOUT 同量级）
STALE_AFTER_SECONDS = 600


def _release_lock(sess, task_id: str) -> None:
    try:
        sess.execute(text("DELETE FROM task_locks WHERE task_id = :tid"), {"tid": task_id})
    except Exception as exc:
        logger.warning("release lock failed for %s: %s", task_id, exc)


def _is_delivered(audio_url: Any, download: Any) -> bool:
    """主音频是否已经交付给用户。

    audio_url：_upload_and_finalize / HF 兜底写入的可播放地址。
    download：R2 对象清单（key → 对象名），只在 cdn_uploader 上传成功之后才写
    （ai_music._upload_and_finalize、_run_retry_stems、voice_clone_task），
    因此非空即代表音频对象已存在。裸 SQL 读回来是 JSON 字符串，需解析后判空。
    """
    if audio_url:
        return True
    if isinstance(download, str):
        try:
            download = json.loads(download)
        except ValueError:
            return False
    return bool(download)


def finalize_stale_task(task_id: str, reason: str = "服务中断，任务已终止", *, force: bool = False) -> dict[str, Any]:
    """把仍处活跃态的任务落为 failed 并退款。

    返回 {"finalized": bool, "user_id": str|None, "refunded": bool}。finalized=False
    表示已被别的路径终态化（CAS 未命中）或任务不存在 —— 调用方因此不会重复退款。
    例外：分轨重试中断但主音频已交付时，返回 finalized=True / refunded=False。
    """
    from app.services import ai_limits, credits_service

    sess = _get_session()
    try:
        sess.execute(text("BEGIN"))
        row = sess.execute(
            text("SELECT user_key, state, generation_quota_weight, audio_url, download "
                 "FROM ai_tasks WHERE task_id = :tid"),
            {"tid": task_id},
        ).fetchone()
        if row is None:
            sess.rollback()
            return {"finalized": False, "user_id": None, "refunded": False}
        mapping = row._mapping if hasattr(row, "_mapping") else row
        user_key = mapping["user_key"]
        state = mapping["state"]
        # 退款权重 = 当初 reserve_generation 实际扣减的权重（建任务时已持久化）。
        # 字段上线前的旧任务为 NULL：无法得知当时实际预留了 1 还是 2，
        # 按「宁可少退，不可多退」取保守值 1，绝不用 2 去冒多退风险。
        raw_weight = mapping.get("generation_quota_weight")

        # ── F9：分轨重试中断 + 主音频已交付 → 只收敛状态、只释放锁，一律不退款 ──
        if state == STEMS_RETRY_STATE and _is_delivered(mapping.get("audio_url"), mapping.get("download")):
            cur = sess.execute(
                text("UPDATE ai_tasks SET state=:to, error=:err, updated_at=:ua "
                     "WHERE task_id=:tid AND state=:frm"),
                {"to": DELIVERED_STEMS_FAILED_STATE,
                 "err": "分轨重试中断，主音频已交付",
                 "ua": time.time(), "tid": task_id, "frm": STEMS_RETRY_STATE},
            )
            if cur.rowcount == 0:
                sess.rollback()
                return {"finalized": False, "user_id": user_key, "refunded": False}
            _release_lock(sess, task_id)
            sess.commit()
            logger.warning("Delivered task %s: stems retry interrupted, converged to %s without refund",
                           task_id, DELIVERED_STEMS_FAILED_STATE)
            return {"finalized": True, "user_id": user_key or None, "refunded": False, "delivered": True}

        if force:
            cur = sess.execute(
                text("UPDATE ai_tasks SET state='failed', error=:err, updated_at=:ua "
                     "WHERE task_id=:tid AND state <> 'completed'"),
                {"err": reason, "ua": time.time(), "tid": task_id},
            )
        else:
            cur = sess.execute(
                text("UPDATE ai_tasks SET state='failed', error=:err, updated_at=:ua "
                     "WHERE task_id=:tid AND state IN ('pending','processing','generating','separating','uploading')"),
                {"err": reason, "ua": time.time(), "tid": task_id},
            )
        if cur.rowcount == 0:
            sess.rollback()
            return {"finalized": False, "user_id": user_key, "refunded": False}
        _release_lock(sess, task_id)
        sess.commit()
    except Exception as exc:
        logger.warning("finalize_stale_task CAS failed for %s: %s", task_id, exc)
        try:
            sess.rollback()
        except Exception:
            pass
        return {"finalized": False, "user_id": None, "refunded": False}
    finally:
        sess.close()

    # 状态已独占翻转 → 此处的退款最多执行一次
    try:
        quota_weight = int(raw_weight) if raw_weight is not None else 1
    except (TypeError, ValueError):
        quota_weight = 1
    quota_weight = max(1, quota_weight)

    user_key = user_key or ""
    if user_key:
        try:
            # 日额度退还：按建任务时持久化的实际预留权重退，global_usage 在
            # ai_limits 内部永不退，成本保护线不变。
            ai_limits.refund_generation(user_key, reason="provider_failed", task_id=task_id,
                                        weight=quota_weight)
        except Exception as exc:
            logger.warning("limits refund failed for %s: %s", task_id, exc)
        try:
            credits_service.refund_generation_credits(user_key, task_id)
        except Exception as exc:
            logger.warning("credits refund failed for %s: %s", task_id, exc)
    return {"finalized": True, "user_id": user_key or None, "quota_weight": quota_weight,
            "refunded": bool(user_key)}


def reconcile_stale_tasks(now: Optional[float] = None) -> int:
    """惰性超时用：把超龄活跃任务终态化。返回处理条数。"""
    now = now or time.time()
    sess = _get_session()
    try:
        rows = sess.execute(
            text(f"SELECT task_id FROM ai_tasks WHERE state IN {_STATE_LIST} AND updated_at + :ttl < :now"),
            {"ttl": STALE_AFTER_SECONDS, "now": now},
        ).fetchall()
    except Exception as exc:
        logger.warning("reconcile_stale_tasks query failed: %s", exc)
        rows = []
    finally:
        sess.close()

    count = 0
    for row in rows:
        tid = (row._mapping if hasattr(row, "_mapping") else row)["task_id"]
        if finalize_stale_task(tid, reason="生成超时（服务未收到结果），已退款").get("finalized"):
            count += 1
    return count


def reconcile_orphans_after_restart() -> int:
    """进程启动后调用：本进程不可能还持有上一进程的任何协程，
    因此库里所有活跃态任务都是孤儿 → 终态化并退款。
    """
    sess = _get_session()
    try:
        rows = sess.execute(
            text(f"SELECT task_id FROM ai_tasks WHERE state IN {_STATE_LIST}")
        ).fetchall()
    except Exception as exc:
        logger.warning("reconcile_orphans_after_restart query failed: %s", exc)
        rows = []
    finally:
        sess.close()

    count = 0
    for row in rows:
        tid = (row._mapping if hasattr(row, "_mapping") else row)["task_id"]
        if finalize_stale_task(tid, reason="服务重启导致任务中断，已自动退款").get("finalized"):
            count += 1
    if count:
        logger.warning("Restart reconciliation finalized %d orphan task(s) (refunds applied only to undelivered ones)", count)
    return count
