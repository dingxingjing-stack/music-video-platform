-- 退款幂等 / 发放原子性 所需 DDL（生产 Supabase / Postgres 手工执行）
--
-- 背景：本仓没有 Alembic，Base.metadata.create_all() 只对「新建的表」生效，
-- 不会给已存在的表补列或补唯一约束。以下三条必须由运维在 SQL Editor 手工执行。
-- 全部使用 IF NOT EXISTS，可重复执行、不会破坏已有数据。
--
-- 执行顺序：先跑「0. 体检」，确认没有重复退款后，再跑 1 / 2 / 3。

-- ── 0. 体检：是否已经存在重复退款（存在则第 3 步的唯一索引会建不上）──────────
SELECT user_id, reference_id, COUNT(*) AS refund_cnt
FROM credits_transactions
WHERE transaction_type = 'refund' AND reference_id IS NOT NULL
GROUP BY user_id, reference_id
HAVING COUNT(*) > 1;
-- 若上面返回了行：说明历史上已经重复退过钱，先把多退的部分用一笔负向 refund 冲正，
-- 再删掉多余的行，最后才建索引。不要直接建索引（会报错并且掩盖账务问题）。


-- ── 1. ai_tasks：退款幂等标记（ai_limits.refund_generation 的 CAS 抢占依赖它）──
ALTER TABLE ai_tasks ADD COLUMN IF NOT EXISTS refunded_at timestamptz;

-- ── 2. ai_tasks：实际预留的额度权重（避免「扣 2 退 1」的少退）────────────────
ALTER TABLE ai_tasks ADD COLUMN IF NOT EXISTS generation_quota_weight integer;

-- ── 3. credits_transactions：同一 (user, task) 最多一笔 refund ────────────────
-- 这是唯一能跨进程/跨 worker 兜住「重复退款」的硬约束。
-- 应用层 credits_service.refund_generation_credits 已把查重与入账收进同一事务，
-- 并对 user_credits 加行锁（仅 PG），但索引仍是最后一道防线。
CREATE UNIQUE INDEX IF NOT EXISTS uq_credits_refund_once
    ON credits_transactions (user_id, reference_id)
    WHERE transaction_type = 'refund' AND reference_id IS NOT NULL;


-- ── 验证（执行完应全部返回预期）────────────────────────────────────────────────
-- SELECT column_name FROM information_schema.columns
--   WHERE table_name='ai_tasks' AND column_name IN ('refunded_at','generation_quota_weight');
--   → 2 行
-- SELECT indexname FROM pg_indexes WHERE indexname='uq_credits_refund_once';
--   → 1 行
