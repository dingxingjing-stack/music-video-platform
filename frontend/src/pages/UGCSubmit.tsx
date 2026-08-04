/**
 * UGC 投稿页面 - 上传模板/素材/效果
 */

import { useState } from 'react';

export default function UGCSubmitPage() {
  const [type, setType] = useState<'template' | 'material' | 'effect'>('template');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('');
  const [tags, setTags] = useState('');
  const [price, setPrice] = useState(2.0);
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{success: boolean, message: string} | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    
    const formData = new FormData();
    formData.append('type', type);
    formData.append('title', title);
    formData.append('description', description);
    formData.append('category', category);
    formData.append('tags', JSON.stringify(tags.split(',').map(t => t.trim())));
    formData.append('price', price.toString());
    if (file) formData.append('file', file);
    
    try {
      const res = await fetch('/api/v1/ugc/submit', {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      setResult(data);
    } catch (err) {
      setResult({ success: false, message: '投稿失败，请重试' });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#121212] text-white py-12">
      <div className="max-w-3xl mx-auto px-6">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold mb-4">
            成为创作者，<span className="text-transparent bg-clip-text bg-gradient-to-r from-orange-400 to-pink-500">赚取收益</span>
          </h1>
          <p className="text-gray-400">
            上传你的 MV 模板、素材或效果，每次下载都能获得分成
          </p>
        </div>

        {/* 收益说明 */}
        <div className="bg-gradient-to-r from-orange-500/10 to-pink-500/10 rounded-xl p-6 mb-8">
          <h3 className="font-bold mb-3">💰 收益分成</h3>
          <div className="grid md:grid-cols-3 gap-4">
            <div>
              <div className="text-2xl font-bold text-orange-400">50%</div>
              <div className="text-sm text-gray-400">模板分成</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-pink-400">40%</div>
              <div className="text-sm text-gray-400">素材分成</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-purple-400">¥1,500</div>
              <div className="text-sm text-gray-400">头部创作者月收入</div>
            </div>
          </div>
        </div>

        {/* 投稿表单 */}
        <form onSubmit={handleSubmit} className="bg-gray-900 rounded-xl p-8 space-y-6">
          {/* 作品类型 */}
          <div>
            <label className="block text-sm font-medium mb-2">作品类型</label>
            <div className="flex gap-4">
              {[
                { value: 'template', label: '📦 MV 模板', price: '50% 分成' },
                { value: 'material', label: '🎨 素材', price: '40% 分成' },
                { value: 'effect', label: '✨ 转场效果', price: '40% 分成' }
              ].map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setType(opt.value as any)}
                  className={`flex-1 p-4 rounded-lg border-2 transition-all ${
                    type === opt.value
                      ? 'border-orange-500 bg-orange-500/10'
                      : 'border-gray-700 hover:border-gray-600'
                  }`}
                >
                  <div className="font-bold">{opt.label}</div>
                  <div className="text-xs text-gray-400 mt-1">{opt.price}</div>
                </button>
              ))}
            </div>
          </div>

          {/* 标题 */}
          <div>
            <label className="block text-sm font-medium mb-2">作品标题</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="例如：夏日海滩 MV 模板"
              className="w-full px-4 py-3 bg-gray-800 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500"
              required
            />
          </div>

          {/* 描述 */}
          <div>
            <label className="block text-sm font-medium mb-2">作品描述</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="介绍你的作品特点、使用场景..."
              rows={4}
              className="w-full px-4 py-3 bg-gray-800 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500"
              required
            />
          </div>

          {/* 分类 */}
          <div>
            <label className="block text-sm font-medium mb-2">分类</label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full px-4 py-3 bg-gray-800 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500"
              required
            >
              <option value="">选择分类</option>
              <option value="travel">旅行</option>
              <option value="music">音乐</option>
              <option value="city">城市</option>
              <option value="nature">自然</option>
              <option value="tech">科技</option>
              <option value="abstract">抽象</option>
              <option value="love">爱情</option>
              <option value="party">派对</option>
            </select>
          </div>

          {/* 标签 */}
          <div>
            <label className="block text-sm font-medium mb-2">标签</label>
            <input
              type="text"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="用逗号分隔，例如：夏日，海滩，清新"
              className="w-full px-4 py-3 bg-gray-800 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500"
              required
            />
          </div>

          {/* 定价 */}
          <div>
            <label className="block text-sm font-medium mb-2">定价 (¥)</label>
            <input
              type="number"
              step="0.1"
              min="0.1"
              max="10"
              value={price}
              onChange={(e) => setPrice(parseFloat(e.target.value))}
              className="w-full px-4 py-3 bg-gray-800 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500"
              required
            />
            <div className="text-xs text-gray-400 mt-1">
              建议定价：模板 ¥1-3, 素材 ¥0.5-2, 效果 ¥0.5-1
            </div>
          </div>

          {/* 文件上传 */}
          <div>
            <label className="block text-sm font-medium mb-2">上传文件</label>
            <div className="border-2 border-dashed border-gray-700 rounded-lg p-8 text-center">
              <input
                type="file"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                accept=".json,.mp4,.mov,.png,.jpg"
                className="hidden"
                id="file-upload"
                required
              />
              <label htmlFor="file-upload" className="cursor-pointer">
                <div className="text-4xl mb-2">📤</div>
                <div className="font-medium">
                  {file ? file.name : '点击或拖拽上传文件'}
                </div>
                <div className="text-sm text-gray-400 mt-1">
                  支持格式：JSON (模板), MP4/MOV (视频), PNG/JPG (图片)
                </div>
              </label>
            </div>
          </div>

          {/* 提交按钮 */}
          <button
            type="submit"
            disabled={submitting}
            className="w-full py-4 bg-gradient-to-r from-orange-500 to-pink-500 rounded-full font-bold hover:scale-105 transition-transform disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? '提交中...' : '提交作品'}
          </button>

          {/* 结果提示 */}
          {result && (
            <div className={`p-4 rounded-lg ${
              result.success ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
            }`}>
              {result.message}
            </div>
          )}
        </form>

        {/* 投稿指南 */}
        <div className="mt-8 bg-gray-900 rounded-xl p-8">
          <h3 className="font-bold mb-4">📋 投稿指南</h3>
          <ul className="space-y-2 text-gray-400">
            <li>✅ 审核时间：1-2 个工作日</li>
            <li>✅ 质量要求：清晰、原创、实用</li>
            <li>✅ 收益结算：每月 15 日打款</li>
            <li>✅ 最低提现：¥50</li>
          </ul>
        </div>
      </div>
    </div>
  );
}