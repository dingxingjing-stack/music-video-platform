import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from '../i18n/useTranslation';

const STORAGE_KEY = 'beta_consent_accepted';

const RULES = [
  { icon: '🎁', title: 'beta.r1Title', text: 'beta.r1Text' },
  { icon: '🔓', title: 'beta.r2Title', text: 'beta.r2Text' },
  { icon: '💧', title: 'beta.r3Title', text: 'beta.r3Text' },
  { icon: '🔒', title: 'beta.r4Title', text: 'beta.r4Text' },
  { icon: '⚠️', title: 'beta.r5Title', text: 'beta.r5Text' },
];

export function BetaConsentModal() {
  const { t } = useTranslation();
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
                  <h2 className="text-xl font-bold gradient-text">{t('beta.heading')}</h2>
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
                    <div className="text-sm font-medium text-white">{t(r.title)}</div>
                    <div className="text-xs text-[#888888] mt-1 leading-relaxed">{t(r.text)}</div>
                  </div>
                </div>
              ))}
            </div>

            {/* Footer */}
            <div className="px-6 py-4 border-t border-[#2a2a2a] flex flex-col sm:flex-row gap-3 items-center justify-between">
              <p className="text-[10px] text-[#555555] text-center sm:text-left">
                {t('beta.consentHint')}
              </p>
              <button
                onClick={handleAccept}
                className="w-full sm:w-auto px-6 py-2.5 rounded-xl font-medium text-sm text-white bg-gradient-to-r from-[#ff6a10] to-[#ee0979] hover:opacity-90 transition-opacity whitespace-nowrap"
              >
                {t('beta.agreeButton')}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
