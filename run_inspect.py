import subprocess
import sys
import os
import re

os.chdir(r"C:\c\Users\dingx\music-video-platform")

env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONUTF8"] = "1"

result = subprocess.run(
    [sys.executable, "-m", "modal", "run", "modal_inspect_secrets.py"],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    timeout=300,
    env=env
)

output = result.stdout + result.stderr
output = re.sub(r'[\u2713\U0001f528]', '', output)
print("Return code:", result.returncode)
print("OUTPUT:")
print(output)