/**
 * WatermarkPanel — copyright fingerprint + blind watermark UI
 *
 * Features:
 *  - One-click "Fingerprint + Watermark" on selected tracks
 *  - Owner ID / Project ID input
 *  - Extraction check: detect if a track has our watermark
 *  - Download watermarked version
 */

import { useState } from 'react';
import { ShieldCheck, Fingerprint, Download, Scan, Loader2 } from 'lucide-react';
import { useTranslation } from '../../i18n/useTranslation';

interface Props {
  trackUrl: string;
  trackName: string;
  onApply?: () => void;
}

interface WatermarkResult {
  fingerprint?: {
    mfcc_hash: string;
    chroma_hash: string;
    spectral_centroid_mean: number;
    spectral_bandwidth_mean: number;
    duration_sec: number;
    composite_id?: string;
  } | null;
  watermark?: {
    owner_id: string;
    project_id: string;
    timestamp: string;
    rights: string;
    signature: string;
  };
  found?: boolean;
  watermarked?: boolean;
  composite_id?: string;
  data?: string;
  message?: string;
}

type Stage = 'idle' | 'fingerprinting' | 'embedding' | 'extracting' | 'done';

export default function WatermarkPanel({ trackUrl, trackName }: Props) {
  const { t } = useTranslation();
  const [stage, setStage] = useState<Stage>('idle');
  const [result, setResult] = useState<WatermarkResult | null>(null);
  const [error, setError] = useState('');
  const [ownerId, setOwnerId] = useState('user-001');
  const [projectId, setProjectId] = useState(`proj-${Date.now().toString(36)}`);

  const apply = async () => {
    setStage('fingerprinting');
    setError('');
    setResult(null);

    try {
      const resp = await fetch('/api/v1/watermark/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          audio_url: trackUrl,
          owner_id: ownerId,
          project_id: projectId,
        }),
      });

      const data: WatermarkResult = await resp.json();
      if (!resp.ok) throw new Error((data as any).detail || 'Failed');
      setResult(data);
      setStage('done');
    } catch (e: any) {
      setError(e.message);
      setStage('idle');
    }
  };

  const extract = async () => {
    setStage('extracting');
    setError('');
    setResult(null);

    try {
      const resp = await fetch('/api/v1/watermark/extract', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ audio_url: trackUrl }),
      });

      const data: WatermarkResult = await resp.json();
      if (!resp.ok) throw new Error((data as any).detail || 'Failed');
      setResult(data);
      setStage('done');
    } catch (e: any) {
      setError(e.message);
      setStage('idle');
    }
  };

  const download = () => {
    if (!result?.data) return;
    const link = document.createElement('a');
    link.href = result.data;
    link.download = `watermarked_${trackName}.wav`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="watermark-panel space-y-3">
      <h4 className="text-sm font-semibold flex items-center gap-2">
        <ShieldCheck size={16} /> {t('watermark.title')}
      </h4>

      {stage === 'idle' && (
        <div className="space-y-2">
          <div className="flex gap-2">
            <input
              className="flex-1 text-xs px-2 py-1 border rounded bg-[#262626] text-[#b0b0b0]"
              placeholder={t('watermark.ownerId')}
              value={ownerId}
              onChange={(e) => setOwnerId(e.target.value)}
            />
            <input
              className="flex-1 text-xs px-2 py-1 border rounded bg-[#262626] text-[#b0b0b0]"
              placeholder={t('watermark.projectId')}
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
            />
          </div>
          <div className="flex gap-2">
            <button
              className="flex-1 text-xs bg-[#ff6a10] text-white px-3 py-1.5 rounded hover:bg-[#ff6a10] flex items-center justify-center gap-1"
              onClick={apply}
              disabled={!trackUrl}
            >
              <Fingerprint size={14} /> {t('watermark.apply')}
            </button>
            <button
              className="flex-1 text-xs bg-[#777777] text-[#e0e0e0] px-3 py-1.5 rounded hover:bg-[#2a2a38] flex items-center justify-center gap-1"
              onClick={extract}
              disabled={!trackUrl}
            >
              <Scan size={14} /> {t('watermark.detect')}
            </button>
          </div>
          {error && (
            <p className="text-xs text-red-600">{error}</p>
          )}
        </div>
      )}

      {(stage === 'fingerprinting' || stage === 'embedding' || stage === 'extracting') && (
        <div className="flex items-center gap-2 text-xs text-[#ff6a10]">
          <Loader2 size={14} className="animate-spin" />
          {stage === 'fingerprinting' && t('watermark.fingerprinting')}
          {stage === 'embedding' && t('watermark.embedding')}
          {stage === 'extracting' && t('watermark.extracting')}
        </div>
      )}

      {stage === 'done' && result && (
        <div className="space-y-2 text-xs">
          {result.fingerprint && (
            <div className="bg-[#ff6a10]/5 border border-[#ff6a10]/30 rounded p-2">
              <p className="font-medium text-[#ff6a10]">{t('watermark.fingerprint')}</p>
              <p className="text-[#777777]">
                {t('watermark.compositeId')} <code className="text-[10px]">{result.fingerprint.mfcc_hash}</code>
              </p>
              <p className="text-[#777777]">
                {t('watermark.centroid')}: {result.fingerprint.spectral_centroid_mean.toFixed(0)} Hz ·
                {t('watermark.bandwidth')}: {result.fingerprint.spectral_bandwidth_mean.toFixed(0)} Hz ·
                {t('watermark.duration')}: {result.fingerprint.duration_sec.toFixed(1)}s
              </p>
            </div>
          )}

          {result.watermark && (
            <div className="bg-green-50 border border-green-200 rounded p-2">
              <p className="font-medium text-green-700">
                {result.found !== undefined
                  ? (result.found ? t('watermark.found') : t('watermark.none'))
                  : t('watermark.embedded')}
              </p>
              <p className="text-[#777777]">
                {t('watermark.owner')}: {result.watermark.owner_id} · {t('watermark.project')}: {result.watermark.project_id}
              </p>
              <p className="text-[#777777]">
                {t('watermark.rights')}: {result.watermark.rights} · {t('watermark.ts')}: {result.watermark.timestamp}
              </p>
              {result.watermark.signature && (
                <p className="text-[#b0b0b0] text-[10px]">
                  {t('watermark.sig')}: {result.watermark.signature}
                </p>
              )}
            </div>
          )}

          {result.watermarked && result.data && (
            <button
              className="w-full text-xs bg-green-600 text-[#e0e0e0] px-3 py-1.5 rounded hover:bg-green-700 flex items-center justify-center gap-1"
              onClick={download}
            >
              <Download size={14} /> {t('watermark.download')}
            </button>
          )}

          <button
            className="w-full text-xs text-[#ff6a10] hover:text-[#ff6a10]"
            onClick={() => { setStage('idle'); setResult(null); }}
          >
            {t('watermark.back')}
          </button>
        </div>
      )}
    </div>
  );
}