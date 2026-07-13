/**
 * VoiceCloningPanel — 声音克隆面板
 * 
 * 功能:
 * - 上传声音样本
 * - 声音档案管理
 * - 声音克隆合成
 * - 音色库浏览
 */

import { useState, useCallback, useEffect } from 'react';

interface VoiceProfile {
  id: string;
  name: string;
  description?: string;
  sample_duration: number;
  tags: string[];
  created_at: string;
}

interface Props {
  onClose: () => void;
}

export function VoiceCloningPanel({ onClose }: Props) {
  const [activeTab, setActiveTab] = useState<'upload' | 'clone' | 'library'>('upload');
  const [voices, setVoices] = useState<VoiceProfile[]>([]);
  const [selectedVoice, setSelectedVoice] = useState<string | null>(null);
  const [cloneText, setCloneText] = useState('');
  const [cloneSpeed, setCloneSpeed] = useState(1.0);
  const [isProcessing, setIsProcessing] = useState(false);
  const [cloneResult, setCloneResult] = useState<any>(null);

  // 加载声音库
  useEffect(() => {
    if (activeTab === 'library') {
      fetch('http://localhost:8000/api/v1/voice/voices?limit=20')
        .then(r => r.json())
        .then(data => {
          if (data.success) {
            setVoices(data.voices);
          }
        })
        .catch(console.error);
    }
  }, [activeTab]);

  // 上传声音样本
  const handleUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsProcessing(true);
    
    // Mock 上传
    setTimeout(() => {
      const newVoice: VoiceProfile = {
        id: `voice_${Date.now()}`,
        name: file.name.replace(/\.[^.]+$/, ''),
        description: '用户上传的声音',
        sample_duration: 120,
        tags: ['user-uploaded'],
        created_at: new Date().toISOString(),
      };
      setVoices(prev => [...prev, newVoice]);
      setSelectedVoice(newVoice.id);
      setActiveTab('clone');
      setIsProcessing(false);
    }, 1500);
  }, []);

  // 执行声音克隆
  const handleClone = useCallback(async () => {
    if (!selectedVoice || !cloneText) return;

    setIsProcessing(true);

    // Mock 克隆
    setTimeout(() => {
      setCloneResult({
        success: true,
        audio_url: `mock://cloned_${selectedVoice}.wav`,
        duration: cloneText.length * 0.08,
        voice_name: '克隆声音',
        processing_time: 2.5,
      });
      setIsProcessing(false);
    }, 2000);
  }, [selectedVoice, cloneText, cloneSpeed]);

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-8">
      <div className="bg-gradient-to-b from-zinc-900 to-zinc-950 rounded-2xl p-6 max-w-5xl w-full max-h-[80vh] overflow-auto shadow-2xl border border-zinc-800">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-white">🎤 AI 声音克隆</h2>
            <p className="text-sm text-zinc-400 mt-1">上传样本 → 训练模型 → AI 模仿</p>
          </div>
          <button onClick={onClose} className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-white rounded-lg transition">
            关闭
          </button>
        </div>

        {/* Tab 导航 */}
        <div className="flex gap-2 mb-6 border-b border-zinc-700">
          {[
            { id: 'upload', label: '📤 上传样本', icon: '📤' },
            { id: 'clone', label: '🎙️ 声音克隆', icon: '🎙️' },
            { id: 'library', label: '📚 音色库', icon: '📚' },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`px-4 py-2 font-medium transition ${
                activeTab === tab.id
                  ? 'text-purple-400 border-b-2 border-purple-500'
                  : 'text-zinc-400 hover:text-white'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === 'upload' && (
          /* 上传样本 */
          <div>
            <div className="text-center py-12">
              <div className="text-5xl mb-4">🎤</div>
              <h3 className="text-xl font-bold text-white mb-2">上传声音样本</h3>
              <p className="text-zinc-400 mb-6">
                上传 1-5 分钟的清晰录音，AI 将学习声音特征
              </p>

              <div className="max-w-md mx-auto mb-6 p-6 bg-zinc-800/50 rounded-xl border border-zinc-700">
                <h4 className="text-sm font-medium text-white mb-3">📋 录制要求</h4>
                <ul className="text-left text-sm text-zinc-400 space-y-2">
                  <li>✓ 清晰的人声，无背景噪音</li>
                  <li>✓ 时长 1-5 分钟</li>
                  <li>✓ 格式：WAV 或 MP3</li>
                  <li>✓ 采样率 ≥ 44.1kHz</li>
                  <li>✓ 单一说话人</li>
                </ul>
              </div>

              <label className="inline-block px-6 py-3 bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white rounded-lg font-medium transition cursor-pointer">
                {isProcessing ? '上传中...' : '📁 选择音频文件'}
                <input
                  type="file"
                  accept="audio/*"
                  onChange={handleUpload}
                  disabled={isProcessing}
                  className="hidden"
                />
              </label>
            </div>
          </div>
        )}

        {activeTab === 'clone' && !cloneResult && (
          /* 声音克隆 */
          <div>
            {/* 声音选择 */}
            <div className="mb-6">
              <label className="text-sm font-medium text-white mb-2 block">选择声音</label>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {voices.length === 0 ? (
                  <div className="col-span-full text-center text-zinc-400 py-4">
                    暂无声音，请先上传样本
                  </div>
                ) : (
                  voices.map(voice => (
                    <button
                      key={voice.id}
                      onClick={() => setSelectedVoice(voice.id)}
                      className={`p-3 rounded-lg border-2 transition text-left ${
                        selectedVoice === voice.id
                          ? 'border-purple-500 bg-purple-500/10'
                          : 'border-zinc-700 bg-zinc-800/50 hover:border-zinc-500'
                      }`}
                    >
                      <div className="text-white font-bold text-sm">{voice.name}</div>
                      <div className="text-xs text-zinc-400">
                        {(voice.sample_duration / 60).toFixed(1)}分钟
                      </div>
                    </button>
                  ))
                )}
              </div>
            </div>

            {/* 文本输入 */}
            <div className="mb-6">
              <label className="text-sm font-medium text-white mb-2 block">合成文本</label>
              <textarea
                value={cloneText}
                onChange={(e) => setCloneText(e.target.value)}
                placeholder="输入要合成的文本内容..."
                rows={4}
                maxLength={1000}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg p-3 text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
              <div className="text-xs text-zinc-400 mt-1 text-right">
                {cloneText.length}/1000 字符
              </div>
            </div>

            {/* 高级选项 */}
            <div className="mb-6 p-4 bg-zinc-800/50 rounded-xl">
              <h4 className="text-sm font-medium text-white mb-3">⚙️ 高级选项</h4>
              
              <div>
                <label className="text-xs text-zinc-400 mb-2 block">
                  速度：<span className="text-white font-medium">{cloneSpeed.toFixed(2)}x</span>
                </label>
                <input
                  type="range"
                  min="0.5"
                  max="2"
                  step="0.1"
                  value={cloneSpeed}
                  onChange={(e) => setCloneSpeed(Number(e.target.value))}
                  className="w-full h-2 bg-zinc-700 rounded-lg appearance-none cursor-pointer"
                />
                <div className="flex justify-between text-xs text-zinc-500 mt-1">
                  <span>0.5x (慢)</span>
                  <span>1.0x (正常)</span>
                  <span>2.0x (快)</span>
                </div>
              </div>
            </div>

            {/* 执行按钮 */}
            <button
              onClick={handleClone}
              disabled={!selectedVoice || !cloneText || isProcessing}
              className="w-full py-4 bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white rounded-xl font-bold text-lg transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isProcessing ? '🎵 合成中...' : '🎙️ 开始克隆'}
            </button>
          </div>
        )}

        {activeTab === 'clone' && cloneResult && (
          /* 克隆结果 */
          <div>
            <div className="p-6 bg-green-500/10 border border-green-500/30 rounded-xl mb-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="text-3xl">✅</div>
                <div>
                  <div className="text-green-400 font-bold text-lg">声音克隆完成!</div>
                  <div className="text-sm text-zinc-400">已生成语音</div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-zinc-400">声音:</span>
                  <span className="text-white ml-2">{cloneResult.voice_name}</span>
                </div>
                <div>
                  <span className="text-zinc-400">时长:</span>
                  <span className="text-white ml-2">{cloneResult.duration.toFixed(2)}秒</span>
                </div>
                <div>
                  <span className="text-zinc-400">处理时间:</span>
                  <span className="text-white ml-2">{cloneResult.processing_time.toFixed(2)}秒</span>
                </div>
              </div>
            </div>

            {/* 音频播放器 (Mock) */}
            <div className="p-4 bg-zinc-800/50 rounded-xl mb-6">
              <div className="flex items-center gap-3">
                <button className="w-12 h-12 rounded-full bg-purple-500 hover:bg-purple-600 flex items-center justify-center text-white text-xl transition">
                  ▶
                </button>
                <div className="flex-1 h-12 bg-zinc-700 rounded-lg flex items-center px-4">
                  <div className="text-sm text-zinc-400">音频波形可视化</div>
                </div>
              </div>
            </div>

            {/* 操作按钮 */}
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => setCloneResult(null)}
                className="px-4 py-3 bg-zinc-700 hover:bg-zinc-600 text-white rounded-lg font-medium transition"
              >
                🔄 重新克隆
              </button>
              <button className="px-4 py-3 bg-gradient-to-r from-green-500 to-emerald-500 hover:from-green-600 hover:to-emerald-600 text-white rounded-lg font-medium transition">
                📥 导出音频
              </button>
            </div>
          </div>
        )}

        {activeTab === 'library' && (
          /* 音色库 */
          <div>
            <h3 className="text-lg font-bold text-white mb-4">📚 音色库 ({voices.length}个声音)</h3>
            
            {voices.length === 0 ? (
              <div className="text-center text-zinc-400 py-12">
                <div className="text-4xl mb-4">📦</div>
                <div>暂无声音</div>
                <button
                  onClick={() => setActiveTab('upload')}
                  className="mt-4 px-4 py-2 bg-purple-500 hover:bg-purple-600 text-white rounded-lg text-sm transition"
                >
                  上传第一个声音
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {voices.map(voice => (
                  <div
                    key={voice.id}
                    className="p-4 bg-zinc-800/50 rounded-xl border border-zinc-700"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="text-white font-bold">{voice.name}</h4>
                      <span className="text-xs text-zinc-400">
                        {(voice.sample_duration / 60).toFixed(1)}分钟
                      </span>
                    </div>
                    {voice.description && (
                      <p className="text-sm text-zinc-400 mb-3">{voice.description}</p>
                    )}
                    <div className="flex items-center gap-2 flex-wrap">
                      {voice.tags.map((tag, i) => (
                        <span
                          key={i}
                          className="text-xs px-2 py-1 bg-zinc-700 text-zinc-300 rounded"
                        >
                          #{tag}
                        </span>
                      ))}
                    </div>
                    <button
                      onClick={() => {
                        setSelectedVoice(voice.id);
                        setActiveTab('clone');
                      }}
                      className="mt-3 w-full px-3 py-2 bg-purple-500 hover:bg-purple-600 text-white rounded-lg text-sm transition"
                    >
                      使用此声音
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default VoiceCloningPanel;