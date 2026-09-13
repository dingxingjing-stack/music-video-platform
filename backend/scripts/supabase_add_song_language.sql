-- ============================================================
-- 幂等补列：public.songs 增加 song_language（歌曲生成语言，独立于 UI locale）
-- 用途：已有部署环境表已存在时，用本脚本补列；新装环境由 supabase_schema.sql 直接建。
-- 幂等：ADD COLUMN IF NOT EXISTS，可重复执行；历史歌曲 song_language 为 NULL，不破坏数据。
-- 用法：Supabase Dashboard → SQL Editor → 粘贴执行（本文件不会自动执行，仅供人工执行）。
-- ============================================================

alter table public.songs
  add column if not exists song_language text;