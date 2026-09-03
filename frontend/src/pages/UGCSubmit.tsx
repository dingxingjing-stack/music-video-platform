/**
 * UGC 投稿页面 - 上传模板/素材/效果
 */

import { useState } from 'react';
import { useTranslation } from '../i18n/useTranslation';

export default function UGCSubmitPage() {
  const { t } = useTranslation();
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
      setResult({ success: false, message: t('ugc.submitFailed') });
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
            {t('ugc.title')}<span className="text-transparent bg-clip-text bg-gradient-to-r from-orange-400 to-pink-500">{t('ugc.titleEarn')}</span>
          </h1>
          <p className="text-gray-400">
            {t('ugc.subtitle')}
          </p>
        </div>

        {/* 收益说明 */}
        <div className="bg-gradient-to-r from-orange-500/10 to-pink-500/10 rounded-xl p-6 mb-8">
          <h3 className="font-bold mb-3">{t('ugc.revenueTitle')}</h3>
          <div className="grid md:grid-cols-3 gap-4">
            <div>
              <div className="text-2xl font-bold text-orange-400">50%</div>
              <div className="text-sm text-gray-400">{t('ugc.templateShare')}</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-pink-400">40%</div>
              <div className="text-sm text-gray-400">{t('ugc.materialShare')}</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-purple-400">¥1,500</div>
              <div className="text-sm text-gray-400">{t('ugc.topCreator')}</div>
            </div>
          </div>
        </div>

        {/* 投稿表单 */}
        <form onSubmit={handleSubmit} className="bg-gray-900 rounded-xl p-8 space-y-6">
          {/* {t('ugc.workType')} */}
          <div>
            <label className="block text-sm font-medium mb-2">{t('ugc.workType')}</label>
            <div className="flex gap-4">
              {[
                { value: 'template', label: t('ugc.typeTemplate'), price: 50 },
                { value: 'material', label: t('ugc.typeMaterial'), price: 40 },
                { value: 'effect', label: t('ugc.typeEffect'), price: 40 }
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
                  <div className="font-bold">{t(opt.label)}</div>
                  <div className="text-xs text-gray-400 mt-1">{t('ugc.share', { n: opt.price })}</div>
                </button>
              ))}
            </div>
          </div>

          {/* 标题 */}
          <div>
            <label className="block text-sm font-medium mb-2">{t('ugc.titleLabel')}</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t('ugc.titlePlaceholder')}
              className="w-full px-4 py-3 bg-gray-800 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500"
              required
            />
          </div>

          {/* 描述 */}
          <div>
            <label className="block text-sm font-medium mb-2">{t('ugc.descLabel')}</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t('ugc.descPlaceholder')}
              rows={4}
              className="w-full px-4 py-3 bg-gray-800 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500"
              required
            />
          </div>

          {/* 分类 */}
          <div>
            <label className="block text-sm font-medium mb-2">{t('ugc.category')}</label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full px-4 py-3 bg-gray-800 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500"
              required
            >
              <option value="">{t('ugc.selectCategory')}</option>
              <option value="travel">{t('ugc.catTravel')}</option>
              <option value="music">{t('ugc.catMusic')}</option>
              <option value="city">{t('ugc.catCity')}</option>
              <option value="nature">{t('ugc.catNature')}</option>
              <option value="tech">{t('ugc.catTech')}</option>
              <option value="abstract">{t('ugc.catAbstract')}</option>
              <option value="love">{t('ugc.catLove')}</option>
              <option value="party">{t('ugc.catParty')}</option>
            </select>
          </div>

          {/* 标签 */}
          <div>
            <label className="block text-sm font-medium mb-2">{t('ugc.tags')}</label>
            <input
              type="text"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder={t('ugc.tagsPlaceholder')}
              className="w-full px-4 py-3 bg-gray-800 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500"
              required
            />
          </div>

          {/* 定价 */}
          <div>
            <label className="block text-sm font-medium mb-2">{t('ugc.price')} (¥)</label>
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
              {t('ugc.priceHint')}
            </div>
          </div>

          {/* 文件上传 */}
          <div>
            <label className="block text-sm font-medium mb-2">{t('ugc.uploadFile')}</label>
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
                  {file ? file.name : t('ugc.dropFile')}
                </div>
                <div className="text-sm text-gray-400 mt-1">
                  {t('ugc.supported')}
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
            {submitting ? t('ugc.submitting') : t('ugc.submit')}
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
          <h3 className="font-bold mb-4">{t('ugc.guideTitle')}</h3>
          <ul className="space-y-2 text-gray-400">
            <li>{t('ugc.guide1')}</li>
            <li>{t('ugc.guide2')}</li>
            <li>{t('ugc.guide3')}</li>
            <li>{t('ugc.guide4')}</li>
          </ul>
        </div>
      </div>
    </div>
  );
}