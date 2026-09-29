"""300s 长生成测试 — 单发无截断（NO HARD MAX）、continuation 独立续写重试、R2"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio

from tests.test_ai_music_flow import isolated_db  # noqa: F401  独立 SQLite（新 schema）+ HF 关闭

def test_max_duration_constant_archived_270():
    """阶段 B：MAX 常量仅存档（270），已退出 normalize，无任何运行时钳制。"""
    from app.services.ai_limits import MAX_AUDIO_DURATION_SECONDS, MAX_TASK_RUNTIME_SECONDS
    assert MAX_AUDIO_DURATION_SECONDS == 270, f"存档常量应为 270 got {MAX_AUDIO_DURATION_SECONDS}"
    assert MAX_TASK_RUNTIME_SECONDS == 900

def test_provider_max_300():
    from app.services.provider_registry import get_provider_registry
    reg = get_provider_registry()
    assert reg.get("fal_stable_audio").max_duration == 300
    assert reg.get("modal_ace_step").max_duration == 300


def test_duration_weight():
    from app.services.ai_limits import get_duration_weight
    assert get_duration_weight(30) == 1
    assert get_duration_weight(120) == 1
    assert get_duration_weight(180) == 2
    assert get_duration_weight(300) == 2

def test_no_truncation_270():
    """阶段 B NO HARD MAX：normalize 只保留下限，300/600 原样保留，绝不截断为 270。"""
    from app.routers.ai_music import MAX_SONG_DURATION_SECONDS
    from app.services.ai_limits import MAX_AUDIO_DURATION_SECONDS, normalize_audio_duration
    # 死常量按本轮指令保持 300 原值（无运行时引用，仅此处记录现状）
    assert MAX_SONG_DURATION_SECONDS == 300
    assert MAX_AUDIO_DURATION_SECONDS == 270, "MAX 常量存档（已退出 normalize）"
    assert normalize_audio_duration(270) == 270
    assert normalize_audio_duration(300) == 300, "300 请求绝不截断为 270"
    assert normalize_audio_duration(600) == 600, "600 请求原样保留"
    assert normalize_audio_duration(60) == 240, "短请求只被抬到 MIN=240 下限"

@pytest.mark.asyncio
async def test_long_generation_single_shot_no_continuation(monkeypatch, isolated_db):
    """阶段 B：300s 不再走 continuation —— 单次生成 + 统一质量门，
    链由 chain_for_operation 选一次；120s 短请求同样单次生成（归一化抬到 MIN=240）。"""
    from app.routers.ai_music import GenerateRequest
    from app.services import task_store
    from app.routers import ai_music
    from app.services import continuation_service as cont_mod

    mock_agnes = AsyncMock()
    mock_agnes.generate_song = AsyncMock(return_value=MagicMock(optimized_prompt="opt", generated_lyrics="lyr"))
    monkeypatch.setattr("app.routers.ai_music.agnes_service", mock_agnes)

    mock_provider = MagicMock()
    mock_provider.name = "yinchao"
    mock_provider.generate = AsyncMock(return_value={
        "success": True,
        "volume_files": {"full_wav": "fake.wav", "_local_path": "/tmp/fake.wav",
                         "_measured_duration_sec": 265.0},
    })

    reg = MagicMock()
    reg.chain_for_operation.return_value = [mock_provider]
    monkeypatch.setattr(ai_music, "get_provider_registry", lambda: reg)

    # continuation 保留为独立续写入口：主链（含 300s）绝不调用它
    cont_mock = AsyncMock(return_value={"success": True, "volume_files": {}})
    monkeypatch.setattr(cont_mod.continuation_service, "generate_long_music", cont_mock)
    monkeypatch.setattr(ai_music, "_upload_and_finalize", AsyncMock())
    monkeypatch.setattr(ai_music, "_log_generation_cost", lambda *a, **k: None)
    monkeypatch.setattr(ai_music, "_try_hf_ace_step_fallback", AsyncMock(return_value=None))

    task_id = task_store.new_task(user_key="test_long")
    task_store.acquire_lock("test_long", task_id)
    try:
        req = GenerateRequest(prompt="test prompt for long song generation 300s", style="pop", duration=300)
        await ai_music._run_generation(task_id, req, "test_long")

        cont_mock.assert_not_called()
        reg.chain_for_operation.assert_called_once_with("normal", song_language=None)
        reg.select.assert_not_called()
        assert mock_provider.generate.await_count == 1
        sent = mock_provider.generate.await_args.args[0]
        assert sent["duration"] == 300, "≥MIN 应原样保留（阶段 B：normalize 只保留下限）"
        assert sent["operation"] == "normal"
        ai_music._upload_and_finalize.assert_awaited_once()

        # 短请求同样单次生成：归一化抬到 240，仍不进 continuation
        task_id2 = task_store.new_task(user_key="test_short")
        task_store.acquire_lock("test_short", task_id2)
        try:
            req2 = GenerateRequest(prompt="short prompt test", style="pop", duration=120)
            await ai_music._run_generation(task_id2, req2, "test_short")
        finally:
            task_store.delete(task_id2)
            task_store.release_lock_for_task(task_id2)
        cont_mock.assert_not_called()
        assert mock_provider.generate.await_count == 2
        assert mock_provider.generate.await_args_list[1].args[0]["duration"] == 240
    finally:
        task_store.delete(task_id)
        task_store.release_lock_for_task(task_id)

@pytest.mark.asyncio
async def test_continuation_second_segment_retry(monkeypatch):
    """第二段独立重试，不重跑首段"""
    from app.services.continuation_service import continuation_service
    # P6-B-C2：本用例桩的是 _stitch_with_crossfade（返回空文件），因此成品时长
    # 硬闸的实测出口也必须桩掉，否则会被 gate 以"测不到=不合规"挡下。
    from unittest.mock import AsyncMock as _AM
    monkeypatch.setattr(continuation_service, "_measure_final_duration",
                        _AM(return_value=271.0))
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
