/**
 * 路由守卫 — 公测阶段权限拦截
 * 1. 未同意公测协议 → 重定向 /landing
 * 2. 灰度功能路由 → 非灰度用户显示锁定组件
 */

import { Navigate } from 'react-router-dom';
import { FeatureGate } from './GrayFeatureLock';

const CONSENT_KEY = 'beta_consent_accepted';

/** 未同意公测协议时重定向到 /landing */
export function ConsentGuard({ children }: { children: React.ReactNode }) {
  const accepted = localStorage.getItem(CONSENT_KEY);
  if (!accepted) {
    return <Navigate to="/landing" replace />;
  }
  return <>{children}</>;
}

/** 灰度功能路由守卫 — 协议 + 灰度权限双拦截 */
export function GrayRoute({ featureKey, userId, children }: { featureKey: string; userId?: string; children: React.ReactNode }) {
  const accepted = localStorage.getItem(CONSENT_KEY);
  if (!accepted) {
    return <Navigate to="/landing" replace />;
  }
  return (
    <FeatureGate featureKey={featureKey} userId={userId} fallback={<FeatureGateFallback />}>
      {children}
    </FeatureGate>
  );
}

function FeatureGateFallback() {
  return (
    <div className="flex items-center justify-center h-full p-8">
      <div className="text-center max-w-md">
        <span className="text-4xl mb-3 block">🔒</span>
        <h2 className="text-lg font-medium text-white mb-2">该功能需要灰度权限</h2>
        <p className="text-sm text-[#888888]">请通过侧边栏灰度专区申请权限后访问</p>
      </div>
    </div>
  );
}