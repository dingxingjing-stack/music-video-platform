import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useTranslation } from '../i18n/useTranslation';

/**
 * 注册页面（Phase 3-2B）
 * 链路：/register → supabase.auth.signUp() → auth.users → DB trigger → public.users
 * 身份唯一来源 = Supabase Auth；前端绝不 INSERT public.users / 不伪造 user_id。
 */
export function RegisterPage() {
  const { register } = useAuth();
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false); // true = 需查邮箱
  const [submitting, setSubmitting] = useState(false);

  // 把 Supabase 常见错误映射为 i18n；未知错误回退通用文案（不暴露内部堆栈）。
  const mapError = (e: any): string => {
    const msg: string = e?.message || '';
    const low = msg.toLowerCase();
    if (low.includes('already registered') || low.includes('already been registered')) return t('auth.emailExists');
    if (low.includes('password') && (low.includes('at least') || low.includes('short') || low.includes('6'))) return t('auth.passwordTooShort');
    if (low.includes('email') && (low.includes('valid') || low.includes('format') || low.includes('invalid'))) return t('auth.invalidEmail');
    if (low.includes('network') || low.includes('fetch') || low.includes('timeout')) return t('auth.networkError');
    return t('auth.genericError');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (!email.includes('@')) {
      setErr(t('auth.invalidEmail'));
      return;
    }
    if (!password) {
      setErr(t('auth.passwordTooShort'));
      return;
    }
    if (password !== confirmPassword) {
      setErr(t('auth.passwordMismatch'));
      return;
    }
    if (password.length < 6) {
      setErr(t('auth.passwordTooShort'));
      return;
    }
    setSubmitting(true);
    try {
      const { needsEmailConfirmation } = await register(email, password);
      if (needsEmailConfirmation) {
        setSubmitted(true);
      } else {
        navigate('/', { replace: true });
      }
    } catch (e: any) {
      setErr(mapError(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-[#e0e0e0] flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-[#1a1a1a] border border-[#2a2a2a] rounded-2xl p-8">
        <div className="text-center mb-6">
          <div className="text-4xl mb-2">🎵</div>
          <h1 className="text-xl font-semibold text-white">{t('auth.registerTitle')}</h1>
          <p className="text-xs text-zinc-500 mt-1">{t('auth.registerSubtitle')}</p>
        </div>

        {submitted ? (
          <div className="text-center space-y-4">
            <div className="text-3xl">📩</div>
            <p className="text-sm text-white">{t('auth.registrationSuccess')}</p>
            <p className="text-xs text-zinc-400">{t('auth.checkEmail')}</p>
            <Link
              to="/"
              className="inline-block w-full py-3 bg-gradient-to-r from-orange-400 to-pink-500 text-white font-semibold rounded-lg hover:opacity-90 transition text-center"
            >
              {t('auth.backToLogin')}
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <input
              type="email"
              placeholder={t('auth.emailPlaceholder')}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              className="w-full px-4 py-3 bg-[#0e0e0e] border border-[#2a2a2a] rounded-lg text-white text-sm focus:outline-none focus:border-orange-400"
            />
            <input
              type="password"
              placeholder={t('auth.passwordPlaceholder')}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="new-password"
              className="w-full px-4 py-3 bg-[#0e0e0e] border border-[#2a2a2a] rounded-lg text-white text-sm focus:outline-none focus:border-orange-400"
            />
            <input
              type="password"
              placeholder={t('auth.confirmPassword')}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              autoComplete="new-password"
              className="w-full px-4 py-3 bg-[#0e0e0e] border border-[#2a2a2a] rounded-lg text-white text-sm focus:outline-none focus:border-orange-400"
            />
            {err && <p className="text-xs text-red-400">{err}</p>}
            <button
              type="submit"
              disabled={submitting}
              className="w-full py-3 bg-gradient-to-r from-orange-400 to-pink-500 text-white font-semibold rounded-lg hover:opacity-90 transition disabled:opacity-50"
            >
              {t('auth.createAccount')}
            </button>
          </form>
        )}

        {!submitted && (
          <Link
            to="/"
            className="block w-full mt-3 py-2 text-xs text-zinc-500 hover:text-white transition text-center"
          >
            {t('auth.alreadyHaveAccount')}
          </Link>
        )}
      </div>
    </div>
  );
}

export default RegisterPage;