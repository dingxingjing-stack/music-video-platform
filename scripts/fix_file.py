#!/usr/bin/env python3
import pathlib

filepath = pathlib.Path(r'C:\Users\dingx\music-video-platform\backend\app\routers\ai_music.py')

# Read as text with utf-8, replacing any problematic chars
with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# The current structure based on analysis:
# After DOWNLOAD_FILES closing brace '}', there should be:
# - blank line
# - async def _try_hf_ace_step_fallback function

# But currently the Provider Registry code was inserted, and the function is missing.
# I need to add back the blank line and the _try_hf_ace_step_fallback function
# after the Provider Registry code.

# Find where to insert: after the get_provider_registry() function ends
# and before _try_hf_ace_step_fallback (which is missing)

# From the file structure, the _try_hf_ace_step_fallback function should come
# after the Provider Registry code. Let me find where to insert it.

# Insert the missing function after the Provider Registry code.
# The Provider Registry code ends with: print("[Provider] Registry initialized...")
# followed by: return _provider_registry

# I'll insert the blank line and the _try_hf_ace_step_fallback function.

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

# Insert the new function after the Provider Registry code
# The Provider Registry code ends with: print("[Provider] Registry initialized...")
# and then: return _provider_registry

# I need to find where "return _provider_registry" is and insert after it
if "return _provider_registry" in content:
    # Insert after "return _provider_registry"
    content = content.replace(
        "return _provider_registry",
        new_function + "return _provider_registry"
    )
    print('Inserted _try_hf_ace_step_fallback function!')
else:
    print('Could not find "return _provider_registry" to insert after')
    # Try alternative: find the Provider Registry section and insert after it
    if "# Provider Registry" in content:
        # Find the end of the Provider Registry section
        idx = content.find("# Provider Registry")
        # Find the next "return _provider_registry" after that
        after_section = content[idx:]
        if "return _provider_registry" in after_section:
            # Insert after it
            after_section = after_section.replace(
                "return _provider_registry",
                new_function + "return _provider_registry"
            )
            # Replace in original content
            full_after = content[idx:]
            content = content.replace(full_after, after_section)
            print('Inserted using alternative method')

# Write the file back
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print('Fix complete!')