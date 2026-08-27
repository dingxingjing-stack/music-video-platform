#!/usr/bin/env python3
with open('/c/Users/dingx/music-video-platform/backend/app/routers/ai_music.py', 'r', encoding='utf-8', errors='ignore') as f:
    data = f.read()

# Fix 1: Replace the MockProvider to not return SoundHelix URLs in production
# The current MockProvider returns https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3
# We'll change it to return None or a development-only indicator

old_mock_provider = '''# Mock Provider
        class MockProvider:
            @property
            def name(self): return "mock"
            @property
            def provider_type(self): return "mock"
            @property
            def capabilities(self): return ["text_to_music", "mock"]
            @property
            def max_duration(self): return 300
            async def generate(self, request: Dict[str, Any]) -> Dict[str, Any]:
                import random
                return {"success": True, "audio_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3", "duration": 30}
            async def health_check(self) -> Dict[str, Any]:
                return {"healthy": True, "provider": "mock"}
            _provider_registry.register(MockProvider())'''

new_mock_provider = '''# Mock Provider (development/testing only)
        # Production systems should not use Mock audio - use real providers instead
        class MockProvider:
            @property
            def name(self): return "mock"
            @property
            def provider_type(self): return "mock"
            @property
            def capabilities(self): return ["text_to_music", "mock"]
            @property
            def max_duration(self): return 300
            async def generate(self, request: Dict[str, Any]) -> Dict[str, Any]:
                # Return None to indicate no audio available - caller should fall back to other providers
                return {"success": False, "error": "Mock audio disabled in production - use real provider"}
            async def health_check(self) -> Dict[str, Any]:
                return {"healthy": True, "provider": "mock"}
            _provider_registry.register(MockProvider())'''

if old_mock_provider in data:
    data = data.replace(old_mock_provider, new_mock_provider)
    print('Fixed MockProvider to disable Mock audio in production')
else:
    print('Could not find MockProvider pattern')

# Fix 2: Remove "mock" from fallback chains (make them conditional or remove mock from them)
# The fallback chains currently include "mock" as a last resort
# We'll change them to exclude mock from production fallback

old_fallback_patterns = [
    '_provider_registry.set_fallback_chain("heartmula", ["ace_step", "hf_ace_step", "mock"])',
    '_provider_registry.set_fallback_chain("ace_step", ["hf_ace_step", "mock"])',
    '_provider_registry.set_fallback_chain("hf_ace_step", ["mock"])',
]

new_fallback_patterns = [
    '# Provider fallback chains (production: heartmula -> ace_step -> hf_ace_step)',
    '_provider_registry.set_fallback_chain("heartmula", ["ace_step", "hf_ace_step"])',
    '_provider_registry.set_fallback_chain("ace_step", ["hf_ace_step"])',
    '_provider_registry.set_fallback_chain("hf_ace_step", [])',
]

# Apply fallback fixes
for old, new in zip(old_fallback_patterns, new_fallback_patterns):
    if old in data:
        data = data.replace(old, new)
        print(f'Fixed fallback chain: {old[:50]}... -> {new[:50]}...')
    else:
        print(f'Pattern not found: {old[:30]}...')

# Write the file back
with open('/c/Users/dingx/music-video-platform/backend/app/routers/ai_music.py', 'w', encoding='utf-8') as f:
    f.write(data)

print('Mock audio fix applied to ai_music.py!')