with open('/c/Users/dingx/music-video-platform/backend/app/routers/ai_music.py', 'r', encoding='utf-8', errors='ignore') as f:
    data = f.read()
lines = data.split('\n')

# Check production fallback chain
print('=== Production Fallback Chain ===')
for i, line in enumerate(lines):
    if 'set_fallback_chain' in line:
        for j in range(i, min(i+3, len(lines))):
            print(f'  Line {j+1}: {lines[j][:150]}')
        print()

# Check MockProvider production behavior
print('=== MockProvider Production Behavior ===')
for i, line in enumerate(lines):
    if 'Mock audio disabled' in line:
        for j in range(max(0,i-1), min(len(lines), i+2)):
            print(f'  Line {j+1}: {lines[j][:150]}')
        print()

# Check provider registry
print('=== Provider Registry ===')
for i, line in enumerate(lines):
    if 'get_provider_registry' in line or '_provider_registry' in line:
        for j in range(max(0,i-1), min(len(lines), i+2)):
            print(f'  Line {j+1}: {lines[j][:150]}')
        print()