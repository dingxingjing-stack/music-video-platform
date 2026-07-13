/**
 * AI 作词组件
 * 
 * 功能：
 * - 主题输入
 * - 风格选择 (8 种)
 * - 情绪选择 (6 种)
 * - 语言选择
 * - 歌词结构预设
 * - 实时生成
 * - 押韵分析显示
 * - 一键应用到歌曲
 */

import { useState, useEffect } from 'react';

interface LyricStyle {
  name: string;
  description: string;
}

interface GenerateParams {
  theme: string;
  style?: string;
  language?: string;
  mood?: string;
  structure?: string;
  custom_lyrics?: string;
  rhyme_scheme?: string;
}

export function AILyricGenerator() {
  // 状态
  const [theme, setTheme] = useState('');
  const [style, setStyle] = useState('pop');
  const [mood, setMood] = useState('happy');
  const [language, setLanguage] = useState('zh');
  const [structure, setStructure] = useState('verse-chorus-verse-chorus-bridge-chorus');
  const [customLyrics, setCustomLyrics] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatedLyrics, setGeneratedLyrics] = useState('');
  const [structureAnalysis, setStructureAnalysis] = useState('');
  const [rhymeAnalysis, setRhymeAnalysis] = useState('');
  
  // 预定义选项
  const STYLES: LyricStyle[] = [
    { name: 'pop', description: '流行情歌' },
    { name: 'rap', description: '说唱/嘻哈' },
    { name: 'rock', description: '摇滚' },
    { name: 'folk', description: '民谣' },
    { name: 'electronic', description: '电子音乐' },
    { name: 'rnb', description: 'R&B 节奏蓝调' },
    { name: 'country', description: '乡村音乐' },
    { name: 'jazz', description: '爵士' },
  ];
  
  const MOODS = [
    { value: 'happy', label: '快乐', emoji: '😊' },
    { value: 'sad', label: '悲伤', emoji: '😢' },
    { value: 'energetic', label: '活力', emoji: '⚡' },
    { value: 'romantic', label: '浪漫', emoji: '💕' },
    { value: 'angry', label: '愤怒', emoji: '😠' },
    { value: 'nostalgic', label: '怀旧', emoji: '🕰️' },
  ];
  
  const LANGUAGES = [
    { value: 'zh', label: '中文' },
    { value: 'en', label: '英文' },
    { value: 'ja', label: '日文' },
  ];
  
  const STRUCTURES = [
    { value: 'verse-chorus-verse-chorus-bridge-chorus', label: '经典 (主 - 副 - 主 - 副 - 桥 - 副)' },
    { value: 'verse-verse-chorus-chorus', label: '简单 (主 - 主 - 副 - 副)' },
    { value: 'chorus-verse-chorus-verse', label: '副歌先行' },
    { value: 'verse-chorus-bridge-chorus', label: '短句结构' },
  ];
  
  // 加载风格和情绪
  useEffect(() => {
    loadStyles();
    loadMoods();
  }, []);
  
  const loadStyles = async () => {
    try {
      await fetch('http://localhost:8000/api/v1/lyrics/styles');
      // 可以使用 API 返回的风格，这里先用预设的
    } catch (e) {
      console.error('加载风格失败:', e);
    }
  };
  
  const loadMoods = async () => {
    try {
      await fetch('http://localhost:8000/api/v1/lyrics/moods');
      // 可以使用 API 返回的情绪
    } catch (e) {
      console.error('加载情绪失败:', e);
    }
  };
  
  // 生成歌词
  const handleGenerate = async () => {
    if (!theme.trim()) {
      console.warn('请输入主题');
      alert('请输入想要创作的主题或故事');
      return;
    }
    
    setIsGenerating(true);
    
    try {
      const params: GenerateParams = {
        theme: theme.trim(),
        style,
        language,
        mood,
        structure,
      };
      
      if (customLyrics.trim()) {
        params.custom_lyrics = customLyrics.trim();
      }
      
      const res = await fetch('http://localhost:8000/api/v1/lyrics/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
      });
      
      const data = await res.json();
      
      if (data.success) {
        setGeneratedLyrics(data.lyrics);
        setStructureAnalysis(data.structure);
        setRhymeAnalysis(data.rhyme_analysis || '');
        
        console.log('✅ 歌词生成成功:', data.structure);
        alert('✅ 歌词生成成功！\n结构：' + data.structure);
      } else {
        throw new Error(data.message || '生成失败');
      }
    } catch (e: any) {
      console.error('生成失败:', e);
      alert('❌ 生成失败：' + e.message);
    } finally {
      setIsGenerating(false);
    }
  };
  
  // 应用到歌曲
  const handleApplyToSong = () => {
    if (!generatedLyrics) return;
    
    window.dispatchEvent(new CustomEvent('apply-lyrics', {
      detail: { lyrics: generatedLyrics }
    }));
    
    console.log('✅ 已应用到歌曲');
    alert('✅ 歌词已发送到歌曲编辑器');
  };
  
  // 复制歌词
  const handleCopy = () => {
    navigator.clipboard.writeText(generatedLyrics);
    console.log('✅ 已复制');
    alert('✅ 歌词已复制到剪贴板');
  };
  
  return (
    <div className="max-w-4xl mx-auto p-6">
      <h2 className="text-2xl font-bold mb-6 text-white">
        🎵 AI 作词助手
      </h2>
      
      {/* 输入区域 */}
      <div className="bg-gray-800/50 rounded-xl p-6 mb-6 backdrop-blur-sm">
        {/* 主题输入 */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            🎯 主题
          </label>
          <input
            type="text"
            value={theme}
            onChange={(e) => setTheme(e.target.value)}
            placeholder="例如：追逐梦想、初恋、夏日旅行..."
            className="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-orange-500"
          />
        </div>
        
        {/* 风格选择 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          {STYLES.map((s) => (
            <button
              key={s.name}
              onClick={() => setStyle(s.name)}
              className={`p-3 rounded-lg text-sm font-medium transition-all ${
                style === s.name
                  ? 'bg-gradient-to-r from-orange-500 to-pink-500 text-white'
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              {s.description}
            </button>
          ))}
        </div>
        
        {/* 情绪选择 */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            😊 情绪
          </label>
          <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
            {MOODS.map((m) => (
              <button
                key={m.value}
                onClick={() => setMood(m.value)}
                className={`p-2 rounded-lg text-sm transition-all ${
                  mood === m.value
                    ? 'bg-gradient-to-r from-orange-500 to-pink-500 text-white'
                    : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                }`}
              >
                <span className="text-xl">{m.emoji}</span>
                <div className="text-xs mt-1">{m.label}</div>
              </button>
            ))}
          </div>
        </div>
        
        {/* 语言选择 */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            🌐 语言
          </label>
          <div className="flex gap-2">
            {LANGUAGES.map((l) => (
              <button
                key={l.value}
                onClick={() => setLanguage(l.value)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  language === l.value
                    ? 'bg-gradient-to-r from-orange-500 to-pink-500 text-white'
                    : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                }`}
              >
                {l.label}
              </button>
            ))}
          </div>
        </div>
        
        {/* 结构选择 */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            📐 歌曲结构
          </label>
          <select
            value={structure}
            onChange={(e) => setStructure(e.target.value)}
            className="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-orange-500"
          >
            {STRUCTURES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
        
        {/* 续写歌词 (可选) */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            ✍️ 续写 (可选)
          </label>
          <textarea
            value={customLyrics}
            onChange={(e) => setCustomLyrics(e.target.value)}
            placeholder="已有歌词片段，AI 将继续创作..."
            rows={4}
            className="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-orange-500"
          />
        </div>
        
        {/* 生成按钮 */}
        <button
          onClick={handleGenerate}
          disabled={isGenerating || !theme.trim()}
          className="w-full py-4 bg-gradient-to-r from-orange-500 to-pink-500 hover:from-orange-600 hover:to-pink-600 disabled:from-gray-600 disabled:to-gray-700 rounded-lg text-white font-bold text-lg transition-all shadow-lg hover:shadow-xl disabled:cursor-not-allowed"
        >
          {isGenerating ? '🎵 创作中...' : '✨ 开始创作歌词'}
        </button>
      </div>
      
      {/* 生成的歌词 */}
      {generatedLyrics && (
        <div className="bg-gray-800/50 rounded-xl p-6 backdrop-blur-sm">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-bold text-white">
              📝 生成的歌词
            </h3>
            <div className="flex gap-2">
              <button
                onClick={handleCopy}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm text-gray-300 transition-all"
              >
                📋 复制
              </button>
              <button
                onClick={handleApplyToSong}
                className="px-4 py-2 bg-gradient-to-r from-orange-500 to-pink-500 hover:from-orange-600 hover:to-pink-600 rounded-lg text-sm text-white font-medium transition-all"
              >
                💿 应用到歌曲
              </button>
            </div>
          </div>
          
          {/* 歌词内容 */}
          <pre className="whitespace-pre-wrap text-gray-200 font-mono text-sm bg-gray-900/50 p-4 rounded-lg mb-4">
            {generatedLyrics}
          </pre>
          
          {/* 分析信息 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <div className="bg-gray-900/50 p-3 rounded-lg">
              <div className="text-gray-400 mb-1">📊 结构分析</div>
              <div className="text-gray-200">{structureAnalysis}</div>
            </div>
            {rhymeAnalysis && (
              <div className="bg-gray-900/50 p-3 rounded-lg">
                <div className="text-gray-400 mb-1">🎵 押韵分析</div>
                <div className="text-gray-200 text-xs whitespace-pre-wrap">{rhymeAnalysis}</div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}