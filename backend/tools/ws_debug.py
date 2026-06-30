#!/usr/bin/env python
"""
Quick WebSocket connectivity tester.

Tests three connection paths:
  1. Direct to backend:   ws://localhost:8000/ws/progress/test-123
  2. Via Vite proxy:      ws://localhost:3000/ws/progress/test-123
  3. REST first, then WS: POST /api/v1/predict/mock → get task_id → connect WS

Usage:
    python tools/ws_debug.py              # test all 3 paths
    python tools/ws_debug.py --direct     # only direct backend
    python tools/ws_debug.py --proxy      # only via Vite proxy
    python tools/ws_debug.py --e2e        # full REST → WS flow
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

import httpx
import websockets

BACKEND = "http://localhost:8000"
WS_BACKEND = "ws://localhost:8000"
PROXY = "ws://localhost:3000"


def _green(t: str) -> str: return f"\033[32m{t}\033[0m"
def _red(t: str) -> str: return f"\033[31m{t}\033[0m"
def _bold(t: str) -> str: return f"\033[1m{t}\033[0m"


async def test_direct(task_id: str = "debug-direct") -> bool:
    """Connect directly to backend WebSocket."""
    print(f"\n  {_bold('Test 1: Direct to backend')}")
    print(f"    ws://localhost:8000/ws/progress/{task_id}")
    try:
        async with websockets.connect(f"{WS_BACKEND}/ws/progress/{task_id}") as ws:
            print(f"    {_green('✓')} Connected!")
            # Send a ping to keep alive briefly
            await asyncio.sleep(0.5)
            await ws.close()
            return True
    except ConnectionRefusedError:
        print(f"    {_red('✗')} Connection refused — backend not running on port 8000?")
        print(f"    Start: uvicorn main:app --reload --port 8000")
        return False
    except Exception as e:
        print(f"    {_red('✗')} {e}")
        return False


async def test_proxy(task_id: str = "debug-proxy") -> bool:
    """Connect via Vite dev server proxy."""
    print(f"\n  {_bold('Test 2: Via Vite proxy')}")
    print(f"    ws://localhost:3000/ws/progress/{task_id}")
    print(f"    (Requires Vite running on port 3000)")
    try:
        async with websockets.connect(f"{PROXY}/ws/progress/{task_id}") as ws:
            print(f"    {_green('✓')} Connected via proxy!")
            await asyncio.sleep(0.5)
            await ws.close()
            return True
    except ConnectionRefusedError:
        print(f"    {_red('✗')} Connection refused — Vite not running on port 3000?")
        print(f"    Start: npm run dev")
        return False
    except Exception as e:
        print(f"    {_red('✗')} {e}")
        return False


async def test_e2e() -> bool:
    """Submit mock task via REST, then connect to WS."""
    print(f"\n  {_bold('Test 3: Full E2E (REST → WS)')}")
    task_id = f"debug-{int(time.time())}"

    # Step 1: REST
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{BACKEND}/api/v1/predict/mock",
                json={"task_id": task_id, "duration": 2.0, "tick_interval": 0.5},
            )
            data = r.json()
            print(f"    REST: {data.get('task_id')} → {data.get('status')}")
    except Exception as e:
        print(f"    {_red('✗')} REST failed: {e}")
        return False

    # Step 2: WS (wait a beat for mock task to start)
    await asyncio.sleep(0.3)
    try:
        async with websockets.connect(f"{WS_BACKEND}/ws/progress/{task_id}") as ws:
            msg_count = 0
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    msg = json.loads(raw)
                    msg_count += 1
                    print(f"    WS #{msg_count}: status={msg.get('status')} progress={msg.get('progress')}%")
                except asyncio.TimeoutError:
                    continue
            print(f"    {_green('✓')} Received {msg_count} messages")
            return msg_count > 0
    except ConnectionRefusedError:
        print(f"    {_red('✗')} WS connection refused")
        return False


async def main():
    print(f"\n{_bold('WebSocket Debug Tool')}")
    print(f"  Backend: {BACKEND}")
    print(f"  Proxy:   {PROXY}")

    results = {}
    results["direct"] = await test_direct()
    results["proxy"] = await test_proxy()
    results["e2e"] = await test_e2e()

    print(f"\n{'='*50}")
    print(f"  {_bold('Results')}")
    for name, ok in results.items():
        icon = _green("✓") if ok else _red("✗")
        print(f"    {icon} {name:8s} {'PASS' if ok else 'FAIL'}")

    if all(results.values()):
        print(f"\n  {_green('All tests passed!')} Full link is operational.")
    else:
        print(f"\n  {_red('Some tests failed.')} Check the suggestions above.")
    print()


if __name__ == "__main__":
    asyncio.run(main())
