#!/usr/bin/env python3
import os

path = '/c/Users/dingx/music-video-platform/backend/app/services/agnes_music_service.py'
print(f'File exists: {os.path.exists(path)}')
print(f'Absolute path: {os.path.abspath(path)}')

if os.path.exists(path):
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    print(f'MOCK_AUDIO_URLS in file: {"MOCK_AUDIO_URLS" in content}')
    print(f'SoundHelix in file: {"SoundHelix" in content}')
    print(f'random.choice in file: {"random.choice" in content}')
    print(f'"# 4. 返回 Mock 音频 URL" in file: {"# 4. 返回 Mock 音频 URL" in content}')
    
    # Show lines around MOCK_AUDIO_URLS
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'MOCK_AUDIO_URLS' in line or 'Mock 音频' in line:
            print(f'  Line {i+1}: {line[:120]}')