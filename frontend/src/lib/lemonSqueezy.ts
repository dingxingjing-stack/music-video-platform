/**
 * Lemon Squeezy 前端适配层（阶段一）。
 *
 * 只做两件事：问后端"这条链路可用吗"，以及拿 checkout_url 后跳转到 Hosted Checkout。
 * 刻意不引入 Lemon.js / overlay SDK —— LS 官方支持纯跳转式 Hosted Checkout，
 * 少一个第三方全局脚本就少一类供应链与 CSP 问题。
 *
 * 前端永远不接触 API Key、Store ID、Variant ID：那些全在后端环境变量里。
 * 这里也**不**做任何"付款成功"判定：发放只认后端 webhook（阶段一尚未实现）。
 */

import { api } from '../config/api';
import { authFetchOptional } from '../api/http';

export interface LemonSqueezyStatus {
  enabled: boolean;
  /** 已配好 Variant ID 的条目 id（如 credits_200 / starter）；不在表里的仍走 Paddle。 */
  items: string[];
}

export async function fetchLemonSqueezyStatus(): Promise<LemonSqueezyStatus> {
  try {
    const res = await authFetchOptional<LemonSqueezyStatus>(
      `${api.base}/api/v1/credits/lemonsqueezy/status`,
    );
    return { enabled: res?.enabled === true, items: Array.isArray(res?.items) ? res.items : [] };
  } catch {
    // 探测失败一律当作"不可用"：购买链路退回 Paddle，绝不因为多一个 provider
    // 而把原本能点的按钮变成死的。
    return { enabled: false, items: [] };
  }
}

/**
 * 让后端建一张 Lemon Squeezy Checkout 并跳转过去。
 * 请求体只允许 pack_id 或 plan_id —— 价格/积分数/Variant ID 由后端解析，
 * 多传字段会被后端 422 拒收（extra="forbid"）。
 */
export async function openLemonSqueezyCheckout(
  body: { pack_id?: string; plan_id?: string },
): Promise<boolean> {
  const res = await authFetchOptional<{ checkout_url?: string }>(
    `${api.base}/api/v1/credits/lemonsqueezy/checkout`,
    { method: 'POST', body },
  );
  const url = res?.checkout_url;
  if (!url) return false;
  window.location.assign(url);
  return true;
}
