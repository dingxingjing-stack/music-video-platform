-- ============================================================
-- Supabase Auth → public.users 自动初始化 (Phase 3-2A)
-- 目标：auth.users 新增用户时，自动在 public.users 建立一致身份
--   public.users.id              = auth.users.id  (UUID 字符串)
--   public.users.supabase_user_id = auth.users.id
--   public.users.email            = auth.users.email
-- 幂等：ON CONFLICT (supabase_user_id) DO NOTHING，不产生重复行。
-- 只插入、不更新、不删除、不触碰既有数据。
--
-- 用法：Supabase Dashboard → SQL Editor → 粘贴执行（本文件不会被执行，仅供人工执行）
-- 注意：public.users.id 当前为 TEXT 主键，直接写入 UUID 字符串；不再生成独立 business UUID。
-- ============================================================

create or replace function public.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    -- auth.users.email 可能为空（手机/OAuth 等）；email 为空的场景暂不回填。
    if new.email is null then
        return new;
    end if;

    insert into public.users (id, supabase_user_id, email)
    values (new.id::text, new.id::text, new.email)
    on conflict (supabase_user_id) do nothing;

    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_auth_user();