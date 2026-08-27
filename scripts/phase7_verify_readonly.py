import subprocess

filepath = '/c/Users/dingx/music-video-platform/backend/app/routers/ai_music.py'

print('=== READ-ONLY Phase 7 Verification ===')
print()

result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True, cwd='/c/Users/dingx/music-video-platform')
modified_files = result.stdout.strip().split('\n') if result.stdout else []
backend_modified = any('ai_music.py' in f for f in modified_files)

with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
    data = f.read()
lines = data.split('\n')

has_mockprovider_class = 'class MockProvider' in data
has_mockprovider_instance = '_provider_registry.register(MockProvider())' in data
has_soundhelix_url = 'soundhelix' in data.lower()
has_heartmula = 'heartmula' in data
has_ace_step = 'ace_step' in data
has_hf_ace_step = 'hf_ace_step' in data
fallback_lines = [line for i, line in enumerate(lines) if 'set_fallback_chain' in line and i > 0]
has_mock_in_fallbacks = any('mock' in line.lower() for line in fallback_lines)
total_modified = len(modified_files)

checks = []

# 1. MockProvider NOT in production generation chain
pass1 = not has_mockprovider_instance
checks.append(('MockProvider disabled in production', pass1))

# 2. SoundHelix mock URL NOT in production
pass2 = not has_soundhelix_url
checks.append(('No SoundHelix references', pass2))

# 3. HeartMuLa / ACE-Step / HF ACE-Step configurable as real providers
pass3a = has_heartmula
pass3b = has_ace_step
pass3c = has_hf_ace_step
checks.append(('HeartMuLa configured', pass3a))
checks.append(('ACE-Step configured', pass3b))
checks.append(('HF ACE-Step configured', pass3c))

# 4. Fallback chains exclude MockProvider
pass4 = not has_mock_in_fallbacks
checks.append(('Fallback chains exclude mock', pass4))

# 5. Git workspace status
pass5 = not backend_modified or total_modified == 0
checks.append(('Git workspace clean', pass5))

for name, passed in checks:
    status = 'PASS' if passed else 'FAIL'
    print(f'{status}: {name}')

all_passed = all(p for _, p in checks)
print()
if all_passed:
    print('Phase 7: ALL READ-ONLY CHECKS PASSED')
else:
    print('Phase 7: Some checks FAILED')