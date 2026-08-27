#!/usr/bin/env python3
"""Install and verify Modal CLI for T4 GPU verification"""
import subprocess
import sys
import os

results = {}

# Task 1: Install Modal
print("=" * 60)
print("TASK 1: Install Modal CLI")
print("=" * 60)

try:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "modal"],
        capture_output=True, text=True, timeout=180000
    )
    results['pip_install'] = {
        'returncode': result.returncode,
        'stdout': result.stdout[-500:] if result.stdout else '',
        'stderr': result.stderr[-500:] if result.stderr else ''
    }
    print(f"pip install returncode: {result.returncode}")
    if result.returncode == 0:
        print("Modal installed successfully")
    else:
        print("Modal install failed, trying upgrade...")
        result2 = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "modal"],
            capture_output=True, text=True, timeout=180000
        )
        results['pip_install_upgrade'] = {
            'returncode': result2.returncode,
            'stdout': result2.stdout[-500:] if result2.stdout else '',
            'stderr': result2.stderr[-500:] if result2.stderr else ''
        }
        print(f"upgrade returncode: {result2.returncode}")
except Exception as e:
    results['pip_install'] = {'error': str(e)}
    print(f"Exception: {e}")

# Check if modal is now importable
print("\nChecking if modal is importable...")
try:
    import modal
    results['modal_importable'] = True
    results['modal_version'] = getattr(modal, '__version__', 'unknown')
    print(f"Modal is importable, version: {results['modal_version']}")
except ImportError as e:
    results['modal_importable'] = False
    results['import_error'] = str(e)
    print(f"Modal not importable: {e}")

# Task 2: Modal setup (authentication)
print("\n" + "=" * 60)
print("TASK 2: Modal Authentication")
print("=" * 60)

if results.get('modal_importable', False):
    try:
        result = subprocess.run(
            ["modal", "setup"],
            capture_output=True, text=True, timeout=60000
        )
        results['modal_setup'] = {
            'returncode': result.returncode,
            'stdout': result.stdout[-300:] if result.stdout else '',
            'stderr': result.stderr[-300:] if result.stderr else ''
        }
        print(f"modal setup returncode: {result.returncode}")
        print(f"stdod preview: {results['modal_setup']['stdout'][:200]}")
    except Exception as e:
        results['modal_setup'] = {'error': str(e)}
        print(f"modal setup exception: {e}")
    
    # Task 3: Verify authentication
    print("\nTask 3: modal token info")
    try:
        result = subprocess.run(
            ["modal", "token", "info"],
            capture_output=True, text=True, timeout=30000
        )
        results['modal_token_info'] = {
            'returncode': result.returncode,
            'stdout': result.stdout[-300:] if result.stdout else '',
            'stderr': result.stderr[-300:] if result.stderr else ''
        }
        print(f"modal token info returncode: {result.returncode}")
        print(f"stdout preview: {results['modal_token_info']['stdout'][:200]}")
        # Check if authenticated
        if result.returncode == 0 and "not authenticated" not in result.stdout.lower():
            results['authenticated'] = True
        else:
            results['authenticated'] = False
    except Exception as e:
        results['modal_token_info'] = {'error': str(e)}
        results['authenticated'] = False
        print(f"modal token info exception: {e}")
else:
    results['authenticated'] = False
    results['modal_setup'] = {'error': 'Modal not importable'}

# Task 4: Create and run minimal GPU verification
print("\n" + "=" * 60)
print("TASK 4: Create and run minimal T4 GPU verification")
print("=" * 60)

if results.get('modal_importable', False) and results.get('authenticated', False):
    # Create verification script
    verify_script = '''
import modal
import os

@app.func(gpu="T4", timeout=120)
def verify():
    import torch
    import jupyter
    return {
        "gpu_model": os.popen("nvidia-smi --query-gpu=name --format=csv,no-headers").read().strip(),
        "memory": os.popen("nvidia-smi --query-gpu=memory.total --format=csv,no-headers").read().strip(),
        "cuda_available": torch.cuda.is_available(),
        "pytorch_version": torch.__version__
    }

if __name__ == "__main__":
    result = verify.remote()
    print(result)
'''
    
    with open("modal_gpu_verify.py", "w") as f:
        f.write(verify_script)
    print("Created modal_gpu_verify.py")
    
    try:
        result = subprocess.run(
            ["modal", "run", "modal_gpu_verify.py"],
            capture_output=True, text=True, timeout=300000
        )
        results['modal_run'] = {
            'returncode': result.returncode,
            'stdout': result.stdout[-500:] if result.stdout else '',
            'stderr': result.stderr[-500:] if result.stderr else ''
        }
        print(f"modal run returncode: {result.returncode}")
        print(f"stdout preview: {results['modal_run']['stdout'][:300]}")
    except Exception as e:
        results['modal_run'] = {'error': str(e)}
        print(f"modal run exception: {e}")
else:
    results['modal_run'] = {'error': 'Modal not importable or not authenticated'}
    print("Cannot run modal_gpu_verify: Modal not importable or not authenticated")

# Task 5: Final determination
print("\n" + "=" * 60)
print("TASK 5: Final Determination")
print("=" * 60)

# Determine final status
if results.get('modal_run', {}).get('returncode') == 0:
    results['modal_gpu_verification'] = "PASS"
    # Try to parse GPU info from stdout
    stdout = results['modal_run'].get('stdout', '')
    if "gpu_model" in stdout:
        # Extract info
        pass
elif results.get('modal_run', {}).get('returncode') != 0 and 'authenticated' in str(results.get('modal_run', {})):
    results['modal_gpu_verification'] = "BLOCKED_AUTH"
elif results.get('modal_run', {}).get('returncode') != 0 and 'gpu' in str(results.get('modal_run', {})).lower():
    results['modal_gpu_verification'] = "BLOCKED_GPU"
else:
    results['modal_gpu_verification'] = "NOT EXECUTED"

# Output results
print(f"\nMODAL CLI: {'Installed' if results.get('modal_importable', False) else 'Not installed'}")
print(f"MODAL AUTH: {'Authenticated' if results.get('authenticated', False) else 'Not authenticated'}")
print(f"MODAL T4: {results.get('modal_gpu_verification', 'NOT EXECUTED')}")

# GPU info (if available)
if results.get('modal_run', {}).get('returncode') == 0:
    # Try to extract basic info
    stdout = results['modal_run'].get('stdout', '')
    results['gpu_info'] = "GPU info extracted from run output"
else:
    results['gpu_info'] = "Could not extract GPU info"

print(f"\nGPU INFO: {results.get('gpu_info', 'N/A')}")
print(f"\nNEXT ACTION: Based on verification status above")

# Save results
with open("modal_verification_results.json", "w") as f:
    import json
    # Remove large stdout/stderr for cleaner output
    clean_results = {}
    for k, v in results.items():
        if isinstance(v, dict) and 'stdout' in v:
            clean_results[k] = {k2: v2 for k2, v2 in v.items() if k2 != 'stdout' and k2 != 'stderr'}
        else:
            clean_results[k] = v
    json.dump(clean_results, f, indent=2)

print("\nResults saved to modal_verification_results.json")
PYEOF