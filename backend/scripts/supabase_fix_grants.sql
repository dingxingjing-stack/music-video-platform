-- ============================================================
-- Supabase 修复脚本 #2 — 补 users 表 + GRANT 授权
-- 项目 ref: nmbkxbldxauvgsbdsljj
-- 用法: Supabase Dashboard → SQL Editor → New query → 粘贴执行
-- ============================================================

-- ---------- 1. 补建 users 表（应用需要，之前建成了 user_stats） ----------
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

-- 可选：把已建错结构的 user_stats 改名/保留均可，应用不读它。
-- 若 user_stats 是误建，可执行：drop view if exists public.user_stats;

-- ---------- 2. GRANT 授权给 service_role（后端用） ----------
grant usage on schema public to service_role;
grant all on all tables in schema public to service_role;
grant all on all sequences in schema public to service_role;
grant all on all functions in schema public to service_role;

-- ---------- 3. 若需 anon 只读公开数据（前端用 Publishable） ----------
grant usage on schema public to anon, authenticated;
grant select on public.songs to anon, authenticated;

-- ---------- 4. RLS 策略：service_role 绕过，anon 默认无写权限 ----------
alter table public.users enable row level security;
alter table public.songs enable row level security;
alter table public.tasks enable row level security;
alter table public.feedback enable row level security;

-- anon/authenticated 可选读公开歌曲（与现有 is_public 逻辑一致）
drop policy if exists "public_read_songs" on public.songs;
create policy "public_read_songs" on public.songs
  for select using (is_public = true);

-- users 表：authenticated 可读/改自己的行
drop policy if exists "users_select_own" on public.users;
create policy "users_select_own" on public.users
  for select using (auth.uid()::text = id);

drop policy if exists "users_update_own" on public.users;
create policy "users_update_own" on public.users
  for update using (auth.uid()::text = id);
