import subprocess, sys, os, time

env = os.environ.copy()
env["PORT"] = "10000"

# Test the exact CMD from Dockerfile - start and kill after 2 seconds
cmd = [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]

print(f"Running: {' '.join(cmd)}")
proc = subprocess.Popen(cmd, cwd=r"C:\Users\dingx\music-video-platform\backend", stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)

# Wait a bit for startup
time.sleep(3)

# Check if process is still alive (meaning uvicorn started)
if proc.poll() is None:
    print("UVICORN_STARTED=YES (process still running)")
    # Try to connect to verify
    import requests
    try:
        r = requests.get("http://localhost:10000/health", timeout=2)
        print(f"HEALTH_CHECK: {r.status_code}")
    except Exception as e:
        print(f"HEALTH_CHECK_FAILED: {e}")
    proc.terminate()
else:
    stdout, stderr = proc.communicate()
    print(f"UVICORN_STARTED=NO (exited with code {proc.returncode})")
    print(f"STDOUT:\n{stdout}")
    print(f"STDERR:\n{stderr}")