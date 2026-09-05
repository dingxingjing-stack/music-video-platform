import { useState, useEffect, useCallback } from 'react';
import { api } from '../config/api';

export interface UserGrayStatus {
  isGray: boolean;
  dailyCredits: number;
  usedToday: number;
  activityScore: number;
  totalGenerations: number;
  canApply: boolean;
}

// 安全默认值：fail-closed。后端不可用 / 未登录时，不允许申请灰度、不默认放行。
const DEFAULT_STATUS: UserGrayStatus = {
  isGray: false,
  dailyCredits: 10,
  usedToday: 0,
  activityScore: 0,
  totalGenerations: 0,
  canApply: false,
};

const API_BASE = api.url('/api/v1/beta');

// 非权限用途的 UI 缓存 key，按 userId 隔离，避免跨用户读到彼此状态。
const storageKey = (userId: string) => `beta_user_status:${userId}`;

export function useUserGrayStatus(userId?: string) {
  const [status, setStatus] = useState<UserGrayStatus>(DEFAULT_STATUS);
  const [loading, setLoading] = useState(true);

  const fetchStatus = useCallback(async () => {
    if (!userId) {
      // 未登录：fail-closed，不读任何缓存作为授权依据。
      setStatus(DEFAULT_STATUS);
      setLoading(false);
      return;
    }

    // 后端是唯一授权来源。localStorage 仅作非权限 UI 缓存，绝不参与授权判断。
    try {
      const res = await fetch(`${API_BASE}/status`, {
        headers: { 'X-User-ID': userId },
        cache: 'no-store',
      });
      if (res.ok) {
        const data = await res.json();
        const merged: UserGrayStatus = {
          isGray: !!data.is_gray,
          dailyCredits: data.daily_credits_limit ?? 10,
          usedToday: data.daily_credits_used ?? 0,
          activityScore: data.activity_score ?? 0,
          totalGenerations: data.total_generations ?? 0,
          canApply: !!data.can_apply,
        };
        setStatus(merged);
        // 仅作为非权限 UI 缓存
        try {
          localStorage.setItem(storageKey(userId), JSON.stringify(merged));
        } catch { /* ignore */ }
      } else {
        // 后端失败：fail-closed，回到安全默认，不信任任何缓存。
        setStatus(DEFAULT_STATUS);
      }
    } catch {
      // 网络失败：fail-closed。
      setStatus(DEFAULT_STATUS);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    setStatus(DEFAULT_STATUS);
    setLoading(true);
    fetchStatus();
  }, [fetchStatus]);

  /**
   * 消耗额度 — 只信任后端结果。后端失败 / 未登录一律不本地扣减。
   * 仅依赖 userId，不依赖 status 闭包，避免竞态。
   */
  const consumeCredit = useCallback(async (amount = 1): Promise<boolean> => {
    if (!userId) {
      // 未登录：禁止消费 Beta 额度。
      return false;
    }

    try {
      const res = await fetch(`${API_BASE}/consume-credit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-User-ID': userId },
        body: JSON.stringify({ amount }),
        cache: 'no-store',
      });
      if (!res.ok) return false;
      const data = await res.json();
      if (!data.success) return false;

      // 用后端返回的最新状态更新本地
      setStatus((prev) => {
        const next: UserGrayStatus = {
          ...prev,
          usedToday: data.used_today ?? prev.usedToday + amount,
          dailyCredits: data.limit ?? prev.dailyCredits,
        };
        try {
          localStorage.setItem(storageKey(userId), JSON.stringify(next));
        } catch { /* ignore */ }
        return next;
      });
      return true;
    } catch {
      // 后端失败：不扣额度，fail-closed。
      return false;
    }
  }, [userId]);

  const refetch = useCallback(() => fetchStatus(), [fetchStatus]);

  return { status, loading, consumeCredit, refetch };
}