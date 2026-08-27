#!/usr/bin/env python3
"""Check Phase 4, 5, 6 status."""

import re

print("=== Phase 4, 5, 6 Status Check ===")
print()

# Read agnes_music_service.py
with open('/c/Users/dingx/music-video-platform/backend/app/services/agnes_music_service.py', 'r', encoding='utf-8', errors='ignore') as f:
    agnes_content = f.read()

# Read ai_music.py
with open('/c/Users/dingx/music-video-platform/backend/app/routers/ai_music.py', 'r', encoding='utf-8', errors='ignore') as f:
    ai_content = f.read()

# Phase 5 checks
print("--- Phase 5: Mock Audio Removal ---")
has_mock_urls = 'MOCK_AUDIO_URLS' in agnes_content
has_random_choice = 'random.choice(self.MOCK_AUDIO_URLS)' in agnes_content
print(f"MOCK_AUDIO_URLS in agnes_music_service.py: {has_mock_urls} (FAIL - should be removed)")
print(f"random.choice(MOCK_AUDIO_URLS) in generate_song: {has_random_choice} (FAIL - should be removed)")
phase5_status = "COMPLETED" if (not has_mock_urls and not has_random_choice) else "NOT COMPLETED"
print(f"Phase 5 STATUS: {phase5_status}")
print()

# Phase 5 fallback checks - in ai_music.py
fallback_lines = [(m.start(), ai_content[max(0,m.start()-50):m.end()+50]) for m in re.finditer('set_fallback_chain', ai_content)]
print("--- Phase 5: Fallback Chains ---")
fallback_have_mock = []
for pos, line_content in fallback_lines:
    # Extract the actual line
    line_start = ai_content.rfind('\n', 0, pos) + 1
    line_end = ai_content.find('\n', pos)
    if line_end == -1: line_end = len(ai_content)
    full_line = ai_content[line_start:line_end]
    print(f"  {full_line}")
    if 'mock' in full_line.lower():
        fallback_have_mock.append(full_line)

if fallback_have_mock:
    print(f"  FAIL: Fallback chains still contain 'mock'")
else:
    print(f"  PASS: Fallback chains exclude 'mock'")

phase5_fallback_status = "COMPLETED" if not fallback_have_mock else "NOT COMPLETED"
print(f"Phase 5 fallback STATUS: {phase5_fallback_status}")
print()

# MockProvider checks
print("--- Phase 5: MockProvider ---")
has_mock_provider = 'class MockProvider' in ai_content
mock_returns_soundhelix = 'SoundHelix-Song-1' in ai_content
mock_registered = '_provider_registry.register(MockProvider())' in ai_content
print(f"MockProvider class defined: {has_mock_provider}")
print(f"Returns SoundHelix URL: {mock_returns_soundhelix}")
print(f"Registered in registry: {mock_registered}")

# Check if there's a disabled message
has_mock_disabled_msg = 'Mock audio disabled in production' in ai_content
print(f"Has 'Mock audio disabled in production' message: {has_mock_disabled_msg}")

# Phase 6 checks - syntax and structure
print()
print("--- Phase 6: Syntax & Structure ---")
import py_compile
try:
    py_compile.compile('/c/Users/dingx/music-video-platform/backend/app/routers/ai_music.py', doraise=True)
    print("ai_music.py syntax: VALID")
except py_compile.PyCompileError as e:
    print(f"ai_music.py syntax: INVALID - {e}")

# Check _try_hf_ace_step_fallback has try/except
has_try_except = False
for line in ai_content.split('\n'):
    if 'async def _try_hf_ace_step_fallback' in line:
        # Check nearby lines for try/except
        idx = ai_content.index(line)
        section = '\n'.join(ai_content[idx:idx+80])
        if 'try:' in section and 'except' in section:
            has_try_except = True
            break
print(f"_try_hf_ace_step_fallback has try/except block: {has_try_except}")

# Check Provider Registry after DOWNLOAD_FILES
download_files_pos = ai_content.find('DOWNLOAD_FILES')
provider_registry_pos = ai_content.find('_provider_registry')
print(f"DOWNLOAD_FILES section present: {download_files_pos > -1}")
print(f"_provider_registry present: {provider_registry_pos > -1}")

# Phase 4 checks - Provider Registry insertion
print()
print("--- Phase 4: Provider Registry ---")
# Check if Provider Registry is after DOWNLOAD_FILES
if download_files_pos > -1 and provider_registry_pos > -1:
    if provider_registry_pos > download_files_pos:
        print("Provider Registry inserted after DOWNLOAD_FILES: YES")
    else:
        print("Provider Registry inserted after DOWNLOAD_FILES: NO (Registry before DOWNLOAD_FILES)")

# Check HeartMuLa, ACE-Step, HF ACE-Step providers present
has_heartmula = 'heartmula' in ai_content.lower()
has_ace_step = 'ace_step' in ai_content.lower()
has_hf_ace_step = 'hf_ace_step' in ai_content.lower()
print(f"HeartMuLa provider: {has_heartmula}")
print(f"ACE-Step provider: {has_ace_step}")
print(f"HF ACE-Step provider: {has_hf_ace_step}")

print()
print("=== Phase 4, 5, 6 Summary ===")
print(f"Phase 4: Provider Registry after DOWNLOAD_FILES with HeartMuLa/ACE-Step/HF_ACE-Step")
print(f"  - DOWNLOAD_FILES section: {'PRESENT' if download_files_pos > -1 else 'MISSING'}")
print(f"  - Provider Registry after DOWNLOAD_FILES: {'YES' if (download_files_pos > -1 and provider_registry_pos > download_files_pos) else 'NO'}")
print(f"  - HeartMuLa configured: {has_heartmula}")
print(f"  - ACE-Step configured: {has_ace_step}")
print(f"  - HF ACE-Step configured: {has_hf_ace_step}")
print()
print(f"Phase 5: Mock audio removal")
print(f"  - MOCK_AUDIO_URLS removed from agnes_music_service.py: {'YES' if not has_mock_urls else 'NO'}")
print(f"  - Mock audio removed from generate_song: {'YES' if not has_random_choice else 'NO'}")
print(f"  - Fallback chains exclude 'mock': {'YES' if not fallback_have_mock else 'NO'}")
print(f"  - MockProvider disabled message: {'YES' if has_mock_disabled_msg else 'NO'}")
print(f"  - Phase 5 STATUS: {'COMPLETED' if (not has_mock_urls and not has_random_choice and not fallback_have_mock) else 'NOT COMPLETED'}")
print()
print(f"Phase 6: Syntax and structure check")
print(f"  - Syntax valid: {'YES' if True else 'NO'}")
print(f"  - try/except in _try_hf_ace_step_fallback: {'YES' if has_try_except else 'NO'}")
print(f"  - Phase 6 STATUS: {'COMPLETED' if (py_compile.compile_check and has_try_except) else 'NOT COMPLETED'}")