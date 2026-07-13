/**
 * PlatformSelector - 平台选择组件
 * 
 * 用于一键发布功能，支持多选平台
 * 展示平台图标、名称、授权状态
 */

import { useState, useEffect } from 'react';

export interface Platform {
  id: string;
  name: string;
  icon: string;
  supported: boolean;
  authorized: boolean;
  features: string[];
}

interface Props {
  selectedPlatforms: string[];
  onPlatformToggle: (platformIds: string[]) => void;
}

export function PlatformSelector({ selectedPlatforms, onPlatformToggle }: Props) {
  const [platforms, setPlatforms] = useState<Platform[]>([]);
  const [loading, setLoading] = useState(true);

  // 获取平台列表
  useEffect(() => {
    fetch('/api/v1/publish/platforms')
      .then(res => res.json())
      .then(data => {
        setPlatforms(data.platforms);
        setLoading(false);
      })
      .catch(err => {
        console.error('Failed to load platforms:', err);
        setLoading(false);
        // Mock 数据
        setPlatforms([
          {
            id: 'youtube',
            name: 'YouTube',
            icon: '📺',
            supported: true,
            authorized: false,
            features: ['标题/描述/标签', '隐私设置', '分类选择'],
          },
          {
            id: 'tiktok',
            name: 'TikTok',
            icon: '🎵',
            supported: true,
            authorized: false,
            features: ['背景音乐', '标签/话题', '隐私设置'],
          },
          {
            id: 'bilibili',
            name: '哔哩哔哩',
            icon: '📱',
            supported: true,
            authorized: false,
            features: ['分区选择', '标签/话题', '版权声明'],
          },
        ]);
      });
  }, []);

  const handleToggle = (platformId: string) => {
    if (selectedPlatforms.includes(platformId)) {
      onPlatformToggle(selectedPlatforms.filter(id => id !== platformId));
    } else {
      onPlatformToggle([...selectedPlatforms, platformId]);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="text-gray-400">加载平台列表...</div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <h4 className="text-white text-sm font-medium">选择发布平台</h4>
      
      <div className="grid grid-cols-3 gap-3">
        {platforms.map(platform => {
          const isSelected = selectedPlatforms.includes(platform.id);
          
          return (
            <button
              key={platform.id}
              onClick={() => handleToggle(platform.id)}
              disabled={!platform.supported}
              className={`
                relative p-4 rounded-lg border-2 transition-all
                ${isSelected
                  ? 'bg-orange-600/20 border-orange-500'
                  : 'bg-gray-800 border-gray-700 hover:border-orange-400'
                }
                ${!platform.supported ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
              `}
            >
              {/* 图标 */}
              <div className="text-3xl mb-2">{platform.icon}</div>
              
              {/* 名称 */}
              <div className="text-white text-sm font-medium">{platform.name}</div>
              
              {/* 授权状态 */}
              <div className={`text-xs mt-1 ${platform.authorized ? 'text-green-400' : 'text-gray-400'}`}>
                {platform.authorized ? '已授权' : '未授权'}
              </div>
              
              {/* 选择指示器 */}
              {isSelected && (
                <div className="absolute top-2 right-2 w-5 h-5 bg-orange-500 rounded-full flex items-center justify-center">
                  <span className="text-white text-xs">✓</span>
                </div>
              )}
            </button>
          );
        })}
      </div>
      
      {/* 提示信息 */}
      {!platforms.some(p => p.authorized) && (
        <div className="bg-yellow-900/30 border border-yellow-600/50 rounded p-3 text-yellow-200 text-xs">
          ⚠️ 部分平台未授权，发布前请完成授权
        </div>
      )}
      
      {/* 已选平台提示 */}
      {selectedPlatforms.length > 0 && (
        <div className="text-xs text-gray-400 mt-2">
          已选择 {selectedPlatforms.length} 个平台：{
            selectedPlatforms.map(id => platforms.find(p => p.id === id)?.name).join(', ')
          }
        </div>
      )}
    </div>
  );
}