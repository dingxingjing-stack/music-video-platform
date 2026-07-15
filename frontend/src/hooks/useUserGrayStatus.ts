import { useState, useEffect, useCallback } from 'react';

export interface UserGrayStatus {
  isGray: boolean;
  dailyCredits: number;
  usedToday: number;
  activityScore: number;
  totalGenerations: number;
  canApply: boolean;
}

const DEFAULT_STATUS: UserGrayStatus = {
  isGray: false,
  dailyCredits: 10,
  usedToday: 0,
  activityScore: 0,
  totalGenerations: 0,
  canApply: true,
};

const STORAGE_KEY = 'beta_user_status';
const API_BASE = 'https://ai-music-backend-8e85.onrender.com/api/v1/beta';

export function useUserGrayStatus(userId?: string) {
  const [status, setStatus] = useState<UserGrayStatus>(DEFAULT_STATUS);
  const [loading, setLoading] = useState(true);

  const fetchStatus = useCallback(async () => {
    try {
      const cached = localStorage.getItem(STORAGE_KEY);
      if (cached) {
        const parsed = JSON.parse(cached);
        setStatus({ ...DEFAULT_STATUS, ...parsed });
      }

      if (userId) {
        const res = await fetch(
          `${API_BASE}/status`,
          { headers: { 'X-User-ID': userId } }
        );
        if (res.ok) {
          const data = await res.json();
          const merged = {
            isGray: data.is_gray ?? false,
            dailyCredits: data.daily_credits_limit ?? 10,
            usedToday: data.daily_credits_used ?? 0,
            activityScore: data.activity_score ?? 0,
            totalGenerations: data.total_generations ?? 0,
            canApply: data.can_apply ?? true,
          };
          setStatus(merged);
          localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
        }
      }
    } catch {
      // 后端不可用时用本地缓存
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  /**
   * 消耗额度 — 同时调用后端 API 并更新本地状态
   */
  const consumeCredit = useCallback(async (amount = 1): Promise<boolean> => {
    if (!userId) {
      // 无 userId 时仅本地扣减
      setStatus((prev) => {
        const next = { ...prev, usedToday: prev.usedToday + amount };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        return next;
      });
      return true;
    }

    // 调用后端 API
    try {
      const res = await fetch(`${API_BASE}/consume-credit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-User-ID': userId },
        body: JSON.stringify({ amount }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          // 用后端返回的最新状态更新本地
          const updated = {
            ...status,
            usedToday: data.used_today ?? status.usedToday + amount,
            dailyCredits: data.limit ?? status.dailyCredits,
          };
          setStatus(updated);
          localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
          return true;
        }
      }
    } catch {
      // API 失败时回退本地扣减
    }

    // 后端调用失败时本地扣减
    setStatus((prev) => {
      const next = { ...prev, usedToday: prev.usedToday + amount };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
    return false;
  }, [userId, status]);

  const refetch = useCallback(() => fetchStatus(), [fetchStatus]);

  return { status, loading, consumeCredit, refetch };
}