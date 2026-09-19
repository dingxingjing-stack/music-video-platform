import { useEffect, useState } from 'react';
import { useTranslation } from '../i18n/useTranslation';
import { api } from '../config/api';
import { authFetchOptional } from '../api/http';

/**
 * Pricing v1（正式产品定价，2026-09-18 定稿）。
 * 展示层静态化：后端 /credits/packages 仍是旧 beta 配置（credits_config.py），
 * 本轮禁改后端，故此处以本文件常量为准；未来接入定价 API 时再切回。
 * 支付后端未配置（/purchase 返回 payment_not_configured）→ 购买按钮一律 disabled + Coming Soon，
 * 绝不制造可付款假象。
 */
const PRICING_V1 = [
  { id: 'starter', name: 'Starter', price_usd: 4.99, credits: 200, description_key: 'pricing.starter_desc', badge: null as string | null },
  { id: 'basic', name: 'Basic', price_usd: 9.99, credits: 500, description_key: 'pricing.basic_desc', badge: null },
  { id: 'pro', name: 'Pro', price_usd: 19.99, credits: 1200, description_key: 'pricing.pro_desc', badge: 'best_value' },
  { id: 'creator', name: 'Creator', price_usd: 39.99, credits: 2800, description_key: 'pricing.creator_desc', badge: null },
];
const FREE_CREDITS = 100;
const CREATION_COST_CREDITS = 30;

export function PricingPage() {
  const { t } = useTranslation();
  const [balance, setBalance] = useState<number | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const bal = await authFetchOptional<{ balance: number }>(`${api.base}/api/v1/credits/balance`);
        setBalance(typeof bal.balance === 'number' ? bal.balance : null);
      } catch {
        setBalance(null);
      }
    })();
  }, []);

  const badgeLabel = (badge: string | null) =>
    badge === 'best_value' ? t('pricing.best_value') : null;

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      <div className="max-w-[1120px] mx-auto px-6 py-12">
        <div className="text-center mb-10">
          <h1 className="text-3xl font-black tracking-tight">{t('pricing.title')}</h1>
          <p className="mt-2 text-sm text-[#8a8a8a]">{t('pricing.subtitle')}</p>
        </div>

        {balance !== null && (
          <div className="mb-6 text-center">
            <span className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-[#141414] border border-[#262626] text-sm">
              <span className="text-[#8a8a8a]">{t('pricing.your_credits')}:</span>
              <span className="font-bold text-orange-400">{balance}</span>
            </span>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
          {/* FREE */}
          <div className="rounded-2xl bg-[#141414] border border-[#1f1f1f] p-6 flex flex-col">
            <div className="text-xs font-bold tracking-widest text-[#8a8a8a]">{t('pricing.free')}</div>
            <div className="mt-2 text-3xl font-black">$0</div>
            <div className="mt-1 text-sm font-semibold text-orange-400">{FREE_CREDITS} {t('pricing.credits')}</div>
            <ul className="mt-4 space-y-1.5 text-xs text-[#b0b0b0]">
              <li className="text-emerald-400">{t('pricing.no_credit_card')}</li>
              <li>{t('pricing.cost_one_creation')}</li>
              <li>{t('pricing.cost_failed_free')}</li>
            </ul>
          </div>

          {/* Paid packages — Pricing v1（静态展示；支付未接入 → Coming Soon） */}
          {PRICING_V1.map((p) => {
            const badge = badgeLabel(p.badge);
            const isPro = p.id === 'pro';
            return (
              <div
                key={p.id}
                className={`rounded-2xl p-6 flex flex-col border ${
                  isPro ? 'border-orange-400 bg-[#1a1208] shadow-lg shadow-orange-500/10' : 'border-[#1f1f1f] bg-[#141414]'
                }`}
              >
                {badge && (
                  <div className={`text-[10px] font-bold px-2 py-0.5 rounded-full w-fit mb-2 ${isPro ? 'bg-orange-400 text-black' : 'bg-[#262626] text-orange-300'}`}>
                    {badge}
                  </div>
                )}
                <div className="text-sm font-semibold text-[#e0e0e0]">{p.name}</div>
                <div className="mt-1 text-2xl font-black">${p.price_usd}</div>
                <div className="mt-1 text-xs text-[#8a8a8a]">{p.credits.toLocaleString('en-US')} {t('pricing.credits')}</div>
                <p className="mt-3 text-xs text-[#b0b0b0]">{t(p.description_key)}</p>
                <button disabled className="mt-auto pt-4 w-full">
                  <span className="block w-full py-2 rounded-lg bg-[#1a1a1a] border border-[#262626] text-[#666666] text-sm font-semibold cursor-not-allowed">
                    {t('pricing.buy_credits')} · {t('pricing.coming_soon')}
                  </span>
                </button>
              </div>
            );
          })}
        </div>

        {/* How Credits Work — v1 官方规则 */}
        <div className="mt-12">
          <h2 className="text-xl font-bold mb-2">{t('pricing.how_credits_work')}</h2>
          <p className="text-sm text-[#8a8a8a] mb-4">{t('pricing.how_credits_work_desc')}</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="rounded-xl bg-[#141414] border border-[#1f1f1f] p-4">
              <div className="text-sm font-medium text-[#e0e0e0]">{CREATION_COST_CREDITS} {t('pricing.credits')}</div>
              <div className="mt-1 text-xs text-[#8a8a8a]">{t('pricing.cost_one_creation')}</div>
            </div>
            <div className="rounded-xl bg-[#141414] border border-[#1f1f1f] p-4">
              <div className="text-sm font-medium text-[#e0e0e0]">{t('pricing.cost_failed_free')}</div>
              <div className="mt-1 text-xs text-[#8a8a8a]">{t('pricing.cost_failed_free_desc')}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default PricingPage;
