-- ============================================================
-- Phone-only Supabase Auth support for public.users
-- 目标：支持 email 为空的手机号 Auth 用户建档
--
-- 用法：Supabase Dashboard → SQL Editor → 粘贴执行（本文件不会被应用自动执行）。
-- 原则：只增加/放宽约束，不重建表、不删除字段、不修改或删除现有用户数据。
-- ============================================================

begin;

-- phone-only Auth 用户通常没有 email；允许 email 为空。
alter table public.users
  alter column email drop not null;

-- 新增手机号字段。phone 可为空；非空时保持全局唯一。
alter table public.users
  add column if not exists phone text;

-- 使用部分唯一索引，避免多个 email/phone 均为空的行与 NULL 唯一性语义冲突。
create unique index if not exists users_phone_unique_idx
  on public.users (phone)
  where phone is not null;

-- 保留既有 supabase_user_id 唯一约束/索引，不进行重建或删除。
commit;
