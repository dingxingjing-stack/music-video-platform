import os
import sys

for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ['node_modules', '.git', '__pycache__', '.next', 'dist', 'build']]
    for f in files:
        if f.endswith(('.py', '.tsx', '.ts', '.json', '.md', '.txt', '.yaml', '.yml')):
            full = os.path.join(root, f)
            rel = os.path.relpath(full, '.')
            sys.stdout.write(rel + '\n')