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

export function useUserGrayStatus(userId?: string) {
  const [status, setStatus] = useState<UserGrayStatus>(DEFAULT_STATUS);
  const [loading, setLoading] = useState(true);

  const fetchStatus = useCallback(async () => {
    // 公测阶段：先从 localStorage 读取，后续接入后端 API
    try {
      const cached = localStorage.getItem(STORAGE_KEY);
      if (cached) {
        const parsed = JSON.parse(cached);
        setStatus({ ...DEFAULT_STATUS, ...parsed });
      }

      // 尝试从后端获取最新状态
      if (userId) {
        const res = await fetch(
          `https://ai-music-backend-8e85.onrender.com/api/v1/beta/status`,
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

  const consumeCredit = useCallback((amount = 1) => {
    setStatus((prev) => {
      const next = { ...prev, usedToday: prev.usedToday + amount };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  const refetch = useCallback(() => fetchStatus(), [fetchStatus]);

  return { status, loading, consumeCredit, refetch };
}
