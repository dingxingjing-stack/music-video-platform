#!/usr/bin/env python
"""
Full-link diagnostic: simulate a mock task end-to-end and verify
WebSocket progress delivery — no browser needed.

Usage:
    # Quick smoke test (runs a mock task, listens on WS, prints output)
    python tools/full_link_diagnostic.py

    # Watch a specific running task
    python tools/full_link_diagnostic.py --watch <task_id>

    # Custom backend URL
    python tools/full_link_diagnostic.py --base http://localhost:8000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from typing import Any

import httpx
import websockets


# ── Config ─────────────────────────────────────────────────────────────────

DEFAULT_BASE = "http://localhost:8000"
WS_BASE = "ws://localhost:8000"
TIMEOUT_REST = 30.0
TIMEOUT_WS = 120.0


# ── Color helpers ──────────────────────────────────────────────────────────

def _color(text: str, code: int) -> str:
    """ANSI color."""
    return f"\033[{code}m{text}\033[0m"


def _green(t: str) -> str: return _color(t, 32)
def _red(t: str) -> str: return _color(t, 31)
def _yellow(t: str) -> str: return _color(t, 33)
def _cyan(t: str) -> str: return _color(t, 36)
def _bold(t: str) -> str: return _color(t, 1)


# ── Unicode-safe symbols (fallback to ASCII on Windows GBK consoles) ───────

def _safe(text: str) -> str:
    """Return ASCII fallback if current encoding can't render the char."""
    try:
        text.encode(sys.stdout.encoding or "utf-8")
        return text
    except (UnicodeEncodeError, AttributeError):
        return ""


# ── REST API tests ─────────────────────────────────────────────────────────

async def test_rest_endpoints(base: str) -> dict[str, Any]:
    """Smoke-test all REST endpoints."""
    results: dict[str, str] = {}

    async with httpx.AsyncClient(timeout=TIMEOUT_REST) as client:
        # 1. Root
        try:
            r = await client.get(f"{base}/")
            results["root"] = _green("OK") if r.status_code == 200 else _red(f"HTTP {r.status_code}")
        except Exception as e:
            results["root"] = _red(f"FAIL: {e}")

        # 2. Health
        try:
            r = await client.get(f"{base}/health")
            data = r.json()
            svc = ", ".join(f"{k}={v.get('healthy')}" for k, v in data.get("services", {}).items())
            results["health"] = _green(f"OK ({svc})")
        except Exception as e:
            results["health"] = _red(f"FAIL: {e}")

        # 3. Mock predict (fire-and-forget endpoint)
        try:
            r = await client.post(
                f"{base}/api/v1/mock/run",
                json={"task_id": "diag-rest", "duration": 2.0, "tick_interval": 0.5},
            )
            data = r.json()
            results["mock"] = _green(f"task_id={data.get('task_id')}")
        except Exception as e:
            results["mock"] = _red(f"FAIL: {e}")

    return results


# ── WebSocket subscriber ──────────────────────────────────────────────────

async def subscribe_ws(task_id: str, timeout: float = TIMEOUT_WS) -> list[dict]:
    """Connect to WS, collect all messages until terminal or timeout."""
    messages: list[dict] = []
    url = WS_BASE.replace("http:", "ws:") + f"/ws/progress/{task_id}"

    try:
        async with websockets.connect(url) as ws:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    msg = json.loads(raw)
                    messages.append(msg)
                    status = msg.get("status", "?")
                    prog = msg.get("progress", 0)
                    bar_len = 20
                    filled = int(bar_len * prog / 100)
                    bar = _safe("█") * filled + _safe("░") * (bar_len - filled)
                    icon = {
                        "completed": _green(_safe("✓")),
                        "failed": _red(_safe("✗")),
                        "running": _cyan(_safe("⟳")),
                        "loading": _yellow(_safe("⏳")),
                    }.get(status, "·")
                    print(
                        f"  {icon} [{msg.get('task_id','?')[:8]:<8s}] "
                        f"{bar} {prog:3d}% | {status:<10s} | {msg.get('message','')}"
                    )
                    if status in ("completed", "failed", "cancelled"):
                        break
                except asyncio.TimeoutError:
                    continue
    except ConnectionRefusedError:
        print(f"  {_red('ERROR')}: Cannot connect to {url}")
        print(f"  {_red('ERROR')}: Is the backend running on port 8000?")
    except (websockets.exceptions.InvalidStatusCode, websockets.exceptions.InvalidHandshake) as e:
        print(f"  {_red('ERROR')}: WebSocket handshake failed: {e}")
        print(f"  {_red('ERROR')}: Check that /ws/progress/{{task_id}} route exists.")
    except Exception as e:
        print(f"  {_red('ERROR')}: {e}")

    return messages


# ── Full E2E test ─────────────────────────────────────────────────────────

async def run_mock_e2e(base: str) -> list[dict]:
    """
    Submit a mock task via REST, then subscribe to its WS.

    Strategy: submit the mock task with a longer duration (5s) so that
    the WebSocket subscriber can catch all progress messages.
    """
    print(f"\n{_bold('STEP 1/2: Submitting mock task via REST')}")

    task_id = f"diag-{int(time.time())}"

    # Use /api/v1/mock/run (fire-and-forget, returns immediately)
    # instead of /api/v1/predict/mock (waits for completion)
    async with httpx.AsyncClient(timeout=TIMEOUT_REST) as client:
        try:
            r = await client.post(
                f"{base}/api/v1/mock/run",
                json={
                    "task_id": task_id,
                    "duration": 5.0,
                    "tick_interval": 0.5,
                },
            )
            data = r.json()
            print(f"  REST response: {json.dumps(data, indent=2)}")
            assert data.get("task_id") == task_id, "task_id mismatch!"
            print(f"  {_green(_safe('✓'))} Task submitted: {task_id}")
        except Exception as e:
            print(f"  {_red(_safe('✗'))} REST submit failed: {e}")
            sys.exit(1)

    print(f"\n{_bold('STEP 2/2: Subscribing to WebSocket')}")
    messages = await subscribe_ws(task_id)

    return messages


# ── Watch mode ────────────────────────────────────────────────────────────

async def watch_task(task_id: str) -> list[dict]:
    """Just subscribe to an existing task's WS (no REST submit)."""
    print(f"\n{_bold('WATCH MODE: Listening on /ws/progress/{task_id}')}")
    print(f"  Wait for someone to submit a task with this task_id...\n")
    messages = await subscribe_ws(task_id)
    return messages


# ── Summary ───────────────────────────────────────────────────────────────

def print_summary(rest_results: dict, ws_messages: list[dict]) -> None:
    print(f"\n{'='*60}")
    print(f"  {_bold('DIAGNOSTIC SUMMARY')}")
    print(f"{'='*60}")

    print(f"\n  REST Endpoints:")
    for name, result in rest_results.items():
        icon = _green(_safe("✓")) if "OK" in result or "task_id=" in result else _safe("·")
        print(f"    {icon} {name:10s} {result}")

    print(f"\n  WebSocket Messages: {len(ws_messages)}")
    if ws_messages:
        statuses = [m.get("status", "?") for m in ws_messages]
        arrow = _safe("→") or "->"
        print(f"    Status sequence: {arrow}".join(statuses))

        # Verify monotonic progress for running states
        running_progs = [m.get("progress", 0) for m in ws_messages if m.get("status") == "running"]
        if running_progs:
            ok = all(running_progs[i] <= running_progs[i + 1] for i in range(len(running_progs) - 1))
            print(f"    Progress monotonic: {_green(_safe('✓') if ok else _safe('✗'))} {running_progs}")

        # Verify terminal state
        last = ws_messages[-1]
        terminal_ok = last.get("status") in ("completed", "failed", "cancelled")
        print(f"    Terminal state: {_green(_safe('✓') if terminal_ok else _red(_safe('✗'))) if terminal_ok else _red(_safe('✗'))} {last.get('status')}")
        if last.get("status") == "completed" and last.get("result_url"):
            print(f"    Result URL: {last['result_url']}")
    else:
        print(f"    {_red('No messages received!')}")

    # Overall verdict
    all_ok = all("OK" in str(v) or "task_id=" in str(v) for v in rest_results.values())
    ws_ok = len(ws_messages) >= 2
    if all_ok and ws_ok:
        print(f"\n  {_green(_safe('✓') + ' FULL LINK OK')} — Backend → REST → WebSocket → Client all working.")
    elif all_ok:
        print(f"\n  {_yellow(_safe('⚠') + ' PARTIAL')} — REST OK but WebSocket had issues. Check backend logs.")
    else:
        print(f"\n  {_red(_safe('✗') + ' FAILED')} — REST endpoint errors. Is the server running?")
    print()


# ── CLI ───────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Full-link diagnostic: REST + WebSocket verification",
    )
    parser.add_argument(
        "mode",
        choices=["e2e", "rest", "watch"],
        nargs="?",
        default="e2e",
        help="e2e: submit mock + WS (default) | rest: check endpoints only | watch: listen on existing task",
    )
    parser.add_argument("--base", default=DEFAULT_BASE, help=f"Backend base URL (default: {DEFAULT_BASE})")
    parser.add_argument("--task-id", default=None, help="Task ID to watch (for 'watch' mode)")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    base = args.base

    if args.mode == "rest":
        results = await test_rest_endpoints(base)
        print_summary(results, [])
        return

    if args.mode == "watch":
        task_id = args.task_id or input("Enter task_id: ").strip()
        if not task_id:
            print("task_id required", file=sys.stderr)
            sys.exit(1)
        messages = await watch_task(task_id)
        print_summary({}, messages)
        return

    # ── e2e mode (default) ───────────────────────────────────────────
    print(f"\n{_bold('FULL-LINK DIAGNOSTIC')}")
    print(f"  Backend: {base}")
    print(f"  WebSocket: {WS_BASE}")
    print()

    # Step 1: REST endpoints
    rest_results = await test_rest_endpoints(base)
    print_summary(rest_results, [])  # show REST status first

    # Step 2: E2E
    ws_messages = await run_mock_e2e(base)

    # Final summary
    print_summary(rest_results, ws_messages)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Aborted.")
        sys.exit(130)
