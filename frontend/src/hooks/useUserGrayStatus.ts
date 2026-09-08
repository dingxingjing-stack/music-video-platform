import { useState, useEffect, useCallback } from 'react';
import { api } from '../config/api';
import { authFetch } from '../api/http';

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

// 非权限用途的 UI 缓存 key（仅按登录用户 id 隔离 UI 缓存，不参与认证身份）。
const storageKey = (userId: string) => `beta_user_status:${userId}`;

export function useUserGrayStatus(userId?: string) {
  const [status, setStatus] = useState<UserGrayStatus>(DEFAULT_STATUS);
  const [loading, setLoading] = useState(true);

  const fetchStatus = useCallback(async () => {
    // 后端是唯一授权来源；身份由 authFetch 自动附 Bearer token。
    try {
      const data = await authFetch<Record<string, any>>(`${API_BASE}/status`);
      const merged: UserGrayStatus = {
        isGray: !!data.is_gray,
        dailyCredits: data.daily_credits_limit ?? 10,
        usedToday: data.daily_credits_used ?? 0,
        activityScore: data.activity_score ?? 0,
        totalGenerations: data.total_generations ?? 0,
        canApply: !!data.can_apply,
      };
      setStatus(merged);
      // 仅作为非权限 UI 缓存（key 来自调用方传入的 userId，非身份来源）
      if (userId) {
        try {
          localStorage.setItem(storageKey(userId), JSON.stringify(merged));
        } catch { /* ignore */ }
      }
    } catch {
      // 未登录 / 后端失败：fail-closed，回到安全默认。
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
   */
  const consumeCredit = useCallback(async (amount = 1): Promise<boolean> => {
    try {
      const data = await authFetch<{ success?: boolean; used_today?: number; limit?: number }>(
        `${API_BASE}/consume-credit`,
        { method: 'POST', body: { amount } },
      );
      if (!data.success) return false;
      setStatus((prev) => {
        const next: UserGrayStatus = {
          ...prev,
          usedToday: data.used_today ?? prev.usedToday + amount,
          dailyCredits: data.limit ?? prev.dailyCredits,
        };
        if (userId) {
          try {
            localStorage.setItem(storageKey(userId), JSON.stringify(next));
          } catch { /* ignore */ }
        }
        return next;
      });
      return true;
    } catch {
      // 后端失败 / 未登录：不扣额度，fail-closed。
      return false;
    }
  }, [userId]);

  const refetch = useCallback(() => fetchStatus(), [fetchStatus]);

  return { status, loading, consumeCredit, refetch };
}