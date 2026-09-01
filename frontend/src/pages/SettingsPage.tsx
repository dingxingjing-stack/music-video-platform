import { useTranslation } from '../i18n/useTranslation';
import { LanguageSwitcher } from '../components/LanguageSwitcher';

export function SettingsPage() {
  const { t } = useTranslation();
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      <div className="max-w-[720px] mx-auto px-6 py-8">
        <h1 className="text-2xl font-black tracking-tight">{t('settings.title')}</h1>
        <p className="mt-1 text-sm text-[#8a8a8a]">{t('settings.subtitle')}</p>

        <div className="mt-6 space-y-4">
          <div className="rounded-2xl bg-[#141414] border border-[#1f1f1f] p-6">
            <h3 className="text-sm font-semibold text-white">{t('settings.language')}</h3>
            <div className="mt-3"><LanguageSwitcher /></div>
          </div>
          <div className="rounded-2xl bg-[#141414] border border-[#1f1f1f] p-6">
            <h3 className="text-sm font-semibold text-white">{t('settings.account')}</h3>
            <p className="mt-1 text-sm text-[#8a8a8a]">{t('settings.accountDesc')}</p>
          </div>
          <div className="rounded-2xl bg-[#141414] border border-[#1f1f1f] p-6">
            <h3 className="text-sm font-semibold text-white">{t('settings.about')}</h3>
            <p className="mt-1 text-sm text-[#8a8a8a]">{t('settings.aboutText')}<br/>© 2026 Zyvexo. All rights reserved.</p>
            <div className="mt-3 flex flex-wrap gap-3 text-xs">
              <a href="/legal/terms" className="text-[#8a8a8a] hover:text-white underline">{t('legal.links.terms')}</a>
              <a href="/legal/privacy" className="text-[#8a8a8a] hover:text-white underline">{t('legal.links.privacy')}</a>
              <a href="/legal/voice-cloning" className="text-[#8a8a8a] hover:text-white underline">{t('legal.links.voiceCloning')}</a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default SettingsPage;
