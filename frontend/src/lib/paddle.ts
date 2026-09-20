// Paddle.js v2 封装 —— 只用于"积分补充包"的一次性 Checkout。
//
// 事实来源：
//   · 商品列表与积分数量 = 后端 GET /api/v1/credits/packs（客户端不写价格、不写积分）
//   · 交易由后端 POST /api/v1/credits/checkout 用服务端 API Key 建单
//   · Credits 由后端 Paddle webhook 验签后发放；本文件只负责"打开收银台 + 通知刷新"
//
// 会员订阅（recurring）不走这里，本文件不产生任何订阅。
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
}): Promise<boolean> {
  const { transactionId, clientToken, environment, onCompleted } = options;
  if (!clientToken || !transactionId) return false;

  const Paddle = await loadPaddle();
  if (!Paddle) return false;

  const env: 'sandbox' | 'production' = environment === 'sandbox' ? 'sandbox' : 'production';
  const initKey = `${env}:${clientToken}`;
  if (initializedKey !== initKey) {
    Paddle.Environment?.set(env);
    Paddle.Initialize({ token: clientToken });
    initializedKey = initKey;
    Paddle.on?.('checkout.completed', (event: Event) => {
      const detail = (event as CustomEvent)?.detail as { name?: string } | undefined;
      if (detail?.name === 'transaction.completed') onCompleted?.();
    });
  }

  Paddle.Checkout.open({ transactionId });
  return true;
}
