"""Start backend server for P0-1 verification"""
import subprocess
import sys
import time

# Start uvicorn in background
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-reload"],
    cwd=r"C:\Users\dingx\music-video-platform\backend",
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

# Wait for server to start
time.sleep(3)

# Test health endpoint
import urllib.request
import json

try:
    req = urllib.request.Request("http://localhost:8000/health")
    with urllib.request.urlopen(req, timeout=5) as resp:
        health = json.loads(resp.read().decode())
    print(f"Backend started successfully: {health.get('status')}")
    print(f"Backend PID: {proc.pid}")
except Exception as e:
    print(f"Backend failed to start: {e}")
    print(f"Stderr: {proc.stderr.read().decode()}")
    proc.terminate()