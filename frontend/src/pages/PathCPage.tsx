/**
 * 声音克隆页面
 * 
 * 功能:
 * - 音色库管理 (预设声音 + 用户上传)
 * - 声音上传 (1-5 分钟训练)
 * - 文本转语音克隆
 * - 速度控制 (0.5x - 2.0x)
 * - 音高调整 (-12 到 +12)
 */

import { useState, useEffect } from 'react';

interface VoiceSample {
  id: string;
  name: string;
  audio_url: string;
  duration: number;
  created_at: string;
}

interface CloneResult {
  success: boolean;
  audio_url: string | null;
  duration: number | null;
  voice_id: string | null;
  error: string | null;
  message: string | null;
}

export function PathCPage() {
  const [activeTab, setActiveTab] = useState<'library' | 'upload' | 'clone'>('library');
  const [voices, setVoices] = useState<VoiceSample[]>([]);
  const [selectedVoice, setSelectedVoice] = useState<string>('');
  const [cloneText, setCloneText] = useState('');
  const [speed, setSpeed] = useState(1.0);
  const [pitchShift, setPitchShift] = useState(0);
  const [isCloning, setIsCloning] = useState(false);
  const [cloneResult, setCloneResult] = useState<CloneResult | null>(null);
  const [uploadUrl, setUploadUrl] = useState('');
  const [uploadName, setUploadName] = useState('');
  const [isUploading, setIsUploading] = useState(false);

  // 加载声音列表
  useEffect(() => {
    fetchVoices();
  }, []);

  const fetchVoices = async () => {
    try {
      const res = await fetch('https://ai-music-backend-8e85.onrender.com/api/v1/voice/voices');
      const data = await res.json();
      setVoices(data);
      if (data.length > 0 && !selectedVoice) {
        setSelectedVoice(data[0].id);
      }
    } catch (error) {
      console.error('Failed to fetch voices:', error);
    }
  };

  // 上传声音
  const handleUpload = async () => {
    if (!uploadUrl) {
      alert('请输入音频 URL');
      return;
    }

    setIsUploading(true);
    try {
      const params = new URLSearchParams({
        audio_url: uploadUrl,
        ...(uploadName && { name: uploadName })
      });

      const res = await fetch(`https://ai-music-backend-8e85.onrender.com/api/v1/voice/upload?${params}`, {
        method: 'POST'
      });

      if (res.ok) {
        const data = await res.json();
        alert(`✅ 声音 "${data.name}" 上传成功！\n\n⏳ 训练需要 1-5 分钟（Mock 模式为即时）`);
        setUploadUrl('');
        setUploadName('');
        fetchVoices();
        setActiveTab('library');
      } else {
        const error = await res.json();
        alert(`❌ 上传失败：${error.detail || '未知错误'}`);
      }
    } catch (error) {
      alert(`❌ 上传失败：${error}`);
    } finally {
      setIsUploading(false);
    }
  };

  // 声音克隆
  const handleClone = async () => {
    if (!cloneText.trim()) {
      alert('请输入要合成的文本');
      return;
    }

    if (!selectedVoice) {
      alert('请选择声音');
      return;
    }

    setIsCloning(true);
    setCloneResult(null);

    try {
      const res = await fetch('https://ai-music-backend-8e85.onrender.com/api/v1/voice/clone', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          voice_id: selectedVoice,
          text: cloneText,
          speed,
          pitch_shift: pitchShift
        })
      });

      if (res.ok) {
        const data: CloneResult = await res.json();
        setCloneResult(data);
        if (data.success) {
          // 自动播放
          const audio = new Audio(data.audio_url!);
          audio.play();
        }
      } else {
        const error = await res.json();
        alert(`❌ 克隆失败：${error.detail || '未知错误'}`);
      }
    } catch (error) {
      alert(`❌ 克隆失败：${error}`);
    } finally {
      setIsCloning(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-3xl font-bold mb-6 bg-gradient-to-r from-orange-400 to-pink-500 bg-clip-text text-transparent">
        🎤 声音克隆
      </h1>

      {/* Tab 切换 */}
      <div className="flex gap-2 mb-6 border-b border-zinc-800">
        <button
          onClick={() => setActiveTab('library')}
          className={`px-4 py-2 rounded-t-lg transition ${
            activeTab === 'library'
              ? 'bg-zinc-800 text-orange-400 border-b-2 border-orange-400'
              : 'text-zinc-400 hover:text-white'
          }`}
        >
          🎵 音色库
        </button>
        <button
          onClick={() => setActiveTab('upload')}
          className={`px-4 py-2 rounded-t-lg transition ${
            activeTab === 'upload'
              ? 'bg-zinc-800 text-orange-400 border-b-2 border-orange-400'
              : 'text-zinc-400 hover:text-white'
          }`}
        >
          📤 上传声音
        </button>
        <button
          onClick={() => setActiveTab('clone')}
          className={`px-4 py-2 rounded-t-lg transition ${
            activeTab === 'clone'
              ? 'bg-zinc-800 text-orange-400 border-b-2 border-orange-400'
              : 'text-zinc-400 hover:text-white'
          }`}
        >
          🎙️ 克隆合成
        </button>
      </div>

      {/* Tab 1: 音色库 */}
      {activeTab === 'library' && (
        <div className="space-y-4">
          <h2 className="text-xl font-semibold mb-4">可用声音</h2>
          {voices.length === 0 ? (
            <div className="card-solid p-10 text-center">
              <div className="text-5xl mb-4">🎤</div>
              <p className="text-secondary mb-2">还没有声音样本</p>
              <p className="text-muted text-sm mb-6">去「上传声音」标签页添加你的第一个声音</p>
              <button onClick={() => setActiveTab('upload')}
                className="btn-base px-5 py-2.5 bg-gradient-to-r from-orange-500 to-pink-500 text-white rounded-lg font-medium"
              >📤 上传声音</button>
            </div>
          ) :
            voices.map((voice) => (
              <div
                key={voice.id}
                className={`p-4 rounded-lg border transition cursor-pointer ${
                  selectedVoice === voice.id
                    ? 'bg-zinc-800 border-orange-400'
                    : 'bg-zinc-900 border-zinc-800 hover:border-zinc-600'
                }`}
                onClick={() => setSelectedVoice(voice.id)}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-medium text-white">{voice.name}</h3>
                    <p className="text-sm text-zinc-400">
                      {voice.duration}s • {voice.created_at.split('T')[0]}
                    </p>
                  </div>
                  <audio controls src={voice.audio_url} className="h-8" />
                </div>
                {selectedVoice === voice.id && (
                  <div className="mt-2 text-xs text-orange-400">✓ 已选择</div>
                )}
              </div>
            ))}
        </div>
      )}

      {/* Tab 2: 上传声音 */}
      {activeTab === 'upload' && (
        <div className="space-y-4">
          <div className="card-solid p-6">
            <h2 className="text-xl font-semibold mb-4">上传声音样本</h2>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-zinc-400 mb-2">
                  音频 URL
                </label>
                <input
                  type="url"
                  value={uploadUrl}
                  onChange={(e) => setUploadUrl(e.target.value)}
                  placeholder="https://example.com/audio.wav"
                  className="w-full px-4 py-2 bg-bg-elevated border border-border-default rounded-lg input-glow text-white"
                />
              </div>

              <div>
                <label className="block text-sm text-zinc-400 mb-2">
                  声音名称（可选）
                </label>
                <input
                  type="text"
                  value={uploadName}
                  onChange={(e) => setUploadName(e.target.value)}
                  placeholder="我的声音"
                  className="w-full px-4 py-2 bg-bg-elevated border border-border-default rounded-lg input-glow text-white"
                />
              </div>

              <button
                onClick={handleUpload}
                disabled={isUploading || !uploadUrl}
                className="w-full py-3 bg-gradient-to-r from-orange-400 to-pink-500 text-white font-semibold rounded-lg hover:opacity-90 transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isUploading ? '⏳ 上传中...' : '📤 上传声音'}
              </button>

              <p className="text-xs text-zinc-500">
                ℹ️ 支持格式：WAV, MP3, FLAC • 建议时长：10-60 秒
                <br />
                ⏳ 训练时间：1-5 分钟（Mock 模式为即时）
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Tab 3: 克隆合成 */}
      {activeTab === 'clone' && (
        <div className="space-y-4">
          <div className="card-solid p-6">
            <h2 className="text-xl font-semibold mb-4">声音克隆合成</h2>

            <div className="space-y-4">
              {/* 声音选择 */}
              <div>
                <label className="block text-sm text-zinc-400 mb-2">
                  选择声音
                </label>
                <select
                  value={selectedVoice}
                  onChange={(e) => setSelectedVoice(e.target.value)}
                  className="w-full px-4 py-2 bg-bg-elevated border border-border-default rounded-lg input-glow text-white"
                >
                  {voices.map((voice) => (
                    <option key={voice.id} value={voice.id}>
                      {voice.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* 文本输入 */}
              <div>
                <label className="block text-sm text-zinc-400 mb-2">
                  合成文本
                </label>
                <textarea
                  value={cloneText}
                  onChange={(e) => setCloneText(e.target.value)}
                  placeholder="输入要合成的文本（最多 1000 字符）"
                  rows={4}
                  maxLength={1000}
                  className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg focus:outline-none focus:border-orange-400 text-white resize-none"
                />
                <p className="text-xs text-zinc-500 mt-1">
                  {cloneText.length}/1000
                </p>
              </div>

              {/* 速度控制 */}
              <div>
                <label className="block text-sm text-zinc-400 mb-2">
                  播放速度：{speed}x
                </label>
                <input
                  type="range"
                  min="0.5"
                  max="2.0"
                  step="0.1"
                  value={speed}
                  onChange={(e) => setSpeed(parseFloat(e.target.value))}
                  className="w-full accent-orange-400"
                />
                <div className="flex justify-between text-xs text-zinc-500">
                  <span>0.5x</span>
                  <span>1.0x</span>
                  <span>2.0x</span>
                </div>
              </div>

              {/* 音高调整 */}
              <div>
                <label className="block text-sm text-zinc-400 mb-2">
                  音高偏移：{pitchShift > 0 ? '+' : ''}{pitchShift}
                </label>
                <input
                  type="range"
                  min="-12"
                  max="12"
                  step="1"
                  value={pitchShift}
                  onChange={(e) => setPitchShift(parseInt(e.target.value))}
                  className="w-full accent-orange-400"
                />
                <div className="flex justify-between text-xs text-zinc-500">
                  <span>-12</span>
                  <span>0</span>
                  <span>+12</span>
                </div>
              </div>

              <button
                onClick={handleClone}
                disabled={isCloning || !cloneText.trim() || !selectedVoice}
                className="w-full py-3 bg-gradient-to-r from-orange-400 to-pink-500 text-white font-semibold rounded-lg hover:opacity-90 transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isCloning ? '⏳ 合成中...' : '🎙️ 开始克隆'}
              </button>
            </div>
          </div>

          {/* 克隆结果 */}
          {cloneResult && (
            <div className={`p-6 rounded-lg ${
              cloneResult.success ? 'bg-green-900/20 border border-green-500' : 'bg-red-900/20 border border-red-500'
            }`}>
              <h3 className="text-lg font-semibold mb-2">
                {cloneResult.success ? '✅ 合成成功' : '❌ 合成失败'}
              </h3>
              {cloneResult.message && (
                <p className="text-sm text-zinc-300 whitespace-pre-line mb-4">
                  {cloneResult.message}
                </p>
              )}
              {cloneResult.success && cloneResult.audio_url && (
                <div className="space-y-3">
                  <audio controls src={cloneResult.audio_url} className="w-full" />
                  <p className="text-xs text-zinc-400">
                    时长：{cloneResult.duration}s
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}