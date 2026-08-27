#!/usr/bin/env python3
with open('/c/Users/dingx/music-video-platform/backend/app/routers/ai_music.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# The missing function based on the original structure
new_function = '''

async def _try_hf_ace_step_fallback(prompt: str, lyrics: str, duration: int) -> Optional[str]:
    """HF ACE-Step Space 兜底：仅接受真实音频 URL，禁止 mock/假音频（SoundHelix）。"""
    if not HF_FALLBACK_ENABLED:
        return None

    hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")
    if not hf_token:
        print("[HF 兜底] 未配置 HF_TOKEN / HUGGINGFACE_TOKEN，跳过")
        return None

    try:
        api_url = "https://ace-step-ace-step.hf.space/run/predict"
        headers = {"Authorization": f"Bearer {hf_token}", "Content-Type": "application/json"}
        payload = {"data": [prompt, lyrics or "", int(duration), 0.7], "fn_index": 0}

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(api_url, headers=headers, json=payload)

        if response.status_code != 200:
            print(f"[HF 兜底] ACE-Step Space 错误: {response.status_code}")
            return None

        data = response.json()
        if not data or "data" not in data or not isinstance(data["data"], list):
            return None
        for item in data["data"]:
            url = None
            if isinstance(item, dict):
                url = item.get("url") or item.get("name")
            if url:
                return url
        return None
'''

# Append blank line and the function
new_content = content + '\n' + new_function

with open('/c/Users/dingx/music-video-platform/backend/app/routers/ai_music.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print('Appended blank line and _try_hf_ace_step_fallback function!')