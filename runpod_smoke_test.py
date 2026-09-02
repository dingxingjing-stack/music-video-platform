import os
import requests
import time
import json

# Render endpoint for health check
RENDER_URL = "https://ai-music-backend-db6h.onrender.com"

# RunPod config (from Render environment - we'll test via direct API)
RUNPOD_ENDPOINT_ID = "xemzf8acz9v1x9"
RUNPOD_BASE = "https://api.runpod.ai/v2"

# Load API key from environment (set in Render)
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")

if not RUNPOD_API_KEY:
    print("ERROR: RUNPOD_API_KEY not set in environment")
    print("Please set RUNPOD_API_KEY in your shell before running this test")
    exit(1)

print(f"Using API Key: {RUNPOD_API_KEY[:4]}***REDACTED***")
print(f"Endpoint ID: {RUNPOD_ENDPOINT_ID}")
print()

headers = {
    "Authorization": f"Bearer {RUNPOD_API_KEY}",
    "Content-Type": "application/json"
}

# 1. Test Render health
print("=" * 50)
print("1. Testing Render Health")
print("=" * 50)
try:
    r = requests.get(f"{RENDER_URL}/health", timeout=10)
    print(f"  HTTP Status: {r.status_code}")
    print(f"  Response: {r.text}")
    RENDER_HEALTH = "PASS" if r.status_code == 200 else "FAIL"
except Exception as e:
    print(f"  Error: {e}")
    RENDER_HEALTH = "FAIL"

print()

# 2. Submit RunPod job
print("=" * 50)
print("2. Submitting RunPod Smoke Test Job")
print("=" * 50)
submit_url = f"{RUNPOD_BASE}/{RUNPOD_ENDPOINT_ID}/run"
payload = {
    "input": {
        "prompt": "smoke test",
        "duration": 10,
        "test_mode": "smoke"
    }
}

try:
    r = requests.post(submit_url, headers=headers, json=payload, timeout=30)
    print(f"  HTTP Status: {r.status_code}")
    print(f"  Response: {r.text}")
    
    if r.status_code not in (200, 201, 202):
        RUNPOD_API = "FAIL"
        RUNPOD_JOB = "FAIL"
        print(f"\nRENDER_HEALTH={RENDER_HEALTH}")
        print(f"RUNPOD_API={RUNPOD_API}")
        print(f"RUNPOD_JOB={RUNPOD_JOB}")
        print(f"WORKER_STARTED=NO")
        print(f"HANDLER=UNKNOWN")
        print(f"CUDA=UNKNOWN")
        print(f"GPU_BILLED=NO")
        exit(1)
    
    data = r.json()
    job_id = data.get("id") or data.get("request_id")
    if not job_id:
        print("  ERROR: No job_id in response")
        RUNPOD_API = "FAIL"
        RUNPOD_JOB = "FAIL"
        print(f"\nRENDER_HEALTH={RENDER_HEALTH}")
        print(f"RUNPOD_API={RUNPOD_API}")
        print(f"RUNPOD_JOB={RUNPOD_JOB}")
        print(f"WORKER_STARTED=NO")
        print(f"HANDLER=UNKNOWN")
        print(f"CUDA=UNKNOWN")
        print(f"GPU_BILLED=NO")
        exit(1)
    
    print(f"  Job ID: {job_id}")
    RUNPOD_API = "PASS"
    
except Exception as e:
    print(f"  Error: {e}")
    RUNPOD_API = "FAIL"
    RUNPOD_JOB = "FAIL"
    print(f"\nRENDER_HEALTH={RENDER_HEALTH}")
    print(f"RUNPOD_API={RUNPOD_API}")
    print(f"RUNPOD_JOB={RUNPOD_JOB}")
    print(f"WORKER_STARTED=NO")
    print(f"HANDLER=UNKNOWN")
    print(f"CUDA=UNKNOWN")
    print(f"GPU_BILLED=NO")
    exit(1)

print()

# 3. Poll for status
print("=" * 50)
print("3. Polling Job Status")
print("=" * 50)
status_url = f"{RUNPOD_BASE}/{RUNPOD_ENDPOINT_ID}/status/{job_id}"
RUNPOD_JOB = "FAIL"
WORKER_STARTED = "NO"
HANDLER = "UNKNOWN"
CUDA = "UNKNOWN"
GPU_BILLED = "NO"
FINAL_STATUS = "UNKNOWN"
output_data = None
error_data = None

deadline = time.time() + 300  # 5 min max
poll_interval = 3

while time.time() < deadline:
    try:
        r = requests.get(status_url, headers=headers, timeout=15)
        print(f"  HTTP Status: {r.status_code}")
        
        if r.status_code == 404:
            print(f"  Job not found (404)")
            break
            
        if r.status_code not in (200, 202):
            print(f"  Error response: {r.text[:500]}")
            time.sleep(poll_interval)
            continue
            
        data = r.json()
        status = data.get("status", "").upper()
        print(f"  Job Status: {status}")
        
        if "queue_position" in data and data["queue_position"] is not None:
            print(f"  Queue Position: {data['queue_position']}")
        
        if "worker_id" in data and data["worker_id"]:
            WORKER_STARTED = "YES"
            print(f"  Worker ID: {data['worker_id']}")
        
        if status in ("COMPLETED", "SUCCEEDED"):
            RUNPOD_JOB = "PASS"
            FINAL_STATUS = "COMPLETED"
            output_data = data.get("output")
            print(f"  Output: {json.dumps(output_data, indent=2)[:2000]}")
            
            # Check handler success
            if output_data and isinstance(output_data, dict):
                if output_data.get("success") is True:
                    HANDLER = "PASS"
                    # Check CUDA
                    gpu_info = output_data.get("output", {}).get("gpu_info", {})
                    if gpu_info.get("cuda_available") is True:
                        CUDA = "PASS"
                    else:
                        CUDA = "FAIL"
                else:
                    HANDLER = "FAIL"
                    error_data = output_data.get("error")
            
            GPU_BILLED = "YES"  # If completed, GPU was used
            break
            
        elif status in ("FAILED", "ERROR"):
            RUNPOD_JOB = "FAIL"
            FINAL_STATUS = "FAILED"
            error_data = data.get("output") or data.get("error") or data
            print(f"  Error: {json.dumps(error_data, indent=2)[:2000]}")
            GPU_BILLED = "YES"  # Worker likely started
            WORKER_STARTED = "YES"
            break
            
        # Still in queue or processing
        if status in ("IN_PROGRESS", "IN_QUEUE"):
            WORKER_STARTED = "YES"
        
        time.sleep(poll_interval)
        
    except Exception as e:
        print(f"  Poll error: {e}")
        time.sleep(poll_interval)

else:
    print("  TIMEOUT: Polling exceeded 300 seconds")
    FINAL_STATUS = "TIMEOUT"

print()

# Final summary
print("=" * 50)
print("FINAL RESULT")
print("=" * 50)
print(f"RENDER_HEALTH={RENDER_HEALTH}")
print(f"RUNPOD_API={RUNPOD_API}")
print(f"RUNPOD_JOB={RUNPOD_JOB}")
print(f"WORKER_STARTED={WORKER_STARTED}")
print(f"HANDLER={HANDLER}")
print(f"CUDA={CUDA}")
print(f"GPU_BILLED={GPU_BILLED}")
print()
print(f"JOB_ID={job_id}")
print(f"FINAL_STATUS={FINAL_STATUS}")

if error_data:
    print(f"ERROR_DETAIL={json.dumps(error_data)[:500]}")

if output_data:
    print(f"OUTPUT_SUMMARY: success={output_data.get('success')}, has_output={'output' in output_data}")