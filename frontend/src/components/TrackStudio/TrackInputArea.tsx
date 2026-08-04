/**
 * TrackInputArea — Prompt / file upload / batch configuration input area.
 *
 * Renders different inputs based on:
 *   - Selected path (a/b/c)
 *   - Mode (single vs batch)
 *   - Whether a file is uploaded
 */

import { useRef } from 'react';
import { useTranslation } from '../../i18n';
import type { PathDefinition, MidiProject } from '../../types/trackStudio';
import { PianoRoll } from './PianoRoll';

interface Props {
  pathDef: PathDefinition;
  batchMode: boolean;
  batchPrompts: string;
  ttsText: string;
  uploadedFile: { name: string; size: number } | null;
  uploadError: string | null;
  batchDuration: number;
  batchTemperature: number;
  onPromptChange: (val: string) => void;
  onTtsTextChange: (val: string) => void;
  onBatchPromptsChange: (val: string) => void;
  onFileUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onFileRemove: () => void;
  onBatchModeToggle: (batch: boolean) => void;
  onDurationChange: (val: number) => void;
  onTemperatureChange: (val: number) => void;
  disabled: boolean;
  loading: boolean;
  onStart: () => void;
  onReset: () => void;
  hasWorkflowResult: boolean;
  // Path D: MIDI project
  midiProject?: MidiProject;
  onMidiProjectChange?: (project: MidiProject) => void;
}

export function TrackInputArea({
  pathDef,
  batchMode,
  batchPrompts,
  ttsText,
  uploadedFile,
  uploadError,
  batchDuration,
  batchTemperature,
  onPromptChange,
  onTtsTextChange,
  onBatchPromptsChange,
  onFileUpload,
  onFileRemove,
  onBatchModeToggle,
  onDurationChange,
  onTemperatureChange,
  disabled,
  loading,
  onStart,
  onReset,
  hasWorkflowResult,
  midiProject,
  onMidiProjectChange,
}: Props) {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const promptCount = batchPrompts.trim().split('\n').filter(Boolean).length;

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const label = pathDef.inputLabel || pathDef.musicLabel || '';

  // Path D: Piano Roll Editor
  if (pathDef.id === 'd') {
    return (
      <div className="rounded-xl border border-[#2a2a38] bg-[#1f1f1f] p-5 space-y-4">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-[#e0e0e0]">{label}</label>
          <span className="text-xs px-2 py-1 bg-[#ff6a10]/10 text-[#ff6a10] rounded-full">
            {t('paths.pathD').split('—')[0].trim()}
          </span>
        </div>
        {midiProject && onMidiProjectChange && (
          <div className="h-96">
            <PianoRoll
              project={midiProject}
              onProjectChange={onMidiProjectChange}
              isPlaying={false}
              currentTick={0}
            />
          </div>
        )}
        {!midiProject && (
          <div className="h-96 flex items-center justify-center text-[#777777]">
            Initializing MIDI editor...
          </div>
        )}
        <div className="flex gap-3">
          <button
            onClick={onStart}
            disabled={disabled}
            className="flex-1 px-6 py-3 bg-[#ff6a10] text-[#e0e0e0] font-semibold rounded-xl
                         hover:bg-[#ff6a10] disabled:opacity-40 disabled:cursor-not-allowed
                         transition-all shadow-lg shadow-[#ff6a10]/20"
          >
            {loading
              ? '⏳ Starting...'
              : `✨ ${pathDef.icon} ${t('ui.generate')}`}
          </button>
          {hasWorkflowResult && (
            <button
              onClick={onReset}
              className="px-6 py-3 text-[#b0b0b0] border border-[#2a2a38] rounded-xl hover:bg-[#262626] hover:border-[#2a2a38] transition-colors"
            >
              {t('common.reset') || 'Reset'}
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-[#2a2a38] bg-[#1f1f1f]/50 p-5 space-y-4">
      {/* Batch Toggle (not for Path C) */}
      {pathDef.id !== 'c' && (
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-[#e0e0e0]">{t('common.settings')}</label>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span className={`text-xs ${!batchMode ? 'text-[#38bdf8] font-medium' : 'text-[#777777]'}`}>
                {t('paths.pathA').split('—')[0].trim()}
              </span>
              <button
                onClick={() => {
                  onBatchModeToggle(false);
                  onBatchPromptsChange('');
                }}
                className={`w-10 h-5 rounded-full transition-colors relative ${
                  !batchMode ? 'bg-[#38bdf8]' : 'bg-[#2a2a38]'
                }`}
              >
                <span
                  className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                    !batchMode ? 'left-5' : 'left-0.5'
                  }`}
                />
              </button>
              <span className={`text-xs ${batchMode ? 'text-[#38bdf8] font-medium' : 'text-[#777777]'}`}>
                {t('ui.batchMode')}
              </span>
            </div>
            {batchMode && batchPrompts.trim() && (
              <span className="text-xs px-2 py-0.5 bg-[#38bdf8]/10 text-[#38bdf8] rounded-full">
                {promptCount} {t('ui.promptsPerLine').split(' ')[0]}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Path C: File Upload */}
      {pathDef.id === 'c' ? (
        <div>
          <label className="text-sm font-medium text-[#e0e0e0]">{label}</label>
          <div className="mt-2 flex items-center gap-3">
            <input
              ref={fileInputRef}
              type="file"
              accept=".wav,.mp3,.mp4,.flac,.ogg,.m4a,.aac"
              onChange={onFileUpload}
              className="hidden"
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="px-4 py-2 text-sm border border-[#777777] rounded-lg hover:bg-[#262626] transition-colors"
            >
              {uploadedFile ? 'Change File' : 'Choose Audio File'}
            </button>
            {uploadedFile && (
              <span className="text-xs text-[#76b900]">
                ✓ {uploadedFile.name} ({formatSize(uploadedFile.size)})
              </span>
            )}
          </div>
          {uploadError && <p className="mt-1 text-xs text-[#ef4444]">{uploadError}</p>}
        </div>
      ) : batchMode ? (
        /* ── Batch Mode Input ───────────────────────────────────── */
        <div className="space-y-3">
          <div>
            <label className="text-sm font-medium text-[#e0e0e0]">
              {t('ui.promptsPerLine')}
            </label>
            <textarea
              value={batchPrompts}
              onChange={(e) => onBatchPromptsChange(e.target.value)}
              rows={6}
              className="w-full mt-1 px-3 py-2 bg-[#262626] border border-[#2a2a38] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#ff6a10] placeholder-gray-600 resize-y font-mono"
              placeholder={'upbeat electronic dance music\nchill lofi hip hop beat\nambient piano melody\ndark synthwave cyberpunk'}
            />
            {batchPrompts.trim() && (
              <p className="text-xs text-[#777777] mt-1">
                {promptCount} prompt(s) ready
              </p>
            )}
          </div>
          {pathDef.id === 'b' && (
            <div>
              <label className="text-sm font-medium text-[#e0e0e0]">
                {t('ui.ttsText')} (one per line, optional)
              </label>
              <textarea
                value={ttsText}
                onChange={(e) => onTtsTextChange(e.target.value)}
                rows={3}
                className="w-full mt-1 px-3 py-2 bg-[#262626] border border-[#2a2a38] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#ff6a10] placeholder-gray-600 resize-y font-mono"
                placeholder={'Line 1 lyrics\nLine 2 lyrics\nLine 3 lyrics'}
              />
              <p className="text-xs text-[#777777] mt-1">
                If fewer lines than prompts, last line repeats cyclically
              </p>
            </div>
          )}
          <div className="grid grid-cols-2 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-[#b0b0b0]">{t('ui.duration')} (s)</label>
              <input
                type="number"
                value={batchDuration}
                onChange={(e) => onDurationChange(Number(e.target.value))}
                min={1}
                max={60}
                className="w-full mt-1 px-3 py-2 bg-[#262626] border border-[#2a2a38] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#ff6a10]"
              />
            </div>
            <div>
              <label className="text-xs text-[#b0b0b0]">{t('ui.temperature')}</label>
              <input
                type="number"
                value={batchTemperature}
                onChange={(e) => onTemperatureChange(Number(e.target.value))}
                min={0}
                max={2}
                step={0.1}
                className="w-full mt-1 px-3 py-2 bg-[#262626] border border-[#2a2a38] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#ff6a10]"
              />
            </div>
          </div>
        </div>
      ) : (
        /* ── Single Mode Input ──────────────────────────────────── */
        <>
          <div>
            <label className="text-sm font-medium text-[#e0e0e0]">{label}</label>
            <input
              type="text"
              value={batchMode ? batchPrompts.split('\n')[0] || '' : ''}
              onChange={(e) => onPromptChange(e.target.value)}
              className="w-full mt-1 px-3 py-2 bg-[#262626] border border-[#2a2a38] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#ff6a10] placeholder-gray-600"
              placeholder={t('ui.musicPrompt')}
            />
          </div>
          {pathDef.id === 'b' && (
            <div>
              <label className="text-sm font-medium text-[#e0e0e0]">
                {t('ui.ttsText')}
              </label>
              <input
                type="text"
                value={ttsText}
                onChange={(e) => onTtsTextChange(e.target.value)}
                className="w-full mt-1 px-3 py-2 bg-[#262626] border border-[#2a2a38] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#ff6a10] placeholder-gray-600"
                placeholder={t('ui.ttsText')}
              />
              {uploadedFile && (
                <div className="mt-2 flex items-center gap-2 text-xs text-[#777777]">
                  <span>📎 {uploadedFile.name} ({formatSize(uploadedFile.size)})</span>
                  <button
                    type="button"
                    onClick={onFileRemove}
                    className="text-[#ef4444] hover:text-[#fca5a5]"
                  >
                    Remove
                  </button>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* Generate / Batch Start Button */}
      <div className="flex gap-3">
        <button
          onClick={onStart}
          disabled={disabled}
          className="flex-1 px-6 py-3 bg-gradient-to-r bg-[#ff6a10] text-[#e0e0e0] font-semibold rounded-xl
                       hover:bg-[#ff6a10] disabled:opacity-40 disabled:cursor-not-allowed
                       transition-all shadow-lg shadow-[#ff6a10]/20"
        >
          {loading
            ? batchMode
              ? '⏳ Starting Batch...'
              : '⏳ Starting...'
            : batchMode
              ? `📦 ${t('ui.batchGenerate')} (${promptCount})`
              : `✨ ${pathDef.icon} ${t('ui.generate')}`}
        </button>
        {hasWorkflowResult && (
          <button
            onClick={onReset}
            className="px-6 py-3 text-[#b0b0b0] border border-[#2a2a38] rounded-xl hover:bg-[#262626] transition-colors"
          >
            {t('common.reset') || 'Reset'}
          </button>
        )}
      </div>
    </div>
  );
}
