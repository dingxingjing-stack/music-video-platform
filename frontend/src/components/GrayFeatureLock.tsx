import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FEATURE_CONFIG } from '../config/features';
import { useUserGrayStatus } from '../hooks/useUserGrayStatus';

interface GrayFeatureLockProps {
  featureKey: string;
  onApply?: () => void;
}

export function GrayFeatureLock({ featureKey, onApply }: GrayFeatureLockProps) {
  const feature = FEATURE_CONFIG[featureKey];
  const [showApply, setShowApply] = useState(false);
  const [reason, setReason] = useState('');
  const [contact, setContact] = useState('');
  const [submitted, setSubmitted] = useState(false);

  if (!feature || feature.level !== 'gray') return null;

  const handleSubmit = async () => {
    try {
      await fetch('https://ai-music-backend-8e85.onrender.com/api/v1/beta/apply-gray', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-User-ID': 'beta_user' },
        body: JSON.stringify({ feature_key: featureKey, reason, contact }),
      });
    } catch { /* 公测容错 */ }
    setSubmitted(true);
    onApply?.();
    setTimeout(() => { setShowApply(false); setSubmitted(false); setReason(''); setContact(''); }, 2500);
  };

  return (
    <>
      {/* 锁定覆盖层 */}
      <div className="relative rounded-xl border border-[#2a2a2a] bg-[#1a1a1a]/80 backdrop-blur-sm p-6 sm:p-8 flex flex-col items-center justify-center text-center min-h-[200px]">
        <div className="absolute top-3 right-3">
          <span className="px-2 py-1 rounded-md bg-[#ff6a10]/10 text-[#ff6a10] text-[10px] font-medium">灰度功能</span>
        </div>
        <span className="text-4xl mb-3 opacity-60">{feature.icon}</span>
        <h3 className="text-base font-medium text-white mb-1">{feature.name}</h3>
        <p className="text-xs text-[#888888] mb-3 max-w-sm">{feature.description}</p>
        <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#2a2a2a] text-[#666666] text-xs mb-4">
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/></svg>
          仅资深测试用户开放
        </div>
        <button
          onClick={() => setShowApply(true)}
          className="px-5 py-2 rounded-lg text-xs font-medium border border-[#ff6a10]/30 text-[#ff6a10] hover:bg-[#ff6a10]/10 transition-colors"
        >
          申请灰度权限 →
        </button>
      </div>

      {/* 申请弹窗 */}
      <AnimatePresence>
        {showApply && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={(e) => e.target === e.currentTarget && setShowApply(false)}
            className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
          >
            <motion.div
              initial={{ scale: 0.9, y: 20 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.9, y: 20 }}
              className="w-full max-w-md bg-gradient-to-b from-[#1e1e1e] to-[#0e0e0e] border border-[#2a2a2a] rounded-2xl overflow-hidden"
            >
              {submitted ? (
                <div className="p-10 text-center">
                  <span className="text-4xl">✅</span>
                  <p className="mt-3 text-white font-medium">申请已提交</p>
                  <p className="mt-1 text-xs text-[#888888]">我们会在 1-3 个工作日内审核并通知</p>
                </div>
              ) : (
                <>
                  <div className="px-5 pt-5 pb-3 border-b border-[#2a2a2a]">
                    <h3 className="font-bold gradient-text text-lg">申请灰度权限</h3>
                    <p className="text-xs text-[#888888] mt-1">{feature.icon} {feature.name} · {feature.description}</p>
                  </div>
                  <div className="p-5 space-y-3">
                    <div>
                      <label className="text-xs text-[#888888] mb-1 block">申请理由</label>
                      <textarea
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        placeholder="请描述您需要该功能的原因..."
                        rows={3}
                        className="w-full rounded-lg bg-[#121212] border border-[#2a2a2a] px-3 py-2 text-sm text-white placeholder:text-[#555555] focus:border-[#ff6a10]/50 focus:outline-none resize-none"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-[#888888] mb-1 block">联系方式（选填）</label>
                      <input
                        value={contact}
                        onChange={(e) => setContact(e.target.value)}
                        placeholder="邮箱 / 微信"
                        className="w-full rounded-lg bg-[#121212] border border-[#2a2a2a] px-3 py-2 text-sm text-white placeholder:text-[#555555] focus:border-[#ff6a10]/50 focus:outline-none"
                      />
                    </div>
                    <div className="flex gap-2 pt-2">
                      <button onClick={() => setShowApply(false)} className="flex-1 py-2 rounded-lg text-sm border border-[#2a2a2a] text-[#888888] hover:bg-[#1a1a1a]">取消</button>
                      <button onClick={handleSubmit} disabled={!reason.trim()} className="flex-1 py-2 rounded-lg text-sm font-medium text-white bg-gradient-to-r from-[#ff6a10] to-[#ee0979] disabled:opacity-40">提交申请</button>
                    </div>
                  </div>
                </>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

// 功能权限路由组件
interface FeatureGateProps {
  featureKey: string;
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

export function FeatureGate({ featureKey, children, fallback }: FeatureGateProps) {
  const { status } = useUserGrayStatus();
  const feature = FEATURE_CONFIG[featureKey];

  if (!feature) return <>{children}</>;

  if (feature.level === 'closed') return <>{fallback ?? null}</>;

  if (feature.level === 'gray' && !status.isGray) {
    return <GrayFeatureLock featureKey={featureKey} />;
  }

  return <>{children}</>;
}
