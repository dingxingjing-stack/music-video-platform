import { useEffect, useState } from "react";
import { api } from "../config/api";
import { authFetch } from "../api/http";
import { useTranslation } from "../i18n/useTranslation";

// ----------------------------------------
// 1️⃣ API helper – 供外部直接调用
// ----------------------------------------
export async function getUserAge(): Promise<number | null> {
  // 身份由 authFetch 从 Supabase Auth 取 access_token；未登录即抛 AuthenticationError → 返回 null（不伪造身份）。
  try {
    const data = await authFetch<{ age?: number }>(api.url('/api/v1/user/age'));
    return data.age ?? null;
  } catch (e) {
    console.error('fetch age error', e);
    return null;
  }
}

// ----------------------------------------
// 2️⃣ React Hook – 供组件内部使用（保持原有行为）
// ----------------------------------------
export const useUserAge = () => {
  const [age, setAge] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { t } = useTranslation();

  useEffect(() => {
    if (typeof window === "undefined") return;
    authFetch<{ age?: number }>(api.url('/api/v1/user/age'))
      .then((data) => {
        setAge(data.age ?? null);
        setLoading(false);
      })
      .catch((e) => {
        // 未登录（AuthenticationError）或失败：不伪造身份，安全无年龄
        setError(t('errors.ageFetchFailed', { msg: e instanceof Error ? e.message : '' }));
        setLoading(false);
      });
  }, [t]);

  return { age, loading, error };
};