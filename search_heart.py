import os

for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ['node_modules', '.git', '__pycache__', '.next', 'dist', 'build', '.pytest_cache', '.ruff_cache']]
    for f in files:
        if f.endswith('.py'):
            full = os.path.join(root, f)
            try:
                with open(full, 'r', encoding='utf-8', errors='ignore') as fh:
                    content = fh.read()
                    if 'heartmula' in content.lower() or 'heartcodec' in content.lower():
                        rel = os.path.relpath(full, '.')
                        print(rel)
            except Exception:
                pass