/**
 * Sentry 前端初始化（最小集成，生产专用）
 *
 * 设计原则：
 * - 仅在 production build（import.meta.env.PROD）且配置了 VITE_SENTRY_DSN 时启用
 * - 本地开发 / 未配置 DSN 时完全不初始化为空操作，不影响页面启动
 * - 不依赖任何 SDK 之外的配置：无 SentryVitePlugin / source map 上传（需要 auth token，未配置）
 * - 隐私：sendDefaultPii=false，错误的 Breadcrumb/Request 不携带用户身份信息
 */
import * as Sentry from '@sentry/react';

const dsn = import.meta.env.VITE_SENTRY_DSN as string | undefined;

if (import.meta.env.PROD && dsn) {
  try {
    Sentry.init({
      dsn,
      // 环境标识：由构建期 env 注入，默认 production
      environment: (import.meta.env.VITE_SENTRY_ENVIRONMENT as string) || 'production',
      // 性能追踪采样率 10%（与后端 traces_sample_rate=0.1 对齐，见 e4c3291）
      tracesSampleRate: 0.1,
      // 仅捕获 4xx/5xx 相关前端的运行时错误；不采样全量 transaction
      sampleRate: 1.0,
      sendDefaultPii: false,
      // 生产禁止 console 日志注入
      enableLogs: false,
      integrations: [
        // 浏览器上下文（UA、url 等）默认集成
        Sentry.browserTracingIntegration(),
      ],
      // 忽略与用户无关的常见噪音（浏览器扩展、网络中断等）
      ignoreErrors: [
        'ResizeObserver loop limit exceeded',
        'ResizeObserver loop completed with undelivered notifications',
        /Non-Error promise rejection/i,
        /Loading chunk .* failed/i,
      ],
      beforeSend(event) {
        // 脱敏兜底：移除可能携带敏感信息的请求头字段
        const headers = (event.request as { headers?: Record<string, string> } | undefined)?.headers;
        if (headers) {
          for (const key of Object.keys(headers)) {
            const lk = key.toLowerCase();
            if (lk === 'authorization' || lk === 'cookie' || lk.includes('token') || lk.includes('key')) {
              headers[key] = '[Filtered]';
            }
          }
        }
        return event;
      },
    });
  } catch {
    // Sentry 初始化失败不得阻塞应用启动
  }
}

export {};
