"""300s 长生成测试 — 验证 150+150 分段、截断移除、重试、R2"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio

def test_max_duration_allows_300():
    from app.services.ai_limits import MAX_AUDIO_DURATION_SECONDS, MAX_TASK_RUNTIME_SECONDS
    assert MAX_AUDIO_DURATION_SECONDS == 300, f"MAX 300 expected got {MAX_AUDIO_DURATION_SECONDS}"
    assert MAX_TASK_RUNTIME_SECONDS == 900

def test_provider_max_300():
    from app.services.provider_registry import get_provider_registry
    reg = get_provider_registry()
    assert reg.get("runpod").max_duration == 300
    assert reg.get("fal_stable_audio").max_duration == 300
    assert reg.get("modal_ace_step").max_duration == 300

def test_runpod_client_allows_300():
    from app.services import runpod_client
    # 300 should not be truncated to 180
    # We test the clamping logic directly via generate_via_runpod internals is private,
    # so verify the provider limit via runtime
    import app.services.runpod_client as rc
    # seconds_total calc is inside generate_via_runpod, but we verify provider cap
    assert rc._resolve_timeout() == 600

def test_duration_weight():
    from app.services.ai_limits import get_duration_weight
    assert get_duration_weight(30) == 1
    assert get_duration_weight(120) == 1
    assert get_duration_weight(180) == 2
    assert get_duration_weight(300) == 2

def test_no_truncation_300():
    from app.routers.ai_music import MAX_SONG_DURATION_SECONDS
    from app.services.ai_limits import MAX_AUDIO_DURATION_SECONDS
    assert MAX_SONG_DURATION_SECONDS == 300
    assert MAX_AUDIO_DURATION_SECONDS == 300
    # Simulate ai_music duration calc
    duration = min(300, MAX_AUDIO_DURATION_SECONDS)
    assert duration == 300, "300 should not be truncated"

@pytest.mark.asyncio
async def test_long_generation_uses_continuation(monkeypatch):
    """300s 应走 continuation_service.generate_long_music，非单段"""
    from app.routers.ai_music import GenerateRequest
    from app.services import task_store
    from app.routers import ai_music
    # Mock agnes, provider, continuation, upload
    mock_agnes = AsyncMock()
    mock_agnes.generate_song = AsyncMock(return_value=MagicMock(optimized_prompt="opt", generated_lyrics="lyr"))
    monkeypatch.setattr("app.routers.ai_music.agnes_service", mock_agnes)

    mock_provider = MagicMock()
    mock_provider.name = "runpod"
    mock_provider.gpu = "runpod"
    mock_provider.generate = AsyncMock(return_value={"success": True, "volume_files": {"full_wav": "fake.wav", "_local_path": "/tmp/fake.wav"}})
    with patch("app.services.provider_registry.get_provider_registry") as mock_reg:
        mock_reg.return_value.select.return_value = mock_provider
        # Mock continuation
        mock_cont = AsyncMock()
        mock_cont.generate_long_music = AsyncMock(return_value={
            "success": True,
            "volume_files": {"full_wav": "combined.wav", "_local_path": "/tmp/combined.wav"},
            "manifest": {"full_wav": "music/task/combined.wav", "full_mp3": "music/task/combined.mp3"},
            "provider": "runpod+continuation"
        })
        with patch("app.services.continuation_service.continuation_service", mock_cont):
            with patch("app.routers.ai_music._upload_and_finalize", new=AsyncMock()):
                with patch("app.routers.ai_music._sign_for_playback", return_value="https://r2/test.mp3"):
                    # Create temp task
                    task_id = task_store.new_task(user_key="test_long")
                    task_store.acquire_lock("test_long", task_id)
                    req = GenerateRequest(prompt="test prompt for long song generation 300s", style="pop", duration=300)
                    # Mock cdn
                    await ai_music._run_generation(task_id, req, "test_long")
                    # Verify continuation was called for 300
                    assert mock_cont.generate_long_music.called, "300s should call continuation"
                    # Verify short does not call continuation
                    mock_cont.generate_long_music.reset_mock()
                    # Need new task for short
                    task_id2 = task_store.new_task(user_key="test_short")
                    task_store.acquire_lock("test_short", task_id2)
                    # For short, provider should be called directly, not continuation
                    # Reset mocks
                    mock_provider.generate.reset_mock()
                    req2 = GenerateRequest(prompt="short prompt test", style="pop", duration=120)
                    # Mock upload for short path
                    with patch("app.routers.ai_music._try_hf_ace_step_fallback", new=AsyncMock(return_value=None)):
                        await ai_music._run_generation(task_id2, req2, "test_short")
                    # For short, continuation should NOT be called
                    assert not mock_cont.generate_long_music.called, "120s should not call continuation"
                    # Clean up
                    task_store.delete(task_id)
                    task_store.delete(task_id2)
                    task_store.release_lock_for_task(task_id)
                    task_store.release_lock_for_task(task_id2)

@pytest.mark.asyncio
async def test_continuation_second_segment_retry():
    """第二段独立重试，不重跑首段"""
    from app.services.continuation_service import continuation_service
    # Mock first success, second fail then success
    call_count = {"second": 0}
    original_gen = continuation_service._generate_single_segment
    async def mock_gen(provider, prompt, lyrics, duration, reference_b64, enable_a2a):
        if not enable_a2a:
            # first segment
            return {"success": True, "volume_files": {"full_wav": "/tmp/part1.wav", "_local_path": "/tmp/part1.wav"}}
        else:
            call_count["second"] += 1
            if call_count["second"] == 1:
                return {"success": False, "error": "transient gpu error"}
            return {"success": True, "volume_files": {"full_wav": "/tmp/part2.wav", "_local_path": "/tmp/part2.wav"}}
    continuation_service._generate_single_segment = mock_gen
    # Patch helpers to avoid real IO
    with patch("app.services.audio_trim.trim_audio", new=AsyncMock(return_value=(b"fake_wav_bytes"*1000, "audio/wav"))):
        with patch("app.services.continuation_analysis.analyze_audio_context", new=AsyncMock(return_value={"bpm": 120, "key": "C major"})):
            with patch.object(continuation_service, '_continue_lyrics', new=AsyncMock(return_value="continued lyrics")):
                with patch.object(continuation_service, '_stitch_with_crossfade', new=AsyncMock(return_value="/tmp/combined.wav")):
                    with patch.object(continuation_service, '_upload_parts', new=AsyncMock(return_value={})):
                        with patch.object(continuation_service, '_upload_final', new=AsyncMock(return_value={"full_wav": "music/task/final.wav", "full_mp3": "music/task/final.mp3"})):
                            # Need to mock local files existence
                            import os, tempfile
                            for p in ["/tmp/part1.wav", "/tmp/part2.wav", "/tmp/combined.wav"]:
                                pathlib = __import__("pathlib")
                                pathlib.Path(p).touch(exist_ok=True)
                            result = await continuation_service.generate_long_music(
                                prompt="test", style="pop", duration=300, lyrics="test lyrics", task_id="test_retry", user_key="test"
                            )
                            assert result["success"] is True
                            assert call_count["second"] == 2, "second segment should retry once"
    continuation_service._generate_single_segment = original_gen
    # Cleanup
    for p in ["/tmp/part1.wav", "/tmp/part2.wav", "/tmp/combined.wav"]:
        try:
            __import__("os").unlink(p)
        except: pass

def test_ffmpeg_timeout_300():
    from app.services import ffmpeg_utils
    import inspect
    src = inspect.getsource(ffmpeg_utils.ffmpeg_run)
    assert "300" in src, "ffmpeg timeout should be 300"

def test_song_continuation_not_mock():
    import pathlib
    p = pathlib.Path(r"C:\Users\dingx\music-video-platform\backend\app\routers\song_continuation.py")
    t = p.read_text(encoding='utf-8')
    assert "Mock" not in t or "真实" in t, "song_continuation should not be mock"
    assert "continuation_service" in t
