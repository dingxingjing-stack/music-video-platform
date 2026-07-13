/**
 * TrackStudioHeader — Enterprise-grade top bar with status, session info, and locale switcher.
 */

import { useTranslation } from '../../i18n';
import type { PersistedSession } from '../../types/trackStudio';

interface Props {
  workflow: PersistedSession['activeWorkflow'];
  historyLength: number;
  wsConnected: boolean;
  wsStatus: string;
  viewMode: 'list' | 'multi-track';
  onViewModeChange: (mode: 'list' | 'multi-track') => void;
}

export function TrackStudioHeader({
  workflow,
  historyLength,
  wsConnected,
  wsStatus,
  viewMode,
  onViewModeChange,
}: Props) {
  const { t, locale, changeLocale } = useTranslation();

  return (
    <header className="sticky top-0 z-50 border-b border-[#2a2a38] bg-[#121212]/85 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex flex-wrap items-center justify-between gap-2">
        {/* Logo */}
        <div className="flex items-center gap-3">
          <span className="text-xl" style={{ color: '#ff6a10' }}>◆</span>
          <div>
            <h1 className="text-base font-bold tracking-tight" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              {t('common.appName')}
            </h1>
            <p className="text-[10px] text-[#777777] uppercase tracking-wider">{t('paths.pathADesc')}</p>
          </div>
        </div>

        {/* Status + Locale */}
        <div className="flex flex-wrap items-center gap-2 sm:gap-4 text-xs">
          {/* Workflow status */}
          <span className="text-[#b0b0b0]">
            {t('common.loading')}:{' '}
            <span className={workflow.running ? 'text-[#febc2e]' : 'text-[#76b900]'}>
              {workflow.running ? 'Generating...' : 'Idle'}
            </span>
          </span>

          {/* WebSocket */}
          {workflow.taskId && (
            <span className="text-[#777777] font-mono">
              {wsConnected ? '●' : '○'} {wsStatus ? wsStatus.toUpperCase() : '—'}
              {wsConnected && (
                <span className="ml-1 text-[#38bdf8] animate-pulse">live</span>
              )}
            </span>
          )}

          {/* History count */}
                    {historyLength > 0 && (
                      <span className="text-[#777777]">
                        📁 {historyLength} {t('common.save')}
                      </span>
                    )}

                    {/* 视图切换 */}
                    <div className="flex gap-1 bg-[#262626] rounded-lg p-1">
                      <button
                        onClick={() => onViewModeChange('list')}
                        className={`px-3 py-1 text-xs rounded transition-all ${
                          viewMode === 'list'
                            ? 'bg-[#3a3a3a] text-[#e0e0e0]'
                            : 'text-[#777777] hover:text-[#e0e0e0]'
                        }`}
                      >
                        列表视图
                      </button>
                      <button
                        onClick={() => onViewModeChange('multi-track')}
                        className={`px-3 py-1 text-xs rounded transition-all ${
                          viewMode === 'multi-track'
                            ? 'bg-[#ff6a10] text-[#121212] font-medium'
                            : 'text-[#777777] hover:text-[#e0e0e0]'
                        }`}
                      >
                        多轨编辑
                      </button>
                    </div>

                    {/* Locale switcher */}
          <select
            value={locale}
            onChange={(e) => changeLocale(e.target.value as any)}
            className="px-2 py-1 bg-[#262626] border border-[#2a2a38] rounded text-xs text-[#e0e0e0]"
            style={{ fontFamily: "'Inter', sans-serif" }}
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
