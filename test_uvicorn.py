import subprocess, sys, os

env = os.environ.copy()
env["PORT"] = "10000"

# Test the exact CMD from Dockerfile
cmd = [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]

print(f"Running: {' '.join(cmd)}")
result = subprocess.run(cmd, cwd=r"C:\Users\dingx\music-video-platform\backend", capture_output=True, text=True, timeout=10, env=env)
print(f"Return code: {result.returncode}")
print(f"STDOUT:\n{result.stdout}")
print(f"STDERR:\n{result.stderr}")