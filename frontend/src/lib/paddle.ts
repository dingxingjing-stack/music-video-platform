// Paddle.js v2 封装 —— 只负责"把后端建好的交易开成收银台"。
//
// 事实来源：
//   · 商品列表与积分数量 = 后端 GET /api/v1/credits/packs 与 /credits/plans（客户端不写价格、不写积分）
//   · 交易由后端 POST /api/v1/credits/checkout 用服务端 API Key 建单（一次性包与会员订阅同一入口）
//   · Credits / 会员等级由后端 Paddle webhook 验签后发放；本文件只负责"打开收银台 + 通知刷新显示"
//
// 因此这里既服务积分补充包，也服务会员订阅：两者都只是"拿 transaction_id 开收银台"。
export interface PaddlePack {
  id: string;
  credits: number;
  price_usd: number;
  price_cents: number;
  currency: string;
  recurring: boolean;
}

export interface PacksResponse {
  currency: string;
  recurring: boolean;
  paddle_configured: boolean;
  paddle_env: string | null;
  client_token: string | null;
  packs: PaddlePack[];
}

interface PaddleCheckout {
  open(options: Record<string, unknown>): void;
}

interface PaddleGlobal {
  Environment?: { set(environment: 'sandbox' | 'production'): void };
  Initialize(options: Record<string, unknown>): void;
  Checkout: PaddleCheckout;
  on?(event: string, handler: (event: Event) => void): void;
}

declare global {
  interface Window {
    Paddle?: PaddleGlobal;
  }
}

const PADDLE_SCRIPT = 'https://cdn.paddle.com/paddle/v2/paddle.js';

let loading: Promise<PaddleGlobal | null> | null = null;
let initializedKey: string | null = null;

/**
 * 当前这次 Checkout 的回调。监听器只在第一次 Initialize 时挂一次（挂多次会让每次打开
 * 收银台都叠加一层回调），回调内容每次 open 前替换。
 */
let activeCheckout: { onCompleted?: () => void; onClosed?: () => void } = {};
let eventsBound = false;

function bindCheckoutEvents(Paddle: PaddleGlobal) {
  if (eventsBound) return;
  eventsBound = true;
  // detail.name 的取值（transaction.completed / subscription.created …）官方文档没有穷举，
  // 所以 completed 一律按"成交了，去刷新显示"处理：入账只认后端 webhook，多刷一次无害，
  // 反过来漏刷会让用户以为付款没生效。
  Paddle.on?.('checkout.completed', () => { activeCheckout.onCompleted?.(); });
  // 关掉收银台后再刷一次：既覆盖"付完就走"，也让中途放弃的用户拿回真实余额显示。
  Paddle.on?.('checkout.closed', () => {
    const cb = activeCheckout.onClosed;
    activeCheckout = {};
    cb?.();
  });
}

/** 懒加载 Paddle.js（不在 index.html 里预置第三方脚本，未购买时零开销）。 */
export function loadPaddle(): Promise<PaddleGlobal | null> {
  if (typeof window === 'undefined') return Promise.resolve(null);
  if (window.Paddle) return Promise.resolve(window.Paddle);
  if (loading) return loading;

  loading = new Promise<PaddleGlobal | null>((resolve) => {
    const script = document.createElement('script');
    script.src = PADDLE_SCRIPT;
    script.async = true;
    script.onload = () => resolve(window.Paddle ?? null);
    script.onerror = () => {
      loading = null;
      resolve(null);
    };
    document.head.appendChild(script);
  });
  return loading;
}

/**
 * 打开一次性积分包的 Checkout。
 * 返回 false 表示 Paddle.js 未能加载或未配置客户端 token（调用方据此提示失败，
 * 但绝不代表付款成功 —— 发放只认后端 webhook）。
 */
export async function openPackCheckout(options: {
  transactionId: string;
  clientToken: string;
  environment?: string | null;
  onCompleted?: () => void;
  /** 收银台被关闭（含付完款后关闭、也含中途放弃）。用它兜底刷新余额，不让 UI 停在付款前状态。 */
  onClosed?: () => void;
}): Promise<boolean> {
  const { transactionId, clientToken, environment, onCompleted, onClosed } = options;
  if (!clientToken || !transactionId) return false;

  const Paddle = await loadPaddle();
  if (!Paddle) return false;

  const env: 'sandbox' | 'production' = environment === 'sandbox' ? 'sandbox' : 'production';
  const initKey = `${env}:${clientToken}`;
  if (initializedKey !== initKey) {
    Paddle.Environment?.set(env);
    Paddle.Initialize({ token: clientToken });
    initializedKey = initKey;
    bindCheckoutEvents(Paddle);
  }

  activeCheckout = { onCompleted, onClosed };
  Paddle.Checkout.open({ transactionId });
  return true;
}
