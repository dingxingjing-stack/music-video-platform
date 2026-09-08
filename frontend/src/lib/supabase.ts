/**
 * Supabase 客户端单例 —— 全项目唯一 createClient，禁止重复创建。
 *
 * 环境变量（VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY）由部署环境注入：
 * - 本地：.env.local
 * - 生产：Cloudflare Pages / Workers 环境变量
 * 前端只使用 anon（publishable）key；绝不放 service_role key 到前端。
 */

import { createClient, type SupabaseClient } from '@supabase/supabase-js';

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

export const isSupabaseConfigured = Boolean(url && anonKey);

export const supabase: SupabaseClient = createClient(url ?? '', anonKey ?? '', {
  auth: {
    persistSession: true, // Supabase 自身 storage 持久化，与项目自造 zyvexo_user/user_id 无关
    autoRefreshToken: true,
  },
});