import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useTranslation } from '../i18n/useTranslation';

export function RequireAuth({ children, feature }: { children: React.ReactNode; feature?: string }) {
  const { isLoggedIn, setShowLogin } = useAuth();
  const { t } = useTranslation();
  if (isLoggedIn) return <>{children}</>;
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="text-center p-10 max-w-md">
        <div className="text-6xl mb-4">🔒</div>
        <h2 className="text-xl font-semibold mb-2 text-white">{t('auth.pleaseLogin')}</h2>
        <p className="text-zinc-400 mb-6 text-sm">{feature ? t('auth.featureNeedsLogin', { feature }) : t('auth.loginToUseAll')}</p>
        <button onClick={() => setShowLogin(true)} className="px-6 py-3 bg-gradient-to-r from-orange-400 to-pink-500 text-white font-semibold rounded-lg hover:opacity-90 transition">
          {t('auth.loginNow')}
        </button>
      </div>
    </div>
  );
}

export function LoginModal() {
  const { showLogin, setShowLogin, login } = useAuth();
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [pwd, setPwd] = useState('');
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.includes('@')) return;
    await login(email, pwd);
  };
  if (!showLogin) return null;
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setShowLogin(false)}>
      <div className="bg-[#1a1a1a] border border-[#2a2a2a] rounded-2xl p-8 w-full max-w-md mx-4" onClick={e => e.stopPropagation()}>
        <div className="text-center mb-6">
          <div className="text-4xl mb-2">🎵</div>
          <h2 className="text-xl font-semibold text-white">{t('auth.loginTitle')}</h2>
          <p className="text-xs text-zinc-500 mt-1">{t('auth.loginSubtitle')}</p>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <input type="email" placeholder={t('auth.emailPlaceholder')} value={email} onChange={e => setEmail(e.target.value)} required className="w-full px-4 py-3 bg-[#0e0e0e] border border-[#2a2a2a] rounded-lg text-white text-sm focus:outline-none focus:border-orange-400" />
          <input type="password" placeholder={t('auth.passwordPlaceholder')} value={pwd} onChange={e => setPwd(e.target.value)} required className="w-full px-4 py-3 bg-[#0e0e0e] border border-[#2a2a2a] rounded-lg text-white text-sm focus:outline-none focus:border-orange-400" />
          <p className="text-[10px] text-zinc-600">{t('auth.betaHint')}</p>
          <button type="submit" className="w-full py-3 bg-gradient-to-r from-orange-400 to-pink-500 text-white font-semibold rounded-lg hover:opacity-90 transition">{t('auth.loginRegister')}</button>
        </form>
        <button onClick={() => setShowLogin(false)} className="w-full mt-3 py-2 text-xs text-zinc-500 hover:text-white transition">{t('auth.continueBrowsing')}</button>
      </div>
    </div>
  );
}