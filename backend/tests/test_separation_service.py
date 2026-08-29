"""Stage 2 第一阶段自动化测试：统一分离接口（MDX + Spleeter fallback）。

覆盖（用户批准的清单）：
  - API contract test（strict 契约 {"success","stems","duration","message"}）
  - 输入 WAV/MP3/不同采样率（Mock 层验证路径与时长）
  - 空文件 / 损坏文件
  - 模型加载失败
  - 超时
  - fallback（MDX 失败 → Spleeter，记录日志与原因）
  - 输出 stem 文件存在性
  - duration 一致性
  - 并发测试
  - 许可审计记录存在性 & 字段完整性

设计：用 Mock 替换 python-audio-separator 的 Separator 与现有 Spleeter 服务，
避免在 CI 下载真实模型权重（权重许可/大小不适合测试环境）。
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.separation.base import (  # noqa: E402
    SEPARATION_CONTRACT_KEYS,
    STEM_NAMES,
    SeparationResult,
)
from app.services.separation.audio_separator_service import AudioSeparatorService  # noqa: E402
from app.services.separation.mdx_separator import MdxSeparator  # noqa: E402
from app.services.separation.spleeter_separator import SpleeterSeparator  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUT_DIR = DATA_DIR / "test_out"


@pytest.fixture()
def wav_file(tmp_path):
    """生成 2 秒真实 WAV（用于时长一致性校验）。"""
    import numpy as np
    import soundfile as sf
    sr = 44100
    t = np.linspace(0, 2.0, int(2.0 * sr), endpoint=False)
    mono = (0.4 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    p = tmp_path / "test.wav"
    sf.write(str(p), mono, sr)
    return p


@pytest.fixture()
def mp3_file(tmp_path):
    """生成 1.5 秒 MP3（若有 ffmpeg）。"""
    import subprocess
    import numpy as np
    import soundfile as sf
    sr = 44100
    t = np.linspace(0, 1.5, int(1.5 * sr), endpoint=False)
    mono = (0.4 * np.sin(2 * np.pi * 330 * t)).astype(np.float32)
    wavp = tmp_path / "src.wav"
    mp3p = tmp_path / "test.mp3"
    sf.write(str(wavp), mono, sr)
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", str(wavp), "-codec:a", "libmp3lame", str(mp3p)],
        capture_output=True,
    )
    if r.returncode != 0 or not mp3p.exists():
        pytest.skip("ffmpeg 不可用，跳过 MP3 用例")
    return mp3p


def _make_mdx_service(tmp_path, **kw):
    """构造 MdxSeparator 并用假 Separator 替换框架（避免下载权重）。"""
    svc = MdxSeparator(output_dir=str(OUT_DIR), model_file_dir=str(DATA_DIR / "models_test"), **kw)

    fake_separator = MagicMock()
    fake_separator.separate.return_value = [
        "out_(Vocals)_UVR_MDXNET_9482.wav",
        "out_(Instrumental)_UVR_MDXNET_9482.wav",
    ]
    # 预写假 stem 文件
    for name in ("out_(Vocals)_UVR_MDXNET_9482.wav", "out_(Instrumental)_UVR_MDXNET_9482.wav"):
        p = OUT_DIR / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\x00" * 100)

    svc._separator = fake_separator
    svc._model_loaded = True
    return svc


# ---------------------------------------------------------------------------
# 1. API contract
# ---------------------------------------------------------------------------

def test_contract_keys_present(wav_file, tmp_path):
    svc = _make_mdx_service(tmp_path)
    res = svc.separate(str(wav_file))
    assert res.success
    assert set(SEPARATION_CONTRACT_KEYS) == set(res.to_contract_dict().keys())
    assert isinstance(res.to_contract_dict()["stems"], list)
    assert isinstance(res.to_contract_dict()["duration"], float)
    assert isinstance(res.to_contract_dict()["message"], str)


def test_contract_no_extra_fields_in_router_view(wav_file, tmp_path):
    """to_contract_dict() 不得泄露审计元数据字段（前端兼容）。"""
    svc = _make_mdx_service(tmp_path)
    res = svc.separate(str(wav_file))
    d = res.to_contract_dict()
    assert set(d.keys()) == set(SEPARATION_CONTRACT_KEYS)
    for k in ("backend", "real_stems", "missing_stems", "fallback_used"):
        assert k not in d


# ---------------------------------------------------------------------------
# 2. 输入格式
# ---------------------------------------------------------------------------

def test_wav_input(wav_file, tmp_path):
    svc = _make_mdx_service(tmp_path)
    res = svc.separate(str(wav_file))
    assert res.success
    assert res.duration == pytest.approx(2.0, abs=0.2)


def test_mp3_input(mp3_file, tmp_path):
    svc = _make_mdx_service(tmp_path)
    res = svc.separate(str(mp3_file))
    assert res.success
    assert res.duration == pytest.approx(1.5, abs=0.3)


def test_16k_mono_input(tmp_path):
    import numpy as np
    import soundfile as sf
    sr = 16000
    t = np.linspace(0, 1.0, int(sr), endpoint=False)
    mono = (0.4 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    p = tmp_path / "mono16.wav"
    sf.write(str(p), mono, sr)
    svc = _make_mdx_service(tmp_path)
    res = svc.separate(str(p))
    assert res.success
    assert res.duration == pytest.approx(1.0, abs=0.2)


# ---------------------------------------------------------------------------
# 3. 空/损坏文件
# ---------------------------------------------------------------------------

def test_empty_file(tmp_path):
    p = tmp_path / "empty.wav"
    p.write_bytes(b"")
    svc = _make_mdx_service(tmp_path)
    res = svc.separate(str(p))
    assert not res.success
    assert "为空" in res.message
    assert res.stems == []


def test_corrupt_file(tmp_path):
    p = tmp_path / "corrupt.wav"
    p.write_bytes(os.urandom(4096))
    svc = _make_mdx_service(tmp_path)
    res = svc.separate(str(p))
    # 损坏文件应返回 failure 而非抛异常 / 崩溃
    assert res.success is False or (res.success and res.duration == 0.0)
    assert isinstance(res.message, str)


def test_missing_file(tmp_path):
    svc = _make_mdx_service(tmp_path)
    res = svc.separate(str(tmp_path / "nope.wav"))
    assert not res.success
    assert "不存在" in res.message


# ---------------------------------------------------------------------------
# 4. 模型加载失败
# ---------------------------------------------------------------------------

def test_model_load_failure(tmp_path):
    svc = MdxSeparator(output_dir=str(OUT_DIR), model_file_dir=str(tmp_path / "m"))
    with patch(
        "app.services.separation.mdx_separator.MdxSeparator._get_separator",
        side_effect=RuntimeError("模型加载失败：corrupt model"),
    ):
        res = svc.separate(str(tmp_path / "x.wav"))
        # 输入文件不存在也会先返回该错误——这里先造个文件
        import numpy as np
        import soundfile as sf
        p = tmp_path / "x.wav"
        sf.write(str(p), np.zeros(44100, dtype=np.float32), 44100)
        res = svc.separate(str(p))
        assert not res.success
        assert "模型加载失败" in res.message


def test_framework_missing(tmp_path):
    """python-audio-separator 未安装时应返回明确 failure。"""
    svc = MdxSeparator(output_dir=str(OUT_DIR), model_file_dir=str(tmp_path / "m"))
    import numpy as np
    import soundfile as sf
    p = tmp_path / "x.wav"
    sf.write(str(p), np.zeros(44100, dtype=np.float32), 44100)
    with patch.dict(sys.modules, {"audio_separator.separator": None}):
        # 强制 ImportError
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name.startswith("audio_separator"):
                raise ImportError("No module named 'audio_separator'")
            return real_import(name, *a, **k)

        with patch("builtins.__import__", side_effect=fake_import):
            res = svc.separate(str(p))
            assert not res.success
            assert "未安装" in res.message


# ---------------------------------------------------------------------------
# 5. 超时
# ---------------------------------------------------------------------------

def test_timeout(tmp_path):
    svc = MdxSeparator(
        output_dir=str(OUT_DIR),
        model_file_dir=str(tmp_path / "m"),
        timeout_seconds=0.05,
    )
    fake = MagicMock()

    def _slow(*a, **k):
        import time
        time.sleep(1.0)
        return []

    fake.separate.side_effect = _slow
    svc._separator = fake
    svc._model_loaded = True
    import numpy as np
    import soundfile as sf
    p = tmp_path / "x.wav"
    sf.write(str(p), np.zeros(44100, dtype=np.float32), 44100)
    res = svc.separate(str(p))
    assert not res.success
    assert "超过" in res.message or "超时" in res.message


# ---------------------------------------------------------------------------
# 6. fallback
# ---------------------------------------------------------------------------

def test_fallback_to_spleeter_on_mdx_failure(wav_file, tmp_path):
    mdx = MagicMock()
    mdx.separate.return_value = SeparationResult.failure("MDX 分离失败：boom", backend="mdx")

    spleeter = MagicMock()
    spleeter.separate.return_value = SeparationResult(
        success=True,
        stems=[str(OUT_DIR / "vocals.wav"), str(OUT_DIR / "drums.wav"),
               str(OUT_DIR / "bass.wav"), str(OUT_DIR / "other.wav")],
        duration=2.0,
        message="Spleeter 分离成功",
        backend="spleeter",
        real_stems=list(STEM_NAMES),
    )
    # 预写 stem 文件
    for n in STEM_NAMES:
        p = OUT_DIR / f"{n}.wav"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\x00" * 50)

    svc = AudioSeparatorService(mdx_backend=mdx, spleeter_backend=spleeter)
    res = svc.separate(str(wav_file))
    assert res.success
    assert res.backend == "spleeter"
    assert res.fallback_used is True
    assert "MDX 失败" in res.fallback_reason
    assert len(res.stems) == 4
    # 校验调用顺序：MDX 先，Spleeter 后
    mdx.separate.assert_called_once()
    spleeter.separate.assert_called_once()


def test_no_fallback_when_disabled(wav_file, tmp_path):
    mdx = MagicMock()
    mdx.separate.return_value = SeparationResult.failure("MDX 失败", backend="mdx")
    spleeter = MagicMock()
    svc = AudioSeparatorService(mdx_backend=mdx, spleeter_backend=spleeter, enable_fallback=False)
    res = svc.separate(str(wav_file))
    assert not res.success
    spleeter.separate.assert_not_called()


def test_force_spleeter_backend(wav_file, tmp_path):
    mdx = MagicMock()
    spleeter = MagicMock()
    spleeter.separate.return_value = SeparationResult(
        success=True, stems=[], duration=2.0, message="ok", backend="spleeter",
    )
    svc = AudioSeparatorService(mdx_backend=mdx, spleeter_backend=spleeter)
    res = svc.separate(str(wav_file), backend="spleeter")
    assert res.backend == "spleeter"
    mdx.separate.assert_not_called()
    spleeter.separate.assert_called_once()


# ---------------------------------------------------------------------------
# 7. stem 文件存在性
# ---------------------------------------------------------------------------

def test_stem_files_exist(wav_file, tmp_path):
    svc = _make_mdx_service(tmp_path)
    res = svc.separate(str(wav_file))
    assert res.success
    for s in res.stems:
        assert Path(s).exists()
        assert Path(s).stat().st_size > 0


def test_stem_semantics_honest(wav_file, tmp_path):
    """MDX 2-stem 必须如实标记 real/missing，不得虚假填 4-stem。"""
    svc = _make_mdx_service(tmp_path)
    res = svc.separate(str(wav_file))
    assert "vocals" in res.real_stems
    assert "instrumental" in res.real_stems
    assert res.derived_stems == ["other"]
    assert set(res.missing_stems) == {"drums", "bass"}


# ---------------------------------------------------------------------------
# 8. duration 一致性
# ---------------------------------------------------------------------------

def test_duration_consistency(wav_file, tmp_path):
    import soundfile as sf
    info = sf.info(str(wav_file))
    svc = _make_mdx_service(tmp_path)
    res = svc.separate(str(wav_file))
    assert res.duration == pytest.approx(info.frames / info.samplerate, abs=0.3)


# ---------------------------------------------------------------------------
# 9. 并发
# ---------------------------------------------------------------------------

def test_concurrent_safety(wav_file, tmp_path):
    svc = _make_mdx_service(tmp_path)
    results = {}
    errors = []

    def _worker(i):
        try:
            results[i] = svc.separate(str(wav_file))
        except Exception as exc:  # noqa: BLE001
            errors.append((i, str(exc)))

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=30)
    assert not any(th.is_alive() for th in threads), "存在未完成线程"
    assert not errors, f"并发异常: {errors}"
    assert all(results[i].success for i in range(4))


# ---------------------------------------------------------------------------
# 10. 许可审计记录
# ---------------------------------------------------------------------------

def test_license_audit_record_exists_and_complete():
    audit_path = Path(__file__).resolve().parents[1] / "app" / "services" / "separation" / "models_license_audit.json"
    assert audit_path.exists(), "必须存在独立许可审计记录"
    data = json.loads(audit_path.read_text(encoding="utf-8"))
    required_fields = {
        "model_name", "model_file", "source", "code_license", "weights_license",
        "training_data", "commercial_confirmation", "redistribution_allowed",
        "attribution_required", "url", "verified_date", "risk", "decision",
    }
    names = {m["model_name"] for m in data["models"]}
    assert "UVR_MDXNET_9482.onnx (MDX-Net)" in names
    for m in data["models"]:
        missing = required_fields - set(m.keys())
        assert not missing, f"{m.get('model_name')} 缺少字段: {missing}"
    # 关键断言：Demucs / MUSDB 系必须是 C（不进生产）
    demucs = next(m for m in data["models"] if "Demucs" in m["model_name"])
    assert demucs["decision"].startswith("C")
    musdb = next(m for m in data["models"] if "MUSDB18HQ" in m["model_name"])
    assert musdb["decision"].startswith("C")