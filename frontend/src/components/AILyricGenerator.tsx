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
import { api } from '../config/api';
import { useTranslation } from '../i18n/useTranslation';

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
  const { t } = useTranslation();
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
    { name: 'pop', description: t('lyricGen.style.pop') },
    { name: 'rap', description: t('lyricGen.style.rap') },
    { name: 'rock', description: t('lyricGen.style.rock') },
    { name: 'folk', description: t('lyricGen.style.folk') },
    { name: 'electronic', description: t('lyricGen.style.electronic') },
    { name: 'rnb', description: t('lyricGen.style.rnb') },
    { name: 'country', description: t('lyricGen.style.country') },
    { name: 'jazz', description: t('lyricGen.style.jazz') },
  ];
  
  const MOODS = [
    { value: 'happy', label: t('lyricGen.mood.happy'), emoji: '😊' },
    { value: 'sad', label: t('lyricGen.mood.sad'), emoji: '😢' },
    { value: 'energetic', label: t('lyricGen.mood.energetic'), emoji: '⚡' },
    { value: 'romantic', label: t('lyricGen.mood.romantic'), emoji: '💕' },
    { value: 'angry', label: t('lyricGen.mood.angry'), emoji: '😠' },
    { value: 'nostalgic', label: t('lyricGen.mood.nostalgic'), emoji: '🕰️' },
  ];
  
  const LANGUAGES = [
    { value: 'zh', label: t('lyricGen.lang.zh') },
    { value: 'en', label: t('lyricGen.lang.en') },
    { value: 'ja', label: t('lyricGen.lang.ja') },
  ];
  
  const STRUCTURES = [
    { value: 'verse-chorus-verse-chorus-bridge-chorus', label: t('lyricGen.structure.opts1') },
    { value: 'verse-verse-chorus-chorus', label: t('lyricGen.structure.opts2') },
    { value: 'chorus-verse-chorus-verse', label: t('lyricGen.structure.opts3') },
    { value: 'verse-chorus-bridge-chorus', label: t('lyricGen.structure.opts4') },
  ];
  
  // 加载风格和情绪
  useEffect(() => {
    loadStyles();
    loadMoods();
  }, []);
  
  const loadStyles = async () => {
    try {
      await fetch(api.url('/api/v1/lyrics/styles'));
      // 可以使用 API 返回的风格，这里先用预设的
    } catch (e) {
      console.error('加载风格失败:', e);
    }
  };
  
  const loadMoods = async () => {
    try {
      await fetch(api.url('/api/v1/lyrics/moods'));
      // 可以使用 API 返回的情绪
    } catch (e) {
      console.error('加载情绪失败:', e);
    }
  };
  
  // 生成歌词
  const handleGenerate = async () => {
    if (!theme.trim()) {
      console.warn('请输入主题');
      alert(t('lyricGen.themeRequired'));
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
      
      const res = await fetch(api.url('/api/v1/lyrics/generate'), {
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
        alert(t('lyricGen.success', { structure: data.structure }));
      } else {
        throw new Error(data.message || t('lyricGen.generateFailed'));
      }
    } catch (e: any) {
      console.error('生成失败:', e);
      alert(t('lyricGen.failed', { msg: e.message }));
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
    alert(t('lyricGen.applied'));
  };
  
  // 复制歌词
  const handleCopy = () => {
    navigator.clipboard.writeText(generatedLyrics);
    console.log('✅ 已复制');
    alert(t('lyricGen.copied'));
  };
  
  return (
    <div className="max-w-4xl mx-auto p-6">
      <h2 className="text-2xl font-bold mb-6 text-white">
        🎵 {t('lyricGen.title')}
      </h2>
      
      {/* 输入区域 */}
      <div className="bg-gray-800/50 rounded-xl p-6 mb-6 backdrop-blur-sm">
        {/* 主题输入 */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            {t('lyricGen.theme')}
          </label>
          <input
            type="text"
            value={theme}
            onChange={(e) => setTheme(e.target.value)}
            placeholder={t('lyricGen.themePlaceholder')}
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
            {t('lyricGen.moodLabel')}
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
            {t('lyricGen.languageLabel')}
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
            {t('lyricGen.structureLabel')}
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
            {t('lyricGen.continueWrite')}
          </label>
          <textarea
            value={customLyrics}
            onChange={(e) => setCustomLyrics(e.target.value)}
            placeholder={t('lyricGen.continuePlaceholder')}
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
          {isGenerating ? t('lyricGen.generating') : t('lyricGen.generate')}
        </button>
      </div>
      
      {/* 生成的歌词 */}
      {generatedLyrics && (
        <div className="bg-gray-800/50 rounded-xl p-6 backdrop-blur-sm">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-bold text-white">
              {t('lyricGen.generatedTitle')}
            </h3>
            <div className="flex gap-2">
              <button
                onClick={handleCopy}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm text-gray-300 transition-all"
              >
                {t('lyricGen.copy')}
              </button>
              <button
                onClick={handleApplyToSong}
                className="px-4 py-2 bg-gradient-to-r from-orange-500 to-pink-500 hover:from-orange-600 hover:to-pink-600 rounded-lg text-sm text-white font-medium transition-all"
              >
                {t('lyricGen.apply')}
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
              <div className="text-gray-400 mb-1">{t('lyricGen.structureAnalysis')}</div>
              <div className="text-gray-200">{structureAnalysis}</div>
            </div>
            {rhymeAnalysis && (
              <div className="bg-gray-900/50 p-3 rounded-lg">
                <div className="text-gray-400 mb-1">{t('lyricGen.rhymeAnalysis')}</div>
                <div className="text-gray-200 text-xs whitespace-pre-wrap">{rhymeAnalysis}</div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}