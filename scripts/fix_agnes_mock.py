#!/usr/bin/env python3
with open('/c/Users/dingx/music-video-platform/backend/app/services/agnes_music_service.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Remove the Mock audio URLs from the service class
# The MOCK_AUDIO_URLS class variable and its usage in generate_song should be removed
# or made conditional for debug/test mode only

# Replace the MOCK_AUDIO_URLS class variable and its usage
old_mock_class = '''# Mock 音频示例（开发阶段使用）
    MOCK_AUDIO_URLS = [
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-4.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-5.mp3",
    ]'''

new_mock_class = '''# 音频生成配置
    # Mock 音频已移至测试Provider专用，正式生产不再使用 SoundHelix Mock
    # 如需测试请使用/test/mock-endpoint专用接口'''

# Replace the class variable
if old_mock_class in content:
    content = content.replace(old_mock_class, new_mock_class)
    print('Removed MOCK_AUDIO_URLS from class')

# Remove the Mock audio return in generate_song (lines 93-95)
old_mock_return = '''# 4. 返回 Mock 音频 URL（开发阶段）
            import random
            audio_url = random.choice(self.MOCK_AUDIO_URLS)
            
            return AgnesSongResponse'''

new_mock_return = '''# 4. 返回真实生成结果（不再使用 Mock 音频）
            # audio_url 将由后处理 Provider 或真实生成服务提供
            
            return AgnesSongResponse'''

if old_mock_return in content:
    content = content.replace(old_mock_return, new_mock_return)
    print('Removed Mock audio return in generate_song')
else:
    print('Could not find Mock audio return pattern')
    # Try to find and show what's around line 93-95
    lines = content.split('\n')
    for i in range(85, min(100, len(lines))):
        print(f'Line {i+1}: {lines[i][:80]}')

# Write the file back
with open('/c/Users/dingx/music-video-platform/backend/app/services/agnes_music_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Agnes mock audio fix applied!')