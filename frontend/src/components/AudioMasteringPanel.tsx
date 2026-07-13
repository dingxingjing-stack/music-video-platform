/**
 * 母带处理组件
 * 
 * 功能:
 * - 上传音频文件
 * - 选择预设 (流媒体/YouTube/俱乐部等)
 * - 自定义参数 (响度/立体声宽度)
 * - 实时进度显示
 * - 前后对比播放
 * - 分析数据显示 (LUFS, Peak)
 */

import { useState, useRef } from 'react';

interface MasteringPreset {
  name: string;
  target_loudness: number;
  stereo_width: number;
  description: string;
}

export function AudioMasteringPanel() {
  const [file, setFile] = useState<File | null>(null);
  const [isMastering, setIsMastering] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<any>(null);
  const [preset, setPreset] = useState('custom');
  const [customLoudness, setCustomLoudness] = useState(-14.0);
  const [customStereoWidth, setCustomStereoWidth] = useState(0.3);
  const [presets, setPresets] = useState<MasteringPreset[]>([]);
  const [error, setError] = useState('');

  const originalAudioRef = useRef<HTMLAudioElement | null>(null);
  const masteredAudioRef = useRef<HTMLAudioElement | null>(null);

  // 加载预设
  useState(() => {
    fetch('http://localhost:8000/api/v1/audio/master/presets')
      .then(res => res.json())
      .then(data => setPresets(data.presets))
      .catch(console.error);
  });

  // 应用预设
  const applyPreset = (presetName: string) => {
    const selected = presets.find(p => p.name === presetName);
    if (selected) {
      setCustomLoudness(selected.target_loudness);
      setCustomStereoWidth(selected.stereo_width);
      setPreset(presetName);
    }
  };

  // 开始母带处理
  const handleMaster = async () => {
    if (!file) return;

    setIsMastering(true);
    setProgress(0);
    setError('');
    setResult(null);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('target_loudness', customLoudness.toString());
    formData.append('stereo_width', customStereoWidth.toString());

    try {
      const response = await fetch('http://localhost:8000/api/v1/audio/master', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (!data.success) {
        throw new Error(data.message || '母带处理失败');
      }

      setResult(data);
      setProgress(100);
    } catch (err: any) {
      setError(err.message || '母带处理失败');
    } finally {
      setIsMastering(false);
    }
  };

  // 下载母带后文件
  const downloadMastered = () => {
    if (result?.output_path) {
      const a = document.createElement('a');
      a.href = result.output_path;
      a.download = `${file?.name.replace(/\.[^/.]+$/, '')}_mastered.wav`;
      a.click();
    }
  };

  return (
    <div className="p-6 bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 min-h-screen">
      <div className="max-w-4xl mx-auto">
        <h2 className="text-2xl font-bold text-white mb-6">
          🎚️ 自动母带处理
        </h2>

        {/* 上传区域 */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            选择音频文件
          </label>
          <div className="border-2 border-dashed border-gray-600 rounded-lg p-6 text-center hover:border-orange-500 transition-colors">
            <input
              type="file"
              accept="audio/*"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="hidden"
              id="master-upload"
            />
            <label htmlFor="master-upload" className="cursor-pointer">
              <div className="text-gray-400">
                <span className="text-4xl">📁</span>
                <p className="mt-2">
                  {file ? file.name : '点击选择或拖拽音频文件'}
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  支持 MP3, WAV, FLAC, M4A
                </p>
              </div>
            </label>
          </div>
        </div>

        {/* 预设选择 */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            快速预设
          </label>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {presets.map((p) => (
              <button
                key={p.name}
                onClick={() => applyPreset(p.name)}
                className={`p-3 rounded-lg border text-left transition-all ${
                  preset === p.name
                    ? 'border-orange-500 bg-orange-500/20'
                    : 'border-gray-600 bg-gray-800 hover:border-gray-500'
                }`}
              >
                <div className="text-sm font-semibold text-white">{p.name}</div>
                <div className="text-xs text-gray-400">{p.description}</div>
              </button>
            ))}
          </div>
        </div>

        {/* 自定义参数 */}
        <div className="mb-6 p-4 bg-gray-800/50 border border-gray-700 rounded-lg">
          <h3 className="text-lg font-semibold text-white mb-4">⚙️ 自定义参数</h3>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-300 mb-2">
                目标响度 (LUFS): {customLoudness} dB
              </label>
              <input
                type="range"
                min="-20"
                max="-6"
                step="0.5"
                value={customLoudness}
                onChange={(e) => {
                  setCustomLoudness(parseFloat(e.target.value));
                  setPreset('custom');
                }}
                className="w-full accent-orange-500"
              />
              <div className="flex justify-between text-xs text-gray-500 mt-1">
                <span>-20 LUFS (保守)</span>
                <span>-6 LUFS (激进)</span>
              </div>
            </div>

            <div>
              <label className="block text-sm text-gray-300 mb-2">
                立体声宽度: {(customStereoWidth * 100).toFixed(0)}%
              </label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={customStereoWidth}
                onChange={(e) => {
                  setCustomStereoWidth(parseFloat(e.target.value));
                  setPreset('custom');
                }}
                className="w-full accent-orange-500"
              />
              <div className="flex justify-between text-xs text-gray-500 mt-1">
                <span>单声道</span>
                <span>超宽立体声</span>
              </div>
            </div>
          </div>
        </div>

        {/* 母带按钮 */}
        <button
          onClick={handleMaster}
          disabled={!file || isMastering}
          className={`w-full py-3 rounded-lg font-semibold transition-all ${
            !file || isMastering
              ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
              : 'bg-gradient-to-r from-orange-500 to-pink-500 text-white hover:opacity-90'
          }`}
        >
          {isMastering ? `母带处理中... ${progress.toFixed(0)}%` : '开始母带处理'}
        </button>

        {/* 进度条 */}
        {isMastering && (
          <div className="mt-4">
            <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-orange-500 to-pink-500 transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        {/* 错误信息 */}
        {error && (
          <div className="mt-4 p-3 bg-red-900/30 border border-red-500 rounded-lg text-red-300">
            ❌ {error}
          </div>
        )}

        {/* 结果展示 */}
        {result && (
          <div className="mt-8">
            <h3 className="text-xl font-bold text-white mb-4">
              ✅ 母带处理完成
            </h3>

            {/* 分析数据对比 */}
            <div className="grid grid-cols-2 gap-4 mb-6">
              <div className="p-4 bg-gray-800/50 border border-gray-700 rounded-lg">
                <h4 className="text-sm font-medium text-gray-400 mb-2">处理前</h4>
                <div className="space-y-2">
                  <div>
                    <span className="text-xs text-gray-500">响度</span>
                    <div className="text-lg font-bold text-orange-400">
                      {result.loudness_before} LUFS
                    </div>
                  </div>
                  <div>
                    <span className="text-xs text-gray-500">峰值</span>
                    <div className="text-lg font-bold text-orange-400">
                      {result.peak_before.toFixed(3)}
                    </div>
                  </div>
                </div>
              </div>

              <div className="p-4 bg-gray-800/50 border border-green-500/50 rounded-lg">
                <h4 className="text-sm font-medium text-green-400 mb-2">处理后</h4>
                <div className="space-y-2">
                  <div>
                    <span className="text-xs text-gray-500">响度</span>
                    <div className="text-lg font-bold text-green-400">
                      {result.loudness_after} LUFS
                    </div>
                  </div>
                  <div>
                    <span className="text-xs text-gray-500">峰值</span>
                    <div className="text-lg font-bold text-green-400">
                      {result.peak_after.toFixed(3)}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* 前后对比播放器 */}
            <div className="space-y-4">
              <div className="p-4 bg-gray-800/50 border border-gray-700 rounded-lg">
                <h4 className="text-sm font-medium text-gray-300 mb-2">原始音频</h4>
                {file && <audio ref={originalAudioRef} src={URL.createObjectURL(file)} className="w-full" />}
              </div>

              <div className="p-4 bg-gray-800/50 border border-green-500/50 rounded-lg">
                <h4 className="text-sm font-medium text-green-400 mb-2">母带后音频</h4>
                <audio ref={masteredAudioRef} src={result.output_path} className="w-full" />
              </div>
            </div>

            {/* 下载按钮 */}
            <button
              onClick={downloadMastered}
              className="mt-6 w-full py-3 bg-gradient-to-r from-green-500 to-emerald-500 text-white rounded-lg font-semibold hover:opacity-90"
            >
              ⬇️ 下载母带后音频
            </button>

            <div className="mt-4 p-4 bg-blue-900/30 border border-blue-500 rounded-lg text-blue-300">
              💡 <strong>提示:</strong> 响度达到 -14 LUFS (流媒体标准)，峰值控制在 -1dB 以下防止削波。
            </div>
          </div>
        )}
      </div>
    </div>
  );
}