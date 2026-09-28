"""P6-B-C3-5-B：continuation 中间分片（R2 part）生命周期与本地临时文件清理。

契约（阶段 B 更新）：
- B1 成功：continuation 内 part1/part2 各上传 1 次；route finalize（final WAV+MP3
  各 1 次）后 route 不再删 part（阶段 B 主链无 route 级 part 清理）；final 对象绝不被删。
- B2 part2 生成失败 → part1 cleanup 被尝试，原始失败信息保留。
- B3 stitch 失败 → 已有 parts cleanup 被尝试。
- B4 duration gate 失败（<MIN=240）→ parts cleanup 被尝试。
- B5 final 上传失败 → route 层 failed + 恰好一次退款语义保留；route 不触碰 part 对象。
- B6 part 删除失败 → 不覆盖原始 generation 结果（continuation 内失败仍原样抛出；
  route 成功路径根本不依赖 delete_object）。
- B7 cleanup 幂等：重复执行、NoSuchKey、非法前缀一律不抛出。

所有 R2 操作均被替身 mock（绝不访问真实 R2）；不改任何测试去迎合实现。
"""

import asyncio
import math
import os
import shutil
import struct
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.services.continuation_service as cont_mod
from app.services.continuation_service import (
    DurationValidationError,
    cleanup_continuation_artifacts,
    continuation_service,
)
from app.routers import ai_music

USER = "u-c35b"


def _provider_returning(result):
    """阶段 B 路由单跳 provider：直接返回 canned 结果（路由不再调 generate_long_music）。"""
    async def _generate(request):
        return result
    return SimpleNamespace(name="fakep", gpu="none", generate=_generate)


# ─────────────────────────────────────────────────────────────────────────────
# 基础工具
# ─────────────────────────────────────────────────────────────────────────────
def _write_real_wav(path, seconds: float = 0.5, rate: int = 8000) -> str:
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


class FakeProvider:
    provider_type = "api"
    capabilities = ["text_to_music"]
    production = True
    max_duration = 300
    gpu = "none"

    def __init__(self, name="fake", succeed_first_n: int = 10 ** 9, directory=None):
        self.name = name
        self.requests = []
        self.written = []
        self.succeed_first_n = succeed_first_n
        self.directory = directory

    async def generate(self, request: dict) -> dict:
        self.requests.append(dict(request))
        if len(self.requests) > self.succeed_first_n:
            return {"success": False, "error": "segment generation boom"}
        p = Path(self.directory) / f"seg{len(self.requests)}.wav"
        _write_real_wav(p)
        self.written.append(str(p))
        return {"success": True, "volume_files": {"full_wav": p.name, "_local_path": str(p)}}


@pytest.fixture()
def r2(monkeypatch):
    """替身 R2：记录 package PUT 与 delete。绝不触真实 R2。"""
    from app.services import cdn_uploader as cdn_mod

    puts = []
    deletes = []
    fail_final = set()

    async def _pkg(task_id, files):
        if task_id in fail_final:
            raise RuntimeError("R2 final PUT boom")
        puts.append((task_id, tuple(files)))
        # 复刻真实 key/MIME 规则：ext 取自本地路径
        return {
            k: f"music/{task_id}/{k}{os.path.splitext(v)[1].lower() or '.wav'}"
            for k, v in files.items()
        }

    def _delete(key):
        deletes.append(key)
        return True

    monkeypatch.setattr(cdn_mod.cdn_uploader, "upload_music_package", _pkg)
    monkeypatch.setattr(cdn_mod.cdn_uploader, "delete_object", _delete)
    monkeypatch.setattr(
        cdn_mod.cdn_uploader, "get_presigned_download_url",
        lambda key, expires_in=600: f"https://signed/{key}",
    )
    return SimpleNamespace(puts=puts, deletes=deletes, fail_final=fail_final)


@pytest.fixture()
def heavy(monkeypatch, tmp_path):
    """桩掉 continuation 的重 IO（context/lyrics/stitch/实测）；快进重试 sleep。"""
    monkeypatch.setattr(cont_mod.task_store, "update", MagicMock())
    monkeypatch.setattr(
        cont_mod, "MAX_AUTO_RETRIES", 1,
    )
    # 重试 sleep 不真睡（保持失败路径语义、加速测试）
    async def _fast_sleep(*_a, **_k):
        return None
    monkeypatch.setattr(cont_mod.asyncio, "sleep", _fast_sleep)

    monkeypatch.setattr(
        continuation_service, "_prepare_continuation_context",
        AsyncMock(return_value=("cmViZA==", {"bpm": 120, "key": "C major"})),
    )
    monkeypatch.setattr(continuation_service, "_continue_lyrics", AsyncMock(return_value="ly2"))
    stitched = tmp_path / "stitched.wav"
    _write_real_wav(stitched)
    monkeypatch.setattr(
        continuation_service, "_stitch_with_crossfade",
        AsyncMock(return_value=str(stitched)),
    )
    monkeypatch.setattr(
        continuation_service, "_measure_final_duration", AsyncMock(return_value=270.5),
    )
    return SimpleNamespace(stitched=stitched)


@pytest.fixture()
def route_env(monkeypatch, tmp_path):
    """路由层替身（不含 _upload_and_finalize：B1/B5/B6b 要走真实收尾逻辑）。"""
    store = MagicMock()
    monkeypatch.setattr(ai_music, "task_store", store)
    fake = FakeProvider("fakep", directory=tmp_path)
    reg = MagicMock()
    reg.fallback_chain.return_value = [fake]
    reg.chain_for_operation.return_value = [fake]
    reg.get.side_effect = lambda name: fake
    monkeypatch.delenv("AI_GENERATION_PROVIDER", raising=False)
    monkeypatch.setattr(ai_music, "get_provider_registry", lambda: reg)
    # 阶段 B：链失败后 HF 兜底仅 normal/lyric_to_music——测试恒 None，绝不真实外呼
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
    # B 测试只关心生命周期：转码交给桩（真编解码行为由 C3-5-C 测试覆盖）
    async def _fake_transcode(wav, dst):
        return dst
    monkeypatch.setattr(ai_music, "_transcode_wav_to_mp3", _fake_transcode)
    return SimpleNamespace(store=store, reg=reg)


async def _run_long(task_id, provider, measured=270.5, monkeypatch=None, **kw):
    if monkeypatch is not None and measured != 270.5:
        monkeypatch.setattr(
            continuation_service, "_measure_final_duration",
            AsyncMock(return_value=measured),
        )
    params = dict(
        prompt="p", style="pop", duration=270, lyrics="ly",
        task_id=task_id, user_key=USER, provider_chain=[provider],
    )
    params.update(kw)
    return await continuation_service.generate_long_music(**params)


def _route_request():
    return ai_music.GenerateRequest(prompt="a song about the light", style="pop", type="song")


# ─────────────────────────────────────────────────────────────────────────────
# B1：成功全链路 —— 4 次 PUT，finalize 后删 parts，final 永不删
# ─────────────────────────────────────────────────────────────────────────────
async def test_b1_success_finalizes_then_cleans_parts_and_locals(
    monkeypatch, tmp_path, r2, heavy, route_env
):
    # Phase 1：真实 continuation（真实 _upload_parts → 替身 R2 PUT）
    prov = FakeProvider(directory=tmp_path)
    result = await _run_long("b1t", prov)
    assert [p[0] for p in r2.puts] == ["b1t_part1", "b1t_part2"], "part 各上传恰 1 次"
    assert result["part_keys"] == [
        "music/b1t_part1/part1_wav.wav",
        "music/b1t_part2/part2_wav.wav",
    ]
    # 成功：本地 segment 立即清理；combined 留给 route；parts 在 finalize 前不删
    for p in prov.written:
        assert not os.path.exists(p), "成功路径 segment 本地文件应清理"
    combined = result["volume_files"]["_local_path"]
    assert os.path.exists(combined), "combined 必须活到 route finalize"
    assert r2.deletes == [], "finalize 之前绝不能删 parts"

    # Phase 2：路由收尾（阶段 B：provider 单次返回 continuation 成品 → 真实
    # _upload_and_finalize → 替身 R2 PUT/预签名；路由不再调 generate_long_music）
    route_env.reg.chain_for_operation.return_value = [_provider_returning(result)]
    await ai_music._run_generation("b1t", _route_request(), USER, 2)

    # 4 次 PUT：part1 + part2 + final(full_wav, full_mp3)，final 只有一次
    assert [p[0] for p in r2.puts] == ["b1t_part1", "b1t_part2", "b1t"]
    assert r2.puts[2][1] == ("full_wav", "full_mp3"), "final 恰好两个逻辑对象、一次上传"
    # 阶段 B：route 成功路径不删任何对象（part 清理仅存在于 continuation 内部失败路径）；
    # final 对象绝不进删除列表
    assert r2.deletes == [], "route 成功路径不触碰 delete_object"
    # 任务终态 completed*、不退款
    assert any(
        c.kwargs.get("state") in ("completed", "completed_with_stems_failed")
        for c in route_env.store.update.call_args_list
    )
    ai_music.refund_generation.assert_not_called()
    # 阶段 B：route 不再删除本地 combined（continuation 内部段文件已自清理）
    assert os.path.exists(combined), "route 不负责本地 combined 生命周期"


# ─────────────────────────────────────────────────────────────────────────────
# B2：part2 生成失败 → part1 cleanup + 原始失败保留
# ─────────────────────────────────────────────────────────────────────────────
async def test_b2_part2_generation_failure_cleans_part1(monkeypatch, tmp_path, r2, heavy):
    prov = FakeProvider(succeed_first_n=1, directory=tmp_path)
    with pytest.raises(RuntimeError, match="续写段生成失败"):
        await _run_long("b2t", prov)
    assert r2.deletes == ["music/b2t_part1/part1_wav.wav"], "part1 cleanup 被尝试"
    assert not os.path.exists(prov.written[0]), "失败路径本地 segment 也清理"


# ─────────────────────────────────────────────────────────────────────────────
# B3：stitch 失败 → 已有 parts cleanup
# ─────────────────────────────────────────────────────────────────────────────
async def test_b3_stitch_failure_cleans_existing_parts(monkeypatch, tmp_path, r2, heavy):
    monkeypatch.setattr(
        continuation_service, "_stitch_with_crossfade",
        AsyncMock(side_effect=RuntimeError("ffmpeg boom")),
    )
    prov = FakeProvider(directory=tmp_path)
    with pytest.raises(RuntimeError, match="FFmpeg 合并失败"):
        await _run_long("b3t", prov)
    assert set(r2.deletes) == {
        "music/b3t_part1/part1_wav.wav",
        "music/b3t_part2/part2_wav.wav",
    }
    for p in prov.written:
        assert not os.path.exists(p)


# ─────────────────────────────────────────────────────────────────────────────
# B4：duration gate 失败（<MIN=240）→ parts cleanup
# ─────────────────────────────────────────────────────────────────────────────
async def test_b4_duration_gate_failure_cleans_parts(monkeypatch, tmp_path, r2, heavy):
    prov = FakeProvider(directory=tmp_path)
    with pytest.raises(DurationValidationError, match="below minimum"):
        await _run_long("b4t", prov, measured=239.9, monkeypatch=monkeypatch)
    assert set(r2.deletes) == {
        "music/b4t_part1/part1_wav.wav",
        "music/b4t_part2/part2_wav.wav",
    }


# ─────────────────────────────────────────────────────────────────────────────
# B5：final 上传失败 → 原始失败/退款语义保留；route 不触碰 part 对象
# ─────────────────────────────────────────────────────────────────────────────
async def test_b5_final_upload_failure_cleans_parts_and_keeps_refund(
    monkeypatch, tmp_path, r2, heavy, route_env
):
    combined = _write_real_wav(tmp_path / "combined.wav")
    result = {
        "success": True,
        "volume_files": {
            "full_wav": "combined.wav",
            "_local_path": combined,
            "_measured_duration_sec": 270.5,
        },
        "provider": "fakep+continuation",
        "part_keys": ["music/b5t_part1/part1_wav.wav", "music/b5t_part2/part2_wav.wav"],
    }
    route_env.reg.chain_for_operation.return_value = [_provider_returning(result)]
    r2.fail_final.add("b5t")

    await ai_music._run_generation("b5t", _route_request(), USER, 2)

    # 阶段 B：route 失败路径不删任何对象（part 属 continuation 内部生命周期）；
    # final 从未上传成功（也不在删除列表）
    assert r2.deletes == [], "route 不做 part 清理"
    assert not any(p[0] == "b5t" for p in r2.puts), "final PUT 失败即未成功上传"
    assert os.path.exists(combined), "route 不删除本地 combined"
    # 原始失败语义保留：failed + provider_failed 退款（cleanup 没有覆盖它）
    assert any(
        c.kwargs.get("state") == "failed"
        for c in route_env.store.update.call_args_list
    )
    ai_music.refund_generation.assert_called_once()
    assert ai_music.refund_generation.call_args.kwargs["reason"] == "provider_failed"
    ai_music.credits_service.refund_generation_credits.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# B6：part 删除失败 → 原始 generation 结果保留
# ─────────────────────────────────────────────────────────────────────────────
async def test_b6_delete_failure_preserves_original_generation_failure(
    monkeypatch, tmp_path, r2, heavy
):
    from app.services import cdn_uploader as cdn_mod

    def _bad_delete(key):
        raise RuntimeError("R2 delete boom")

    monkeypatch.setattr(cdn_mod.cdn_uploader, "delete_object", _bad_delete)
    monkeypatch.setattr(
        continuation_service, "_stitch_with_crossfade",
        AsyncMock(side_effect=RuntimeError("ffmpeg boom")),
    )
    prov = FakeProvider(directory=tmp_path)
    # 清理失败绝不能把原始 FFmpeg 失败改成别的错误，也绝不能吞掉
    with pytest.raises(RuntimeError, match="FFmpeg 合并失败"):
        await _run_long("b6t", prov)


async def test_b6_route_success_survives_delete_failure(
    monkeypatch, tmp_path, r2, heavy, route_env
):
    from app.services import cdn_uploader as cdn_mod

    def _bad_delete(key):
        raise RuntimeError("R2 delete boom")

    monkeypatch.setattr(cdn_mod.cdn_uploader, "delete_object", _bad_delete)

    combined = _write_real_wav(tmp_path / "combined6.wav")
    result = {
        "success": True,
        "volume_files": {"full_wav": "combined6.wav", "_local_path": combined,
                         "_measured_duration_sec": 270.5},
        "provider": "fakep+continuation",
        "part_keys": ["music/b6r_part1/part1_wav.wav", "music/b6r_part2/part2_wav.wav"],
    }
    route_env.reg.chain_for_operation.return_value = [_provider_returning(result)]
    await ai_music._run_generation("b6r", _route_request(), USER, 2)

    # 阶段 B：route 成功路径不依赖 delete_object（删除桩必炸也无妨），仍进 completed*、绝不退款
    assert any(
        c.kwargs.get("state") in ("completed", "completed_with_stems_failed")
        for c in route_env.store.update.call_args_list
    )
    ai_music.refund_generation.assert_not_called()
    assert not any(
        c.kwargs.get("state") == "failed"
        for c in route_env.store.update.call_args_list
    )


# ─────────────────────────────────────────────────────────────────────────────
# B7：cleanup 幂等 + 白名单前缀（final/他人 key 永不删）
# ─────────────────────────────────────────────────────────────────────────────
def test_b7_cleanup_is_idempotent_and_prefix_whitelisted(monkeypatch):
    from app.services import cdn_uploader as cdn_mod

    calls = []

    def _delete(key):
        calls.append(key)
        if len(calls) > 2:
            raise RuntimeError("NoSuchKey")  # 已删除/不存在
        return True

    monkeypatch.setattr(cdn_mod.cdn_uploader, "delete_object", _delete)
    keys = ["music/t7_part1/part1_wav.wav", "music/t7_part2/part2_wav.wav"]

    cleanup_continuation_artifacts("t7", keys, ["/nonexistent/does_not_exist.wav"])
    cleanup_continuation_artifacts("t7", keys, [None, ""])  # 再次执行：幂等不抛
    assert len(calls) == 4, "两次执行各尝试两个 key，全程无异常"

    # 白名单：非本任务 part 前缀（含 final 对象）绝不删除
    cleanup_continuation_artifacts(
        "t7",
        ["music/t7/full_wav.wav", "music/t7/full_mp3.mp3", "music/other_part1/x.wav"],
        None,
    )
    assert len(calls) == 4, "final/他人 key 一律跳过"

    # 任何参数组合都不允许抛出
    cleanup_continuation_artifacts("t7", None, None)
    cleanup_continuation_artifacts("t7", [None, 123, "music/t7_part1/a.wav"], [123])


# ─────────────────────────────────────────────────────────────────────────────
# B5-API：cdn_uploader.delete_object 单元（幂等、永不抛）
# ─────────────────────────────────────────────────────────────────────────────
def test_delete_object_api_idempotent_and_never_raises(monkeypatch):
    import boto3
    from botocore.exceptions import ClientError

    from app.services import cdn_uploader as cdn_mod

    monkeypatch.setattr(cdn_mod.cdn_uploader, "provider", cdn_mod.CDNProvider.R2)
    state = {"mode": "ok", "calls": []}

    class _FakeS3:
        def delete_object(self, Bucket, Key):
            state["calls"].append((Bucket, Key))
            if state["mode"] == "missing":
                raise ClientError(
                    {"Error": {"Code": "NoSuchKey", "Message": "gone"}}, "DeleteObject",
                )
            if state["mode"] == "error":
                raise ClientError(
                    {"Error": {"Code": "InternalError", "Message": "boom"}}, "DeleteObject",
                )
            return {}

    monkeypatch.setattr(boto3, "client", lambda *a, **k: _FakeS3())

    assert cdn_mod.cdn_uploader.delete_object("music/t/part.wav") is True
    state["mode"] = "missing"
    assert cdn_mod.cdn_uploader.delete_object("music/t/part.wav") is True, "NoSuchKey = 已清理"
    state["mode"] = "error"
    assert cdn_mod.cdn_uploader.delete_object("music/t/part.wav") is False, "错误只降级不抛出"
    assert len(state["calls"]) == 3

    # 非 R2 环境：跳过并返回 False，不抛
    monkeypatch.setattr(cdn_mod.cdn_uploader, "provider", cdn_mod.CDNProvider.LOCAL)
    assert cdn_mod.cdn_uploader.delete_object("music/t/part.wav") is False
