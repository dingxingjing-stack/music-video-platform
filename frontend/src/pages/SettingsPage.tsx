import { useTranslation } from '../i18n/useTranslation';
import { LanguageSwitcher } from '../components/LanguageSwitcher';

export function SettingsPage() {
  const { t } = useTranslation();
  const tr = (k:string, fb:string)=> t(k)===k?fb:t(k);
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      <div className="max-w-[720px] mx-auto px-6 py-8">
        <h1 className="text-2xl font-black tracking-tight">{tr('settings.title','Settings')}</h1>
        <p className="mt-1 text-sm text-[#8a8a8a]">{tr('settings.subtitle','Manage preferences and account')}</p>

        <div className="mt-6 space-y-4">
          <div className="rounded-2xl bg-[#141414] border border-[#1f1f1f] p-6">
            <h3 className="text-sm font-semibold text-white">{tr('settings.language','Language')}</h3>
            <div className="mt-3"><LanguageSwitcher /></div>
          </div>
          <div className="rounded-2xl bg-[#141414] border border-[#1f1f1f] p-6">
            <h3 className="text-sm font-semibold text-white">{tr('settings.account','Account')}</h3>
            <p className="mt-1 text-sm text-[#8a8a8a]">Account management is available via the sidebar user section and login modal. More settings will appear here as backend features land.</p>
          </div>
          <div className="rounded-2xl bg-[#141414] border border-[#1f1f1f] p-6">
            <h3 className="text-sm font-semibold text-white">{tr('settings.about','About')}</h3>
            <p className="mt-1 text-sm text-[#8a8a8a]">Zyvexo · AI Music Studio · Public Beta v2.0<br/>© 2026 Zyvexo. All rights reserved.</p>
            <div className="mt-3 flex flex-wrap gap-3 text-xs">
              <a href="/legal/terms" className="text-[#8a8a8a] hover:text-white underline">Terms</a>
              <a href="/legal/privacy" className="text-[#8a8a8a] hover:text-white underline">Privacy</a>
              <a href="/legal/voice-cloning" className="text-[#8a8a8a] hover:text-white underline">Voice Clone Policy</a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default SettingsPage;
