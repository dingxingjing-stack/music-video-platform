/**
 * CopyrightDetector - 版权检测组件
 * 
 * 功能:
 * - 上传音频扫描
 * - 显示风险等级
 * - 匹配详情
 * - 版权库管理
 */

import { useState, useCallback } from 'react';

interface Match {
  id: string;
  original_id: string;
  similarity: number;
  risk_level: 'safe' | 'low' | 'medium' | 'high';
  matched_segments: Array<{ start: number; end: number; similarity: number }>;
}

interface ScanResult {
  scan_id: string;
  file_name: string;
  risk_level: 'safe' | 'low' | 'medium' | 'high';
  matches: Match[];
  timestamp: string;
}

const RISK_COLORS = {
  safe: '#22c55e',
  low: '#eab308',
  medium: '#f97316',
  high: '#ef4444'
};

const RISK_LABELS = {
  safe: '安全',
  low: '低风险',
  medium: '中风险',
  high: '高风险'
};

export function CopyrightDetector({ userId, onClose }: { userId: string; onClose?: () => void }) {
  const [dragOver, setDragOver] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [uploading, setUploading] = useState(false);

  // 上传并扫描
  const scanAudio = useCallback(async (file: File) => {
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('user_id', userId);

      const response = await fetch('/api/v1/copyright/scan', {
        method: 'POST',
        body: formData
      });

      if (response.ok) {
        const data = await response.json();
        setResult(data);
      } else {
        alert('扫描失败：' + response.statusText);
      }
    } catch (error) {
      console.error('扫描失败:', error);
      alert('扫描失败，请重试');
    } finally {
      setUploading(false);
    }
  }, [userId]);

  // 处理文件拖放
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('audio/')) {
      scanAudio(file);
    } else {
      alert('请上传音频文件');
    }
  }, [scanAudio]);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      scanAudio(file);
    }
  }, [scanAudio]);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 overflow-auto">
      <div className="w-[800px] max-h-[90vh] bg-[#1e1e1e] rounded-xl border border-[#2a2a2a] overflow-hidden my-8">
        {/* 头部 */}
        <div className="flex items-center justify-between p-4 border-b border-[#2a2a2a]">
          <div>
            <h2 className="text-xl font-bold text-[#e0e0e0]">🛡️ 版权检测</h2>
            <p className="text-xs text-[#777777]">音频指纹识别 • 风险等级评估</p>
          </div>
          <button
            onClick={onClose || (() => {})}
            className="text-[#777777] hover:text-white text-2xl"
          >
            ✕
          </button>
        </div>

        {/* 上传区 */}
        <div
          onDragOver={e => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          className={`m-4 border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
            dragOver 
              ? 'border-orange-500 bg-orange-500/10' 
              : 'border-[#2a2a2a] hover:border-[#3a3a3a]'
          }`}
        >
          {uploading ? (
            <div className="text-[#e0e0e0]">
              <div className="text-4xl mb-2">📤</div>
              <div className="text-sm">正在上传并扫描...</div>
            </div>
          ) : result ? (
            <div className="text-left">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <div className="text-sm text-[#777777] mb-1">扫描文件</div>
                  <div className="text-[#e0e0e0] font-medium">{result.file_name}</div>
                </div>
                <div
                  className="px-3 py-1 rounded-full text-xs font-medium"
                  style={{ 
                    backgroundColor: RISK_COLORS[result.risk_level] + '20',
                    color: RISK_COLORS[result.risk_level]
                  }}
                >
                  {RISK_LABELS[result.risk_level]}
                </div>
              </div>

              {/* 匹配结果 */}
              {result.matches.length > 0 ? (
                <div className="space-y-2">
                  <div className="text-xs text-[#777777]">匹配作品 ({result.matches.length})</div>
                  {result.matches.map(match => (
                    <div
                      key={match.id}
                      className="p-3 bg-[#1a1a1a] rounded-lg border border-[#2a2a2a]"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-[#e0e0e0]">作品 #{match.original_id}</span>
                        <span className="text-xs px-2 py-0.5 rounded" style={{
                          backgroundColor: RISK_COLORS[match.risk_level] + '20',
                          color: RISK_COLORS[match.risk_level]
                        }}>
                          相似度 {Math.round(match.similarity * 100)}%
                        </span>
                      </div>
                      <div className="w-full bg-[#2a2a2a] rounded-full h-1.5">
                        <div
                          className="h-1.5 rounded-full transition-all"
                          style={{ 
                            width: `${match.similarity * 100}%`,
                            backgroundColor: RISK_COLORS[match.risk_level]
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-4 text-[#22c55e]">
                  <div className="text-2xl mb-2">✅</div>
                  <div className="text-sm">未发现匹配作品，音频安全</div>
                </div>
              )}

              <button
                onClick={() => setResult(null)}
                className="mt-4 w-full py-2 bg-[#2a2a2a] hover:bg-[#333333] rounded-lg text-sm text-[#e0e0e0]"
              >
                扫描其他文件
              </button>
            </div>
          ) : (
            <div onClick={() => document.getElementById('file-input')?.click()}>
              <div className="text-4xl mb-3">🎵</div>
              <div className="text-[#e0e0e0] font-medium mb-1">拖拽音频文件到此处</div>
              <div className="text-xs text-[#777777] mb-3">或点击选择文件</div>
              <div className="text-[10px] text-[#555555]">
                支持 MP3, WAV, FLAC, AAC • 最大 50MB
              </div>
              <input
                id="file-input"
                type="file"
                accept="audio/*"
                onChange={handleFileSelect}
                className="hidden"
              />
            </div>
          )}
        </div>

        {/* 底部提示 */}
        <div className="p-4 border-t border-[#2a2a2a] text-center text-xs text-[#777777]">
          基于音频指纹识别技术 • 检测相似度 ≥45% 的匹配作品
        </div>
      </div>
    </div>
  );
}