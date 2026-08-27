import subprocess
result = subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True, text=True)
print("pip version:", result.stdout)
result2 = subprocess.run([sys.executable, "-c", "import modal; print(modal.__version__)"], capture_output=True, text=True)
print("modal:", result2.stdout)