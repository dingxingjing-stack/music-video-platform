#!/usr/bin/env python3
with open('/c/Users/dingx/music-video-platform/backend/app/routers/ai_music.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

# The try block is at lines 233-255 (1-indexed), which are indices 232-254 (0-indexed)
# But looking at the structure, the try block starts around line 233
# And the function ends at line 255 with "        return None"

# I need to add an except block before the return None

# Let me find the exact position of the try: and add except after the for loop
# The function structure should be:
# try:
#     ...
# except Exception as e:
#     ...
# return None

# First, find line 233 (1-indexed) which is lines[232] (0-indexed)
# and add the except block after the for loop (around line 253-254)

# Actually, let me just locate and fix the specific issue
for i in range(222, min(260, len(lines))):
    if i >= 230 and 'try:' in lines[i]:
        print(f'Found try: at 0-indexed {i}, 1-indexed {i+1}: {lines[i].rstrip()}')
        # The except should go after the for loop and before return None
        # Looking at the current lines 233-255:
        # 233: try:
        # 234-245: various code
        # 246-254: for item in data["data"]: ... url = ...
        # 255: return None
        
        # I need to add except Exception as e: before line 255
        # Let me insert after line 254 (which is the if url: return url line or similar)
        
# Let me take a different approach - replace the entire function body
# from the try block through the end

# Find where the function content starts and ends
# The function starts at line 223 (async def) 
# and the try block starts at line 233

# Let me replace lines 233-255 with a corrected version
# Lines 233-255 (1-indexed) = indices 232-254 (0-indexed)

# The new content for the try/except block:
new_try_except = [
    '    try:\n',
    '        api_url = "https://ace-step-ace-step.hf.space/run/predict"\n',
    '        headers = {"Authorization": f"Bearer {hf_token}", "Content-Type": "application/json"}\n',
    '        payload = {"data": [prompt, lyrics or "", int(duration), 0.7], "fn_index": 0}\n',
    '',
    '        async with httpx.AsyncClient(timeout=120.0) as client:\n',
    '            response = await client.post(api_url, headers=headers, json=payload)\n',
    '',
    '        if response.status_code != 200:\n',
    '            print(f"[HF 兜底] ACE-Step Space 错误: {response.status_code}")\n',
    '            return None\n',
    '',
    '        data = response.json()\n',
    '        if not data or "data" not in data or not isinstance(data["data"], list):\n',
    '            return None\n',
    '        for item in data["data"]:\n',
    '            url = None\n',
    '            if isinstance(item, dict):\n',
    '                url = item.get("url") or item.get("name")\n',
    '            if url:\n',
    '                return url\n',
    '    except Exception as e:\n',
    '        print(f"[HF 兜底] ACE-Step Space 错误: {e}")\n',
    '        return None\n',
]

# Replace lines 233-255 (1-indexed) = indices 232-254 (0-indexed)
# But need to check the exact range
# The function starts at line 223 (0-indexed 222)
# Lines 233-255 are indices 232-254

# Let me verify the indices
print(f'Total lines: {len(lines)}')
print(f'Lines 233-255 exist: {232 < len(lines) and 254 < len(lines)}')

# Actually, let me just find and replace the try block
# by finding the "    try:" line and replacing from there

for i in range(len(lines)):
    if '    try:' in lines[i] and i >= 220 and i <= 240:
        print(f'Found try: at 0-indexed {i}, 1-indexed {i+1}')
        # Replace from this line through line 255 (or the end of the function)
        # But I need to know where the function ends
        
# This is getting too complicated. Let me just rewrite the whole file with the correct function.
print('Taking alternative approach...')
"