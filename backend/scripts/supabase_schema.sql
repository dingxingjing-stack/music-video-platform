-- ============================================================
-- Supabase 建表脚本 (music-video-platform backend)
-- 项目 ref: nmbkxbldxauvgsbdsljj
-- 用法: 打开 Supabase Dashboard → SQL Editor → New query → 粘贴执行
-- ============================================================

-- ---------- users ----------
create table if not exists public.users (
  id text primary key,
  supabase_user_id text unique,
  email text unique not null,
  username text,
  avatar_url text,
  credits integer default 100,
  subscription_tier text default 'free',
  age integer,
  is_verified boolean default false,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- ---------- songs ----------
create table if not exists public.songs (
  id text primary key,
  user_id text references public.users(id) on delete cascade,
  title text not null,
  lyrics text,
  style text,
  duration_seconds integer,
  audio_url text,
  cover_image_url text,
  mv_url text,
  status text default 'pending',
  is_public boolean default false,
  play_count integer default 0,
  like_count integer default 0,
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- ---------- tasks ----------
create table if not exists public.tasks (
  id text primary key default gen_random_uuid()::text,
  user_id text references public.users(id) on delete cascade,
  task_type text not null,
  status text default 'pending',
  progress integer default 0,
  result jsonb,
  error_message text,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  completed_at timestamptz
);

-- ---------- feedback ----------
create table if not exists public.feedback (
  id text primary key default gen_random_uuid()::text,
  name text,
  text text not null,
  created_at timestamptz default now()
);

-- ---------- 索引 ----------
create index if not exists idx_songs_user on public.songs(user_id, created_at desc);
create index if not exists idx_tasks_user on public.tasks(user_id);
create index if not exists idx_feedback_created on public.feedback(created_at desc);

-- ---------- RLS: 服务端用 service_role 绕过；anon 只读公开数据 ----------
alter table public.users enable row level security;
alter table public.songs enable row level security;
alter table public.tasks enable row level security;
alter table public.feedback enable row level security;

-- 无需策略：后端使用 service_role（默认绕过 RLS）。
-- 若需开放 anon 读公开歌曲，取消注释下面两条：
-- create policy "public read songs" on public.songs
--   for select using (is_public = true);
