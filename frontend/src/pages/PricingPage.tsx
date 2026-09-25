import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from '../i18n/useTranslation';
import { api } from '../config/api';
import { authFetchOptional, AuthenticationError } from '../api/http';
import { openPackCheckout, type PaddlePack, type PacksResponse } from '../lib/paddle';
import { checkoutNoticeKey } from '../lib/paddleErrors';
import { fetchLemonSqueezyStatus, openLemonSqueezyCheckout } from '../lib/lemonSqueezy';

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

/**
 * 目录接口取不到时的兜底展示数据（与后端 /credits/packs 当前的 4 档完全一致）。
 * 只用于"让用户看得见有哪些档、并能点重试"——按钮保持 disabled，
 * 绝不因为兜底就造出可点的付款按钮。
 */
const FALLBACK_PACKS: PaddlePack[] = [
  { id: 'credits_200', credits: 200, price_usd: 4.99, price_cents: 499, currency: 'USD', recurring: false },
  { id: 'credits_500', credits: 500, price_usd: 9.99, price_cents: 999, currency: 'USD', recurring: false },
  { id: 'credits_1200', credits: 1200, price_usd: 19.99, price_cents: 1999, currency: 'USD', recurring: false },
  { id: 'credits_2800', credits: 2800, price_usd: 39.99, price_cents: 3999, currency: 'USD', recurring: false },
];

export function PricingPage() {
  const { t } = useTranslation();
  const [balance, setBalance] = useState<number | null>(null);
  const [packs, setPacks] = useState<PacksResponse | null>(null);
  const [plans, setPlans] = useState<PlansResponse | null>(null);
  const [planOfRecord, setPlanOfRecord] = useState<{ plan_id: string; current_period_end: string | null } | null>(null);
  const [busyPack, setBusyPack] = useState<string | null>(null);
  const [packNotice, setPackNotice] = useState<string | null>(null);
  // 目录是否"取失败了"（区别于"取到了但后端没配这档 Price"）：
  // 失败时界面必须给重试入口，不能退化成"即将上线"，也不能整块消失。
  const [plansFailed, setPlansFailed] = useState(false);
  const [packsFailed, setPacksFailed] = useState(false);
  const [catalogRetrying, setCatalogRetrying] = useState(false);
  // Lemon Squeezy 路由表：只有后端配好某条目 Variant 时才接管该条目的购买，
  // 其余情况（含未配置、探测失败）一律保持现有 Paddle 行为。
  const [lsRoute, setLsRoute] = useState<{ enabled: boolean; items: string[] }>({ enabled: false, items: [] });

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

  // 两个目录并行 + 各自隔离：任一个接口失败或慢都不能拖住另一个，否则用户看到的是
  // "整页没有付款按钮"，而真实原因只是一个接口在等待。
  const loadCatalog = useCallback(async () => {
    setCatalogRetrying(true);
    try {
      const [p, l] = await Promise.allSettled([
        authFetchOptional<PacksResponse>(`${api.base}/api/v1/credits/packs`),
        authFetchOptional<PlansResponse>(`${api.base}/api/v1/credits/plans`),
      ]);
      // fulfilled 才用数据；rejected 置 null 并记住"这是请求失败"，
      // 界面据此给重试入口，而不是把正常套餐降级成"即将上线"或整块隐藏。
      setPacks(p.status === 'fulfilled' ? p.value : null);
      setPlans(l.status === 'fulfilled' ? l.value : null);
      setPacksFailed(p.status === 'rejected');
      setPlansFailed(l.status === 'rejected');
    } finally {
      setCatalogRetrying(false);
    }
  }, []);

  useEffect(() => {
    refreshAccount();
    loadCatalog();
    fetchLemonSqueezyStatus().then(setLsRoute);
  }, [refreshAccount, loadCatalog]);

  const retryCatalog = () => {
    setPackNotice(null);
    refreshAccount();
    loadCatalog();
  };

  // 购买积分补充包 / 订阅会员：后端建单 → Paddle.js 打开收银台 → 支付成功回调只负责刷新显示。
  // 真正的 Credits 与会员等级都发生在后端 webhook（前端任何回调都不入账）。
  const openCheckout = async (
    body: { pack_id?: string; plan_id?: string },
    key: string,
    setBusy: (v: string | null) => void,
  ) => {
    const config = body.pack_id ? packs : plans;
    const itemId = (body.pack_id || body.plan_id || '');
    if (lsRoute.enabled && lsRoute.items.includes(itemId)) {
      // 该条目由 Lemon Squeezy 承接：后端建单 → 跳转 Hosted Checkout。
      // 放在 paddle_configured 闸门之前，否则 LS-only 配置会被误判成"未开放"。
      setBusy(key);
      setPackNotice(null);
      try {
        const opened = await openLemonSqueezyCheckout(body);
        if (!opened) setPackNotice(t('pricing.packs_unavailable'));
      } catch (err) {
        setPackNotice(err instanceof AuthenticationError
          ? t('pricing.packs_login_required')
          : t(checkoutNoticeKey(err)));
      } finally {
        setBusy(null);
      }
      return;
    }
    if (!config?.paddle_configured) {
      // 到这里说明后端没配齐该档 Price：必须给出可见原因，不能静默 return（点一下没反应最难排查）。
      setPackNotice(t('pricing.packs_unavailable'));
      return;
    }
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
        // 收银台关闭后再刷一次：Paddle 的 webhook 是异步的，成交后立刻读余额可能还是旧值，
        // 而"关掉了"是确定的时机，多刷一次成本极低、也不会改动任何数字。
        onClosed: () => { refreshAccount(); },
      });
      if (!opened) setPackNotice(t('pricing.packs_unavailable'));
    } catch (err) {
      // 后端会把 Paddle 的机器码原样回传（如 503 transaction_checkout_not_enabled）。
      // 这类账号级故障一律显示"稍后重试"就是在骗用户，也会让人去查我们这边的代码。
      setPackNotice(err instanceof AuthenticationError
        ? t('pricing.packs_login_required')
        : t(checkoutNoticeKey(err)));
    } finally {
      setBusy(null);
    }
  };

  const buyPack = (pack: PaddlePack) => openCheckout({ pack_id: pack.id }, pack.id, setBusyPack);
  const buyPlan = (plan: MembershipPlan) => openCheckout({ plan_id: plan.id }, plan.id, setBusyPack);

  const badgeLabel = (badge: string | null) =>
    badge === 'best_value' ? t('pricing.best_value') : null;

  // 补充包区块的数据源：接口成功用接口，接口失败用同档位的兜底数据（按钮仍是禁用的），
  // 这样"购买更多 Credits"不会因为一次请求失败就整块消失。
  const packList: PaddlePack[] = packs?.packs?.length
    ? packs.packs
    : (packsFailed ? FALLBACK_PACKS : []);
  const packsConfigured = packs?.paddle_configured ?? false;

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
                  if (!plan && plansFailed) {
                    // 目录请求失败 ≠ 这档套餐没上线 —— 给重试，绝不降级成"即将上线"
                    return (
                      <button onClick={retryCatalog} disabled={catalogRetrying} className="mt-auto pt-4 w-full">
                        <span className="block w-full py-2 rounded-lg bg-[#1a1a1a] border border-[#262626] text-[#b0b0b0] text-sm font-semibold hover:text-white disabled:opacity-60">
                          {t('myCreations.retry')}
                        </span>
                      </button>
                    );
                  }
                  if (!plan || !plans?.paddle_configured) {
                    // 后端确实没配这档 Recurring Price → 保持原有 disabled + Coming Soon
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

        {/* 购买结果提示：放在页面级，套餐区与补充包区共用。
            此前它只渲染在补充包区块内部，点击套餐失败（未登录 / 建单 502）时用户看不到任何反馈。 */}
        {packNotice && (
          <p className="mt-4 text-sm text-orange-300" role="status">{packNotice}</p>
        )}

        {/* 积分补充包（一次性购买）：接口失败时仍按同档位展示 + 重试，按钮保持禁用；
            只有后端真的没配 Price ID 才提示不可用。绝不出现可点的假按钮。 */}
        {packList.length > 0 && (
          <div className="mt-12">
            <h2 className="text-xl font-bold mb-1">{t('pricing.packs_title')}</h2>
            <p className="text-sm text-[#8a8a8a] mb-4">{t('pricing.packs_subtitle')}</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {packList.map((p) => (
                <div key={p.id} className="rounded-xl bg-[#141414] border border-[#1f1f1f] p-5 flex flex-col">
                  <div className="text-lg font-black">{p.credits.toLocaleString('en-US')}</div>
                  <div className="text-xs text-[#8a8a8a]">
                    {t('pricing.credits')} · {t('pricing.packs_one_time')}
                  </div>
                  <div className="mt-2 text-sm font-semibold text-orange-400">${p.price_usd.toFixed(2)}</div>
                  <button
                    onClick={() => buyPack(p)}
                    disabled={!packsConfigured || busyPack !== null}
                    className="mt-4 w-full py-2 rounded-lg text-sm font-semibold bg-orange-400 text-black hover:bg-orange-300 disabled:bg-[#1a1a1a] disabled:text-[#666666] disabled:border disabled:border-[#262626] disabled:cursor-not-allowed"
                  >
                    {busyPack === p.id ? t('pricing.packs_busy') : t('pricing.packs_buy')}
                  </button>
                </div>
              ))}
            </div>
            {packsFailed ? (
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <p className="text-xs text-orange-300" role="status">{t('pricing.packs_error')}</p>
                <button
                  onClick={retryCatalog}
                  disabled={catalogRetrying}
                  className="px-3 py-1 rounded-lg bg-[#1a1a1a] border border-[#262626] text-[#e0e0e0] text-xs font-semibold hover:bg-[#222222] disabled:opacity-60"
                >
                  {t('myCreations.retry')}
                </button>
              </div>
            ) : !packsConfigured && (
              <p className="mt-3 text-xs text-[#8a8a8a]">{t('pricing.packs_unavailable')}</p>
            )}
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

        {/* 购买条款与政策入口：支付服务商审核要求用户在付款前能直接读到条款、隐私与退款政策 */}
        <div className="mt-12 border-t border-[#1f1f1f] pt-6 pb-2 text-center">
          <p className="text-xs text-[#8a8a8a] leading-relaxed max-w-[720px] mx-auto">{t('pricing.legal_notice')}</p>
          <div className="mt-3 flex flex-wrap justify-center gap-x-5 gap-y-2 text-xs text-[#6a6a6a]">
            <a href="/legal/terms" className="hover:text-white underline-offset-2 hover:underline">{t('legal.links.terms')}</a>
            <a href="/legal/privacy" className="hover:text-white underline-offset-2 hover:underline">{t('legal.links.privacy')}</a>
            <a href="/legal/credits-refund" className="hover:text-white underline-offset-2 hover:underline">{t('legal.links.creditsRefund')}</a>
            <a href={`mailto:${t('legal.privacy.contactEmail')}`} className="hover:text-white underline-offset-2 hover:underline">{t('legal.links.contact')}</a>
          </div>
        </div>
      </div>
    </div>
  );
}

export default PricingPage;
