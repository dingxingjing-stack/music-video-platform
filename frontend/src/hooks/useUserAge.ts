import { useEffect, useState } from "react";

// ----------------------------------------
// 1️⃣ API helper – 供外部直接调用
// ----------------------------------------
export async function getUserAge(): Promise<number | null> {
  try {
    const resp = await fetch('/api/v1/user/age', { credentials: 'same-origin' });
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
    fetch('/api/v1/user/age', { credentials: 'same-origin' })
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
