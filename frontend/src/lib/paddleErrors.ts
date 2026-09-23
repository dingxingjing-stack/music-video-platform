/**
 * /credits/checkout 失败 → 该显示哪条文案。
 *
 * 独立成"无 import 的纯函数"有两个原因：① PricingPage 的 catch 里先判
 * AuthenticationError，剩下的映射逻辑要能被直接单测（不拖进 supabase/http 客户端）；
 * ② 后端的 detail 就是 Paddle 的机器码，一旦把它当"未知字符串"统一压成"稍后重试"，
 * 账号级问题（Checkout 未开通）就会被误读成我们侧的偶发故障。
 */

/** 账号级前置条件：Paddle 自己没被开通，重试永远不会变好。 */
const ACCOUNT_LEVEL_CODES = new Set([
  'transaction_checkout_not_enabled',
]);

const NOTICE_KEYS = {
  checkoutNotEnabled: 'pricing.packs_checkout_not_enabled',
  generic: 'pricing.packs_error',
} as const;

/**
 * api/http.ts 的 toHttpError 把后端 detail 拼成 `HTTP <status>: <detail>`，
 * 所以这里既要能吃原始 message，也要能吃被前缀包起来的形态。
 */
export function checkoutNoticeKey(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err ?? '');
  const match = /^HTTP\s+\d{3}:\s*(.+)$/.exec(raw);
  const detail = (match ? match[1] : raw).trim();
  return ACCOUNT_LEVEL_CODES.has(detail) ? NOTICE_KEYS.checkoutNotEnabled : NOTICE_KEYS.generic;
}
