-- ============================================================
-- Supabase 修复脚本 #3 — 补齐缺失列
-- 项目 ref: nmbkxbldxauvgsbdsljj
-- 用法: Supabase Dashboard → SQL Editor → New query → 粘贴执行
-- ============================================================

-- ---------- songs 表补列 ----------
alter table public.songs
  add column if not exists lyrics text,
  add column if not exists style text,
  add column if not exists duration_seconds integer,
  add column if not exists cover_image_url text,
  add column if not exists mv_url text,
  add column if not exists status text default 'pending',
  add column if not exists is_public boolean default false,
  add column if not exists play_count integer default 0,
  add column if not exists like_count integer default 0,
  add column if not exists metadata jsonb default '{}'::jsonb;

-- ---------- users 表补列 ----------
alter table public.users
  add column if not exists supabase_user_id text unique,
  add column if not exists username text,
  add column if not exists credits integer default 100,
  add column if not exists subscription_tier text default 'free',
  add column if not exists age integer,
  add column if not exists is_verified boolean default false;

-- ---------- tasks 表补列（若结构不完整） ----------
alter table public.tasks
  add column if not exists user_id text references public.users(id) on delete cascade,
  add column if not exists task_type text not null default 'generic',
  add column if not exists status text default 'pending',
  add column if not exists progress integer default 0,
  add column if not exists result jsonb,
  add column if not exists error_message text,
  add column if not exists completed_at timestamptz;

-- ---------- feedback 表补列 ----------
alter table public.feedback
  add column if not exists name text,
  add column if not exists text text not null default '';

-- ---------- 索引 ----------
create index if not exists idx_songs_user on public.songs(user_id, created_at desc);
create index if not exists idx_tasks_user on public.tasks(user_id);
create index if not exists idx_feedback_created on public.feedback(created_at desc);
