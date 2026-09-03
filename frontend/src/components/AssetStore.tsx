/**
 * AssetStore - {t('assetstore.title')}组件
 * 
 * 功能:
 * - 浏览付费/免费素材
 * - 分类筛选 (视频/效果器/转场)
 * - 搜索
 * - 购买/下载
 * - 预览
 */

import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from '../i18n/useTranslation';

interface Asset {
  id: string;
  name: string;
  description: string;
  type: string;
  price: number;
  thumbnail_url: string;
  preview_url?: string;
  tags: string[];
  rating: number;
  downloads: number;
  is_premium: boolean;
}

interface Props {
  userId: string;
  onClose: () => void;
}

const TYPE_FILTERS = [
  { key: 'all', label: 'assetstore.typeAll' },
  { key: 'video', label: 'assetstore.typeVideo' },
  { key: 'effect', label: 'assetstore.typeEffect' },
  { key: 'transition', label: 'assetstore.typeTransition' },
  { key: 'template', label: 'assetstore.typeTemplate' }
];

const PRICE_FILTERS = [
  { key: 'all', label: 'assetstore.priceAll' },
  { key: 'free', label: 'assetstore.priceFree' },
  { key: 'paid', label: 'assetstore.pricePaid' }
];

export function AssetStore({ userId, onClose }: Props) {
  const { t } = useTranslation();
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState('all');
  const [priceFilter, setPriceFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState('downloads');
  const [purchased, setPurchased] = useState<string[]>([]);
  const [isMobile, setIsMobile] = useState(false);

  // 检测设备类型
  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 768);
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  // 加载素材列表
  const loadAssets = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (typeFilter !== 'all') params.set('type_filter', typeFilter);
      if (priceFilter !== 'all') params.set('is_premium', priceFilter === 'paid' ? 'true' : 'false');
      if (search) params.set('search', search);
      params.set('sort_by', sortBy);
      params.set('limit', '20');

      const response = await fetch(`/api/v1/store/assets?${params}`);
      const data = await response.json();
      setAssets(data);
    } catch (error) {
      console.error('加载素材失败:', error);
    } finally {
      setLoading(false);
    }
  }, [typeFilter, priceFilter, search, sortBy]);

  // 加载已购列表
  const loadPurchases = useCallback(async () => {
    try {
      const response = await fetch(`/api/v1/store/purchases?user_id=${userId}`);
      const data = await response.json();
      setPurchased(data.map((a: Asset) => a.id));
    } catch (error) {
      console.error('加载已购列表失败:', error);
    }
  }, [userId]);

  // 购买素材
  const purchaseAsset = useCallback(async (assetId: string, price: number) => {
    if (price === 0) {
      // 免费素材直接下载
      try {
        const response = await fetch(`/api/v1/store/download/${assetId}?user_id=${userId}`);
        const data = await response.json();
        if (response.ok) {
          window.open(data.download_url, '_blank');
          alert(t('assetstore.downloadStarted'));
        }
      } catch (error) {
        console.error('下载失败:', error);
      }
      return;
    }

    // 付费素材购买确认
    if (!confirm(t('assetstore.confirmBuy', { price }))) return;

    try {
      const response = await fetch('/api/v1/store/purchase', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          asset_id: assetId,
          payment_method: 'alipay'
        })
      });

      const result = await response.json();
      if (response.ok) {
        alert(t('assetstore.buySuccess'));
        setPurchased(prev => [...prev, assetId]);
        loadPurchases();
      } else {
        alert(t('assetstore.buyFailed', { detail: result.detail }));
      }
    } catch (error) {
      console.error('购买失败:', error);
      alert(t('assetstore.buyFailedRetry'));
    }
  }, [userId, loadPurchases]);

  // 预览素材
  const previewAsset = useCallback(async (asset: Asset) => {
    if (!asset.preview_url) {
      alert(t('assetstore.noPreview'));
      return;
    }

    // TODO: 打开预览模态框
    alert(t('assetstore.previewAsset', { name: asset.name }));
  }, []);

  useEffect(() => {
    loadAssets();
    loadPurchases();
  }, [loadAssets, loadPurchases]);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 overflow-auto">
      <div className={`max-h-[90vh] bg-[#1e1e1e] rounded-xl border border-[#2a2a2a] overflow-hidden my-8 ${
        isMobile ? 'w-full h-full rounded-none' : 'w-[1000px]'
      }`}>
        {/* 头部 */}
        <div className="flex items-center justify-between p-4 border-b border-[#2a2a2a]">
          <div>
            <h2 className="text-xl font-bold text-[#e0e0e0]">🏪 {t('assetstore.title')}</h2>
            <p className="text-xs text-[#777777]">{t('assetstore.count', { n: assets.length })}</p>
          </div>
          <button onClick={onClose} className="text-[#777777] hover:text-white transition">✕</button>
        </div>

        {/* 筛选工具栏 */}
        <div className={`flex ${
          isMobile ? 'flex-col gap-3' : 'items-center gap-4'
        } p-4 border-b border-[#2a2a2a]`}>
          {/* 搜索框 */}
          <input
            type="text"
            placeholder={t('assetstore.searchPlaceholder')}
            value={search}
            onChange={e => setSearch(e.target.value)}
            className={`bg-[#252525] border border-[#2a2a2a] rounded-lg text-sm text-[#e0e0e0] placeholder-[#777777] focus:outline-none focus:border-orange-500 ${
              isMobile ? 'w-full px-3 py-2' : 'flex-1 px-3 py-2'
            }`}
          />

          {/* 类型筛选 */}
          <div className={`flex ${isMobile ? 'overflow-x-auto' : 'gap-2'}`}>
            {TYPE_FILTERS.slice(0, 4).map(filter => (
              <button
                key={filter.key}
                onClick={() => setTypeFilter(filter.key)}
                className={`px-3 py-2 text-sm rounded-lg transition ${
                  typeFilter === filter.key
                    ? 'bg-orange-500 text-white'
                    : 'bg-[#252525] text-[#777777] hover:bg-[#2a2a2a]'
                }`}
              >
                {t(filter.label)}
              </button>
            ))}
          </div>

          {/* 价格筛选 */}
          <div className="flex gap-2">
            {PRICE_FILTERS.map(filter => (
              <button
                key={filter.key}
                onClick={() => setPriceFilter(filter.key)}
                className={`px-3 py-2 text-sm rounded-lg transition ${
                  priceFilter === filter.key
                    ? 'bg-orange-500 text-white'
                    : 'bg-[#252525] text-[#777777] hover:bg-[#2a2a2a]'
                }`}
              >
                {t(filter.label)}
              </button>
            ))}
          </div>

          {/* 排序 */}
          <select
            value={sortBy}
            onChange={e => setSortBy(e.target.value)}
            className="px-3 py-2 bg-[#252525] border border-[#2a2a2a] rounded-lg text-sm text-[#e0e0e0] focus:outline-none focus:border-orange-500"
          >
            <option value="downloads">{t('assetstore.sortPopular')}</option>
            <option value="rating">{t('assetstore.sortRating')}</option>
            <option value="price">{t('assetstore.sortPrice')}</option>
          </select>
        </div>

        {/* 素材列表 */}
        <div className="p-6 overflow-auto max-h-[60vh]">
          {loading ? (
            <div className="text-center text-[#777777] py-8">{t('assetstore.loading')}</div>
          ) : assets.length === 0 ? (
            <div className="text-center text-[#777777] py-8">{t('assetstore.empty')}</div>
          ) : (
            <div className={`grid gap-4 ${
            isMobile ? 'grid-cols-1' : 'grid-cols-3'
          }`}>
              {assets.map(asset => (
                <div
                  key={asset.id}
                  className="bg-[#252525] rounded-xl overflow-hidden border border-[#2a2a2a] hover:border-[#3a3a3a] transition group"
                >
                  {/* 缩略图 */}
                  <div className="relative aspect-video bg-[#1e1e1e]">
                    <div className="absolute inset-0 flex items-center justify-center text-[#777777]">
                      {t('assetstore.previewLabel')}
                    </div>
                    {asset.is_premium && (
                      <div className="absolute top-2 left-2 px-2 py-1 text-xs bg-orange-500 text-white rounded">
                        {t('assetstore.paid')}
                      </div>
                    )}
                    {purchased.includes(asset.id) && (
                      <div className="absolute top-2 right-2 px-2 py-1 text-xs bg-green-500 text-white rounded">
                        {t('assetstore.purchased')}
                      </div>
                    )}
                    
                    {/* 预览按钮 */}
                    {asset.preview_url && (
                      <button
                        onClick={() => previewAsset(asset)}
                        className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center transition"
                      >
                        <span className="px-4 py-2 bg-white/20 backdrop-blur rounded-lg text-white text-sm">
                          {t('assetstore.previewBtn')}
                        </span>
                      </button>
                    )}
                  </div>

                  {/* 信息区 */}
                  <div className="p-4">
                    <div className="flex items-start justify-between mb-2">
                      <h3 className="font-bold text-[#e0e0e0] text-sm line-clamp-1">{asset.name}</h3>
                      <div className="text-xs text-[#777777] flex items-center gap-1">
                        ⭐ {asset.rating}
                      </div>
                    </div>

                    <p className="text-xs text-[#777777] mb-3 line-clamp-2">{asset.description}</p>

                    {/* 标签 */}
                    <div className="flex flex-wrap gap-1 mb-3">
                      {asset.tags.slice(0, 3).map((tag, i) => (
                        <span key={i} className="px-2 py-0.5 text-xs bg-[#2a2a2a] text-[#777777] rounded">
                          {tag}
                        </span>
                      ))}
                    </div>

                    {/* 价格和购买 */}
                    <div className="flex items-center justify-between">
                      <div className="text-lg font-bold">
                        {asset.price === 0 ? (
                          <span className="text-green-500">{t('assetstore.free')}</span>
                        ) : (
                          <span className="text-orange-500">¥{asset.price}</span>
                        )}
                      </div>

                      {purchased.includes(asset.id) ? (
                        <button className="px-4 py-2 bg-green-500/20 text-green-500 text-sm rounded-lg cursor-default">
                          {t('assetstore.alreadyBought')}
                        </button>
                      ) : (
                        <button
                          onClick={() => purchaseAsset(asset.id, asset.price)}
                          className="px-4 py-2 bg-gradient-to-r from-orange-500 to-pink-500 text-white text-sm rounded-lg hover:from-orange-600 hover:to-pink-600 transition"
                        >
                          {asset.price === 0 ? t('assetstore.download') : t('assetstore.buy')}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 底部提示 */}
        <div className={`p-4 border-t border-[#2a2a2a] text-center text-xs text-[#777777] ${
          isMobile ? 'pb-8' : ''
        }`}>
          {t('assetstore.footer')}
        </div>
      </div>
    </div>
  );
}