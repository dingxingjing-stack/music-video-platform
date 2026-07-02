/**
 * TrackStudioHeader — Top bar with title, backend status, and session info.
 */

import { useTranslation } from '../../i18n';
import type { PersistedSession } from '../../types/trackStudio';

interface Props {
  workflow: PersistedSession['activeWorkflow'];
  historyLength: number;
  wsConnected: boolean;
  wsStatus: string;
}

export function TrackStudioHeader({
  workflow,
  historyLength,
  wsConnected,
  wsStatus,
}: Props) {
  const { t, locale, changeLocale } = useTranslation();

  return (
    <header className="border-b border-gray-800 bg-gray-950/80 backdrop-blur">
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🎛️</span>
          <div>
            <h1 className="text-lg font-bold tracking-tight">{t('common.appName')}</h1>
            <p className="text-xs text-gray-500">{t('paths.pathADesc')}</p>
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs text-gray-500">
          <span>
            {t('common.loading')}:{' '}
            <span className={workflow.running ? 'text-amber-400' : 'text-emerald-400'}>
              {workflow.running ? 'Generating...' : 'Idle'}
            </span>
          </span>
          {workflow.taskId && (
            <span className="text-gray-600 font-mono">
              {wsConnected ? '●' : '○'} {wsStatus ? wsStatus.toUpperCase() : '—'}
              {wsConnected && (
                <span className="ml-1 text-blue-400 animate-pulse">live</span>
              )}
            </span>
          )}
          {historyLength > 0 && (
            <span className="text-gray-600">
              📁 {historyLength} {t('common.save')}
            </span>
          )}
          <select
            value={locale}
            onChange={(e) => changeLocale(e.target.value as any)}
            className="px-2 py-1 bg-gray-800 border border-gray-700 rounded text-xs text-white"
          >
            {['zh', 'en', 'ja', 'ko', 'es', 'fr', 'pt', 'ru', 'de'].map((l) => (
              <option key={l} value={l}>
                {l === 'zh' && '中文'}
                {l === 'en' && 'English'}
                {l === 'ja' && '日本語'}
                {l === 'ko' && '한국어'}
                {l === 'es' && 'Español'}
                {l === 'fr' && 'Français'}
                {l === 'pt' && 'Português'}
                {l === 'ru' && 'Русский'}
                {l === 'de' && 'Deutsch'}
              </option>
            ))}
          </select>
        </div>
      </div>
    </header>
  );
}
