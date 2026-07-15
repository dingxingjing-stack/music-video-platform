import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const STORAGE_KEY = 'beta_consent_accepted';

const RULES = [
  { icon: '🎁', title: '每日免费额度', text: '普通用户每日可免费生成 10 次作品，资深测试用户 30 次/日' },
  { icon: '🔓', title: '灰度功能解锁', text: '活跃度达到 100 分且累计生成 ≥50 次可申请灰度权限，解锁 MV 生成、协作编辑等高级功能' },
  { icon: '💧', title: '公测水印', text: '公测期间生成的所有作品将自动嵌入「公测水印」，可用于个人学习欣赏，不可商用' },
  { icon: '🔒', title: '付费模块关闭', text: '素材商城、付费订阅、UGC 收益提现等功能公测期间暂不开放' },
  { icon: '⚠️', title: '禁止商用', text: '公测阶段所有生成的测试素材仅限个人使用，禁止商业用途' },
];

export function BetaConsentModal() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    const accepted = localStorage.getItem(STORAGE_KEY);
    if (!accepted) {
      const timer = setTimeout(() => setShow(true), 800);
      return () => clearTimeout(timer);
    }
  }, []);

  const handleAccept = () => {
    localStorage.setItem(STORAGE_KEY, 'true');
    localStorage.setItem(STORAGE_KEY + '_at', new Date().toISOString());
    setShow(false);
  };

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
          onClick={(e) => e.target === e.currentTarget && handleAccept()}
        >
          <motion.div
            initial={{ scale: 0.9, y: 20 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.9, y: 20 }}
            className="w-full max-w-lg bg-gradient-to-b from-[#1e1e1e] to-[#0e0e0e] border border-[#2a2a2a] rounded-2xl overflow-hidden shadow-2xl"
          >
            {/* Header */}
            <div className="px-6 pt-6 pb-4 bg-gradient-to-r from-[#ff6a10]/10 to-[#ee0979]/10 border-b border-[#2a2a2a]">
              <div className="flex items-center gap-3">
                <span className="text-3xl">🎵</span>
                <div>
                  <h2 className="text-xl font-bold gradient-text">公测须知</h2>
                  <p className="text-xs text-[#888888] mt-0.5">Beta Test Agreement · v2.0</p>
                </div>
              </div>
            </div>

            {/* Rules */}
            <div className="px-6 py-5 space-y-3 max-h-[50vh] overflow-y-auto">
              {RULES.map((r, i) => (
                <div key={i} className="flex gap-3 p-3 rounded-lg bg-[#121212] border border-[#2a2a2a]">
                  <span className="text-xl flex-shrink-0">{r.icon}</span>
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-white">{r.title}</div>
                    <div className="text-xs text-[#888888] mt-1 leading-relaxed">{r.text}</div>
                  </div>
                </div>
              ))}
            </div>

            {/* Footer */}
            <div className="px-6 py-4 border-t border-[#2a2a2a] flex flex-col sm:flex-row gap-3 items-center justify-between">
              <p className="text-[10px] text-[#555555] text-center sm:text-left">
                点击同意即表示您已阅读并接受上述公测规则
              </p>
              <button
                onClick={handleAccept}
                className="w-full sm:w-auto px-6 py-2.5 rounded-xl font-medium text-sm text-white bg-gradient-to-r from-[#ff6a10] to-[#ee0979] hover:opacity-90 transition-opacity whitespace-nowrap"
              >
                ✓ 已阅读并同意
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
