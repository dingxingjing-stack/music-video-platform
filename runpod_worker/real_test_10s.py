#!/usr/bin/env python3
"""
真实 HeartMuLa 10s 测试 — 单次 /run，轮询 /status
不输出 Secret，仅报告指定字段
"""
import os, sys, time, json
from pathlib import Path

# 加载 .env（不覆写已存在环境变量）
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
    load_dotenv(Path(__file__).parent.parent / "backend" / ".env")
    load_dotenv(Path(__file__).parent.parent.parent / ".env")  # fallback
except Exception:
    pass

import httpx

endpoint_id = os.getenv("RUNPOD_ENDPOINT_ID")
api_key = os.getenv("RUNPOD_API_KEY")
hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")

# 掩码检查，不输出真实值
def is_configured(v): return bool(v and v.strip())
print(f"RUNPOD_ENDPOINT_ID={'configured' if is_configured(endpoint_id) else 'missing'}")
print(f"RUNPOD_API_KEY={'configured' if is_configured(api_key) else 'missing'}")
print(f"HF_TOKEN={'configured' if is_configured(hf_token) else 'missing'} (worker 内部使用)")

if not endpoint_id or not api_key:
    print("ERROR: RUNPOD_ENDPOINT_ID / RUNPOD_API_KEY 未配置，无法执行")
    sys.exit(1)

base = "https://api.runpod.ai/v2"
headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
payload = {"input": {"prompt": "A beautiful cinematic piano melody", "duration": 10}}

submit_url = f"{base}/{endpoint_id}/run"
print(f"POST {base}/{endpoint_id[:4]}****/run")
print(f"input: {json.dumps(payload, ensure_ascii=False)}")

t0 = time.monotonic()
try:
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(submit_url, headers=headers, json=payload)
        submit_time = round(time.monotonic() - t0, 2)
        print(f"RunPod HTTP status: {resp.status_code}")
        try:
            data = resp.json()
            print(f"submit raw keys: {list(data.keys())}")
        except Exception as e:
            print(f"submit not JSON: {resp.text[:500]}")
            sys.exit(1)

        if resp.status_code not in (200,201,202):
            print(f"submit error body: {json.dumps(data, indent=2, ensure_ascii=False)[:2000]}")
            # 按要求报告
            print(json.dumps({
                "RunPod HTTP status": resp.status_code,
                "job_id": None,
                "final status": None,
                "worker_started": False,
                "handler_success": None,
                "success": False,
                "generation_time": None,
                "gpu_name": None,
                "CUDA version": None,
                "torch version": None,
                "output_file": False,
                "file_size": 0,
                "error": f"submit failed {resp.status_code}: {str(data)[:500]}",
                "model_download_time": None,
                "model_load_time": None,
                "inference_time": None,
                "total_time": submit_time,
            }, indent=2, ensure_ascii=False))
            sys.exit(0)

        job_id = data.get("id") or data.get("request_id") or data.get("jobId")
        print(f"job_id: {job_id}")
        if not job_id:
            print(json.dumps({"error":"no job_id","data":data}, indent=2))
            sys.exit(1)

        # 轮询
        status_url = f"{base}/{endpoint_id}/status/{job_id}"
        print(f"polling {base}/{endpoint_id[:4]}****/status/{job_id[:8]}****")
        max_polls = 60  # 5min
        poll_interval = 5
        poll_start = time.monotonic()
        final = {}
        worker_started = False
        handler_success = None
        gpu_name = None
        cuda_ver = None
        torch_ver = None
        output_file = False
        file_size = 0
        generation_time = None
        model_download_time = None
        model_load_time = None
        total_time = None
        error = None
        success = False

        for i in range(max_polls):
            time.sleep(poll_interval)
            try:
                with httpx.Client(timeout=15.0) as c2:
                    s_resp = c2.get(status_url, headers={"Authorization": f"Bearer {api_key}"})
                if s_resp.status_code != 200:
                    print(f"poll {i} HTTP {s_resp.status_code}")
                    continue
                s_data = s_resp.json()
                status = (s_data.get("status") or "").upper()
                # 兼容字段
                if s_data.get("workerId") or s_data.get("worker_id"):
                    worker_started = True
                if status in ("IN_QUEUE","IN_PROGRESS","RUNNING"):
                    worker_started = True
                    print(f"poll {i} status {status}")
                    continue
                if status in ("COMPLETED","SUCCEEDED","COMPLETED ","FAILED","ERROR","CANCELLED","TIMED_OUT"):
                    print(f"poll {i} final status {status}")
                    final = s_data
                    # 解析 output
                    out = s_data.get("output")
                    # 尝试从 output 提取 worker 返回的字段
                    if isinstance(out, dict):
                        # heartmula_worker 返回的直接字段
                        handler_success = out.get("success")
                        success = bool(out.get("success"))
                        generation_time = out.get("generation_time") or out.get("total_time")
                        gpu_name = out.get("gpu_name")
                        cuda_ver = out.get("cuda_version")
                        torch_ver = out.get("torch_version")
                        # 额外 timing
                        model_download_time = out.get("model_download_time")
                        model_load_time = out.get("model_load_time")
                        # 文件
                        fn = out.get("filename") or out.get("output_file")
                        if fn:
                            output_file = True
                            # 无法直接获取文件大小（RunPod 返回的是路径），尝试从 output 推断
                            # 若 worker 返回 file_size
                            file_size = out.get("file_size") or out.get("size") or 0
                        # 错误
                        if not success:
                            error = out.get("error") or s_data.get("error") or str(out)[:1000]
                    else:
                        # 非 dict output（如 smoke test 的简单输出）
                        handler_success = None
                        success = (status == "COMPLETED")
                        error = str(out)[:1000] if status in ("FAILED","ERROR") else None
                    # 记录 timing
                    total_time = round(time.monotonic() - t0, 2)
                    # 若 output 含 timing，优先使用，否则用 poll 总耗时
                    break
            except Exception as e:
                print(f"poll {i} exception {e}")
                continue
        else:
            # timeout
            final = {"status":"TIMEOUT"}
            error = "poll timeout 5min"
            total_time = round(time.monotonic() - t0, 2)

        # 最终报告（不含 Secret）
        report = {
            "RunPod HTTP status": resp.status_code,
            "job_id": job_id,
            "final status": final.get("status") if isinstance(final, dict) else str(final)[:200],
            "worker_started": worker_started,
            "handler_success": handler_success,
            "success": success,
            "generation_time": generation_time,
            "gpu_name": gpu_name,
            "CUDA version": cuda_ver,
            "torch version": torch_ver,
            "output_file": output_file,
            "file_size": file_size,
            "error": error,
            "model_download_time": model_download_time,
            "model_load_time": model_load_time,
            "inference_time": generation_time,
            "total_time": total_time,
            "raw_output_keys": list(final.get("output", {}).keys()) if isinstance(final, dict) and isinstance(final.get("output"), dict) else None,
        }
        print("="*60)
        print("REPORT")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        # 保存报告到文件（不含 Secret）
        Path("runpod_worker/last_run_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("report saved to runpod_worker/last_run_report.json")

except Exception as e:
    import traceback
    tb = traceback.format_exc()[-3000:]
    print(json.dumps({
        "RunPod HTTP status": None,
        "job_id": None,
        "final status": None,
        "worker_started": False,
        "handler_success": None,
        "success": False,
        "generation_time": None,
        "gpu_name": None,
        "CUDA version": None,
        "torch version": None,
        "output_file": False,
        "file_size": 0,
        "error": f"{type(e).__name__}: {e}\n{tb}",
        "model_download_time": None,
        "model_load_time": None,
        "inference_time": None,
        "total_time": round(time.monotonic()-t0,2) if 't0' in locals() else None,
    }, indent=2, ensure_ascii=False))
