-- =====================================================
-- 公测灰度权限系统 - Supabase 建表脚本
-- 执行方式: 在 Supabase Dashboard → SQL Editor 中运行
-- =====================================================

-- 1. 公测用户表
CREATE TABLE IF NOT EXISTS beta_users (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL UNIQUE,
  is_gray BOOLEAN DEFAULT FALSE,
  daily_credits_used INTEGER DEFAULT 0,
  daily_credits_limit INTEGER DEFAULT 10,
  total_generations INTEGER DEFAULT 0,
  activity_score INTEGER DEFAULT 0,
  gray_unlocked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_beta_users_user_id ON beta_users(user_id);
CREATE INDEX IF NOT EXISTS idx_beta_users_is_gray ON beta_users(is_gray);

-- 2. 灰度申请记录表
CREATE TABLE IF NOT EXISTS beta_gray_applications (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  contact TEXT DEFAULT '',
  feature_key TEXT DEFAULT '',
  status TEXT DEFAULT 'pending',  -- pending / approved / rejected
  reviewed_at TIMESTAMPTZ,
  reviewer_note TEXT DEFAULT '',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_beta_applications_user_id ON beta_gray_applications(user_id);
CREATE INDEX IF NOT EXISTS idx_beta_applications_status ON beta_gray_applications(status);

-- 3. Bug 反馈表
CREATE TABLE IF NOT EXISTS beta_bug_reports (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  report_type TEXT DEFAULT 'bug',  -- bug / suggestion / other
  description TEXT NOT NULL,
  status TEXT DEFAULT 'open',      -- open / resolved / wontfix
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. 启用 Row Level Security (RLS)
ALTER TABLE beta_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE beta_gray_applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE beta_bug_reports ENABLE ROW LEVEL SECURITY;

-- 5. RLS 策略: 用户只能读写自己的记录
CREATE POLICY "users_select_own" ON beta_users FOR SELECT USING (true);
CREATE POLICY "users_insert_own" ON beta_users FOR INSERT WITH CHECK (true);
CREATE POLICY "users_update_own" ON beta_users FOR UPDATE USING (true);

CREATE POLICY "apps_select_own" ON beta_gray_applications FOR SELECT USING (true);
CREATE POLICY "apps_insert_own" ON beta_gray_applications FOR INSERT WITH CHECK (true);

CREATE POLICY "bugs_select_own" ON beta_bug_reports FOR SELECT USING (true);
CREATE POLICY "bugs_insert_own" ON beta_bug_reports FOR INSERT WITH CHECK (true);

-- 6. updated_at 自动更新触发器
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_beta_users_updated ON beta_users;
CREATE TRIGGER trigger_beta_users_updated
  BEFORE UPDATE ON beta_users
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
