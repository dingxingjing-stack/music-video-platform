/**
 * Prompt enhancer — 把简短的原始想法扩展成专业的音乐生成 prompt。
 *
 * 对接现有后端「音质/Prompt 增强」端点（app/routers/audio_quality.py）：
 *   POST /api/v1/audio/enhance-prompt
 *   请求: { user_prompt, style?, template? }
 *   响应: { original, enhanced, improvements[] }
 *
 * 说明：原实现调用的是已废弃的 /api/v1/mv/gemini/generate（MV 路由已下线），
 * 现改接到仍可用的通用 prompt 增强端点，功能不变（生歌前扩展 prompt 用）。
 */
export async function enhancePrompt(rawPrompt: string): Promise<string> {
  if (!rawPrompt || rawPrompt.trim().length < 3) return rawPrompt;

  try {
    const resp = await fetch('/api/v1/audio/enhance-prompt', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_prompt: rawPrompt }),
    });

    if (!resp.ok) {
      console.warn('Prompt enhancement failed, using original');
      return rawPrompt;
    }

    const data = await resp.json();
    const enhanced = data?.enhanced;
    return typeof enhanced === 'string' && enhanced.trim() ? enhanced.trim() : rawPrompt;
  } catch {
    console.warn('Prompt enhancement network error, using original');
    return rawPrompt;
  }
}