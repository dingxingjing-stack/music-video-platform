/**
 * TransitionLibrary — 转场效果库组件
 * 
 * P0-5: 20+ 种转场效果
 * 分类: 基础/滑动/缩放/旋转/特效
 */

import { useState } from 'react';
import { TRANSITIONS, TRANSITION_CATEGORIES, Transition, getTransitionsByCategory } from '../data/transitions';

interface Props {
  onTransitionSelect: (transition: Transition, clipId?: string) => void;
  duration?: number;
}

export function TransitionLibrary({ onTransitionSelect, duration }: Props) {
  const [selectedCategory, setSelectedCategory] = useState<string>('基础');
  const [transitionDuration, setTransitionDuration] = useState(1.0);
  const [hoveredTransition, setHoveredTransition] = useState<Transition | null>(null);
  
  const transitions = getTransitionsByCategory(selectedCategory as any);

  const handleSelect = (transition: Transition) => {
    onTransitionSelect({ ...transition, defaultDuration: transitionDuration });
  };

  return (
    <div className="bg-gray-900 rounded-lg p-4 h-full flex flex-col">
      <h3 className="text-white font-semibold mb-3">🎞️ 转场效果库</h3>
      
      {/* 分类筛选 */}
      <div className="flex flex-wrap gap-2 mb-4">
        {TRANSITION_CATEGORIES.map(cat => (
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
      
      {/* 时长调节 */}
      <div className="mb-4 p-3 bg-gray-800 rounded">
        <div className="flex items-center justify-between mb-2">
          <label className="text-gray-300 text-xs">转场时长</label>
          <span className="text-orange-400 text-xs font-mono">{transitionDuration.toFixed(1)}s</span>
        </div>
        <input
          type="range"
          min="0.2"
          max="3.0"
          step="0.1"
          value={transitionDuration}
          onChange={e => setTransitionDuration(parseFloat(e.target.value))}
          className="w-full"
        />
      </div>
      
      {/* 转场列表 */}
      <div className="flex-1 overflow-y-auto">
        <div className="grid grid-cols-2 gap-2">
          {transitions.map(transition => (
            <div
              key={transition.id}
              className={`p-2 rounded cursor-pointer transition border ${
                hoveredTransition?.id === transition.id
                  ? 'bg-orange-900/30 border-orange-500'
                  : 'bg-gray-800 border-gray-700 hover:border-orange-400'
              }`}
              onClick={() => handleSelect(transition)}
              onMouseEnter={() => setHoveredTransition(transition)}
              onMouseLeave={() => setHoveredTransition(null)}
            >
              {/* 图标 + 名称 */}
              <div className="flex items-center gap-2 mb-1">
                <span className="text-2xl">{transition.icon}</span>
                <span className="text-white text-sm font-medium">{transition.name}</span>
              </div>
              
              {/* 描述 */}
              <p className="text-gray-400 text-xs line-clamp-2">
                {transition.description}
              </p>
              
              {/* 时长标签 */}
              <div className="flex items-center gap-2 mt-2">
                <span className="text-xs bg-gray-700 text-gray-300 px-1 rounded">
                  {transition.defaultDuration}s
                </span>
                {hoveredTransition?.id === transition.id && (
                  <span className="text-xs text-orange-400">
                    点击应用 →
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
      
      {/* 统计信息 */}
      <div className="mt-3 text-xs text-gray-500 border-t border-gray-700 pt-2">
        当前分类：{selectedCategory} | {transitions.length} 种转场
      </div>
      
      {/* 使用说明 */}
      {hoveredTransition && (
        <div className="absolute bottom-20 left-4 right-4 bg-gray-800 rounded-lg p-3 shadow-xl border border-gray-700">
          <div className="flex items-start gap-3">
            <span className="text-3xl">{hoveredTransition.icon}</span>
            <div className="flex-1">
              <h4 className="text-white font-medium text-sm">{hoveredTransition.name}</h4>
              <p className="text-gray-400 text-xs mt-1">{hoveredTransition.description}</p>
              <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
                <span>时长：{transitionDuration}s</span>
                <span>缓动：{hoveredTransition.params.easing || 'linear'}</span>
                {hoveredTransition.params.direction && (
                  <span>方向：{hoveredTransition.params.direction}</span>
                )}
              </div>
            </div>
            <button
              onClick={() => handleSelect(hoveredTransition)}
              className="px-3 py-1.5 bg-orange-600 hover:bg-orange-500 text-white text-xs rounded"
            >
              应用
            </button>
          </div>
        </div>
      )}
    </div>
  );
}