/**
 * MembershipCenter - 会员中心组件
 * 
 * 功能:
 * - 会员等级展示
 * - 计划对比
 * - 购买/续费/取消
 * - 使用配额监控
 * - 权益列表
 */

import { useState, useEffect, useCallback } from 'react';

interface Plan {
  id: string;
  name: string;
  tier: string;
  price_monthly: number;
  price_yearly: number;
  features: string[];
  limits: Record<string, number>;
  popular?: boolean;
}

interface Subscription {
  user_id: string;
  plan_id: string;
  tier: string;
  status: string;
  start_date: string;
  end_date: string;
  auto_renew: boolean;
  trial_days_left?: number;
}

interface UsageQuota {
  key: string;
  label: string;
  used: number;
  limit: number;
  remaining: number;
  unit: string;
}

interface Props {
  userId: string;
  onClose: () => void;
}

const TIER_COLORS: Record<string, string> = {
  free: 'from-gray-500 to-gray-600',
  premium: 'from-orange-500 to-pink-500',
  vip: 'from-purple-500 to-indigo-600'
};

export function MembershipCenter({ userId, onClose }: Props) {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [billingCycle, setBillingCycle] = useState<'monthly' | 'yearly'>('monthly');
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'plans' | 'status' | 'usage'>('plans');
  const [isMobile, setIsMobile] = useState(false);

  // 检测设备类型
  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 768);
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  // 加载会员计划
  const loadPlans = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/subscription/plans');
      const data = await response.json();
      setPlans(data);
    } catch (error) {
      console.error('加载计划失败:', error);
    }
  }, []);

  // 加载会员状态
  const loadSubscription = useCallback(async () => {
    try {
      const response = await fetch(`/api/v1/subscription/status?user_id=${userId}`);
      const data = await response.json();
      setSubscription(data);
    } catch (error) {
      console.error('加载会员状态失败:', error);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  // 加载使用配额
  const loadUsage = useCallback(async () => {
    try {
      const response = await fetch(`/api/v1/subscription/usage?user_id=${userId}`);
      const data = await response.json();
      return data.quota;
    } catch (error) {
      console.error('加载使用配额失败:', error);
      return {};
    }
  }, [userId]);

  // 购买会员
  const purchasePlan = useCallback(async (planId: string) => {
    try {
      const response = await fetch('/api/v1/subscription/purchase', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          plan_id: planId,
          billing_cycle: billingCycle,
          payment_method: 'alipay'
        })
      });
      
      const result = await response.json();
      if (response.ok) {
        alert('购买成功！');
        loadSubscription();
        setTab('status');
      } else {
        alert(`购买失败：${result.detail}`);
      }
    } catch (error) {
      console.error('购买失败:', error);
      alert('购买失败，请重试');
    }
  }, [userId, billingCycle, loadSubscription]);

  // 取消订阅
  const cancelSubscription = useCallback(async () => {
    if (!confirm('确定要取消订阅吗？')) return;
    
    try {
      const response = await fetch(`/api/v1/subscription/cancel?user_id=${userId}`, {
        method: 'PUT'
      });
      const result = await response.json();
      if (response.ok) {
        alert(`取消成功，有效期到 ${new Date(result.end_date).toLocaleDateString()}`);
        loadSubscription();
      } else {
        alert(`取消失败：${result.detail}`);
      }
    } catch (error) {
      console.error('取消失败:', error);
    }
  }, [userId, loadSubscription]);

  // 使用配额组件
  const UsageBar = ({ quota }: { quota: UsageQuota }) => {
    const percentage = quota.limit === -1 
      ? 0 
      : Math.min(100, (quota.used / quota.limit) * 100);
    
    return (
      <div className="mb-4">
        <div className="flex justify-between text-sm mb-1">
          <span className="text-[#e0e0e0]">{quota.label}</span>
          <span className="text-[#777777]">
            {quota.limit === -1 ? '无限制' : `${quota.remaining}/${quota.limit} ${quota.unit}`}
          </span>
        </div>
        <div className="h-2 bg-[#2a2a2a] rounded-full overflow-hidden">
          <div 
            className={`h-full ${
              percentage > 80 ? 'bg-red-500' : percentage > 50 ? 'bg-orange-500' : 'bg-green-500'
            } transition-all`}
            style={{ width: `${percentage}%` }}
          />
        </div>
      </div>
    );
  };

  useEffect(() => {
    loadPlans();
    loadSubscription();
  }, [loadPlans, loadSubscription]);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 overflow-auto">
      <div className={`max-h-[90vh] bg-[#1e1e1e] rounded-xl border border-[#2a2a2a] overflow-hidden my-8 ${
        isMobile ? 'w-full h-full rounded-none' : 'w-[900px]'
      }`}>
        {/* 头部 */}
        <div className="flex items-center justify-between p-4 border-b border-[#2a2a2a]">
          <div>
            <h2 className="text-xl font-bold text-[#e0e0e0]">👑 会员中心</h2>
            <p className="text-xs text-[#777777]">
              {subscription?.tier === 'vip' ? 'VIP 专业版' : 
               subscription?.tier === 'premium' ? '高级版' : '免费版'}
            </p>
          </div>
          <button onClick={onClose} className="text-[#777777] hover:text-white transition">✕</button>
        </div>

        {/* 标签页 */}
        <div className="flex border-b border-[#2a2a2a]">
          {[
            { key: 'plans', label: '会员计划' },
            { key: 'status', label: '我的会员' },
            { key: 'usage', label: '使用配额' }
          ].map(item => (
            <button
              key={item.key}
              onClick={() => setTab(item.key as typeof tab)}
              className={`flex-1 py-3 text-sm font-medium transition ${
                tab === item.key
                  ? 'text-orange-500 border-b-2 border-orange-500 bg-[#252525]'
                  : 'text-[#777777] hover:text-white'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        {/* 内容区 */}
        <div className="p-6 overflow-auto max-h-[60vh]">
          {loading ? (
            <div className="text-center text-[#777777] py-8">加载中...</div>
          ) : tab === 'plans' ? (
            /* 会员计划 */
            <div className={`grid gap-4 ${
              isMobile ? 'grid-cols-1' : 'grid-cols-3'
            }`}>
              {plans.map(plan => (
                <div
                  key={plan.id}
                  className={`p-5 rounded-xl border transition relative ${
                    plan.popular 
                      ? 'border-orange-500 bg-gradient-to-br from-[#252525] to-[#1a1a2e]' 
                      : 'border-[#2a2a2a] bg-[#1e1e1e] hover:border-[#3a3a3a]'
                  }`}
                >
                  {plan.popular && (
                    <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 text-xs bg-gradient-to-r from-orange-500 to-pink-500 text-white rounded-full">
                      最受欢迎
                    </div>
                  )}
                  
                  <div className={`text-lg font-bold mb-2 bg-gradient-to-r ${TIER_COLORS[plan.tier]} bg-clip-text text-transparent`}>
                    {plan.name}
                  </div>
                  
                  <div className="text-3xl font-bold text-[#e0e0e0] mb-4">
                    ¥{billingCycle === 'yearly' ? plan.price_yearly : plan.price_monthly}
                    <span className="text-sm font-normal text-[#777777]">/{billingCycle === 'yearly' ? '年' : '月'}</span>
                  </div>
                  
                  <ul className="space-y-2 mb-4">
                    {plan.features.slice(0, 4).map((feature, i) => (
                      <li key={i} className="text-sm text-[#999999] flex items-center gap-2">
                        <span className="text-green-500">✓</span> {feature}
                      </li>
                    ))}
                  </ul>
                  
                  {plan.tier !== 'free' && (
                    <label className="flex items-center gap-2 text-xs text-[#777777] mb-4">
                      <input
                        type="radio"
                        checked={billingCycle === (plan.tier === 'free' ? 'monthly' : billingCycle)}
                        onChange={() => setBillingCycle(billingCycle === 'monthly' ? 'yearly' : 'monthly')}
                        className="accent-orange-500"
                      />
                      {billingCycle === 'yearly' ? '年付省 17%' : '月付'}
                    </label>
                  )}
                  
                  <button
                    onClick={() => purchasePlan(plan.id)}
                    disabled={subscription?.plan_id === plan.id}
                    className={`w-full py-2.5 rounded-lg font-medium transition ${
                      subscription?.plan_id === plan.id
                        ? 'bg-[#2a2a2a] text-[#777777] cursor-not-allowed'
                        : 'bg-gradient-to-r from-orange-500 to-pink-500 text-white hover:from-orange-600 hover:to-pink-600'
                    }`}
                  >
                    {subscription?.plan_id === plan.id ? '当前计划' : '立即购买'}
                  </button>
                </div>
              ))}
            </div>
          ) : tab === 'status' ? (
            /* 会员状态 */
            subscription ? (
              <div className="space-y-6">
                <div className={`p-6 rounded-xl bg-gradient-to-br ${TIER_COLORS[subscription.tier]}`}>
                  <div className="text-white">
                    <div className="text-2xl font-bold mb-1">
                      {subscription.tier === 'vip' ? 'VIP 专业版' : 
                       subscription.tier === 'premium' ? '高级版' : '免费版'}
                    </div>
                    <div className="text-sm opacity-80">
                      有效期至 {new Date(subscription.end_date).toLocaleDateString()}
                    </div>
                    {subscription.trial_days_left && (
                      <div className="mt-2 text-xs bg-white/20 inline-block px-2 py-1 rounded">
                        试用剩余 {subscription.trial_days_left} 天
                      </div>
                    )}
                  </div>
                </div>
                
                {subscription.status !== 'cancelled' && (
                  <div className="flex items-center justify-between">
                    <div className="text-sm text-[#777777]">
                      自动续费：{subscription.auto_renew ? '已开启' : '已关闭'}
                    </div>
                    <button
                      onClick={cancelSubscription}
                      className="text-sm text-red-500 hover:text-red-400"
                    >
                      取消订阅
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center text-[#777777] py-8">暂无会员信息</div>
            )
          ) : tab === 'usage' ? (
            /* 使用配额 */
            <div>
              <h3 className="text-lg font-bold text-[#e0e0e0] mb-4">本月使用情况</h3>
              <div className="space-y-4">
                {[
                  { key: 'music_generation', label: 'AI 音乐生成', unit: '首' },
                  { key: 'mv_templates', label: 'MV 模板使用', unit: '次' },
                  { key: 'storage_gb', label: '存储空间', unit: 'GB' },
                  { key: 'ai_features', label: 'AI 功能', unit: '次' }
                ].map(item => (
                  <UsageBar
                    key={item.key}
                    quota={{
                      ...item,
                      used: 0,
                      limit: subscription?.tier === 'premium' || subscription?.tier === 'vip' ? -1 : 5,
                      remaining: subscription?.tier === 'premium' || subscription?.tier === 'vip' ? -1 : 5
                    }}
                  />
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}