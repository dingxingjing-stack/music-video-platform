/**
 * 路由守卫 v2 — 全功能开放版
 * 1. 未登录 → 显示 RequireAuth 拦截（不踢到 landing）
 * 2. 灰度锁全部移除 — 登录用户直接放行
 */
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const CONSENT_KEY = 'beta_consent_accepted';

/** 未同意公测协议时重定向到 /landing */
export function ConsentGuard({ children }: { children: React.ReactNode }) {
  const accepted = localStorage.getItem(CONSENT_KEY);
  if (!accepted) return <Navigate to="/landing" replace />;
  return <>{children}</>;
}

/** 灰度路由守卫 — 全功能开放后直接放行登录用户 */
export function GrayRoute({ children }: { children: React.ReactNode; featureKey?: string; userId?: string }) {
  const accepted = localStorage.getItem(CONSENT_KEY);
  if (!accepted) return <Navigate to="/landing" replace />;
  return <>{children}</>;
}
