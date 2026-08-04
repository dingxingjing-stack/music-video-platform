/**
 * AssetStore - 素材商店组件
 * 
 * 功能:
 * - 浏览付费/免费素材
 * - 分类筛选 (视频/效果器/转场)
 * - 搜索
 * - 购买/下载
 * - 预览
 */

import { useState, useEffect, useCallback } from 'react';

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
  { key: 'all', label: '全部' },
  { key: 'video', label: '🎬 视频' },
  { key: 'effect', label: '🎨 效果器' },
  { key: 'transition', label: '✨ 转场' },
  { key: 'template', label: '📋 模板' }
];

const PRICE_FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'free', label: '免费' },
  { key: 'paid', label: '付费' }
];

export function AssetStore({ userId, onClose }: Props) {
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
          alert('下载已开始！');
        }
      } catch (error) {
        console.error('下载失败:', error);
      }
      return;
    }

    // 付费素材购买确认
    if (!confirm(`确认购买此素材？\n价格：¥${price}`)) return;

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
        alert('购买成功！');
        setPurchased(prev => [...prev, assetId]);
        loadPurchases();
      } else {
        alert(`购买失败：${result.detail}`);
      }
    } catch (error) {
      console.error('购买失败:', error);
      alert('购买失败，请重试');
    }
  }, [userId, loadPurchases]);

  // 预览素材
  const previewAsset = useCallback(async (asset: Asset) => {
    if (!asset.preview_url) {
      alert('暂无预览视频');
      return;
    }

    // TODO: 打开预览模态框
    alert(`预览：${asset.name}\n(实际应播放 30 秒带水印预览)`);
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
            <h2 className="text-xl font-bold text-[#e0e0e0]">🏪 素材商店</h2>
            <p className="text-xs text-[#777777]">{assets.length} 个素材</p>
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
            placeholder="搜索素材..."
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
                {filter.label}
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
                {filter.label}
              </button>
            ))}
          </div>

          {/* 排序 */}
          <select
            value={sortBy}
            onChange={e => setSortBy(e.target.value)}
            className="px-3 py-2 bg-[#252525] border border-[#2a2a2a] rounded-lg text-sm text-[#e0e0e0] focus:outline-none focus:border-orange-500"
          >
            <option value="downloads">🔥 最热</option>
            <option value="rating">⭐ 评分</option>
            <option value="price">💰 价格</option>
          </select>
        </div>

        {/* 素材列表 */}
        <div className="p-6 overflow-auto max-h-[60vh]">
          {loading ? (
            <div className="text-center text-[#777777] py-8">加载中...</div>
          ) : assets.length === 0 ? (
            <div className="text-center text-[#777777] py-8">暂无素材</div>
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
                      🎬 预览图
                    </div>
                    {asset.is_premium && (
                      <div className="absolute top-2 left-2 px-2 py-1 text-xs bg-orange-500 text-white rounded">
                        付费
                      </div>
                    )}
                    {purchased.includes(asset.id) && (
                      <div className="absolute top-2 right-2 px-2 py-1 text-xs bg-green-500 text-white rounded">
                        已购
                      </div>
                    )}
                    
                    {/* 预览按钮 */}
                    {asset.preview_url && (
                      <button
                        onClick={() => previewAsset(asset)}
                        className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center transition"
                      >
                        <span className="px-4 py-2 bg-white/20 backdrop-blur rounded-lg text-white text-sm">
                          ▶ 预览
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
                          <span className="text-green-500">免费</span>
                        ) : (
                          <span className="text-orange-500">¥{asset.price}</span>
                        )}
                      </div>

                      {purchased.includes(asset.id) ? (
                        <button className="px-4 py-2 bg-green-500/20 text-green-500 text-sm rounded-lg cursor-default">
                          已购买
                        </button>
                      ) : (
                        <button
                          onClick={() => purchaseAsset(asset.id, asset.price)}
                          className="px-4 py-2 bg-gradient-to-r from-orange-500 to-pink-500 text-white text-sm rounded-lg hover:from-orange-600 hover:to-pink-600 transition"
                        >
                          {asset.price === 0 ? '下载' : '购买'}
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
          付费素材购买后可无限次下载 • 支持支付宝/微信支付
        </div>
      </div>
    </div>
  );
}