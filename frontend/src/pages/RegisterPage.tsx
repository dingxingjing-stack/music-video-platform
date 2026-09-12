import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useTranslation } from '../i18n/useTranslation';

/**
 * 产品级注册页面（Phase 3-2B 升级版）
 * 流程：
 *   选择方式（Email / Phone）
 *   → Email 分步：Email → Password(+confirm) → signUp
 *   → 情况 A（有 session）→ onboarding → 首页
 *   → 情况 B（需邮箱验证）→ Check your email（resend / back to login）
 * 身份唯一来源 = Supabase Auth；前端绝不 INSERT public.users / 不伪造 user_id。
 */

type Step = 'method' | 'email' | 'password' | 'verify' | 'onboarding';

export function RegisterPage() {
  const { register, resendVerification } = useAuth();
  const { t, locale, changeLocale, localeNames } = useTranslation();
  const navigate = useNavigate();

  const [step, setStep] = useState<Step>('method');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [displayName, setDisplayName] = useState('');
  const [preferredLang, setPreferredLang] = useState<string>(locale);
  const [err, setErr] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [resendState, setResendState] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle');

  const mapError = (e: any): string => {
    const msg: string = e?.message || '';
    const low = msg.toLowerCase();
    if (low.includes('already registered') || low.includes('already been registered')) return t('auth.emailExists');
    if (low.includes('password') && (low.includes('at least') || low.includes('short') || low.includes('6'))) return t('auth.passwordTooShort');
    if (low.includes('email') && (low.includes('valid') || low.includes('format') || low.includes('invalid'))) return t('auth.invalidEmail');
    if (low.includes('network') || low.includes('fetch') || low.includes('timeout')) return t('auth.networkError');
    return t('auth.genericError');
  };

  const goEmail = () => {
    setErr(null);
    setStep('email');
  };

  const goPassword = () => {
    setErr(null);
    if (!email.includes('@')) {
      setErr(t('auth.invalidEmail'));
      return;
    }
    setStep('password');
  };

  const goOnboarding = () => {
    // 把 onboarding 的 preferred language 应用到当前站点语言
    if (preferredLang !== locale) changeLocale(preferredLang as any);
    navigate('/', { replace: true });
  };

  const submitRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (!password) { setErr(t('auth.passwordTooShort')); return; }
    if (password !== confirmPassword) { setErr(t('auth.passwordMismatch')); return; }
    if (password.length < 6) { setErr(t('auth.passwordTooShort')); return; }
    setSubmitting(true);
    try {
      const { needsEmailConfirmation } = await register(email, password);
      if (needsEmailConfirmation) {
        setStep('verify');
      } else {
        if (!displayName.trim()) {
          setStep('onboarding');
        } else {
          goOnboarding();
        }
      }
    } catch (e: any) {
      setErr(mapError(e));
    } finally {
      setSubmitting(false);
    }
  };

  const resend = async () => {
    setResendState('sending');
    setErr(null);
    try {
      await resendVerification(email);
      setResendState('sent');
    } catch {
      setResendState('error');
    } finally {
      setResendState((s) => (s === 'sending' ? 'error' : s));
    }
  };

  const inputCls = 'w-full px-4 py-3 bg-[#0e0e0e] border border-[#2a2a2a] rounded-lg text-white text-sm focus:outline-none focus:border-orange-400';
  const primaryBtn = 'w-full py-3 bg-gradient-to-r from-orange-400 to-pink-500 text-white font-semibold rounded-lg hover:opacity-90 transition disabled:opacity-50';

  // ── Step: method ──
  if (step === 'method') {
    return (
      <div className="min-h-screen bg-[#0a0a0a] text-[#e0e0e0] flex items-center justify-center px-4">
        <div className="w-full max-w-md bg-[#1a1a1a] border border-[#2a2a2a] rounded-2xl p-8">
          <div className="text-center mb-6">
            <div className="text-4xl mb-2">🎵</div>
            <h1 className="text-xl font-semibold text-white">{t('auth.registerTitle')}</h1>
            <p className="text-xs text-zinc-500 mt-1">{t('auth.registerSubtitle')}</p>
          </div>

          <div className="space-y-3">
            <button onClick={goEmail} className={primaryBtn}>{t('auth.continueEmail')}</button>
            <button onClick={() => setErr(t('auth.phoneNotConfigured'))} className="w-full py-3 bg-[#1e1e1e] border border-[#2a2a2a] text-white font-semibold rounded-lg hover:bg-[#262626] transition">
              {t('auth.continuePhone')}
            </button>
            {err && <p className="text-xs text-amber-400 text-center">{err}</p>}
          </div>

          <div className="mt-4 text-center">
            <Link to="/" className="text-xs text-zinc-500 hover:text-white transition">{t('auth.alreadyHaveAccount')}</Link>
          </div>

          <div className="mt-6 pt-4 border-t border-[#2a2a2a] flex justify-center gap-4 text-[10px] text-zinc-500">
            <Link to="/legal/terms" className="hover:text-white transition">{t('auth.termsOfService')}</Link>
            <Link to="/legal/privacy" className="hover:text-white transition">{t('auth.privacyPolicy')}</Link>
          </div>
        </div>
      </div>
    );
  }

  // ── Step: email ──
  if (step === 'email') {
    return (
      <div className="min-h-screen bg-[#0a0a0a] text-[#e0e0e0] flex items-center justify-center px-4">
        <div className="w-full max-w-md bg-[#1a1a1a] border border-[#2a2a2a] rounded-2xl p-8">
          <h2 className="text-xl font-semibold text-white mb-6">{t('auth.emailLabel')}</h2>
          <form onSubmit={(e) => { e.preventDefault(); goPassword(); }} className="space-y-4">
            <input type="email" placeholder={t('auth.emailPlaceholder')} value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" className={inputCls} />
            {err && <p className="text-xs text-red-400">{err}</p>}
            <button type="submit" className={primaryBtn}>{t('auth.continueButton')}</button>
          </form>
          <button onClick={() => setStep('method')} className="w-full mt-3 py-2 text-xs text-zinc-500 hover:text-white transition">{t('auth.backToLogin')}</button>
        </div>
      </div>
    );
  }

  // ── Step: password ──
  if (step === 'password') {
    return (
      <div className="min-h-screen bg-[#0a0a0a] text-[#e0e0e0] flex items-center justify-center px-4">
        <div className="w-full max-w-md bg-[#1a1a1a] border border-[#2a2a2a] rounded-2xl p-8">
          <h2 className="text-xl font-semibold text-white mb-2">{t('auth.createAccount')}</h2>
          <p className="text-xs text-zinc-500 mb-6">{email}</p>
          <form onSubmit={submitRegister} className="space-y-4">
            <div className="relative">
              <input type={showPassword ? 'text' : 'password'} placeholder={t('auth.passwordPlaceholder')} value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="new-password" className={inputCls} />
              <button type="button" onClick={() => setShowPassword((s) => !s)} className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-zinc-500 hover:text-white">
                {showPassword ? t('auth.hidePassword') : t('auth.showPassword')}
              </button>
            </div>
            <input type={showPassword ? 'text' : 'password'} placeholder={t('auth.confirmPassword')} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required autoComplete="new-password" className={inputCls} />
            {err && <p className="text-xs text-red-400">{err}</p>}
            <button type="submit" disabled={submitting} className={primaryBtn}>{t('auth.createAccount')}</button>
          </form>
          <button onClick={() => setStep('email')} className="w-full mt-3 py-2 text-xs text-zinc-500 hover:text-white transition">{t('auth.backToLogin')}</button>
        </div>
      </div>
    );
  }

  // ── Step: verify (情况 B) ──
  if (step === 'verify') {
    return (
      <div className="min-h-screen bg-[#0a0a0a] text-[#e0e0e0] flex items-center justify-center px-4">
        <div className="w-full max-w-md bg-[#1a1a1a] border border-[#2a2a2a] rounded-2xl p-8 text-center">
          <div className="text-4xl mb-3">📩</div>
          <h2 className="text-xl font-semibold text-white">{t('auth.checkEmailTitle')}</h2>
          <p className="text-xs text-zinc-400 mt-2">{t('auth.checkEmailDetail')}</p>
          <p className="text-sm text-white mt-3 font-medium">{email}</p>
          <div className="space-y-3 mt-6">
            <button onClick={resend} disabled={resendState === 'sending'} className={primaryBtn}>
              {resendState === 'sent' ? t('auth.resendSent') : t('auth.resendEmail')}
            </button>
            {resendState === 'error' && <p className="text-xs text-red-400">{t('auth.resendFailed')}</p>}
            <Link to="/" className="block w-full py-2 text-xs text-zinc-500 hover:text-white transition text-center">{t('auth.backToLogin')}</Link>
          </div>
        </div>
      </div>
    );
  }

  // ── Step: onboarding (情况 A) ──
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-[#e0e0e0] flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-[#1a1a1a] border border-[#2a2a2a] rounded-2xl p-8">
        <div className="text-center mb-6">
          <div className="text-4xl mb-2">🎉</div>
          <h2 className="text-xl font-semibold text-white">{t('auth.onboardingTitle')}</h2>
        </div>
        <form onSubmit={(e) => { e.preventDefault(); goOnboarding(); }} className="space-y-4">
          <input placeholder={t('auth.displayName')} value={displayName} onChange={(e) => setDisplayName(e.target.value)} required className={inputCls} />
          <select value={preferredLang} onChange={(e) => setPreferredLang(e.target.value)} className={inputCls}>
            {Object.entries(localeNames).map(([code, name]) => (
              <option key={code} value={code}>{name}</option>
            ))}
          </select>
          <button type="submit" className={primaryBtn}>{t('auth.continueToZyvexo')}</button>
          <button type="button" onClick={() => navigate('/', { replace: true })} className="w-full py-2 text-xs text-zinc-500 hover:text-white transition">{t('auth.skip')}</button>
        </form>
      </div>
    </div>
  );
}

export default RegisterPage;