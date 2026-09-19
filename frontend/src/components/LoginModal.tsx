import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useTranslation } from '../i18n/useTranslation';
import { PHONE_COUNTRIES } from '../config/phoneCountries';

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
  const { showLogin, setShowLogin, login, sendPhoneOtp, verifyPhoneOtp } = useAuth();
  const { t } = useTranslation();
  const [mode, setMode] = useState<'email' | 'phone'>('email');
  const [phoneStep, setPhoneStep] = useState<'phone' | 'otp'>('phone');
  const [email, setEmail] = useState('');
  const [pwd, setPwd] = useState('');
  const [countryCode, setCountryCode] = useState('CN');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [otp, setOtp] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const selectedCountry = PHONE_COUNTRIES.find((country) => country.code === countryCode) ?? PHONE_COUNTRIES.find((country) => country.code === 'CN')!;
  const dialCode = selectedCountry.dialCode;
  const getFullPhone = () => `${dialCode}${phoneNumber.replace(/\D/g, '')}`;

  // 把 Supabase 原始英文错误映射为用户可读的 i18n 文案（与 RegisterPage.mapError 一致）
  const mapEmailError = (e: any): string => {
    const msg: string = e?.message || '';
    const low = msg.toLowerCase();
    if (low.includes('not confirmed') || low.includes('email not confirmed') || low.includes('unverified')) {
      return t('auth.emailNotConfirmed');
    }
    if (low.includes('invalid login') || low.includes('invalid credentials') || low.includes('password') || low.includes('email')) {
      return t('auth.invalidCredentials');
    }
    if (low.includes('network') || low.includes('fetch') || low.includes('timeout')) {
      return t('auth.networkError');
    }
    return t('auth.loginFailed');
  };

  const mapOtpError = (e: any): string => {
    const msg: string = e?.message || '';
    const low = msg.toLowerCase();
    if (low.includes('expired')) return t('auth.otpExpired');
    if (low.includes('invalid') || low.includes('token') || low.includes('otp')) return t('auth.otpInvalid');
    if (low.includes('phone')) return t('auth.invalidPhone');
    if (low.includes('network') || low.includes('fetch') || low.includes('timeout')) return t('auth.networkError');
    return t('auth.otpFailed');
  };

  const switchMode = (next: 'email' | 'phone') => {
    setMode(next);
    setErr(null);
    setOtp('');
    if (next === 'email') setPhoneStep('phone');
  };

  const submitEmail = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.includes('@')) return;
    setErr(null);
    setSubmitting(true);
    try {
      await login(email, pwd);
    } catch (e: any) {
      setErr(mapEmailError(e));
    } finally {
      setSubmitting(false);
    }
  };

  const submitPhone = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (!phoneNumber.replace(/\D/g, '').match(/^\d{5,14}$/)) {
      setErr(t('auth.invalidPhone'));
      return;
    }
    setSubmitting(true);
    try {
      await sendPhoneOtp(getFullPhone());
      setPhoneStep('otp');
    } catch (e: any) {
      setErr(mapOtpError(e));
    } finally {
      setSubmitting(false);
    }
  };

  const submitOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!otp.trim()) return;
    setErr(null);
    setSubmitting(true);
    try {
      await verifyPhoneOtp(getFullPhone(), otp.trim());
    } catch (e: any) {
      setErr(mapOtpError(e));
    } finally {
      setSubmitting(false);
    }
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

        <div className="grid grid-cols-2 gap-2 mb-4 text-xs">
          <button onClick={() => switchMode('email')} className={`py-2 rounded-lg border transition ${mode === 'email' ? 'border-orange-400 text-white bg-[#262626]' : 'border-[#2a2a2a] text-zinc-500 hover:text-white'}`}>
            {t('auth.continueEmail')}
          </button>
          <button onClick={() => switchMode('phone')} className={`py-2 rounded-lg border transition ${mode === 'phone' ? 'border-orange-400 text-white bg-[#262626]' : 'border-[#2a2a2a] text-zinc-500 hover:text-white'}`}>
            {t('auth.continuePhone')}
          </button>
        </div>

        {mode === 'email' && (
          <form onSubmit={submitEmail} className="space-y-4">
            <input type="email" placeholder={t('auth.emailPlaceholder')} value={email} onChange={e => setEmail(e.target.value)} required className="w-full px-4 py-3 bg-[#0e0e0e] border border-[#2a2a2a] rounded-lg text-white text-sm focus:outline-none focus:border-orange-400" />
            <input type="password" placeholder={t('auth.passwordPlaceholder')} value={pwd} onChange={e => setPwd(e.target.value)} required className="w-full px-4 py-3 bg-[#0e0e0e] border border-[#2a2a2a] rounded-lg text-white text-sm focus:outline-none focus:border-orange-400" />
            {err && <p className="text-xs text-red-400">{err}</p>}
            <button type="submit" disabled={submitting} className="w-full py-3 bg-gradient-to-r from-orange-400 to-pink-500 text-white font-semibold rounded-lg hover:opacity-90 transition disabled:opacity-50">
              {t('auth.loginRegister')}
            </button>
          </form>
        )}

        {mode === 'phone' && phoneStep === 'phone' && (
          <form onSubmit={submitPhone} className="space-y-4">
            <div className="flex gap-2">
              <select value={countryCode} onChange={(e) => setCountryCode(e.target.value)} className="w-48 px-3 py-3 bg-[#0e0e0e] border border-[#2a2a2a] rounded-lg text-white text-sm focus:outline-none focus:border-orange-400" aria-label={t('auth.phoneCountryCode')}>
                {PHONE_COUNTRIES.map((country) => <option key={country.code} value={country.code}>{country.name} {country.dialCode}</option>)}
              </select>
              <input inputMode="numeric" autoComplete="tel-national" placeholder={t('auth.phoneNumberPlaceholder')} value={phoneNumber} onChange={e => setPhoneNumber(e.target.value)} required className="min-w-0 flex-1 px-4 py-3 bg-[#0e0e0e] border border-[#2a2a2a] rounded-lg text-white text-sm focus:outline-none focus:border-orange-400" />
            </div>
            <p className="text-xs text-zinc-500">{t('auth.phoneOtpHint')}</p>
            {err && <p className="text-xs text-red-400">{err}</p>}
            <button type="submit" disabled={submitting} className="w-full py-3 bg-gradient-to-r from-orange-400 to-pink-500 text-white font-semibold rounded-lg hover:opacity-90 transition disabled:opacity-50">
              {submitting ? t('auth.sendingCode') : t('auth.sendVerificationCode')}
            </button>
          </form>
        )}

        {mode === 'phone' && phoneStep === 'otp' && (
          <form onSubmit={submitOtp} className="space-y-4">
            <p className="text-xs text-zinc-400">{t('auth.verificationSentTo')}: {getFullPhone()}</p>
            <input inputMode="numeric" autoComplete="one-time-code" placeholder={t('auth.verificationCode')} value={otp} onChange={e => setOtp(e.target.value.replace(/\D/g, '').slice(0, 8))} required className="w-full px-4 py-3 bg-[#0e0e0e] border border-[#2a2a2a] rounded-lg text-white text-sm focus:outline-none focus:border-orange-400" />
            {err && <p className="text-xs text-red-400">{err}</p>}
            <button type="submit" disabled={submitting} className="w-full py-3 bg-gradient-to-r from-orange-400 to-pink-500 text-white font-semibold rounded-lg hover:opacity-90 transition disabled:opacity-50">
              {submitting ? t('auth.verifyingCode') : t('auth.verifyAndLogin')}
            </button>
            <div className="flex items-center justify-between text-xs">
              <button type="button" onClick={() => { setPhoneStep('phone'); setOtp(''); setErr(null); }} className="py-2 text-zinc-500 hover:text-white transition">{t('auth.changePhoneNumber')}</button>
              <button type="button" disabled={submitting} onClick={async () => { setErr(null); setSubmitting(true); try { await sendPhoneOtp(getFullPhone()); } catch (e: any) { setErr(mapOtpError(e)); } finally { setSubmitting(false); } }} className="py-2 text-orange-400 hover:text-orange-300 transition">
                {t('auth.resendCode')}
              </button>
            </div>
          </form>
        )}

        <div className="flex items-center justify-between mt-3">
          <Link
            to="/register"
            onClick={() => setShowLogin(false)}
            className="py-2 text-xs text-orange-400 hover:text-orange-300 transition"
          >
            {t('auth.noAccount')}
          </Link>
          <button onClick={() => setShowLogin(false)} className="py-2 text-xs text-zinc-500 hover:text-white transition">{t('auth.continueBrowsing')}</button>
        </div>
      </div>
    </div>
  );
}
