/**
 * Gemini prompt enhancer — uses /api/v1/mv/gemini/generate to
 * expand a short user prompt into a professional music generation prompt.
 */

export async function enhancePrompt(rawPrompt: string): Promise<string> {
  if (!rawPrompt || rawPrompt.trim().length < 3) return rawPrompt;

  const enhancerInstruction = `You are a professional music producer. Expand the following user idea into a detailed music generation prompt. Include: genre, tempo (BPM), mood, instruments, and production style. Output ONLY the expanded prompt — no explanations, no markdown.

User idea: "${rawPrompt}"`;

  try {
    const resp = await fetch('/api/v1/mv/gemini/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: enhancerInstruction }),
    });

    if (!resp.ok) {
      console.warn('Prompt enhancement failed, using original');
      return rawPrompt;
    }

    const data = await resp.json();
    const text = data?.candidates?.[0]?.content?.parts?.[0]?.text;
    return text?.trim() || rawPrompt;
  } catch {
    console.warn('Prompt enhancement network error, using original');
    return rawPrompt;
  }
}