/**
 * AudioExporter — 音频导出面板（分轨 + 混音）
 */

import { useState, useCallback } from 'react';
import type { Track } from '../../types/trackStudio';

interface StemTrack {
  name: string;
  label: string;
  url: string;
  color: string;
}

interface ExportOptions {
  format: 'wav' | 'mp3' | 'flac';
  sampleRate: number;
  bitDepth: number;
  channels: number;
  includeStems: boolean;
  normalize: boolean;
  dither: boolean;
}

interface Props {
  tracks: Track[];
  onClose: () => void;
}

const DEFAULT_OPTIONS: ExportOptions = {
  format: 'wav',
  sampleRate: 44100,
  bitDepth: 24,
  channels: 2,
  includeStems: true,
  normalize: false,
  dither: true,
};

export function AudioExporter({ tracks, onClose }: Props) {
  const [options, setOptions] = useState<ExportOptions>(DEFAULT_OPTIONS);
  const [isExporting, setIsExporting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<{ success: boolean; message: string; files?: string[] } | null>(null);
  const [stems, setStems] = useState<StemTrack[]>([]);
  const [showStems, setShowStems] = useState(false);

  const handleExport = useCallback(async () => {
    setIsExporting(true);
    setProgress(0);
    setResult(null);

    try {
      // Mock 导出进度
      const steps = tracks.length + 1;
      for (let i = 0; i <= tracks.length; i++) {
        await new Promise(resolve => setTimeout(resolve, 300));
        setProgress(Math.round((i / steps) * 100));
      }

      setResult({
        success: true,
        message: '导出成功！',
        files: [
          'master.wav',
          ...tracks.filter(t => !t.muted).map(t => `${t.name}.wav`),
        ],
      });
    } catch (error) {
      setResult({
        success: false,
        message: error instanceof Error ? error.message : '导出失败',
      });
    } finally {
      setIsExporting(false);
      setProgress(100);
    }
  }, [tracks]);

  // AI 智能分轨
  const handleAIStemsExport = useCallback(async () => {
    if (tracks.length === 0) return;

    try {
      // 使用第一个轨道的音频作为示例
      const audioUrl = tracks[0].clips?.[0]?.url || 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3';

      const response = await fetch('https://ai-music-backend-8e85.onrender.com/api/v1/export/stems', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ audio_url: audioUrl }),
      });

      const data = await response.json();
      if (data.success) {
        setStems(data.stems);
        setShowStems(true);
      } else {
        alert('分轨失败：' + (data.error || '未知错误'));
      }
    } catch (error) {
      alert('分轨失败：' + (error instanceof Error ? error.message : '网络错误'));
    }
  }, [tracks]);

  const formatLabels = {
    wav: 'WAV (无损)',
    mp3: 'MP3 (有损)',
    flac: 'FLAC (无损压缩)',
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="w-[600px] max-h-[80vh] bg-[#1e1e1e] rounded-xl border border-[#2a2a2a] overflow-hidden flex flex-col">
        {/* 头部 */}
        <div className="flex items-center justify-between p-4 border-b border-[#2a2a2a]">
          <div>
            <h2 className="text-lg font-bold text-[#e0e0e0]">🎵 音频导出</h2>
            <p className="text-xs text-[#777777]">导出混音 + 分轨文件</p>
          </div>
          <button onClick={onClose} className="text-[#777777] hover:text-white transition">✕</button>
        </div>

        {/* AI 分轨按钮 */}
        <div className="p-4 border-b border-[#2a2a2a]">
          <button
            onClick={handleAIStemsExport}
            disabled={tracks.length === 0}
            className="w-full px-4 py-3 bg-gradient-to-r from-purple-500 to-indigo-500 hover:from-purple-600 hover:to-indigo-600 text-white rounded-lg text-sm font-medium transition disabled:opacity-50 flex items-center justify-center gap-2"
          >
            🤖 AI 智能分轨
          </button>
          {showStems && stems.length > 0 && (
            <div className="mt-3 p-3 bg-[#2a2a2a] rounded-lg">
              <p className="text-xs text-[#777777] mb-2">✅ 分轨结果 ({stems.length}轨):</p>
              <div className="flex gap-2 flex-wrap">
                {stems.map(stem => (
                  <div
                    key={stem.name}
                    className="px-2 py-1 rounded text-xs text-white flex items-center gap-1"
                    style={{ backgroundColor: stem.color }}
                  >
                    <span>{stem.label}</span>
                    <a href={stem.url} target="_blank" rel="noreferrer" className="underline">🎧</a>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 导出设置 */}
        <div className="p-4 space-y-4 overflow-auto">
          {/* 格式选择 */}
          <div>
            <label className="text-xs text-[#777777] mb-1 block">格式</label>
            <div className="flex gap-2">
              {(Object.keys(formatLabels) as Array<keyof typeof formatLabels>).map(fmt => (
                <button
                  key={fmt}
                  onClick={() => setOptions({ ...options, format: fmt })}
                  className={`flex-1 px-3 py-2 rounded text-sm transition ${
                    options.format === fmt
                      ? 'bg-gradient-to-r from-orange-500 to-pink-500 text-white'
                      : 'bg-[#2a2a2a] text-[#e0e0e0] hover:bg-[#333333]'
                  }`}
                >
                  {formatLabels[fmt]}
                </button>
              ))}
            </div>
          </div>

          {/* 采样率 */}
          <div>
            <label className="text-xs text-[#777777] mb-1 block">采样率</label>
            <select
              value={options.sampleRate}
              onChange={(e) => setOptions({ ...options, sampleRate: Number(e.target.value) })}
              className="w-full bg-[#2a2a2a] border border-[#3a3a3a] rounded px-3 py-2 text-sm text-[#e0e0e0]"
            >
              <option value={44100}>44.1 kHz (CD 标准)</option>
              <option value={48000}>48 kHz (视频标准)</option>
              <option value={96000}>96 kHz (高解析)</option>
            </select>
          </div>

          {/* 位深 */}
          <div>
            <label className="text-xs text-[#777777] mb-1 block">位深</label>
            <select
              value={options.bitDepth}
              onChange={(e) => setOptions({ ...options, bitDepth: Number(e.target.value) })}
              className="w-full bg-[#2a2a2a] border border-[#3a3a3a] rounded px-3 py-2 text-sm text-[#e0e0e0]"
            >
              <option value={16}>16-bit (CD 标准)</option>
              <option value={24}>24-bit (专业标准)</option>
              <option value={32}>32-bit float (最高质量)</option>
            </select>
          </div>

          {/* 分轨导出 */}
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-[#e0e0e0]">导出分轨</p>
              <p className="text-xs text-[#777777]">为每个轨道生成单独文件</p>
            </div>
            <button
              onClick={() => setOptions({ ...options, includeStems: !options.includeStems })}
              className={`w-12 h-6 rounded-full transition ${
                options.includeStems ? 'bg-orange-500' : 'bg-[#3a3a3a]'
              }`}
            >
              <div className={`w-5 h-5 bg-white rounded-full transition-transform ${
                options.includeStems ? 'translate-x-6' : 'translate-x-0.5'
              }`} />
            </button>
          </div>

          {/* 轨道状态预览 */}
          <div>
            <p className="text-xs text-[#777777] mb-2">轨道状态 ({tracks.length}个)</p>
            <div className="space-y-1 max-h-32 overflow-auto">
              {tracks.map(track => (
                <div key={track.id} className="flex items-center justify-between text-xs">
                  <span className={track.muted ? 'text-[#777777]' : 'text-[#e0e0e0]'}>
                    {track.name}
                  </span>
                  <div className="flex gap-2">
                    {track.muted && <span className="text-[#ef4444]">🔇 静音</span>}
                    {track.solo && <span className="text-orange-500">🎧 独奏</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 进度条 */}
        {isExporting && (
          <div className="px-4 pb-4">
            <div className="h-2 bg-[#2a2a2a] rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-orange-500 to-pink-500 transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="text-xs text-center text-[#777777] mt-2">正在导出... {progress}%</p>
          </div>
        )}

        {/* 结果 */}
        {result && (
          <div className={`p-4 text-center text-sm ${
            result.success ? 'bg-[#22c55e]/20 text-[#22c55e]' : 'bg-[#ef4444]/20 text-[#ef4444]'
          }`}>
            <p className="font-medium">{result.message}</p>
            {result.files && (
              <div className="mt-2 text-xs text-[#777777]">
                <p>生成文件:</p>
                <ul className="list-disc list-inside">
                  {result.files.map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* 底部按钮 */}
        <div className="p-4 border-t border-[#2a2a2a] flex items-center justify-between">
          <button
            onClick={onClose}
            disabled={isExporting}
            className="px-3 py-1.5 bg-[#2a2a2a] hover:bg-[#333333] text-[#e0e0e0] rounded text-sm transition disabled:opacity-50"
          >
            取消
          </button>
          <button
            onClick={handleExport}
            disabled={isExporting || tracks.length === 0}
            className="px-6 py-2 bg-gradient-to-r from-orange-500 to-pink-500 hover:from-orange-600 hover:to-pink-600 text-white rounded-lg text-sm font-medium transition disabled:opacity-50"
          >
            {isExporting ? '导出中...' : `导出 ${tracks.length}个轨道`}
          </button>
        </div>
      </div>
    </div>
  );
}