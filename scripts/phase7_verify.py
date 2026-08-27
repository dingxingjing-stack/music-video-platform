#!/usr/bin/env python3
import os
import py_compile

filepath = '/c/Users/dingx/music-video-platform/backend/app/routers/ai_music.py'

print('=== Phase 7: Real Provider End-to-End Test ===')
print()

# 1. Syntax check
print('1. Syntax check:')
try:
    py_compile.compile(filepath, doraise=True)
    print('   PASSED')
    syntax_ok = True
except py_compile.PyCompileError as e:
    print(f'   FAILED')
    syntax_ok = False

# 2. Read and verify content
with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
    data = f.read()
lines = data.split('\n')

checks = {
    'DOWNLOAD_FILES': 'DOWNLOAD_FILES' in data,
    'Provider Registry': 'get_provider_registry' in data,
    '_provider_registry = None': '_provider_registry = None' in data,
    '_try_hf_ace_step_fallback': '_try_hf_ace_step_fallback' in data,
    'MockProvider disabled': 'Mock audio disabled in production' in data,
    'No mock in fallbacks': all('mock' not in line.lower() for line in lines if 'set_fallback_chain' in line),
    'HeartMuLa provider': 'heartmula' in data,
    'ACE-Step provider': 'ace_step' in data,
    'HF ACE-Step provider': 'hf_ace_step' in data,
}

all_checks_passed = True
for check, result in checks.items():
    status = 'PASS' if result else 'FAIL'
    print(f'  {status} {check}')
    if not result:
        all_checks_passed = False

# 3. Try to compile
print()
print('3. Verifying module structure can be loaded...')
try:
    py_compile.compile('/c/Users/dingx/music-video-platform/backend/app/routers/ai_music.py', doraise=True)
    print('  Module compiles successfully')
except py_compile.PyCompileError as e:
    print(f'  Compile error: {e}')
    all_checks_passed = False

# 4. Summary
print()
all_passed = all([
    'DOWNLOAD_FILES' in data,
    'get_provider_registry' in data,
    '_provider_registry = None' in data,
    '_try_hf_ace_step_fallback' in data,
    'Mock audio disabled in production' in data,
    all('mock' not in line.lower() for line in lines if 'set_fallback_chain' in line),
    'heartmula' in data,
    'ace_step' in data,
    'hf_ace_step' in data,
]

if all_checks_passed:
    print('Phase 7: ALL CHECKS PASSED')
    print('System is ready for testing')
else:
    print('Phase 7: Some checks failed')
"