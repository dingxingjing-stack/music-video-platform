import { Link } from 'react-router-dom';
import { useTranslation } from '../i18n/useTranslation';

export default function NotFound() {
  const { t } = useTranslation();
  return (
    <div className="min-h-screen bg-[#0a0a0a] flex flex-col items-center justify-center px-6 text-center">
      <p className="text-6xl font-black text-white">404</p>
      <Link
        to="/"
        className="mt-6 inline-block px-4 py-2 rounded-lg bg-white text-[#0a0a0a] text-sm font-semibold hover:bg-[#ededed] transition"
      >
        {t('nav.home')}
      </Link>
    </div>
  );
}
