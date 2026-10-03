import { test, expect, type Page } from '@playwright/test';

/**
 * P3-D-1 L3 音频文件分享 — e2e 场景测试（全部 mock，零真实后端 / 零真实平台）。
 *
 * 覆盖授权要求的场景：
 *   A 正常文件分享          B canShare 不存在        C canShare({files}) === false
 *   D 文件分享抛普通错误     E 用户取消（AbortError）  F navigator.share 不存在
 *   G URL share 也失败       H mp3 / flac / wav MIME  I 文件名 edge cases
 *
 * mock 手段（只 mock 浏览器 API 与网络，不 mock 业务代码）：
 *   - page.route 拦截分享 API 与音频文件（零后端依赖）
 *   - addInitScript 覆盖 navigator.share / canShare / clipboard（捕获调用参数）
 */

const TOKEN = 'e2etesttoken';
const AUDIO_PATH = '/mock-audio.mp3';

interface CapturedFile {
  name: string;
  type: string;
  size: number;
}
interface CapturedShare {
  title?: string;
  text?: string;
  url?: string;
  files?: CapturedFile[];
}

interface MockConfig {
  shareAvailable: boolean;
  canShareFiles: boolean | undefined; // undefined = canShare 属性不存在
  shareErrorName: string | undefined;
  /** true = 只有第一次 share() 调用抛错（模拟文件分支失败、后续分支正常） */
  throwOnce: boolean;
}

async function setupSharePage(
  page: Page,
  opts: {
    title?: string;
    audioExt?: 'mp3' | 'flac' | 'wav';
    canShareFiles?: boolean | undefined;
    shareAvailable?: boolean;
    shareErrorName?: string;
    throwOnce?: boolean;
  } = {}
): Promise<{ shareCalls: CapturedShare[]; clipboardCalls: string[] }> {
  // canShareFiles 用 'in' 检查：解构默认值会把显式传 undefined 吞成默认 true
  const canShareFiles: boolean | undefined =
    'canShareFiles' in opts ? opts.canShareFiles : true;
  const {
    title = 'Sunset Drive',
    audioExt = 'mp3',
    shareAvailable = true,
    shareErrorName,
  } = opts;
  const throwOnce = 'throwOnce' in opts ? !!opts.throwOnce : false;
  const audioUrl = `/mock-audio.${audioExt}`;
  const mime =
    audioExt === 'flac' ? 'audio/flac' : audioExt === 'wav' ? 'audio/wav' : 'audio/mpeg';

  // 分享 API：返回与后端 GET /share/{token} 相同结构的公开 payload（零 PII）
  await page.route(`**/api/v1/share/${TOKEN}`, (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        task_id: 'e2e-task-1',
        title,
        duration: 120,
        audio_url: audioUrl,
        expires_in: 600,
        brand: 'Melovar',
      }),
    })
  );
  // 音频文件：3 字节假音频（足够构造 File / Blob）
  await page.route(`**/mock-audio.${audioExt}`, (route) =>
    route.fulfill({ contentType: mime, body: Buffer.from([0x49, 0x44, 0x33]) })
  );

  // 覆盖浏览器分享 API；把 File 元数据（name/type/size）抽出便于断言
  await page.addInitScript(
    (cfg: MockConfig) => {
      const shareCalls: CapturedShare[] = [];
      const clipboardCalls: string[] = [];
      (window as unknown as Record<string, unknown>).__shareCalls = shareCalls;
      (window as unknown as Record<string, unknown>).__clipboardCalls = clipboardCalls;
      const nav = navigator as unknown as Record<string, unknown>;
      if (cfg.shareAvailable) {
        let thrown = false; // 作用域在 value 之外：跨多次调用计数（throwOnce 语义）
        Object.defineProperty(nav, 'share', {
          configurable: true,
          value: async (d?: Record<string, unknown>) => {
            shareCalls.push({
              ...(d ?? {}),
              files: Array.isArray(d?.files)
                ? (d?.files as File[]).map((f) => ({ name: f.name, type: f.type, size: f.size }))
                : undefined,
            });
            if (cfg.shareErrorName && (!cfg.throwOnce || !thrown)) {
              thrown = true;
              const e = new Error(cfg.shareErrorName);
              (e as unknown as { name: string }).name = cfg.shareErrorName;
              throw e;
            }
          },
        });
        if (cfg.canShareFiles !== undefined) {
          Object.defineProperty(nav, 'canShare', {
            configurable: true,
            value: (d?: { files?: unknown }) =>
              d?.files ? cfg.canShareFiles : true,
          });
        } else {
          // 显式抹掉 Chromium（Windows）原生的 canShare，模拟"不支持 canShare"的旧浏览器
          Object.defineProperty(nav, 'canShare', { configurable: true, value: undefined });
        }
      }
      Object.defineProperty(nav, 'clipboard', {
        configurable: true,
        value: {
          writeText: async (t: string) => {
            clipboardCalls.push(t);
          },
        },
      });
    },
    { shareAvailable, canShareFiles, shareErrorName, throwOnce } satisfies MockConfig
  );

  await page.goto(`/share/${TOKEN}`);
  // 主分享按钮（en: share.systemShare = "Share…"；zh: "系统分享"）
  await page.getByRole('button', { name: /^(Share|系统分享)/ }).first().click();
  // onSystemShare 是异步链（可能含 fetch）——等微任务队列稳定
  await page.waitForTimeout(300);

  const shareCalls = await page.evaluate(
    () => (window as unknown as Record<string, unknown>).__shareCalls as CapturedShare[]
  );
  const clipboardCalls = await page.evaluate(
    () => (window as unknown as Record<string, unknown>).__clipboardCalls as string[]
  );
  return { shareCalls, clipboardCalls };
}

test.describe('P3-D-1 L3 audio file share', () => {
  test('A: canShare(files)=true → 分享音频文件（title/text/files 齐全，share 恰好调用一次）', async ({ page }) => {
    const { shareCalls, clipboardCalls } = await setupSharePage(page, { title: 'Sunset Drive' });
    expect(shareCalls).toHaveLength(1);
    const call = shareCalls[0];
    expect(call.files).toHaveLength(1);
    expect(call.files![0]).toMatchObject({ name: 'Melovar-Sunset Drive.mp3', type: 'audio/mpeg' });
    expect(call.files![0].size).toBe(3);
    expect(call.title).toBe('Sunset Drive');
    expect(call.text).toContain('Sunset Drive');
    expect(clipboardCalls).toHaveLength(0);
  });

  test('B: navigator.canShare 不存在 → 跳过文件分享，回退 URL 分享', async ({ page }) => {
    const { shareCalls, clipboardCalls } = await setupSharePage(page, { canShareFiles: undefined });
    expect(shareCalls).toHaveLength(1);
    expect(shareCalls[0].files).toBeUndefined();
    expect(shareCalls[0].url).toContain(`/share/${TOKEN}`);
    expect(clipboardCalls).toHaveLength(0);
  });

  test('C: canShare({files}) === false → 回退 URL 分享', async ({ page }) => {
    const { shareCalls, clipboardCalls } = await setupSharePage(page, { canShareFiles: false });
    expect(shareCalls).toHaveLength(1);
    expect(shareCalls[0].files).toBeUndefined();
    expect(shareCalls[0].url).toContain(`/share/${TOKEN}`);
    expect(clipboardCalls).toHaveLength(0);
  });

  test('D: 文件分享抛普通错误 → 降级下一层（cover）成功，无 copy、无重试', async ({ page }) => {
    const { shareCalls, clipboardCalls } = await setupSharePage(page, { shareErrorName: 'TypeError', throwOnce: true });
    // 降级链逐层尝试：[0] 音频（抛错）→ [1] 封面（成功）→ 结束（URL 层不必再试）
    expect(shareCalls).toHaveLength(2);
    expect(shareCalls[0].files![0].type).toBe('audio/mpeg');
    expect(shareCalls[1].files![0].type).toBe('image/png');
    expect(clipboardCalls).toHaveLength(0);
  });

  test('E: 用户取消（AbortError）→ 静默返回：不弹错、不降级、不复制、不再分享', async ({ page }) => {
    const { shareCalls, clipboardCalls } = await setupSharePage(page, { shareErrorName: 'AbortError' });
    expect(shareCalls).toHaveLength(1); // 只尝试一次
    expect(shareCalls[0].files).toHaveLength(1);
    expect(clipboardCalls).toHaveLength(0); // 未自动复制
  });

  test('F: navigator.share 不存在 → Copy Link 兜底', async ({ page }) => {
    const { shareCalls, clipboardCalls } = await setupSharePage(page, { shareAvailable: false });
    expect(shareCalls).toHaveLength(0);
    expect(clipboardCalls).toHaveLength(1);
    expect(clipboardCalls[0]).toContain(`/share/${TOKEN}`);
  });

  test('G: 文件分享与 URL 分享均失败 → Copy Link 最终兜底（无无限重试）', async ({ page }) => {
    const { shareCalls, clipboardCalls } = await setupSharePage(page, { shareErrorName: 'DataError' });
    // audio → cover → url 三层各尝试一次，随后复制兜底
    expect(shareCalls).toHaveLength(3);
    expect(clipboardCalls).toHaveLength(1);
    expect(clipboardCalls[0]).toContain(`/share/${TOKEN}`);
  });

  for (const [ext, expectedMime] of [
    ['mp3', 'audio/mpeg'],
    ['flac', 'audio/flac'],
    ['wav', 'audio/wav'],
  ] as const) {
    test(`H: ${ext} → MIME ${expectedMime}`, async ({ page }) => {
      const { shareCalls } = await setupSharePage(page, { audioExt: ext, title: 'Format Check' });
      expect(shareCalls).toHaveLength(1);
      expect(shareCalls[0].files![0].type).toBe(expectedMime);
      expect(shareCalls[0].files![0].name).toBe(`Melovar-Format Check.${ext}`);
    });
  }

  test('I: 文件名 — 中文标题保留、无危险字符', async ({ page }) => {
    const { shareCalls } = await setupSharePage(page, { title: '日落之歌: a/b\\c*d?e"f<g>i|j' });
    const name = shareCalls[0].files![0].name;
    for (const ch of ['/', '\\', ':', '*', '?', '"', '<', '>', '|']) {
      expect(name).not.toContain(ch);
    }
    expect(name).toBe('Melovar-日落之歌 abcdefgij.mp3'); // 原串无 'h'：f<g>i|j → fgij
  });

  test('I: 文件名 — 空标题兜底 Melovar.mp3', async ({ page }) => {
    const { shareCalls } = await setupSharePage(page, { title: '' });
    expect(shareCalls[0].files![0].name).toBe('Melovar.mp3');
  });

  test('I: 文件名 — 超长标题截断到 60 字符', async ({ page }) => {
    const { shareCalls } = await setupSharePage(page, { title: 'x'.repeat(200) });
    const name = shareCalls[0].files![0].name;
    const base = name.replace(/^Melovar-/, '').replace(/\.mp3$/, '');
    expect(base.length).toBeLessThanOrEqual(60);
    expect(name).toMatch(/^Melovar-x+\.mp3$/);
  });
});
