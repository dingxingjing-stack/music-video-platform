import { useEffect, useState } from 'react';
import { api } from '../config/api';
import { authFetch } from '../api/http';

// ----------------------------------------
// useCreditsBalance — 登录用户余额（GET /api/v1/credits/balance）
//
// 说明：
//  - 数据唯一来源 = 后端 credits_service.get_credit_summary()（balance 等字段）
//  - 身份由 authFetch 从 Supabase Auth 取 access_token，未登录抛 AuthenticationError
//  - 任何失败（未登录 / 网络 / 服务端）都安全降级为 balance=null，绝不抛出导致组件崩溃
// ----------------------------------------

export interface CreditsBalance {
  balance: number;
  lifetime_earned?: number;
  lifetime_spent?: number;
  welcome_bonus_claimed?: boolean;
  email_verification_bonus_claimed?: boolean;
  first_song_bonus_claimed?: boolean;
}

export const useCreditsBalance = (enabled: boolean) => {
  const [balance, setBalance] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!enabled) {
      // 未登录：不请求，清零状态
      setBalance(null);
      setError(false);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(false);

    authFetch<CreditsBalance>(api.url('/api/v1/credits/balance'))
      .then((data) => {
        if (cancelled) return;
        setBalance(typeof data?.balance === 'number' ? data.balance : null);
        setLoading(false);
      })
      .catch(() => {
        // 未登录 / 网络 / 服务端失败：静默降级，不显示余额，不崩溃
        if (cancelled) return;
        setBalance(null);
        setError(true);
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [enabled]);

  return { balance, loading, error };
};