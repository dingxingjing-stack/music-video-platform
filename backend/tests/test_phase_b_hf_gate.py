"""P1/P3：HF 兜底产物必须过统一 240s 成品质量门，并纳入 R2 finalize 生命周期。

覆盖（本地桩 + 本地 WAV，绝不真实调用 HF/Provider/任何网络）：
1  HF 产物 239.9s → DurationValidationError → failed、无 R2、quota/credits 各恰一次退款、临时文件清理
2  HF 产物 240.0s → 过门 → 真实 finalize（R2 桩）→ completed*、Melovar 自控预签名 URL 交付、
   远端 HF URL 绝不直接交付、cost 恰一次 success(hf_ace_step)
3  HF 产物 300s / 600s → completed、实测保留原时长不截断为 240/270
4  HF 下载失败（禁止真实 HTTP，走真实 _download_hf_audio）→ failed + 恰好一次退款 + 无 R2
5  HF 全流程绝不二次 reserve；门失败亦不二次 refund
6  _download_hf_audio 单元：非 2xx / HTML 内容 / 过短字节 → None；真 WAV → 本地路径
7  P3 cost 位置：HF 成功 success；下载失败/门失败恰一次 failed、绝无 success
"""

import os
import shutil
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers import ai_music
from app.services import ai_limits
from tests.test_ai_music_flow import isolated_db  # noqa: F401  独立 SQLite + HF 关闭
from tests.test_phase_b_routing import (  # noqa: F401  复用 route/_req/_states 桩体系
    _forbid_http,
    _req,
    _states,
    RecProvider,
    route,
)

HF_URL = "https://ace-step-ace-step.hf.space/file=generated_abc.wav"

# 模块导入时（fixture 尚未运行）捕获原件：route fixture 会把它们换成 Mock
_REAL_FINALIZE = ai_music._upload_and_finalize
_REAL_GATE = ai_music._enforce_duration_gate


# ─────────────────────────────────────────────────────────────────────────────
# 本地 WAV 工具（真实文件 → 真实 librosa 实测，不注入 _measured_duration_sec）
# ─────────────────────────────────────────────────────────────────────────────
def _make_wav(path, seconds, rate=8000) -> str:
    """生成指定时长的静音 WAV（rate 取 8000Hz：任意秒数均整帧，实测值精确）。"""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(round(seconds * rate)))
    return str(path)


def _chain_exhausted(r):
    """链首两次尝试全部失败（MAX_AUTO_RETRIES=1 → 1+1 次）→ 走尽进入 HF 门。"""
    r.set_chain(RecProvider("yinchao", results=[
        {"success": False, "error": "transient down 1"},
        {"success": False, "error": "transient down 2"},
    ]))


def _stub_download(monkeypatch, local: str):
    async def _dl(url):
        return local

    monkeypatch.setattr(ai_music, "_download_hf_audio", _dl)


def _install_r2_stubs(monkeypatch):
    """真实 _upload_and_finalize 所需的网络/转码桩：返回 (uploaded_files 记录)。"""
    async def _fake_transcode(src, dst):
        shutil.copyfile(src, dst)
        return dst

    uploaded = {}

    async def _fake_upload(task_id, files):
        # finalize 仍在执行时（临时文件尚未清理）记录交付文件的真实时长
        uploaded["files"] = dict(files)
        try:
            with wave.open(files["full_wav"]) as w:
                uploaded["dur"] = w.getnframes() / w.getframerate()
        except Exception:  # noqa: BLE001  记录失败由用例断言暴露
            uploaded["dur"] = None
        return {
            "full_wav": f"music/{task_id}/full_wav.wav",
            "full_mp3": f"music/{task_id}/full_mp3.mp3",
        }

    monkeypatch.setattr(ai_music, "_upload_and_finalize", _REAL_FINALIZE)
    monkeypatch.setattr(ai_music, "_transcode_wav_to_mp3", _fake_transcode)
    monkeypatch.setattr(ai_music, "cdn_uploader", SimpleNamespace(
        upload_music_package=AsyncMock(side_effect=_fake_upload),
        get_presigned_download_url=(
            lambda key, expires_in=600, **kw: f"https://cdn.test/{key}?e={expires_in}"
        ),
    ))
    return uploaded


def _cost_mock():
    return ai_music._log_generation_cost


# ─────────────────────────────────────────────────────────────────────────────
# 1) HF 239.9s → 门失败：failed、无 R2、恰一次退款、临时文件清理
# ─────────────────────────────────────────────────────────────────────────────
async def test_hf_239_9_fails_gate_single_refund_no_r2(route, monkeypatch, tmp_path):
    _chain_exhausted(route)
    route.hf.return_value = HF_URL
    local = _make_wav(tmp_path / "hf_239_9.wav", 239.9)
    _stub_download(monkeypatch, local)
    reserve = MagicMock()
    monkeypatch.setattr(ai_limits, "reserve_generation", reserve)

    await ai_music._run_generation("hfgate-239", _req(), "uB", 2)

    route.finalize.assert_not_called(), "门失败绝不能产生 R2 终对象"
    states = _states(route.store)
    assert "failed" in states
    assert "uploading" not in states and "completed" not in states, \
        "门必须在 uploading/completed 之前"
    errs = [c.kwargs.get("error") for c in route.store.update.call_args_list
            if c.kwargs.get("state") == "failed"]
    assert any(e and "DurationValidationError" in str(e) and "below minimum 240" in str(e)
               for e in errs), f"必须走统一 DurationValidationError 路径: {errs}"
    route.refund.assert_called_once()
    assert route.refund.call_args.kwargs["reason"] == "provider_failed"
    assert route.refund.call_args.kwargs["weight"] == 2, "按透传权重退，不重算"
    route.credits.assert_called_once(), "Credits rollback 恰好一次"
    reserve.assert_not_called(), "HF 全流程绝不二次 reserve"
    assert not os.path.exists(local), "HF 临时文件必须清理"
    cost = _cost_mock()
    assert cost.call_count == 1, "P3：门失败恰一次 cost 记录"
    assert cost.call_args.args[3] == "failed"


# ─────────────────────────────────────────────────────────────────────────────
# 2) HF 240.0s → 过门 → 真实 finalize（R2 桩）→ completed + 自控 URL
# ─────────────────────────────────────────────────────────────────────────────
async def test_hf_240_finalizes_r2_delivers_controlled_url(route, monkeypatch, tmp_path):
    _chain_exhausted(route)
    route.hf.return_value = HF_URL
    local = _make_wav(tmp_path / "hf_240.wav", 240.0)
    _stub_download(monkeypatch, local)
    uploaded = _install_r2_stubs(monkeypatch)

    await ai_music._run_generation("hfgate-240", _req(duration=240), "uB", 2)

    finals = [c.kwargs for c in route.store.update.call_args_list if "download" in c.kwargs]
    assert len(finals) == 1, "恰好一次 R2 finalize 收尾"
    assert finals[0]["state"] in ("completed", "completed_with_stems_failed"), \
        "API 层视图即 completed"
    audio_url = finals[0].get("audio_url") or ""
    assert audio_url.startswith("https://cdn.test/music/"), "交付 Melovar 自控预签名 URL"
    assert HF_URL not in audio_url, "远端 HF URL 绝不直接交付"
    assert "uploading" in _states(route.store), "过门后才进入 uploading/R2"
    assert "full_wav" in uploaded["files"], "R2 收到本地成品文件"
    route.refund.assert_not_called()
    route.credits.assert_not_called()
    cost = _cost_mock()
    assert cost.call_count == 1, "P3：成功恰一次 cost"
    assert cost.call_args.args[3] == "success"
    assert cost.call_args.args[2].name == "hf_ace_step"
    assert not os.path.exists(local), "HF 临时文件必须清理"


# ─────────────────────────────────────────────────────────────────────────────
# 3) HF 300s / 600s → completed、实测保留原时长（不截断为 240/270）
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("seconds", [300, 600])
async def test_hf_long_duration_preserved_no_truncation(route, monkeypatch, tmp_path, seconds):
    _chain_exhausted(route)
    route.hf.return_value = HF_URL
    local = _make_wav(tmp_path / f"hfgate_{seconds}.wav", seconds)
    _stub_download(monkeypatch, local)
    uploaded = _install_r2_stubs(monkeypatch)

    gate_seen = []

    async def _spy_gate(volume_result):
        got = await _REAL_GATE(volume_result)
        gate_seen.append(got)
        return got

    monkeypatch.setattr(ai_music, "_enforce_duration_gate", _spy_gate)

    await ai_music._run_generation(f"hfgate-{seconds}", _req(duration=seconds), "uB", 2)

    assert gate_seen == [float(seconds)], "门实测原时长并放行，绝不截断"
    assert uploaded.get("dur") is not None, "R2 收到可读的完整成品文件"
    assert abs(uploaded["dur"] - seconds) < 0.01, "进入 R2 的文件保持完整时长"
    finals = [c.kwargs for c in route.store.update.call_args_list if "download" in c.kwargs]
    assert len(finals) == 1
    assert finals[0]["state"] in ("completed", "completed_with_stems_failed")
    route.refund.assert_not_called()
    assert _cost_mock().call_args.args[3] == "success"
    assert not os.path.exists(local), "HF 临时文件必须清理"


# ─────────────────────────────────────────────────────────────────────────────
# 4) HF 下载失败（真实 _download_hf_audio + 禁止任何 HTTP）→ 统一失败 + 恰一次退款
# ─────────────────────────────────────────────────────────────────────────────
async def test_hf_download_failure_fails_once(route, monkeypatch):
    _chain_exhausted(route)
    route.hf.return_value = HF_URL
    _forbid_http(monkeypatch, ai_music)  # 任何 httpx 连接企图 → 爆炸 → 按 provider failure
    reserve = MagicMock()
    monkeypatch.setattr(ai_limits, "reserve_generation", reserve)

    await ai_music._run_generation("hfdl-fail", _req(), "uB", 2)

    route.hf.assert_awaited_once()
    route.finalize.assert_not_called(), "下载失败绝不产生 R2 终对象"
    assert "failed" in _states(route.store)
    route.refund.assert_called_once()
    assert route.refund.call_args.kwargs["reason"] == "provider_failed"
    route.credits.assert_called_once(), "Credits rollback 恰好一次"
    reserve.assert_not_called()
    cost = _cost_mock()
    assert cost.call_count == 1 and cost.call_args.args[3] == "failed", \
        "P3：下载失败恰一次 failed cost"
    assert not any(c.args[3] == "success" for c in cost.call_args_list)


# ─────────────────────────────────────────────────────────────────────────────
# 5) HF 成功绝不二次 reserve（额度仍只由 generate 入口 reserve 一次）
# ─────────────────────────────────────────────────────────────────────────────
async def test_hf_success_never_second_reserve(route, monkeypatch, tmp_path):
    reserve = MagicMock()
    monkeypatch.setattr(ai_limits, "reserve_generation", reserve)
    _chain_exhausted(route)
    route.hf.return_value = HF_URL
    local = _make_wav(tmp_path / "hf_noreserve.wav", 240.0)
    _stub_download(monkeypatch, local)

    await ai_music._run_generation("hf-noreserve", _req(), "uB", 2)

    reserve.assert_not_called(), "路由/HF 阶段绝不二次占用额度"
    route.finalize.assert_awaited_once()
    route.refund.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 6) _download_hf_audio 单元：非 2xx / HTML / 过短 → None；真 WAV → 本地路径
# ─────────────────────────────────────────────────────────────────────────────
class _StreamResp:
    def __init__(self, status, ctype, body):
        self.status_code = status
        self.headers = {"content-type": ctype}
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def aiter_bytes(self):
        yield self._body


class _StreamClient:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def stream(self, *a, **k):
        return self._resp


@pytest.mark.parametrize("status,ctype,body,expect_none", [
    (500, "audio/wav", b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 2048, True),
    (200, "text/html; charset=utf-8", b"<html>quota page</html>" * 200, True),
    (200, "application/json", b'{"error":"x"}' * 100, True),
    (200, "audio/wav", b"x" * 512, True),
    (200, "audio/wav", None, False),  # body=真 WAV 字节（下方注入）
])
async def test_download_hf_audio_contract(monkeypatch, tmp_path, status, ctype, body, expect_none):
    if body is None:
        wav_path = _make_wav(tmp_path / "ok.wav", 0.25)
        body = open(wav_path, "rb").read()
    resp = _StreamResp(status, ctype, body)
    monkeypatch.setattr(ai_music.httpx, "AsyncClient", lambda *a, **k: _StreamClient(resp))

    out = await ai_music._download_hf_audio("https://hf.space/file=audio.bin")

    if expect_none:
        assert out is None, f"status={status} ctype={ctype} 应判为 provider failure"
    else:
        assert out and os.path.exists(out), "真 WAV 下载成功返回本地路径"
        assert ai_music._is_wav_file(out)
        ai_music._cleanup_hf_temp_file(out)


async def test_download_hf_audio_rejects_bad_url_without_network(monkeypatch):
    """非法/禁用 URL 在建立任何连接之前即判 None（零网络）。"""
    _forbid_http(monkeypatch, ai_music)

    assert await ai_music._download_hf_audio("") is None
    assert await ai_music._download_hf_audio("ftp://evil/x") is None
    assert await ai_music._download_hf_audio("https://soundhelix.com/examples.mp3") is None
