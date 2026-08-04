"""Read .env, set os.environ, then start uvicorn."""
import os
import sys
import re

# Load .env into os.environ
env_path = os.path.join(os.path.dirname(__file__) or '.', '.env')
with open(env_path, encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            idx = line.index('=')
            key = line[:idx].strip()
            val = line[idx+1:].strip()
            val = val.strip('"').strip("'")
            if key and val:
                os.environ[key] = val

# Add backend/ to sys.path (equivalent to PYTHONPATH=backend)
backend_dir = os.path.join(os.path.dirname(__file__) or '.', 'backend')
if os.path.isdir(backend_dir) and backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Print key mock vars for verification
for k in ['TTS_FORCE_MOCK', 'MUSIC_FORCE_MOCK', 'VIDEO_FORCE_MOCK',
          'TTS_BACKEND_MODE', 'MUSIC_BACKEND_MODE', 'VIDEO_BACKEND_MODE',
          'WORKFLOW_MODE']:
    print(f"  {k}={os.environ.get(k, '')!r}")

print("Starting uvicorn on 0.0.0.0:8000...")
import uvicorn
uvicorn.run('backend.main:app', host='0.0.0.0', port=8000)