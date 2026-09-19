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

/**
 * 只读探测 Google provider 是否真的已在 Supabase 启用。
 * 只有 true 才渲染 Google 登录入口 —— 外部配置未完成时不出现可点击的假入口。
 * 任何失败（网络/权限/字段缺失）一律按未启用处理。
 */
export async function isGoogleLoginEnabled(): Promise<boolean> {
  if (!isSupabaseConfigured || !url || !anonKey) return false;
  try {
    const res = await fetch(`${url.replace(/\/+$/, '')}/auth/v1/settings`, {
      headers: { apikey: anonKey, Authorization: `Bearer ${anonKey}` },
    });
    if (!res.ok) return false;
    const data = await res.json();
    return data?.external?.google === true;
  } catch {
    return false;
  }
}

export const supabase: SupabaseClient = createClient(url ?? '', anonKey ?? '', {
  auth: {
    persistSession: true, // Supabase 自身 storage 持久化，与项目自造 zyvexo_user/user_id 无关
    autoRefreshToken: true,
  },
});