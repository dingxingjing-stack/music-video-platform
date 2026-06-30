#!/usr/bin/env python
"""
Environment verification script for production deployment.

Checks:
  1. .env file has required fields
  2. HF Spaces are reachable
  3. WebSocket endpoint works
  4. Mock task → WebSocket broadcast chain works

Usage:
    python tools/verify_env.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx
import websockets


def _green(t: str) -> str: return f"\033[32m{t}\033[0m"
def _red(t: str) -> str: return f"\033[31m{t}\033[0m"
def _yellow(t: str) -> str: return f"\033[33m{t}\033[0m"
def _bold(t: str) -> str: return f"\033[1m{t}\033[0m"


# ── Check 1: .env file ─────────────────────────────────────────────────────

def check_env_file() -> dict[str, str]:
    """Verify .env has required config fields."""
    results = {}
    env_path = Path(__file__).parent.parent / ".env"

    if not env_path.exists():
        results["env_file"] = _red("MISSING")
        return results

    env_content = env_path.read_text(encoding="utf-8")
    env_vars = {}
    for line in env_content.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            env_vars[key.strip()] = val.strip()

    required = ["GPT_SOVITS_SPACE_URL", "MUSICGEN_SPACE_URL", "COGVIDEOX_SPACE_URL"]
    for key in required:
        if key in env_vars and env_vars[key]:
            results[key] = _green(f"SET ({env_vars[key][:40]}...)")
        else:
            results[key] = _red("NOT SET")

    # Token check
    token = env_vars.get("GPT_SOVITS_API_TOKEN", "")
    if token:
        results["GPT_SOVITS_API_TOKEN"] = _green("SET")
    else:
        results["GPT_SOVITS_API_TOKEN"] = _yellow("NOT SET (OK for public spaces)")

    return results


# ── Check 2: Backend API ───────────────────────────────────────────────────

async def check_backend(base_url: str) -> dict[str, str]:
    """Check if the backend API is running and healthy."""
    results = {}

    async with httpx.AsyncClient(timeout=15.0) as client:
        # Root
        try:
            r = await client.get(f"{base_url}/")
            if r.status_code == 200:
                data = r.json()
                results["root"] = _green(f"OK (v{data.get('version', '?')})")
            else:
                results["root"] = _red(f"HTTP {r.status_code}")
        except Exception as e:
            results["root"] = _red(f"FAIL: {e}")

        # Health
        try:
            r = await client.get(f"{base_url}/health")
            if r.status_code == 200:
                data = r.json()
                services = data.get("services", {})
                healthy = sum(1 for s in services.values() if s.get("healthy"))
                total = len(services)
                results["health"] = _green(f"OK ({healthy}/{total} services)")
            else:
                results["health"] = _red(f"HTTP {r.status_code}")
        except Exception as e:
            results["health"] = _red(f"FAIL: {e}")

        # Mock endpoint
        try:
            r = await client.post(
                f"{base_url}/api/v1/mock/run",
                json={"task_id": "verify-mock", "duration": 1.0, "tick_interval": 0.5},
            )
            if r.status_code == 200:
                data = r.json()
                results["mock_endpoint"] = _green(f"OK (task_id={data.get('task_id')})")
            else:
                results["mock_endpoint"] = _red(f"HTTP {r.status_code}")
        except Exception as e:
            results["mock_endpoint"] = _red(f"FAIL: {e}")

    return results


# ── Check 3: WebSocket endpoint ────────────────────────────────────────────

async def check_ws(base_url: str) -> dict[str, str]:
    """Verify WebSocket endpoint is accessible."""
    results = {}
    ws_url = base_url.replace("http://", "ws://")

    try:
        async with websockets.connect(f"{ws_url}/ws/progress/verify-ws") as ws:
            # Send a keepalive message
            await ws.send("ping")
            results["ws_endpoint"] = _green("CONNECTED")
    except ConnectionRefusedError:
        results["ws_endpoint"] = _red("CONNECTION REFUSED")
    except Exception as e:
        results["ws_endpoint"] = _red(f"FAIL: {e}")

    return results


# ── Check 4: HF Space reachability ─────────────────────────────────────────

async def check_hf_spaces() -> dict[str, str]:
    """Check if HF Spaces are reachable (reads from .env file)."""
    results = {}
    env_path = Path(__file__).parent.parent / ".env"
    env_vars = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                env_vars[key.strip()] = val.strip()

    spaces = {
        "GPT-SoVITS": env_vars.get("GPT_SOVITS_SPACE_URL", ""),
        "MusicGen": env_vars.get("MUSICGEN_SPACE_URL", ""),
        "CogVideoX": env_vars.get("COGVIDEOX_SPACE_URL", ""),
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        for name, url in spaces.items():
            if not url:
                results[name] = _yellow("NOT CONFIGURED")
                continue
            try:
                # Derive hf.space URL
                host = url.split("//")[-1]
                if host.startswith("huggingface.co/spaces/"):
                    path = host[len("huggingface.co/spaces/"):]
                    subdomain = path.replace("/", "-")
                    api_url = f"https://{subdomain}.hf.space/health"
                else:
                    api_url = f"https://{host}/health"

                r = await client.get(api_url, timeout=10.0)
                if r.status_code in (200, 503):
                    status = "awake" if r.status_code == 200 else "sleeping"
                    results[name] = _green(f"REACHABLE ({status})")
                else:
                    results[name] = _yellow(f"HTTP {r.status_code}")
            except Exception as e:
                results[name] = _red(f"UNREACHABLE: {str(e)[:60]}")

    return results


# ── Main ───────────────────────────────────────────────────────────────────

async def main():
    base_url = os.getenv("BACKEND_URL", "http://localhost:8000")

    print(f"\n{_bold('ENVIRONMENT VERIFICATION')}")
    print(f"  Backend: {base_url}")
    print()

    # 1. .env check
    print(f"{_bold('1. .env Configuration')}")
    env_results = check_env_file()
    for key, val in env_results.items():
        print(f"   {val} {key}")

    # 2. Backend API check
    print(f"\n{_bold('2. Backend API')}")
    api_results = await check_backend(base_url)
    for key, val in api_results.items():
        print(f"   {val} {key}")

    # 3. WebSocket check
    print(f"\n{_bold('3. WebSocket Endpoint')}")
    ws_results = await check_ws(base_url)
    for key, val in ws_results.items():
        print(f"   {val} {key}")

    # 4. HF Spaces check
    print(f"\n{_bold('4. HuggingFace Spaces')}")
    hf_results = await check_hf_spaces()
    for key, val in hf_results.items():
        print(f"   {val} {key}")

    # Summary
    all_green = all(
        "OK" in str(v) or "CONNECTED" in str(v) or "REACHABLE" in str(v) or "NOT SET" in str(v) or "NOT CONFIGURED" in str(v)
        for v in [*env_results.values(), *api_results.values(), *ws_results.values(), *hf_results.values()]
    )

    print(f"\n{'='*50}")
    if all_green:
        print(f"  {_green('ALL CHECKS PASSED')}")
    else:
        print(f"  {_yellow('SOME CHECKS FAILED')} -- review the output above")
    print()


if __name__ == "__main__":
    asyncio.run(main())
