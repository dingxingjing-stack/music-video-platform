#!/usr/bin/env python
"""
Diagnostic tool: test the Inference Service API without a full UI.

Usage:
    # Test mock endpoint (no real HF Space needed)
    python tools/check_api.py mock

    # Test GPT-SoVITS (requires real .env config)
    python tools/check_api.py tts --text "你好世界" --audio-file sample.wav

    # Test music generation
    python tools/check_api.py music --prompt "jazz piano"

    # Check health
    python tools/check_api.py health

    # List all endpoints
    python tools/check_api.py root

Requires:
    pip install httpx websocket-client
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
import time
from pathlib import Path
from typing import Any, Optional

import httpx
import websockets

BASE_URL = "http://localhost:8000"


# ===========================================================================
# Helpers
# ===========================================================================

def print_json(data: Any, indent: int = 2) -> None:
    print(json.dumps(data, indent=indent, ensure_ascii=False))


def print_step(label: str, duration: float = 0) -> None:
    suffix = f" ({duration:.2f}s)" if duration > 0 else ""
    print(f"\n{'='*60}")
    print(f"  {label}{suffix}")
    print(f"{'='*60}")


def read_audio_bytes(path: str) -> bytes:
    p = Path(path)
    if not p.exists():
        print(f"ERROR: Audio file not found: {path}", file=sys.stderr)
        sys.exit(1)
    return p.read_bytes()


# ===========================================================================
# REST API tests
# ===========================================================================

async def test_root(client: httpx.AsyncClient) -> None:
    """Test GET / — API root info."""
    print_step("TEST: API Root")
    resp = await client.get(f"{BASE_URL}/")
    print_json(resp.json())


async def test_health(client: httpx.AsyncClient) -> None:
    """Test GET /health — service health check."""
    print_step("TEST: Health Check")
    resp = await client.get(f"{BASE_URL}/health")
    data = resp.json()
    print_json(data)
    status = data.get("status", "?")
    services = data.get("services", {})
    for svc, info in services.items():
        healthy = info.get("healthy", False)
        msg = info.get("message", "")
        icon = "OK" if healthy else "FAIL"
        print(f"  [{icon}] {svc}: {msg}")


async def test_task_status(client: httpx.AsyncClient, task_id: str) -> None:
    """Test GET /api/v1/tasks/{task_id} — subscriber info."""
    print_step(f"TEST: Task Status — {task_id}")
    resp = await client.get(f"{BASE_URL}/api/v1/tasks/{task_id}")
    print_json(resp.json())


async def test_mock_predict(client: httpx.AsyncClient) -> None:
    """Test POST /api/v1/predict/mock — simulated task."""
    print_step("TEST: Mock Predict (duration=3s)")
    resp = await client.post(f"{BASE_URL}/api/v1/predict/mock", json={
        "task_id": "diag-mock-001",
        "duration": 3.0,
        "tick_interval": 0.5,
    })
    data = resp.json()
    print_json(data)
    return data.get("task_id")


async def test_tts_predict(
    client: httpx.AsyncClient,
    text: str,
    audio_file: Optional[str] = None,
    audio_bytes: Optional[bytes] = None,
) -> None:
    """Test POST /api/v1/predict/tts — real GPT-SoVITS call."""
    if not audio_bytes and audio_file:
        audio_bytes = read_audio_bytes(audio_file)

    if not audio_bytes:
        print("ERROR: --audio-file required (or pipe bytes via stdin)", file=sys.stderr)
        sys.exit(1)

    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")

    print_step(f"TEST: TTS Predict — '{text}'")
    print(f"  Audio file size: {len(audio_bytes)} bytes")
    print(f"  Base64 size: {len(audio_b64)} chars")

    resp = await client.post(f"{BASE_URL}/api/v1/predict/tts", json={
        "task_id": "diag-tts-001",
        "text": text,
        "language": "zh",
        "reference_audio": audio_b64,
    })
    print_json(resp.json())


async def test_music_predict(client: httpx.AsyncClient, prompt: str) -> None:
    """Test POST /api/v1/predict/music — real MusicGen call."""
    print_step(f"TEST: Music Predict — '{prompt}'")
    resp = await client.post(f"{BASE_URL}/api/v1/predict/music", json={
        "task_id": "diag-music-001",
        "prompt": prompt,
        "duration": 15.0,
    })
    print_json(resp.json())


# ===========================================================================
# WebSocket test
# ===========================================================================

async def test_ws_subscribe(task_id: str, duration: float = 120.0) -> None:
    """Connect to WebSocket and print each progress message."""
    ws_url = f"ws://{BASE_URL.lstrip('http://')}/ws/progress/{task_id}"
    print_step(f"TEST: WebSocket Subscribe — {task_id}")
    print(f"  Connecting to: {ws_url}")

    try:
        async with websockets.connect(ws_url) as ws:
            print(f"  Connected. Waiting for progress updates (timeout: {duration:.0f}s)...")
            deadline = time.monotonic() + duration
            msg_count = 0

            async for message in ws:
                elapsed = time.monotonic() - deadline + duration
                msg = json.loads(message)
                msg_count += 1

                bar_len = 30
                prog = msg.get("progress", 0)
                filled = int(bar_len * prog / 100)
                bar = "█" * filled + "░" * (bar_len - filled)
                status = msg.get("status", "?")
                message_text = msg.get("message", "")

                print(
                    f"  [{msg_count:3d}] {bar} {prog:3d}% | "
                    f"{status:10s} | {message_text}"
                )

                if msg.get("status") in ("completed", "failed", "cancelled"):
                    print(f"\n  Terminal state reached: {status}")
                    if status == "completed" and msg.get("result_url"):
                        print(f"  Result URL: {msg['result_url']}")
                    break

                if time.monotonic() > deadline:
                    print(f"\n  Timeout reached after {msg_count} messages.")
                    break

            print(f"\n  Received {msg_count} WebSocket messages.")

    except ConnectionRefusedError:
        print("  ERROR: Cannot connect to server. Is uvicorn running?", file=sys.stderr)
        print(f"  Run: uvicorn main:app --reload --port 8000", file=sys.stderr)
        sys.exit(1)
    except ImportError:
        print(
            "  ERROR: websocket-client not installed. Install with:",
            file=sys.stderr
        )
        print("  pip install websocket-client", file=sys.stderr)
        sys.exit(1)


async def test_ws_with_mock(duration: float = 5.0) -> None:
    """End-to-end: submit mock task → subscribe WebSocket → receive progress."""
    print_step("E2E TEST: Mock Task + WebSocket")

    # Step 1: Submit mock task
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{BASE_URL}/api/v1/predict/mock", json={
            "task_id": "diag-e2e-001",
            "duration": duration,
            "tick_interval": 0.5,
        })
        data = resp.json()
        task_id = data["task_id"]
        print(f"  Task submitted: {task_id}")
        print_json(data)

    # Step 2: Subscribe to WebSocket
    await test_ws_subscribe(task_id, duration=duration + 10)


# ===========================================================================
# CLI
# ===========================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inference Service API Diagnostic Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s root                  Show API info
  %(prog)s health                Check service health
  %(prog)s mock                  Run mock prediction
  %(prog)s mock-ws               Mock + WebSocket e2e test
  %(prog)s tts --audio-file x.wav  Real TTS prediction
  %(prog)s music --prompt "jazz"   Real music generation
        """,
    )
    parser.add_argument(
        "command",
        choices=[
            "root", "health", "mock", "mock-ws",
            "tts", "music", "ws",
        ],
        help="Command to run",
    )
    parser.add_argument("--text", default="你好世界", help="Text for TTS (default: '你好世界')")
    parser.add_argument("--audio-file", help="Path to WAV/MP3 audio file for TTS")
    parser.add_argument("--prompt", default="upbeat jazz piano", help="Prompt for music generation")
    parser.add_argument("--duration", type=float, default=3.0, help="Duration in seconds for mock tasks")
    parser.add_argument("--ws-timeout", type=float, default=120.0, help="WebSocket listen timeout")
    parser.add_argument("--base-url", default=BASE_URL, help=f"API base URL (default: {BASE_URL})")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    global BASE_URL
    BASE_URL = args.base_url

    # Override print functions to use BASE_URL
    def patched_print_step(*a, **kw):
        print_step(*a, **kw)

    async with httpx.AsyncClient(timeout=180.0) as client:
        cmd = args.command

        try:
            if cmd == "root":
                await test_root(client)

            elif cmd == "health":
                await test_health(client)

            elif cmd == "mock":
                result = await test_mock_predict(client)
                task_id = result.get("task_id", "unknown")
                await test_task_status(client, task_id)

            elif cmd == "mock-ws":
                await test_ws_with_mock(duration=args.duration)

            elif cmd == "tts":
                audio_bytes = None
                if args.audio_file:
                    audio_bytes = read_audio_bytes(args.audio_file)
                await test_tts_predict(client, args.text, audio_bytes=audio_bytes)

            elif cmd == "music":
                await test_music_predict(client, args.prompt)

            elif cmd == "ws":
                task_id = input("Enter task_id to monitor: ").strip()
                if not task_id:
                    print("ERROR: task_id required", file=sys.stderr)
                    sys.exit(1)
                await test_ws_subscribe(task_id, duration=args.ws_timeout)

        except httpx.ConnectError:
            print(
                f"\n  ERROR: Cannot connect to {BASE_URL}",
                file=sys.stderr,
            )
            print("  Is the server running?", file=sys.stderr)
            print(
                "  Start it with: uvicorn main:app --reload --port 8000",
                file=sys.stderr,
            )
            sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Aborted by user.")
        sys.exit(130)
