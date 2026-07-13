/**
 * 音频分离组件 (Demucs)
 * 
 * 功能:
 * - 上传音频文件
 * - 选择分离模型
 * - 实时进度显示
 * - 四轨播放预览 (人声/鼓/贝斯/其他)
 * - 分轨下载
 */

import { useState, useRef } from 'react';

export function AudioSeparationPanel() {
  const [file, setFile] = useState<File | null>(null);
  const [isSeparating, setIsSeparating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stems, setStems] = useState<string[]>([]);
  const [model, setModel] = useState('htdemucs');
  const [error, setError] = useState('');
  
  const audioRefs = useRef<{ [key: string]: HTMLAudioElement | null }>({});

  const STEM_LABELS = {
    vocals: '🎤 人声',
    drums: '🥁 鼓',
    bass: '🎸 贝斯',
    other: '🎹 其他',
  };

  // 上传并分离
  const handleSeparate = async () => {
    if (!file) return;

    setIsSeparating(true);
    setProgress(0);
    setError('');
    setStems([]);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('model', model);

    try {
      const response = await fetch('http://localhost:8000/api/v1/audio/separate', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (!data.success) {
        throw new Error(data.message || '分离失败');
      }

      setStems(data.stems);
      setProgress(100);
    } catch (err: any) {
      setError(err.message || '分离失败，请重试');
    } finally {
      setIsSeparating(false);
    }
  };

  // 播放单独轨道
  const playStem = (stemName: string) => {
    const audio = audioRefs.current[stemName];
    if (audio) {
      audio.play();
    }
  };

  // 停止所有轨道
  const stopAll = () => {
    Object.values(audioRefs.current).forEach(audio => {
      if (audio) {
        audio.pause();
        audio.currentTime = 0;
      }
    });
  };

  // 下载分轨
  const downloadStem = (url: string, name: string) => {
    const a = document.createElement('a');
    a.href = url;
    a.download = `${name}.wav`;
    a.click();
  };

  return (
    <div className="p-6 bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 min-h-screen">
      <div className="max-w-4xl mx-auto">
        <h2 className="text-2xl font-bold text-white mb-6">
          🎵 音频分离 (Demucs)
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
              id="audio-upload"
            />
            <label htmlFor="audio-upload" className="cursor-pointer">
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

        {/* 模型选择 */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            分离模型
          </label>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="w-full px-4 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-orange-500"
          >
            <option value="htdemucs">HT-Demucs (推荐，快速)</option>
            <option value="htdemucs_ft">HT-Demucs FT (音质更好)</option>
            <option value="htdemucs_6s">HT-Demucs 6s (6 轨分离)</option>
          </select>
        </div>

        {/* 分离按钮 */}
        <button
          onClick={handleSeparate}
          disabled={!file || isSeparating}
          className={`w-full py-3 rounded-lg font-semibold transition-all ${
            !file || isSeparating
              ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
              : 'bg-gradient-to-r from-orange-500 to-pink-500 text-white hover:opacity-90'
          }`}
        >
          {isSeparating ? `分离中... ${progress.toFixed(0)}%` : '开始分离'}
        </button>

        {/* 进度条 */}
        {isSeparating && (
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

        {/* 分离结果 */}
        {stems.length > 0 && (
          <div className="mt-8">
            <h3 className="text-xl font-bold text-white mb-4">
              ✅ 分离完成 - 4 轨音频
            </h3>

            <div className="space-y-4">
              {Object.entries(STEM_LABELS).map(([key, label], idx) => (
                <div
                  key={key}
                  className="p-4 bg-gray-800/50 border border-gray-700 rounded-lg"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-lg font-semibold text-white">
                      {label}
                    </span>
                    <div className="flex gap-2">
                      <button
                        onClick={() => playStem(key)}
                        className="px-3 py-1 bg-orange-500 text-white text-sm rounded hover:bg-orange-600"
                      >
                        ▶️ 播放
                      </button>
                      <button
                        onClick={() => stopAll()}
                        className="px-3 py-1 bg-gray-600 text-white text-sm rounded hover:bg-gray-700"
                      >
                        ⏹️ 停止
                      </button>
                      <button
                        onClick={() => downloadStem(stems[idx], key)}
                        className="px-3 py-1 bg-gray-600 text-white text-sm rounded hover:bg-gray-700"
                      >
                        ⬇️ 下载
                      </button>
                    </div>
                  </div>

                  <audio
                    ref={(el) => (audioRefs.current[key] = el)}
                    src={stems[idx]}
                    className="w-full"
                  />
                </div>
              ))}
            </div>

            <div className="mt-6 p-4 bg-blue-900/30 border border-blue-500 rounded-lg text-blue-300">
              💡 <strong>提示:</strong> 可以单独播放每个轨道，或同时播放多个轨道来预览混音效果。
            </div>
          </div>
        )}
      </div>
    </div>
  );
}