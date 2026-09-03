/**
 * IdleState — Empty-state illustration when no tracks or history exist.
 */

import { useTranslation } from '../../i18n/useTranslation';

export function IdleState() {
  const { t } = useTranslation();
  return (
    <div className="text-center py-12 text-[#777777]">
      <p className="text-4xl mb-3">🎧</p>
      <p className="text-sm">{t('trackStudio.idleSelectPrompt')}</p>
      <div className="mt-4 grid grid-cols-3 gap-4 text-xs max-w-lg mx-auto">
        <div className="p-3 rounded-lg bg-[#1f1f1f]/50 border border-[#2a2a38]">
          <p className="text-[#b0b0b0] font-medium">{t('trackStudio.pathA')}</p>
          <p className="text-[#777777] mt-1">{t('trackStudio.pathADesc')}</p>
        </div>
        <div className="p-3 rounded-lg bg-[#1f1f1f]/50 border border-[#2a2a38]">
          <p className="text-[#b0b0b0] font-medium">{t('trackStudio.pathB')}</p>
          <p className="text-[#777777] mt-1">{t('trackStudio.pathBDesc')}</p>
        </div>
        <div className="p-3 rounded-lg bg-[#1f1f1f]/50 border border-[#2a2a38]">
          <p className="text-[#b0b0b0] font-medium">{t('trackStudio.pathC')}</p>
          <p className="text-[#777777] mt-1">{t('trackStudio.pathCDesc')}</p>
        </div>
      </div>
    </div>
  );
}
