import { useEffect, useState } from "react";
import { api } from "../config/api";
import { getUserId } from "./useAiMusicTask";

// ----------------------------------------
// 1️⃣ API helper – 供外部直接调用
// ----------------------------------------
export async function getUserAge(): Promise<number | null> {
  // 未登录时没有可信用户 ID，不伪造、不阻塞，直接返回 null
  const userId = getUserId();
  if (!userId) return null;
  try {
    // 与全站一致走绝对后端地址（绕开 Worker 静态/代理层），CORS 由后端放行
    const resp = await fetch(api.url('/api/v1/user/age'), {
      headers: { 'X-User-ID': userId },
      credentials: 'include',
    });
    if (!resp.ok) return null;
    const data = await resp.json();
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

  useEffect(() => {
    if (typeof window === "undefined") return;
    const userId = getUserId();
    // 未登录：无年龄、不阻塞页面
    if (!userId) {
      setLoading(false);
      return;
    }
    fetch(api.url('/api/v1/user/age'), {
      headers: { 'X-User-ID': userId },
      credentials: 'include',
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        setAge(data.age);
        setLoading(false);
      })
      .catch((e) => {
        setError(`获取年龄失败: ${e.message}`);
        setLoading(false);
      });
  }, []);

  return { age, loading, error };
};