"""P6-B-C2 + 阶段 B：成品时长硬下限 + operation 功能分链的契约测试。

覆盖本轮锁定的产品决策：
- D1 人声成品实测必须 >= MIN_AUDIO_DURATION_SECONDS（无 ±5s 容差）；阶段 B
  下限由 270 调整为 240（MIN_AUDIO_DURATION_SECONDS 默认值 270 → 240）。
- D2 MAX_AUDIO_DURATION_SECONDS=270 常量保留存档，normalize 只保留下限
  （≥MIN 原样保留：240→240、300→300、600→600），crossfade 补偿只加在第二段上。
- D3 不足/测不到 => 抛 DurationValidationError => 由 ai_music 既有失败路径统一
      failed + refund_generation + refund_generation_credits，绝不做第二套退款。
- 阶段 B 路由：主链不再按 duration 分混链——normal/instrumental 统一走
  chain_for_operation 单次生成 + 统一质量门；continuation 仅保留独立续写入口，
  §六/§七/§九 的 continuation_service 内部契约继续锁定。
- §六/§七 第二段命令值必须是 122。
- §八 provider payload 不动，语言指令在 prompt 层传播。
- §九 provider chain 由路由选一次并注入，continuation 不再自行 selection。

全部 provider / R2 / DB / LLM 均为 fake 或注入替身；禁止任何真实外部调用。
"""

import pathlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.services.continuation_service as cont_mod
from app.services.continuation_service import (
    CROSSFADE_DURATION,
    DurationValidationError,
    continuation_service,
)
from app.services import ai_limits
from app.routers import ai_music


# ─────────────────────────────────────────────────────────────────────────────
# D1：duration 归一化（阶段 B：只保留下限，低于 MIN 抬到 MIN；≥MIN 原样保留）
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, 240), (0, 240), (-1, 240), (5, 240), (60, 240), (120, 240), (180, 240),
        (240, 240), (269, 269), (270, 270), (271, 271), (300, 300),
        ("abc", 240), (270.7, 270),
    ],
)
def test_c2_normalize_audio_duration_is_deterministic_and_never_raises(raw, expected):
    out = ai_limits.normalize_audio_duration(raw)
    assert out == expected
    assert out >= ai_limits.MIN_AUDIO_DURATION_SECONDS   # 永不越过下限
    # 确定性：同一输入两次调用结果一致，且不抛异常
    assert ai_limits.normalize_audio_duration(raw) == out


def test_c2_min_and_max_constants_phase_b():
    assert ai_limits.MAX_AUDIO_DURATION_SECONDS == 270   # 存档常量保留（已退出 normalize）
    assert ai_limits.MIN_AUDIO_DURATION_SECONDS == 240   # 阶段 B：270 → 240
    # 计费口径未被阶段 B 改动：>120 => weight 2，<=120 => 1
    assert ai_limits.get_duration_weight(270) == 2
    assert ai_limits.get_duration_weight(120) == 1


# ─────────────────────────────────────────────────────────────────────────────
# continuation 侧夹具：注入 provider chain + 桩掉所有重 IO
# ─────────────────────────────────────────────────────────────────────────────
class FakeProvider:
    provider_type = "api"
    capabilities = ["text_to_music"]
    production = True
    max_duration = 300
    gpu = "none"

    def __init__(self, name):
        self.name = name
        self.requests = []

    async def generate(self, request: dict) -> dict:
        self.requests.append(dict(request))
        return {"success": False, "error": "不该被真实调用"}


@pytest.fixture()
def ok_provider(tmp_path):
    """返回一个每次生成都写出真实临时 wav 文件、并记录 payload 的 provider。"""
    counter = {"n": 0}

    class Ok(FakeProvider):
        async def generate(self, request: dict) -> dict:
            self.requests.append(dict(request))
            counter["n"] += 1
            p = tmp_path / f"seg{counter['n']}.wav"
            p.write_bytes(b"RIFFfake")
            return {"success": True, "volume_files": {"full_wav": p.name, "_local_path": str(p)}}

    return Ok("injected-a")


@pytest.fixture()
def stub_heavy_io(monkeypatch, tmp_path):
    """桩掉参考段/拼接/R2 上传/实测以外的重 IO，返回可断言的上传记录。"""
    combined = tmp_path / "combined.wav"
    combined.write_bytes(b"RIFFfake")
    monkeypatch.setattr(
        cont_mod.task_store, "update", lambda *a, **k: None
    )
    monkeypatch.setattr(
        continuation_service, "_prepare_continuation_context",
        AsyncMock(return_value=("cmViZA==", {"bpm": 120, "key": "C major"})),
    )
    monkeypatch.setattr(continuation_service, "_continue_lyrics", AsyncMock(return_value="ly2"))
    monkeypatch.setattr(
        continuation_service, "_stitch_with_crossfade", AsyncMock(return_value=str(combined))
    )
    parts = MagicMock()
    parts.return_value = {}
    monkeypatch.setattr(continuation_service, "_upload_parts", AsyncMock(side_effect=parts))
    final = AsyncMock(return_value={"full_wav": f"music/t/full_wav.wav"})
    monkeypatch.setattr(continuation_service, "_upload_final", final)
    return SimpleNamespace(combined=combined, parts=parts, final=final)


def _registry_booms():
    raise AssertionError("已注入 provider_chain 时不得再解析全局 registry")


def _write_real_wav(path, seconds: float = 0.5, rate: int = 8000) -> str:
    """写一个可被 ffmpeg 解码的最小正弦 WAV（C3-5-C：_upload_and_finalize 会对
    WAV 源做 MP3 转码，桩位文件必须是真 RIFF/WAVE）。"""
    import math
    import struct
    import wave

    n = int(seconds * rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / rate)))
            for i in range(n)
        )
        w.writeframes(frames)
    return str(path)


async def _run_long(provider_chain, measured, monkeypatch, **kw):
    monkeypatch.setattr(
        continuation_service, "_measure_final_duration",
        AsyncMock(return_value=measured) if not isinstance(measured, Exception) else AsyncMock(side_effect=measured),
    )
    params = dict(prompt="p", style="pop", duration=270, lyrics="ly",
                  task_id="t-c2", user_key="u-c2", provider_chain=provider_chain)
    params.update(kw)
    return await continuation_service.generate_long_music(**params)


# ─────────────────────────────────────────────────────────────────────────────
# §七/§六：第二段命令值 = 122，且 target 未被 +crossfade
# ─────────────────────────────────────────────────────────────────────────────
async def test_c2_second_segment_commanded_duration_is_122(ok_provider, stub_heavy_io, monkeypatch, tmp_path):
    await _run_long([ok_provider], 270.5, monkeypatch)
    flags = [(r.get("duration"), bool(r.get("enable_audio2audio"))) for r in ok_provider.requests]
    assert flags[0] == (150, False), "首段必须是 150"
    assert flags[1] == (122, True), f"第二段必须是 122（ceil(270-150+1.5)），实得 {flags[1]}"
    # target 绝不能被抬到 271.5：两段命令值之和 = 272，扣掉 crossfade 才是 270.5
    assert flags[0][0] + flags[1][0] == 272
    assert CROSSFADE_DURATION == 1.5


# ─────────────────────────────────────────────────────────────────────────────
# D1 硬闸：270.0/240.0 通过 / 239.9 失败 / 测不到 失败，且失败时绝不上传最终成品
# ─────────────────────────────────────────────────────────────────────────────
async def test_c2_gate_passes_at_exactly_270(ok_provider, stub_heavy_io, monkeypatch):
    result = await _run_long([ok_provider], 270.0, monkeypatch)
    assert result["success"] is True
    assert result["volume_files"]["_measured_duration_sec"] == 270.0
    # C3-5-A：达标也不再由 continuation 执行 final PUT（唯一 owner = route._upload_and_finalize）
    stub_heavy_io.final.assert_not_called()
    assert "manifest" not in result, "不得返回未真实上传的 final manifest"


async def test_c2_gate_passes_at_exactly_240(ok_provider, stub_heavy_io, monkeypatch):
    """阶段 B 边界：240.0 == MIN 恰好通过，不截断。"""
    result = await _run_long([ok_provider], 240.0, monkeypatch)
    assert result["success"] is True
    assert result["volume_files"]["_measured_duration_sec"] == 240.0
    stub_heavy_io.final.assert_not_called()


async def test_c2_gate_fails_at_239_9_and_skips_final_upload(ok_provider, stub_heavy_io, monkeypatch):
    with pytest.raises(DurationValidationError) as ei:
        await _run_long([ok_provider], 239.9, monkeypatch)
    assert "239" in str(ei.value) and "240" in str(ei.value)   # 错误文本必须带实测值与门槛
    stub_heavy_io.final.assert_not_called()                    # 短音频绝不交付


async def test_c2_gate_fails_when_duration_cannot_be_measured(ok_provider, stub_heavy_io, monkeypatch):
    # N1：测不到 == 不合规；且不得被吞成 warning
    with pytest.raises(DurationValidationError):
        await _run_long([ok_provider], RuntimeError("librosa cannot decode"), monkeypatch)
    stub_heavy_io.final.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# P6-B-C3-5-A：final PUT 唯一 owner + 成功路径 PUT 总数 = 4（非 6）
# ─────────────────────────────────────────────────────────────────────────────
async def test_c3_5_a_success_total_puts_is_4_single_final_owner(
    ok_provider, monkeypatch, tmp_path
):
    """真实 _upload_parts/_upload_final 桩位下，成功 continuation + route 收尾恰 4 次 PUT：
    part1=1 + part2=1 + route final=2；continuation 侧 final PUT=0、不返回 manifest。"""
    monkeypatch.setattr(cont_mod.task_store, "update", lambda *a, **k: None)
    monkeypatch.setattr(
        continuation_service, "_prepare_continuation_context",
        AsyncMock(return_value=("cmViZA==", {"bpm": 120, "key": "C major"})),
    )
    monkeypatch.setattr(continuation_service, "_continue_lyrics", AsyncMock(return_value="ly2"))
    # C3-5-C：A1 走真实 _upload_and_finalize → 需要可被 ffmpeg 转码的真 WAV
    combined = tmp_path / "combined.wav"
    _write_real_wav(combined)
    monkeypatch.setattr(continuation_service, "_stitch_with_crossfade", AsyncMock(return_value=str(combined)))
    monkeypatch.setattr(continuation_service, "_measure_final_duration", AsyncMock(return_value=270.5))

    final_mock = AsyncMock(return_value={"full_wav": "music/should/not/happen.wav"})
    monkeypatch.setattr(continuation_service, "_upload_final", final_mock)

    from app.services.cdn_uploader import cdn_uploader

    puts = []

    async def _pkg(task_id, files):
        puts.append((task_id, tuple(files)))
        return {logical: f"music/{task_id}/{logical}.wav" for logical in files}

    monkeypatch.setattr(cdn_uploader, "upload_music_package", _pkg)
    monkeypatch.setattr(
        cdn_uploader, "get_presigned_download_url",
        lambda key, expires_in=600: f"https://signed/{key}",
    )

    result = await continuation_service.generate_long_music(
        prompt="p", style="pop", duration=270, lyrics="ly",
        task_id="t-c35a", user_key="u-c35a", provider_chain=[ok_provider],
    )

    # continuation 侧：只有 part1 + part2，各 1 次 PUT；final PUT = 0
    assert puts == [
        ("t-c35a_part1", ("part1_wav",)),
        ("t-c35a_part2", ("part2_wav",)),
    ]
    final_mock.assert_not_called()
    assert "manifest" not in result
    assert result["volume_files"]["_measured_duration_sec"] == 270.5
    assert result["volume_files"]["_local_path"] == str(combined)

    # route 侧唯一 final owner：_upload_and_finalize 恰好 2 次 PUT（full_wav + full_mp3）
    await ai_music._upload_and_finalize("t-c35a", result["volume_files"])
    total_puts = sum(len(files) for _, files in puts)
    assert total_puts == 4, f"成功路径 PUT 总数必须是 4，实得 {total_puts}: {puts}"
    assert puts[2] == ("t-c35a", ("full_wav", "full_mp3"))
    assert sum(1 for _, files in puts for k in files if k == "full_wav") == 1, "full_wav 恰好上传 1 次"
    assert sum(1 for _, files in puts for k in files if k == "full_mp3") == 1, "full_mp3 恰好上传 1 次"


async def test_c3_5_a_stitch_failure_skips_final_upload(ok_provider, stub_heavy_io, monkeypatch):
    monkeypatch.setattr(
        continuation_service, "_stitch_with_crossfade",
        AsyncMock(side_effect=RuntimeError("ffmpeg boom")),
    )
    with pytest.raises(RuntimeError, match="ffmpeg"):
        await _run_long([ok_provider], 270.5, monkeypatch)
    stub_heavy_io.final.assert_not_called()
    # fixture 里 parts 是 _upload_parts 背后的 side_effect MagicMock：按 call_count 断言
    assert stub_heavy_io.parts.call_count == 2, "part 上传按既有顺序先于 stitch（保留现状）"


async def test_c2_measurement_seam_does_not_swallow_exceptions(monkeypatch):
    class Boom:
        @staticmethod
        def get_duration(*a, **k):
            raise ValueError("decode failed")
    monkeypatch.setitem(__import__("sys").modules, "librosa", Boom)
    with pytest.raises(ValueError):
        await continuation_service._measure_final_duration("whatever.wav")


# ─────────────────────────────────────────────────────────────────────────────
# §九：chain 注入生效（continuation 不再自行 selection）
# ─────────────────────────────────────────────────────────────────────────────
async def test_c2_injected_chain_is_used_and_registry_not_consulted(
    ok_provider, stub_heavy_io, monkeypatch
):
    import app.services.provider_registry as pr
    monkeypatch.setattr(pr, "get_provider_registry", _registry_booms)
    other = FakeProvider("injected-b")
    result = await _run_long([ok_provider, other], 271.0, monkeypatch)
    assert result["provider"] == "injected-a+continuation"
    assert other.requests == []                      # 第一家成功就不碰第二家


# ─────────────────────────────────────────────────────────────────────────────
# 路由层（阶段 B）：operation 功能分链单次生成 + 统一质量门 + D3 退款冒泡
# ─────────────────────────────────────────────────────────────────────────────
class OkProvider(FakeProvider):
    """恒成功：返回带预实测时长的 volume_files，让质量门直接采信（不触 librosa）。"""
    measured = 245.0

    async def generate(self, request: dict) -> dict:
        self.requests.append(dict(request))
        return {
            "success": True,
            "volume_files": {
                "full_wav": "out.wav",
                "_local_path": "out.wav",
                "_measured_duration_sec": self.measured,
            },
            "provider": self.name,
        }


@pytest.fixture()
def route_env(monkeypatch):
    """把路由依赖的 DB / 计费 / R2 / LLM / HF 全部换成替身；返回可断言的记录器。"""
    monkeypatch.delenv("AI_GENERATION_PROVIDER", raising=False)  # 默认走 chain_for_operation
    store = MagicMock()
    store.get.return_value = {"generation_quota_weight": 2}
    monkeypatch.setattr(ai_music, "task_store", store)
    reg = MagicMock()
    y, t, m = OkProvider("yinchao"), OkProvider("tempolor"), OkProvider("mureka")
    reg.chain_for_operation.side_effect = lambda op, song_language=None: (
        [y, m] if op == "instrumental" else [y, t]
    )
    reg.get.side_effect = lambda name: {"yinchao": y, "tempolor": t, "mureka": m}.get(name)
    monkeypatch.setattr(ai_music, "get_provider_registry", lambda: reg)
    monkeypatch.setattr(
        ai_music.agnes_service, "generate_song",
        AsyncMock(return_value=SimpleNamespace(optimized_prompt="prompt-x", generated_lyrics="la la")),
    )
    monkeypatch.setattr(ai_music, "_log_generation_cost", lambda *a, **k: None)
    monkeypatch.setattr(ai_music, "_upload_and_finalize", AsyncMock(return_value=None))
    monkeypatch.setattr(ai_music, "refund_generation", MagicMock(return_value={"refunded": True}))
    monkeypatch.setattr(ai_music.credits_service, "refund_generation_credits",
                        MagicMock(return_value={"success": True}))
    # HF 为 development 兜底：测试里恒 None，避免任何真实外呼
    monkeypatch.setattr(ai_music, "_try_hf_ace_step_fallback", AsyncMock(return_value=None))
    return SimpleNamespace(store=store, reg=reg, y=y, t=t, m=m)


async def _drive_route(monkeypatch, **req_kw):
    """跑一次 _run_generation；返回 continuation mock 供断言「主链绝不进续写」。"""
    from app.services.continuation_service import continuation_service as _cont
    cont_mock = AsyncMock(return_value={"success": True, "volume_files": {}})
    monkeypatch.setattr(_cont, "generate_long_music", cont_mock)
    params = {"prompt": "a song", "style": "pop", "type": "song"}
    params.update(req_kw)
    req = ai_music.GenerateRequest(**params)
    await ai_music._run_generation("task-c2", req, "uA", 2)
    return cont_mock


async def test_c2_route_human_generation_uses_operation_chain(route_env, monkeypatch):
    cont_mock = await _drive_route(monkeypatch, duration=60, song_language="zh")

    cont_mock.assert_not_called()                               # 阶段 B：主链绝不进 continuation
    route_env.reg.chain_for_operation.assert_called_once_with("normal", song_language="zh")
    route_env.reg.select.assert_not_called()                    # 未设显式 provider env → 不走单跳
    # 显式设定一个 <MIN 的入参：归一化抬到 240，仍单次生成、不得 4xx
    assert route_env.y.requests[0]["duration"] == 240
    assert route_env.y.requests[0]["operation"] == "normal"
    assert route_env.y.requests[0]["song_language"] == "zh"     # 语言随 provider payload 传播
    assert route_env.t.requests == []                           # 链首成功 → 绝不碰下一家
    assert any(c.kwargs.get("ai_provider") == "agnes+yinchao"
               for c in route_env.store.update.call_args_list)
    ai_music._upload_and_finalize.assert_awaited_once()         # 达标成品走既有上传/收尾


async def test_c2_route_instrumental_stays_on_operation_chain(route_env, monkeypatch):
    y_fail = FakeProvider("yinchao")                              # 链首失败 → 换链尾
    route_env.reg.chain_for_operation.side_effect = lambda op, song_language=None: [y_fail, route_env.m]
    cont_mock = await _drive_route(monkeypatch, duration=240, instrumental=True)

    cont_mock.assert_not_called()                               # 器乐绝不进 continuation
    route_env.reg.chain_for_operation.assert_called_once_with("instrumental", song_language=None)
    assert len(y_fail.requests) == 1 + ai_limits.MAX_AUTO_RETRIES  # 按既有策略打满再换家
    assert route_env.m.requests, "instrumental 链第二跳必须是 mureka"
    assert route_env.m.requests[0]["is_instrumental"] is True
    assert route_env.m.requests[0]["operation"] == "instrumental"
    assert route_env.t.requests == [], "instrumental 绝不进入 TemPolor"
    route_env.reg.select.assert_not_called()


async def test_c2_route_short_final_uses_existing_full_refund_path(route_env, monkeypatch):
    short = OkProvider("yinchao")
    short.measured = 239.0                                      # 低于 MIN=240 → 质量门拒绝
    route_env.reg.chain_for_operation.side_effect = lambda op, song_language=None: [short, route_env.t]
    await _drive_route(monkeypatch, duration=240)

    route_env.store.update.assert_any_call(
        "task-c2", state="failed",
        error="DurationValidationError: final duration 239.0s is below minimum 240s",
    )
    ai_music.refund_generation.assert_called_once()
    kw = ai_music.refund_generation.call_args
    assert kw.kwargs["task_id"] == "task-c2"
    assert kw.kwargs["weight"] == 2
    assert kw.kwargs["reason"] == "provider_failed"        # 复用既有 reason，不新增退款语义
    ai_music.credits_service.refund_generation_credits.assert_called_once_with("uA", "task-c2")
    # 短音频不得被交付：最终上传/完成状态写入都没发生
    ai_music._upload_and_finalize.assert_not_called()
    assert all(c.kwargs.get("state") != "completed"
               and c.kwargs.get("state") != "completed_with_stems_failed"
               for c in route_env.store.update.call_args_list)


async def test_c2_route_missing_provider_result_fails_without_delivery(route_env, monkeypatch):
    y, t = FakeProvider("yinchao"), FakeProvider("tempolor")   # 恒失败（retryable）
    route_env.reg.chain_for_operation.side_effect = lambda op, song_language=None: [y, t]
    await _drive_route(monkeypatch, duration=240)

    assert y.requests and t.requests, "链首打满重试后应切到链尾"
    assert ai_music.refund_generation.call_count == 1          # 恰好一次退款（含 HF 返回 None）
    ai_music.credits_service.refund_generation_credits.assert_called_once_with("uA", "task-c2")
    assert not any("completed" in str(c) for c in route_env.store.update.call_args_list)
