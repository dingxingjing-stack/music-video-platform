/**
 * MVTemplateGallery — MV 模板库组件
 * 
 * P0-4: 20+ 种专业 MV 模板
 * 分类: 流行/摇滚/电子/抒情/说唱/民谣/古风/R&B
 */

import { useState } from 'react';
import { MV_TEMPLATES, MVTemplate, MV_CATEGORIES } from '../data/mv-templates';

interface Props {
  onTemplateSelect: (template: MVTemplate) => void;
}

export function MVTemplateGallery({ onTemplateSelect }: Props) {
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [previewTemplate, setPreviewTemplate] = useState<MVTemplate | null>(null);

  const filteredTemplates = MV_TEMPLATES.filter(template => {
    const matchesCategory = selectedCategory === 'all' || template.category === selectedCategory;
    const matchesSearch = template.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         template.description.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesCategory && matchesSearch;
  });

  const handleApplyTemplate = (template: MVTemplate) => {
    onTemplateSelect(template);
  };

  return (
    <div className="bg-gray-900 rounded-lg p-4 h-full flex flex-col">
      <h3 className="text-white font-semibold mb-3">🎬 MV 模板库</h3>
      
      {/* 搜索栏 */}
      <div className="mb-4 flex gap-2">
        <input
          type="text"
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
          placeholder="搜索模板..."
          className="flex-1 bg-gray-800 text-white px-3 py-2 rounded text-sm"
        />
      </div>
      
      {/* 分类标签 */}
      <div className="flex flex-wrap gap-2 mb-4">
        <button
          onClick={() => setSelectedCategory('all')}
          className={`px-3 py-1 rounded text-xs font-medium transition ${
            selectedCategory === 'all'
              ? 'bg-orange-600 text-white'
              : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
          }`}
        >
          全部
        </button>
        {MV_CATEGORIES.map(cat => (
          <button
            key={cat}
            onClick={() => setSelectedCategory(cat)}
            className={`px-3 py-1 rounded text-xs font-medium transition ${
              selectedCategory === cat
                ? 'bg-orange-600 text-white'
                : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>
      
      {/* 模板网格 */}
      <div className="flex-1 overflow-y-auto">
        <div className="grid grid-cols-2 gap-3">
          {filteredTemplates.map(template => (
            <div
              key={template.id}
              className="bg-gray-800 rounded overflow-hidden cursor-pointer hover:ring-2 hover:ring-orange-500 transition group"
              onClick={() => setPreviewTemplate(template)}
            >
              {/* 缩略图占位 */}
              <div className="relative aspect-video bg-gradient-to-br from-orange-900 to-gray-900 flex items-center justify-center">
                <div className="text-4xl">{template.style === '明亮' ? '☀️' : template.style === '暗黑' ? '🌙' : '🎭'}</div>
                <div className="absolute top-1 right-1 bg-black/70 text-white text-xs px-1 rounded">
                  {template.duration}s
                </div>
              </div>
              
              {/* 信息 */}
              <div className="p-2">
                <h4 className="text-white text-sm font-medium truncate">{template.name}</h4>
                <p className="text-gray-400 text-xs truncate">{template.description}</p>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-xs bg-orange-900/50 text-orange-300 px-1 rounded">
                    {template.category}
                  </span>
                  <span className="text-xs text-gray-500">{template.style}</span>
                </div>
              </div>
              
              {/* 应用按钮 (悬停显示) */}
              <button
                onClick={e => {
                  e.stopPropagation();
                  handleApplyTemplate(template);
                }}
                className="w-full py-1.5 bg-orange-600/0 group-hover:bg-orange-600 hover:bg-orange-500 text-white text-xs transition font-medium"
              >
                应用此模板
              </button>
            </div>
          ))}
        </div>
        
        {filteredTemplates.length === 0 && (
          <div className="text-center text-gray-400 py-8">
            暂无模板
          </div>
        )}
      </div>
      
      {/* 统计信息 */}
      <div className="mt-3 text-xs text-gray-500 border-t border-gray-700 pt-2">
        共 {MV_TEMPLATES.length} 个模板 | 当前显示 {filteredTemplates.length} 个
      </div>
      
      {/* 预览弹窗 */}
      {previewTemplate && (
        <div
          className="fixed inset-0 bg-black/70 flex items-center justify-center z-50"
          onClick={() => setPreviewTemplate(null)}
        >
          <div
            className="bg-gray-800 rounded-lg p-4 max-w-2xl w-full mx-4"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex justify-between items-center mb-3">
              <h4 className="text-white font-semibold text-lg">{previewTemplate.name}</h4>
              <button
                onClick={() => setPreviewTemplate(null)}
                className="text-gray-400 hover:text-white text-2xl"
              >
                ✕
              </button>
            </div>
            
            {/* 预览区域 */}
            <div className="aspect-video bg-gradient-to-br from-orange-900 to-gray-900 rounded mb-4 flex items-center justify-center">
              <div className="text-6xl">
                {previewTemplate.style === '明亮' ? '☀️' : previewTemplate.style === '暗黑' ? '🌙' : '🎭'}
              </div>
            </div>
            
            {/* 详情 */}
            <div className="mb-4">
              <p className="text-gray-300 text-sm mb-2">{previewTemplate.description}</p>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <span className="text-gray-400">分类:</span>
                  <span className="text-white ml-2">{previewTemplate.category}</span>
                </div>
                <div>
                  <span className="text-gray-400">风格:</span>
                  <span className="text-white ml-2">{previewTemplate.style}</span>
                </div>
                <div>
                  <span className="text-gray-400">时长:</span>
                  <span className="text-white ml-2">{previewTemplate.duration}秒</span>
                </div>
                <div>
                  <span className="text-gray-400">默认转场:</span>
                  <span className="text-white ml-2">{previewTemplate.config.defaultTransition || '淡入淡出'}</span>
                </div>
              </div>
            </div>
            
            {/* 配置预览 */}
            <div className="bg-gray-900 rounded p-3 mb-4">
              <h5 className="text-white text-xs font-medium mb-2">模板配置:</h5>
              <div className="text-xs text-gray-400 space-y-1">
                <div>字幕位置：{previewTemplate.config.subtitlePosition || '底部'}</div>
                <div>滤镜：{previewTemplate.config.filter || '无'}</div>
                <div>节奏匹配：{previewTemplate.config.beatSync ? '✅' : '❌'}</div>
              </div>
            </div>
            
            {/* 操作按钮 */}
            <div className="flex gap-2">
              <button
                onClick={() => {
                  handleApplyTemplate(previewTemplate);
                  setPreviewTemplate(null);
                }}
                className="flex-1 py-2.5 bg-orange-600 hover:bg-orange-500 text-white rounded font-medium"
              >
                应用此模板
              </button>
              <button
                onClick={() => setPreviewTemplate(null)}
                className="px-4 py-2.5 bg-gray-700 hover:bg-gray-600 text-white rounded"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}