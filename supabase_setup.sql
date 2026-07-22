-- =============================================================
-- Supabase Free Tier 初始化脚本
-- 在 Supabase SQL Editor 中完整执行一次
-- =============================================================

-- 1. 任务表（状态机 + 4 轨下载链接）
CREATE TABLE IF NOT EXISTS public.audio_separate_tasks (
    task_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID,
    audio_origin_url TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending',
    vocals_url       TEXT,
    drums_url        TEXT,
    bass_url         TEXT,
    other_url        TEXT,
    error_message    TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at      TIMESTAMPTZ
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_audio_separate_tasks_status ON public.audio_separate_tasks(status);
CREATE INDEX IF NOT EXISTS idx_audio_separate_tasks_user_id ON public.audio_separate_tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_audio_separate_tasks_created_at ON public.audio_separate_tasks(created_at DESC);


-- =============================================================
-- 2. Storage 公开桶（控制台手动创建，名称固定）
--    audio-originals   用户上传原音频
--    audio-stems       4 条分轨 WAV
-- =============================================================
--
-- 在 Supabase 控制台 → Storage → New bucket：
--   - name = "audio-originals", Public = true
--   - name = "audio-stems",     Public = true
--
-- 两个桶创建后，将 Service Role key 复制到 Render 环境变量 SUPABASE_SERVICE_ROLE_KEY
-- Project URL 复制到 SUPABASE_URL
