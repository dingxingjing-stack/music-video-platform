#!/usr/bin/env python
"""
End-to-end TTS flow test.

Simulates the full production flow:
  1. Upload a local audio file (base64) or use placeholder
  2. POST /api/v1/tts/run → get task_id
  3. Connect WS /ws/progress/{task_id} → monitor progress
  4. On completed → verify elapsed_time and result_url
  5. Auto-retry for stress testing

Usage:
    # Single test with mock (no HF Space needed)
    python tools/test_tts_flow.py --iterations 3

    # Real TTS with a local audio file
    python tools/test_tts_flow.py --audio-file sample.wav --iterations 1

    # Custom text and backend URL
    python tools/test_tts_flow.py --text "Hello world" --base http://localhost:8000
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import struct
import sys
import time
from pathlib import Path

import httpx
import websockets


# ── Config ─────────────────────────────────────────────────────────────────

DEFAULT_BASE = "http://localhost:8000"
WS_BASE = "ws://localhost:8000"
TIMEOUT_REST = 120.0
TIMEOUT_WS = 300.0
MAX_RETRIES = 3
RETRY_DELAY = 2.0


# ── Helpers ────────────────────────────────────────────────────────────────

def _green(t: str) -> str: return f"\033[32m{t}\033[0m"
def _red(t: str) -> str: return f"\033[31m{t}\033[0m"
def _yellow(t: str) -> str: return f"\033[33m{t}\033[0m"
def _bold(t: str) -> str: return f"\033[1m{t}\033[0m"
def _cyan(t: str) -> str: return f"\033[36m{t}\033[0m"


def _safe(text: str) -> str:
    """ASCII fallback for Windows GBK consoles."""
    try:
        text.encode(sys.stdout.encoding or "utf-8")
        return text
    except (UnicodeEncodeError, AttributeError):
        return ""


def generate_minimal_wav_base64() -> str:
    """Generate a 1-second silence WAV file as base64."""
    sample_rate = 16000
    duration = 1
    num_samples = sample_rate * duration
    data_size = num_samples * 2  # 16-bit PCM
    file_size = 36 + data_size

    buf = bytearray(file_size)

    # RIFF header
    buf[0:4] = b"RIFF"
    buf[4:8] = struct.pack("<I", file_size)
    buf[8:12] = b"WAVE"
    # fmt chunk
    buf[12:16] = b"fmt "
    struct.pack_into("<I", buf, 16, 16)  # fmt chunk size
    struct.pack_into("<H", buf, 20, 1)   # PCM
    struct.pack_into("<H", buf, 22, 1)   # mono
    struct.pack_into("<I", buf, 24, sample_rate)
    struct.pack_into("<I", buf, 28, sample_rate * 2)
    struct.pack_into("<H", buf, 32, 2)   # block align
    struct.pack_into("<H", buf, 34, 16)  # bits per sample
    # data chunk
    buf[36:40] = b"data"
    struct.pack_into("<I", buf, 40, data_size)
    # silence (all zeros)

    return base64.b64encode(bytes(buf)).decode("ascii")


def load_audio_file(path: str) -> str:
    """Read a local audio file and return base64."""
    p = Path(path)
    if not p.exists():
        print(f"  {_red('ERROR')}: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    data = p.read_bytes()
    return base64.b64encode(data).decode("ascii")


# ── Single flow test ──────────────────────────────────────────────────────

async def run_flow(
    base_url: str,
    task_id: str,
    use_mock: bool = False,
    text: str = "",
    audio_base64: str = "",
) -> dict:
    """
    Execute one complete flow:
      1. POST /api/v1/tts/run (or /api/v1/mock/run)
      2. Connect WS /ws/progress/{task_id}
      3. Monitor until terminal state
      4. Verify result
    """
    result = {
        "task_id": task_id,
        "success": False,
        "elapsed_time": None,
        "result_url": None,
        "messages_received": 0,
        "error": None,
    }

    # ── Step 1: Submit task ──────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_REST) as client:
            if use_mock:
                url = f"{base_url}/api/v1/mock/run"
                body = {
                    "task_id": task_id,
                    "duration": 5.0,
                    "tick_interval": 0.5,
                }
            else:
                url = f"{base_url}/api/v1/tts/run"
                body = {
                    "task_id": task_id,
                    "text": text,
                    "language": "zh",
                    "reference_audio": audio_base64,
                }

            r = await client.post(url, json=body)

            if r.status_code != 200:
                result["error"] = f"HTTP {r.status_code}: {r.text[:200]}"
                return result

            data = r.json()
            if data.get("task_id") != task_id:
                result["error"] = f"task_id mismatch: expected {task_id}, got {data.get('task_id')}"
                return result

    except Exception as e:
        result["error"] = f"REST submit failed: {e}"
        return result

    # ── Step 2: Connect WS and monitor ───────────────────────────────────
    ws_url = WS_BASE.replace("http:", "ws:") + f"/ws/progress/{task_id}"
    messages = []

    try:
        async with websockets.connect(ws_url) as ws:
            deadline = time.monotonic() + TIMEOUT_WS
            while time.monotonic() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    msg = json.loads(raw)
                    messages.append(msg)
                    status = msg.get("status", "?")
                    prog = msg.get("progress", 0)

                    if status in ("completed", "failed", "cancelled"):
                        break
                except asyncio.TimeoutError:
                    continue

    except ConnectionRefusedError:
        result["error"] = "WS connection refused"
        return result
    except Exception as e:
        result["error"] = f"WS error: {e}"
        return result

    # ── Step 3: Verify results ───────────────────────────────────────────
    result["messages_received"] = len(messages)

    if not messages:
        result["error"] = "No WebSocket messages received"
        return result

    last_msg = messages[-1]
    status = last_msg.get("status", "")

    if status != "completed":
        result["error"] = f"Terminal status is '{status}', expected 'completed'"
        return result

    # Check elapsed_time in metadata
    metadata = last_msg.get("metadata", {})
    elapsed = metadata.get("elapsed_time")
    result["elapsed_time"] = elapsed
    result["result_url"] = last_msg.get("result_url")

    # Verify progress is 100
    if last_msg.get("progress") != 100:
        result["error"] = f"Final progress is {last_msg.get('progress')}, expected 100"
        return result

    result["success"] = True
    return result


# ── Stress test loop ──────────────────────────────────────────────────────

async def stress_test(
    base_url: str,
    text: str,
    audio_base64: str,
    iterations: int,
    use_mock: bool = False,
) -> None:
    """Run flow multiple times with auto-retry."""
    endpoint = "/api/v1/mock/run" if use_mock else "/api/v1/tts/run"
    print(f"\n{_bold('END-TO-END FLOW TEST')}")
    print(f"  Iterations: {iterations}")
    print(f"  Backend: {base_url}")
    print(f"  Endpoint: {endpoint}")
    audio_desc = "placeholder (1s silence)"
    print(f"  Audio: {audio_desc}")
    print()

    passed = 0
    failed = 0
    total_elapsed = 0.0
    results_log = []

    for i in range(1, iterations + 1):
        # Retry logic
        attempt = 0
        success = False

        while attempt < MAX_RETRIES and not success:
            if attempt > 0:
                print(f"  Retry {attempt}/{MAX_RETRIES} for iteration {i}...")
                await asyncio.sleep(RETRY_DELAY)

            task_id = f"test-{i}-{int(time.time())}"
            result = await run_flow(
                base_url=base_url,
                task_id=task_id,
                use_mock=use_mock,
                text=text,
                audio_base64=audio_base64,
            )
            results_log.append(result)

            if result["success"]:
                success = True
                passed += 1
                elapsed_str = f"{result['elapsed_time']:.1f}s" if result['elapsed_time'] else "N/A"
                print(
                    f"  [{i:3d}/{iterations}] {_green('PASS')} | "
                    f"elapsed={elapsed_str} | "
                    f"ws_msgs={result['messages_received']} | "
                    f"url={result['result_url'] or 'N/A'}"
                )
                total_elapsed += (result["elapsed_time"] or 0)
            else:
                attempt += 1
                if attempt >= MAX_RETRIES:
                    failed += 1
                    print(
                        f"  [{i:3d}/{iterations}] {_red('FAIL')} | "
                        f"error={result['error'][:80]}"
                    )
                else:
                    print(
                        f"  [{i:3d}/{iterations}] {_yellow('RETRY')} | "
                        f"error={result['error'][:60]}"
                    )

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  {_bold('SUMMARY')}")
    print(f"{'='*60}")
    print(f"  Total:      {iterations}")
    print(f"  Passed:     {_green(passed)}")
    print(f"  Failed:     {_red(failed)}")
    if passed > 0:
        avg_elapsed = total_elapsed / passed
        print(f"  Avg elapsed: {avg_elapsed:.1f}s")
        print(f"  Total time:  {sum(r.get('elapsed_time', 0) or 0 for r in results_log):.1f}s")

    if failed == 0:
        print(f"\n  {_green('ALL ITERATIONS PASSED')}")
    else:
        print(f"\n  {_red(f'{failed} ITERATIONS FAILED')}")

    # ── Detailed failure log ─────────────────────────────────────────────
    failures = [r for r in results_log if not r["success"]]
    if failures:
        print(f"\n  {_bold('FAILURE DETAILS')}")
        for r in failures:
            print(f"    task_id={r['task_id']} | error={r['error']}")

    print()


# ── CLI ────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="End-to-End Flow Test (Mock or TTS)",
    )
    parser.add_argument(
        "--audio-file",
        default=None,
        help="Path to a local audio file (wav/mp3/flac). If omitted, generates a 1s silence placeholder.",
    )
    parser.add_argument(
        "--text",
        default="你好世界，这是一段语音合成测试",
        help="Text to synthesize (TTS mode only)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1,
        help="Number of iterations for stress testing (default: 1)",
    )
    parser.add_argument(
        "--base",
        default=DEFAULT_BASE,
        help=f"Backend base URL (default: {DEFAULT_BASE})",
    )
    parser.add_argument(
        "--use-mock",
        action="store_true",
        help="Use /api/v1/mock/run instead of /api/v1/tts/run (for testing without real HF Space)",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    # Resolve audio base64
    if args.audio_file:
        audio_b64 = load_audio_file(args.audio_file)
        size_kb = len(audio_b64) / 1024
        print(f"  Loaded audio file: {args.audio_file} ({size_kb:.0f} KB base64)")
    else:
        audio_b64 = generate_minimal_wav_base64()
        print(f"  Using placeholder audio (1s silence)")

    await stress_test(
        base_url=args.base,
        text=args.text,
        audio_base64=audio_b64,
        iterations=args.iterations,
        use_mock=args.use_mock,
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Aborted.")
        sys.exit(130)
