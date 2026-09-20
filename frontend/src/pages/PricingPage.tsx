import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from '../i18n/useTranslation';
import { api } from '../config/api';
import { authFetchOptional, AuthenticationError } from '../api/http';
import { openPackCheckout, type PaddlePack, type PacksResponse } from '../lib/paddle';

/** 会员计划（一次性补充包见 /packs；两者共用同一套后端建单 + Paddle.js 流程） */
export interface MembershipPlan {
  id: string;
  name: string;
  price_usd: number;
  currency: string;
  credits_per_month: number;
  interval: string;
  recurring: boolean;
}

interface PlansResponse {
  currency: string;
  interval: string;
  recurring: boolean;
  paddle_configured: boolean;
  paddle_env: string | null;
  client_token: string | null;
  plans: MembershipPlan[];
}

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
  const [packs, setPacks] = useState<PacksResponse | null>(null);
  const [plans, setPlans] = useState<PlansResponse | null>(null);
  const [planOfRecord, setPlanOfRecord] = useState<{ plan_id: string; current_period_end: string | null } | null>(null);
  const [busyPack, setBusyPack] = useState<string | null>(null);
  const [packNotice, setPackNotice] = useState<string | null>(null);

  const refreshAccount = useCallback(async () => {
    try {
      const bal = await authFetchOptional<{ balance: number }>(`${api.base}/api/v1/credits/balance`);
      setBalance(typeof bal.balance === 'number' ? bal.balance : null);
    } catch {
      setBalance(null);
    }
    try {
      const res = await authFetchOptional<{ membership: { plan_id: string; current_period_end: string | null } | null }>(
        `${api.base}/api/v1/credits/membership`);
      setPlanOfRecord(res?.membership ? { plan_id: res.membership.plan_id,
                                            current_period_end: res.membership.current_period_end } : null);
    } catch {
      setPlanOfRecord(null);
    }
  }, []);

  useEffect(() => {
    refreshAccount();
    (async () => {
      try {
        const [packsResp, plansResp] = await Promise.all([
          authFetchOptional<PacksResponse>(`${api.base}/api/v1/credits/packs`),
          authFetchOptional<PlansResponse>(`${api.base}/api/v1/credits/plans`),
        ]);
        setPacks(packsResp);
        setPlans(plansResp);
      } catch {
        setPacks(null);     // 拉不到就不显示补充包区块，也绝不做可点的假按钮
        setPlans(null);
      }
    })();
  }, [refreshAccount]);

  // 购买积分补充包 / 订阅会员：后端建单 → Paddle.js 打开收银台 → 支付成功回调只负责刷新显示。
  // 真正的 Credits 与会员等级都发生在后端 webhook（前端任何回调都不入账）。
  const openCheckout = async (
    body: { pack_id?: string; plan_id?: string },
    key: string,
    setBusy: (v: string | null) => void,
  ) => {
    const config = body.pack_id ? packs : plans;
    if (!config?.paddle_configured) return;
    setBusy(key);
    setPackNotice(null);
    try {
      const order = await authFetchOptional<{ transaction_id: string }>(
        `${api.base}/api/v1/credits/checkout`,
        { method: 'POST', body },
      );
      const opened = await openPackCheckout({
        transactionId: order.transaction_id,
        clientToken: config.client_token || '',
        environment: config.paddle_env,
        onCompleted: () => { refreshAccount(); },
      });
      if (!opened) setPackNotice(t('pricing.packs_unavailable'));
    } catch (err) {
      setPackNotice(err instanceof AuthenticationError ? t('pricing.packs_login_required') : t('pricing.packs_error'));
    } finally {
      setBusy(null);
    }
  };

  const buyPack = (pack: PaddlePack) => openCheckout({ pack_id: pack.id }, pack.id, setBusyPack);
  const buyPlan = (plan: MembershipPlan) => openCheckout({ plan_id: plan.id }, plan.id, setBusyPack);

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
                {(() => {
                  const plan = plans?.plans.find((x) => x.id === p.id);
                  if (!plan || !plans?.paddle_configured) {
                    // 后端未配置该 Recurring Price → 保持原有 disabled + Coming Soon
                    return (
                      <button disabled className="mt-auto pt-4 w-full">
                        <span className="block w-full py-2 rounded-lg bg-[#1a1a1a] border border-[#262626] text-[#666666] text-sm font-semibold cursor-not-allowed">
                          {t('pricing.buy_credits')} · {t('pricing.coming_soon')}
                        </span>
                      </button>
                    );
                  }
                  const isCurrent = planOfRecord?.plan_id === plan.id;
                  return (
                    <button onClick={() => buyPlan(plan)} disabled={busyPack !== null} className="mt-auto pt-4 w-full">
                      <span className="block w-full py-2 rounded-lg bg-orange-400 text-black text-sm font-semibold hover:bg-orange-300 disabled:opacity-60 disabled:cursor-not-allowed">
                        {busyPack === plan.id
                          ? t('pricing.packs_busy')
                          : isCurrent
                            ? t('pricing.plan_current')
                            : `${t('pricing.plan_subscribe')} $${plan.price_usd.toFixed(2)}${t('pricing.plan_per_month')}`}
                      </span>
                    </button>
                  );
                })()}
              </div>
            );
          })}
        </div>

        {plans?.plans.length ? (
          <p className="mt-3 text-xs text-[#666666]">{t('pricing.plan_recurring_note')}</p>
        ) : null}

        {/* 积分补充包（一次性购买）：后端未配置 Price ID 时整块不渲染，绝不出现假按钮 */}
        {packs && packs.packs.length > 0 && (
          <div className="mt-12">
            <h2 className="text-xl font-bold mb-1">{t('pricing.packs_title')}</h2>
            <p className="text-sm text-[#8a8a8a] mb-4">{t('pricing.packs_subtitle')}</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {packs.packs.map((p) => (
                <div key={p.id} className="rounded-xl bg-[#141414] border border-[#1f1f1f] p-5 flex flex-col">
                  <div className="text-lg font-black">{p.credits.toLocaleString('en-US')}</div>
                  <div className="text-xs text-[#8a8a8a]">
                    {t('pricing.credits')} · {t('pricing.packs_one_time')}
                  </div>
                  <div className="mt-2 text-sm font-semibold text-orange-400">${p.price_usd.toFixed(2)}</div>
                  <button
                    onClick={() => buyPack(p)}
                    disabled={!packs.paddle_configured || busyPack !== null}
                    className="mt-4 w-full py-2 rounded-lg text-sm font-semibold bg-orange-400 text-black hover:bg-orange-300 disabled:bg-[#1a1a1a] disabled:text-[#666666] disabled:border disabled:border-[#262626] disabled:cursor-not-allowed"
                  >
                    {busyPack === p.id ? t('pricing.packs_busy') : t('pricing.packs_buy')}
                  </button>
                </div>
              ))}
            </div>
            {!packs.paddle_configured && (
              <p className="mt-3 text-xs text-[#8a8a8a]">{t('pricing.packs_unavailable')}</p>
            )}
            {packNotice && <p className="mt-3 text-xs text-orange-300">{packNotice}</p>}
            <p className="mt-2 text-xs text-[#666666]">{t('pricing.packs_wait_note')}</p>
          </div>
        )}

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
