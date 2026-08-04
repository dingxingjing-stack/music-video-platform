/**
 * OneClickPublish - 一键发布组件
 * 支持 YouTube, TikTok, Bilibili, Instagram Reels
 */

import { useState, useCallback } from 'react';

interface Platform {
  id: string;
  name: string;
  icon: string;
  color: string;
  oauth_required: boolean;
}

interface PublishData {
  title: string;
  description: string;
  tags: string[];
  privacy: 'public' | 'unlisted' | 'private';
  thumbnail_url?: string;
  category?: string;
}

interface UploadStatus {
  task_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: Record<string, number>;
  results: Record<string, { success: boolean; url: string; message: string }>;
}

const PLATFORMS: Platform[] = [
  { id: 'youtube', name: 'YouTube', icon: '📺', color: '#FF0000', oauth_required: true },
  { id: 'tiktok', name: 'TikTok', icon: '🎵', color: '#000000', oauth_required: true },
  { id: 'bilibili', name: '哔哩哔哩', icon: '📱', color: '#FB7299', oauth_required: true },
  { id: 'instagram', name: 'Instagram Reels', icon: '📸', color: '#E4405F', oauth_required: true },
];

export function OneClickPublish({ videoUrl, onClose }: { videoUrl: string; onClose?: () => void }) {
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([]);
  const [publishData, setPublishData] = useState<PublishData>({
    title: '',
    description: '',
    tags: [],
    privacy: 'public',
  });
  const [tagInput, setTagInput] = useState('');
  const [isPublishing, setIsPublishing] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<UploadStatus | null>(null);

  // 切换平台选择
  const togglePlatform = useCallback((platformId: string) => {
    setSelectedPlatforms(prev =>
      prev.includes(platformId)
        ? prev.filter(p => p !== platformId)
        : [...prev, platformId]
    );
  }, []);

  // 添加标签
  const addTag = useCallback(() => {
    if (tagInput.trim() && !publishData.tags.includes(tagInput.trim())) {
      setPublishData(prev => ({
        ...prev,
        tags: [...prev.tags, tagInput.trim()]
      }));
      setTagInput('');
    }
  }, [tagInput, publishData.tags]);

  // 删除标签
  const removeTag = useCallback((tag: string) => {
    setPublishData(prev => ({
      ...prev,
      tags: prev.tags.filter(t => t !== tag)
    }));
  }, []);

  // 获取授权
  const handleAuth = useCallback(async (platform: string) => {
    try {
      const response = await fetch(`/api/v1/publish/auth/${platform}`, {
        method: 'POST',
      });
      const data = await response.json();
      if (data.auth_url) {
        window.open(data.auth_url, '_blank');
      }
    } catch (error) {
      console.error('授权失败:', error);
    }
  }, []);

  // 执行发布
  const handlePublish = useCallback(async () => {
    if (selectedPlatforms.length === 0) {
      alert('请至少选择一个平台');
      return;
    }

    if (!publishData.title.trim()) {
      alert('请填写视频标题');
      return;
    }

    setIsPublishing(true);

    try {
      const response = await fetch('/api/v1/publish/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          video_url: videoUrl,
          platforms: selectedPlatforms,
          ...publishData,
        }),
      });

      const data: UploadStatus & { task_id: string } = await response.json();
      
      if (data.success) {
        setUploadStatus({
          task_id: data.task_id,
          status: data.status,
          progress: data.progress,
          results: data.results,
        });

        // 轮询状态
        const pollInterval = setInterval(async () => {
          const statusResponse = await fetch(`/api/v1/publish/status/${data.task_id}`);
          const statusData: UploadStatus = await statusResponse.json();
          
          setUploadStatus(statusData);

          if (statusData.status === 'completed' || statusData.status === 'failed') {
            clearInterval(pollInterval);
          }
        }, 2000);
      } else {
        alert('发布失败：' + data.message);
        setIsPublishing(false);
      }
    } catch (error) {
      console.error('发布错误:', error);
      alert('发布失败，请重试');
      setIsPublishing(false);
    }
  }, [selectedPlatforms, publishData, videoUrl]);

  return (
    <div className="bg-[#1a1a1a] rounded-lg p-6 max-w-2xl mx-auto">
      <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
        <span>🚀</span> 一键发布
      </h2>

      {/* 平台选择 */}
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-[#e0e0e0] mb-3">选择平台</h3>
        <div className="grid grid-cols-2 gap-3">
          {PLATFORMS.map(platform => (
            <button
              key={platform.id}
              onClick={() => togglePlatform(platform.id)}
              className={`p-4 rounded-lg border-2 transition-all ${
                selectedPlatforms.includes(platform.id)
                  ? 'border-orange-500 bg-orange-500/10'
                  : 'border-[#3a3a3a] bg-[#252525] hover:border-[#555]'
              }`}
              style={{
                borderColor: selectedPlatforms.includes(platform.id) ? platform.color : undefined
              }}
            >
              <div className="flex items-center gap-3">
                <span className="text-3xl">{platform.icon}</span>
                <div className="text-left">
                  <div className="font-semibold text-white">{platform.name}</div>
                  {platform.oauth_required && (
                    <div className="text-xs text-[#888] mt-1">需要授权</div>
                  )}
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* 视频信息 */}
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-[#e0e0e0] mb-3">视频信息</h3>
        
        <div className="space-y-4">
          <div>
            <label className="block text-sm text-[#888] mb-1">标题 *</label>
            <input
              type="text"
              value={publishData.title}
              onChange={(e) => setPublishData(prev => ({ ...prev, title: e.target.value }))}
              className="w-full bg-[#252525] border border-[#3a3a3a] rounded-lg px-4 py-2 text-white focus:outline-none focus:border-orange-500"
              placeholder="输入吸引人的标题"
            />
          </div>

          <div>
            <label className="block text-sm text-[#888] mb-1">描述</label>
            <textarea
              value={publishData.description}
              onChange={(e) => setPublishData(prev => ({ ...prev, description: e.target.value }))}
              className="w-full bg-[#252525] border border-[#3a3a3a] rounded-lg px-4 py-2 text-white focus:outline-none focus:border-orange-500 resize-none"
              rows={4}
              placeholder="描述你的视频内容..."
            />
          </div>

          <div>
            <label className="block text-sm text-[#888] mb-1">标签</label>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addTag()}
                className="flex-1 bg-[#252525] border border-[#3a3a3a] rounded-lg px-4 py-2 text-white focus:outline-none focus:border-orange-500"
                placeholder="输入标签后按回车"
              />
              <button
                onClick={addTag}
                className="bg-orange-600 hover:bg-orange-700 text-white px-4 py-2 rounded-lg transition-colors"
              >
                添加
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {publishData.tags.map(tag => (
                <span
                  key={tag}
                  className="bg-[#3a3a3a] text-[#e0e0e0] px-3 py-1 rounded-full text-sm flex items-center gap-2"
                >
                  #{tag}
                  <button
                    onClick={() => removeTag(tag)}
                    className="hover:text-white"
                  >
                    ✕
                  </button>
                </span>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm text-[#888] mb-1">隐私设置</label>
            <select
              value={publishData.privacy}
              onChange={(e) => setPublishData(prev => ({ ...prev, privacy: e.target.value as any }))}
              className="w-full bg-[#252525] border border-[#3a3a3a] rounded-lg px-4 py-2 text-white focus:outline-none focus:border-orange-500"
            >
              <option value="public">公开 - 任何人都可以看到</option>
              <option value="unlisted">不公开 - 只有知道链接的人可以看到</option>
              <option value="private">私密 - 只有你可以看到</option>
            </select>
          </div>
        </div>
      </div>

      {/* 上传状态 */}
      {uploadStatus && (
        <div className="mb-6 p-4 bg-[#252525] rounded-lg">
          <h3 className="text-lg font-semibold text-[#e0e0e0] mb-3">发布进度</h3>
          <div className="space-y-3">
            {Object.entries(uploadStatus.progress).map(([platform, progress]) => {
              const platformInfo = PLATFORMS.find(p => p.id === platform);
              const result = uploadStatus.results[platform];
              return (
                <div key={platform}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-white flex items-center gap-2">
                      {platformInfo?.icon} {platformInfo?.name}
                    </span>
                    <span className="text-[#888]">{progress}%</span>
                  </div>
                  <div className="w-full bg-[#3a3a3a] rounded-full h-2 overflow-hidden">
                    <div
                      className="h-full transition-all duration-300"
                      style={{
                        width: `${progress}%`,
                        backgroundColor: platformInfo?.color || '#f97316'
                      }}
                    />
                  </div>
                  {result && (
                    <div className={`text-xs mt-1 ${result.success ? 'text-green-500' : 'text-red-500'}`}>
                      {result.message}
                      {result.url && (
                        <a href={result.url} target="_blank" rel="noopener noreferrer" className="underline ml-2">
                          查看视频
                        </a>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 操作按钮 */}
      <div className="flex gap-3">
        {uploadStatus ? (
          <button
            onClick={onClose}
            className="flex-1 bg-[#3a3a3a] hover:bg-[#4a4a4a] text-white py-3 rounded-lg transition-colors"
          >
            关闭
          </button>
        ) : (
          <>
            <button
              onClick={onClose}
              className="flex-1 bg-[#3a3a3a] hover:bg-[#4a4a4a] text-white py-3 rounded-lg transition-colors"
            >
              取消
            </button>
            <button
              onClick={handlePublish}
              disabled={isPublishing || selectedPlatforms.length === 0}
              className="flex-1 bg-gradient-to-r from-orange-500 to-pink-500 hover:from-orange-600 hover:to-pink-600 text-white py-3 rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed font-semibold"
            >
              {isPublishing ? '发布中...' : `发布到 ${selectedPlatforms.length} 个平台`}
            </button>
          </>
        )}
      </div>
    </div>
  );
}