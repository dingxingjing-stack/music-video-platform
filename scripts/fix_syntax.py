#!/usr/bin/env python3
with open('/c/Users/dingx/music-video-platform/backend/app/routers/ai_music.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

# Find the _try_hf_ace_step_fallback function and fix the try/except block
# The function starts at line 223 (1-indexed), which is lines[222] (0-indexed)
# The try block is missing its except

# Let me locate the exact lines and fix
for i in range(len(lines)):
    # Look for the try: block inside the function
    if i >= 222 and i <= 255 and '    try:' in lines[i]:
        print(f'Found try: at 0-indexed {i}, 1-indexed {i+1}')
        # The except should be added after the for loop and before return None
        # Current structure around lines 233-255:
        # 233: try:
        # 234-245: various code
        # 246-254: for item in data["data"]: ... 
        # 255: return None
        
        # I need to add except Exception as e: before line 255
        # Let me insert after line 254 (the "            if url:\n                return url\n" line)
        
        # Actually, let me find the "return None" line and add except before it
        for j in range(i, min(len(lines), i+30)):
            if 'return None' in lines[j] and j > i:
                # Insert except block before this line
                except_block = [
                    '    except Exception as e:\n',
                    '        print(f\"[HF 兜底] ACE-Step Space 错误: {e}\")\n',
                    '        return None\n',
                ]
                # Insert except_block before lines[j]
                new_lines = lines[:j] + except_block + lines[j:]
                with open('/c/Users/dingx/music-video-platform/backend/app/routers/ai_music.py', 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                print(f'Fixed syntax error by adding except block before line {j+1}')
                break
        break

# Verify the fix
with open('/c/Users/dingx/music-video-platform/backend/app/routers/ai_music.py', 'r', encoding='utf-8', errors='ignore') as f:
    check_data = f.read()
import py_compile
try:
    py_compile.compile('/c/Users/dingx/music-video-platform/backend/app/routers/ai_music.py', doraise=True)
    print('Syntax OK after fix!')
except py_compile.PyCompileError as e:
    print(f'Syntax error still present: {e}')
"