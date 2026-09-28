"""P6-B-C3-5-C：full_mp3 必须是真 MP3（格式/MIME/download/签名全链路契约）。

契约（本轮新增，均为真 ffmpeg 编解码或格式级断言）：
- C1 WAV 上传物是 RIFF/WAVE；源 WAV 不被修改。
- C2 MP3 上传物是真 MP3（ID3/帧同步）。
- C3 MP3 不是 WAV（bytes 级判定，不看扩展名）。
- C4 Content-Type：full_wav=audio/wav，full_mp3=audio/mpeg；key 扩展名一致。
- C5 download fmt=mp3/wav 分别返回对应对象的预签名 URL。
- C6 _sign_for_playback("full_mp3"/"full_wav") 分别指向正确对象。
- C7 MP3 编码失败 → 正常 generation failure/refund 路径（failed + 退款）。
- C8 MP3 与源 WAV 时长基本一致（无明显截断）。

依赖：真 ffmpeg/ffprobe（本地已具备）；缺失时相关用例 skip（不会伪造通过）。
R2 全部 mock，绝不访问真实 R2。
"""

import asyncio
import math
import os
import shutil
import struct
import subprocess
import tempfile
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.services.continuation_service as cont_mod
from app.routers import ai_music

USER = "u-c35c"
HAS_FFMPEG = shutil.which("ffmpeg") is not None
HAS_FFPROBE = shutil.which("ffprobe") is not None

needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="需要本机 ffmpeg（不自行下载二进制）")
needs_ffprobe = pytest.mark.skipif(not (HAS_FFMPEG and HAS_FFPROBE), reason="需要 ffmpeg + ffprobe")


def _write_real_wav(path, seconds: float = 1.0, rate: int = 22050) -> str:
    n = int(seconds * rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(
            b"".join(
                struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / rate)))
                for i in range(n)
            )
        )
    return str(path)


def _is_wav_bytes(b: bytes) -> bool:
    return len(b) >= 12 and b[:4] == b"RIFF" and b[8:12] == b"WAVE"


def _is_mp3_bytes(b: bytes) -> bool:
    if b[:3] == b"ID3":
        return True
    return len(b) >= 2 and b[0] == 0xFF and (b[1] & 0xE0) == 0xE0


def _ffprobe_duration(path) -> float:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True, text=True, timeout=30,
    )
    return float(out.stdout.strip())


@pytest.fixture()
def r2_safe(monkeypatch):
    """替身 R2：真实 upload_music_package 逻辑可用，但 upload_private/presign/delete 全 mock。"""
    from app.services import cdn_uploader as cdn_mod

    uploaded = []

    async def _upload_private(path, key, content_type):
        uploaded.append((key, content_type, Path(path).read_bytes()[:8192]))
        return key

    deletes = []
    monkeypatch.setattr(cdn_mod.cdn_uploader, "upload_private", _upload_private)
    monkeypatch.setattr(
        cdn_mod.cdn_uploader, "get_presigned_download_url",
        lambda key, expires_in=600: f"https://signed/{key}",
    )
    monkeypatch.setattr(cdn_mod.cdn_uploader, "delete_object", lambda key: deletes.append(key) or True)
    return SimpleNamespace(uploaded=uploaded, deletes=deletes)


@pytest.fixture()
def route_env(monkeypatch):
    store = MagicMock()
    monkeypatch.setattr(ai_music, "task_store", store)
    reg = MagicMock()
    fake = SimpleNamespace(name="fakep", gpu="none")
    reg.fallback_chain.return_value = [fake]
    reg.chain_for_operation.return_value = [fake]
    reg.get.side_effect = lambda name: fake
    monkeypatch.delenv("AI_GENERATION_PROVIDER", raising=False)
    monkeypatch.setattr(ai_music, "get_provider_registry", lambda: reg)
    # 阶段 B：链失败后 HF 兜底——测试恒 None，绝不真实外呼
    monkeypatch.setattr(ai_music, "_try_hf_ace_step_fallback", AsyncMock(return_value=None))
    monkeypatch.setattr(
        ai_music.agnes_service, "generate_song",
        AsyncMock(return_value=SimpleNamespace(optimized_prompt="p", generated_lyrics="ly")),
    )
    monkeypatch.setattr(ai_music, "_log_generation_cost", lambda *a, **k: None)
    monkeypatch.setattr(ai_music, "refund_generation", MagicMock(return_value={"refunded": True}))
    monkeypatch.setattr(
        ai_music.credits_service, "refund_generation_credits",
        MagicMock(return_value={"success": True}),
    )
    return SimpleNamespace(store=store, reg=reg)


def _completed_task(task_id="c5t"):
    return {
        "task_id": task_id,
        "user_key": USER,
        "state": "completed",
        "download": {
            "full_wav": f"music/{task_id}/full_wav.wav",
            "full_mp3": f"music/{task_id}/full_mp3.mp3",
        },
        "stems_state": "failed",
    }


# ─────────────────────────────────────────────────────────────────────────────
# C1 + C2 + C3：上传物字节级格式（真 ffmpeg 编码）
# ─────────────────────────────────────────────────────────────────────────────
@needs_ffmpeg
async def test_c1_c2_c3_upload_receives_real_wav_and_real_mp3(
    monkeypatch, tmp_path, r2_safe
):
    from app.services import cdn_uploader as cdn_mod

    src = tmp_path / "song.wav"
    _write_real_wav(src, seconds=0.8)
    before = src.read_bytes()

    # 捕获 upload_music_package 收到的 {逻辑名: 本地路径}，由 upload_private 副本记字节
    async def _pkg(task_id, files):
        manifest = {}
        for logical, path in files.items():
            ext = os.path.splitext(path)[1].lower() or ".wav"
            content_type = "audio/mpeg" if ext == ".mp3" else "audio/wav"
            await cdn_mod.cdn_uploader.upload_private(path, f"music/{task_id}/{logical}{ext}", content_type)
            manifest[logical] = f"music/{task_id}/{logical}{ext}"
        return manifest

    monkeypatch.setattr(cdn_mod.cdn_uploader, "upload_music_package", _pkg)
    monkeypatch.setattr(ai_music, "task_store", MagicMock())

    await ai_music._upload_and_finalize("c3t", {"full_wav": str(src), "_local_path": str(src)})

    by_logical = {key.split("/")[-1].rsplit(".", 1)[0]: (key, ct, data)
                  for key, ct, data in r2_safe.uploaded}
    wav_key, wav_ct, wav_bytes = by_logical["full_wav"]
    mp3_key, mp3_ct, mp3_bytes = by_logical["full_mp3"]

    # C1：WAV 真是 WAV，且源文件未被修改
    assert _is_wav_bytes(wav_bytes), "full_wav 上传物必须是 RIFF/WAVE"
    assert src.read_bytes() == before, "源 WAV 不得被修改"
    assert _is_wav_bytes(before), "源仍是 WAV"
    # C2：MP3 真是 MP3
    assert _is_mp3_bytes(mp3_bytes), "full_mp3 上传物必须是真 MP3"
    # C3：MP3 不是 WAV
    assert not _is_wav_bytes(mp3_bytes), "MP3 不得是 WAV 字节"
    # 附带：key 与 MIME 正确（C4 的 upload 层）
    assert wav_key.endswith("full_wav.wav") and wav_ct == "audio/wav"
    assert mp3_key.endswith("full_mp3.mp3") and mp3_ct == "audio/mpeg"


# ─────────────────────────────────────────────────────────────────────────────
# C4：MIME / key 契约（upload_music_package 规则）
# ─────────────────────────────────────────────────────────────────────────────
async def test_c4_mime_and_key_match_real_extensions(monkeypatch, tmp_path, r2_safe):
    from app.services import cdn_uploader as cdn_mod

    wav = tmp_path / "a.wav"
    _write_real_wav(wav, seconds=0.1)
    mp3 = tmp_path / "b.mp3"
    mp3.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" + b"\x00" * 64)

    manifest = await cdn_mod.cdn_uploader.upload_music_package(
        "c4t", {"full_wav": str(wav), "full_mp3": str(mp3)},
    )
    assert manifest == {
        "full_wav": "music/c4t/full_wav.wav",
        "full_mp3": "music/c4t/full_mp3.mp3",
    }
    pairs = {(k, ct) for k, ct, _ in r2_safe.uploaded}
    assert ("music/c4t/full_wav.wav", "audio/wav") in pairs
    assert ("music/c4t/full_mp3.mp3", "audio/mpeg") in pairs


# ─────────────────────────────────────────────────────────────────────────────
# C5：download wav/mp3 分别返回正确对象
# ─────────────────────────────────────────────────────────────────────────────
def test_c5_download_returns_correct_object_per_format(monkeypatch):
    task = _completed_task("c5t")
    store = MagicMock()
    store.get.return_value = task
    monkeypatch.setattr(ai_music, "task_store", store)
    monkeypatch.setattr(ai_music, "check_and_log_download", lambda *a, **k: True)
    from app.services.cdn_uploader import cdn_uploader as _cdn

    monkeypatch.setattr(
        _cdn, "get_presigned_download_url",
        lambda key, expires_in=600: f"https://signed/{key}",
    )

    r_mp3 = asyncio.run(
        ai_music.download_file(None, "c5t", file="full", fmt="mp3", user_id=USER)
    )
    r_wav = asyncio.run(
        ai_music.download_file(None, "c5t", file="full", fmt="wav", user_id=USER)
    )
    r_wav2 = asyncio.run(
        ai_music.download_file(None, "c5t", file="full_wav", fmt="wav", user_id=USER)
    )
    assert r_mp3["url"] == "https://signed/music/c5t/full_mp3.mp3"
    assert r_wav["url"] == "https://signed/music/c5t/full_wav.wav"
    assert r_wav2["url"] == "https://signed/music/c5t/full_wav.wav"
    assert r_mp3["format"] == "mp3"


# ─────────────────────────────────────────────────────────────────────────────
# C6：signed playback wav/mp3 分别指向正确对象
# ─────────────────────────────────────────────────────────────────────────────
def test_c6_sign_for_playback_points_to_correct_objects(monkeypatch):
    seen = []
    from app.services import cdn_uploader as cdn_mod

    monkeypatch.setattr(
        cdn_mod.cdn_uploader, "get_presigned_download_url",
        lambda key, expires_in=600: seen.append(key) or f"https://signed/{key}",
    )
    manifest = _completed_task("c6t")["download"]

    url_mp3 = ai_music._sign_for_playback("c6t", "full_mp3", manifest)
    url_wav = ai_music._sign_for_playback("c6t", "full_wav", manifest)
    assert url_mp3 == "https://signed/music/c6t/full_mp3.mp3"
    assert url_wav == "https://signed/music/c6t/full_wav.wav"
    assert seen == ["music/c6t/full_mp3.mp3", "music/c6t/full_wav.wav"]


# ─────────────────────────────────────────────────────────────────────────────
# C7：MP3 编码失败 → 正常 failed + refund 路径
# ─────────────────────────────────────────────────────────────────────────────
async def test_c7_mp3_encoding_failure_enters_failure_refund_path(
    monkeypatch, tmp_path, r2_safe, route_env
):
    combined = _write_real_wav(tmp_path / "combined.wav", seconds=0.5)
    result = {
        "success": True,
        "volume_files": {"full_wav": "combined.wav", "_local_path": combined,
                         "_measured_duration_sec": 270.5},
        "provider": "fakep",
    }
    # 阶段 B：路由单跳 provider 直接返回成品（路由不再调 generate_long_music）；
    # 过统一质量门后在 _upload_and_finalize 内转码失败 → 既有 failed/refund 路径
    async def _gen(_req):
        return result

    route_env.reg.chain_for_operation.return_value = [
        SimpleNamespace(name="fakep", gpu="none", generate=_gen)
    ]
    monkeypatch.setattr(
        ai_music, "_transcode_wav_to_mp3",
        AsyncMock(side_effect=RuntimeError("MP3 转码失败: fake encoder error")),
    )

    req = ai_music.GenerateRequest(prompt="a song about the light", style="pop", type="song")
    await ai_music._run_generation("c7t", req, USER, 2)

    # 正常失败路径：failed 状态 + provider_failed 退款 + Credits 退款
    assert any(
        c.kwargs.get("state") == "failed"
        for c in route_env.store.update.call_args_list
    ), "转码失败必须进入既有 failed 状态"
    ai_music.refund_generation.assert_called_once()
    assert ai_music.refund_generation.call_args.kwargs["reason"] == "provider_failed"
    ai_music.credits_service.refund_generation_credits.assert_called_once()
    # 阶段 B：route 不做 part 删除（continuation 内部才持 part 生命周期；不访问真实 R2）
    assert r2_safe.deletes == []


# ─────────────────────────────────────────────────────────────────────────────
# C8：MP3 与 WAV 时长基本一致（无明显截断）
# ─────────────────────────────────────────────────────────────────────────────
@needs_ffprobe
async def test_c8_mp3_duration_matches_source_wav(tmp_path):
    src = tmp_path / "d.wav"
    _write_real_wav(src, seconds=1.0, rate=22050)
    out = tmp_path / "d.mp3"
    await ai_music._transcode_wav_to_mp3(str(src), str(out))

    wav_dur = _ffprobe_duration(src)
    mp3_dur = _ffprobe_duration(out)
    assert abs(mp3_dur - wav_dur) <= 0.2, (
        f"MP3 时长 {mp3_dur}s 与源 {wav_dur}s 差异过大（截断/变速）"
    )
    assert mp3_dur >= wav_dur - 0.2, "MP3 不得明显短于源（截断）"


# ─────────────────────────────────────────────────────────────────────────────
# §17：_upload_and_finalize 本地临时目录 成功/失败 路径都清理
# ─────────────────────────────────────────────────────────────────────────────
@needs_ffmpeg
async def test_upload_finalize_cleans_local_tmpdir_on_success_and_failure(
    monkeypatch, tmp_path, r2_safe
):
    created = []
    real_mkdtemp = tempfile.mkdtemp

    def _spy(*a, **k):
        d = real_mkdtemp(*a, **k)
        created.append(d)
        return d

    monkeypatch.setattr(tempfile, "mkdtemp", _spy)
    monkeypatch.setattr(ai_music, "task_store", MagicMock())

    # 成功路径：转码 + 上传完成 → tmp_dir 清理
    src = tmp_path / "ok.wav"
    _write_real_wav(src, seconds=0.5)
    await ai_music._upload_and_finalize("t17a", {"full_wav": str(src), "_local_path": str(src)})
    assert created and all(not os.path.exists(d) for d in created), "成功后本地临时目录必须清理"

    # 失败路径（转码异常）：原始异常照常抛出，tmp_dir 同样清理
    created.clear()
    monkeypatch.setattr(
        ai_music, "_transcode_wav_to_mp3",
        AsyncMock(side_effect=RuntimeError("MP3 转码失败: boom")),
    )
    with pytest.raises(RuntimeError, match="MP3 转码失败"):
        await ai_music._upload_and_finalize("t17b", {"full_wav": str(src), "_local_path": str(src)})
    assert created and all(not os.path.exists(d) for d in created), "失败后本地临时目录必须清理"
    # 源 WAV 不受影响
    assert _is_wav_bytes(src.read_bytes())
