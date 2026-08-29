"""tts_client + voice_clone_task 本地静态/单元测试（不触碰真实 Modal / GPU / R2）。

通过 sys.modules 注入假 modal / 假 cdn_uploader，验证：
  1. tts_client 引用正确的 Modal App 名与函数名（synthesize_cloned）
  2. 参考音频统一写入卷 /refs/{voice_id}，生成结果从 /generated/ 取回（目录分离）
  3. QueueFullError 语义：modal 队列满 -> 抛出 QueueFullError（不吞掉）
  4. voice_clone_task 编排链：processing -> generating -> uploading -> completed
  5. 失败路径：QueueFullError / 超时 / 其它异常 -> failed + 释放用户锁
  6. 参考音频命名恒为 refs/{voice_id}.wav（与 ai_music 的 refs 约定一致）
"""

import asyncio
import struct
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]


def _wav_bytes(seconds: float = 0.1, rate: int = 8000) -> bytes:
    """构造最小合法 16-bit PCM WAV（mono），满足 ASR 参考音频校验。"""
    n_frames = int(rate * seconds)
    data = b"\x00\x00" * n_frames
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
    return (
        b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
        + b"fmt " + struct.pack("<I", 16) + fmt
        + b"data" + struct.pack("<I", len(data)) + data
    )


_WAV = _wav_bytes()


class _FakeVolume:
    def __init__(self, name: str = ""):
        self.name = name
        self._added: list[tuple[str, str]] = []
        self._files: dict[str, bytes] = {}

    @classmethod
    def from_name(cls, name: str):
        return cls(name=name)

    def add_local_file(self, local_path: str, remote_path: str):
        self._added.append((local_path, remote_path))
        if Path(local_path).exists():
            self._files[remote_path] = Path(local_path).read_bytes()

    def commit(self):
        pass

    def read_file(self, remote_path: str):
        data = self._files.get(remote_path, b"")
        yield data


class _FakeFunction:
    def __init__(self, *, remote_result=None, raise_queue_full=False, raise_other=None):
        self.remote_result = remote_result
        self.raise_queue_full = raise_queue_full
        self.raise_other = raise_other
        self.calls: list[tuple] = []

    def remote(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.raise_queue_full:
            raise RuntimeError("503 ... queue is full")
        if self.raise_other:
            raise self.raise_other
        return self.remote_result


_FAKE_MODAL_INSTANCE: "_FakeModal | None" = None


class _FakeModal:
    def __init__(self):
        global _FAKE_MODAL_INSTANCE
        _FAKE_MODAL_INSTANCE = self
        self.volumes: dict[str, _FakeVolume] = {}
        self.functions: dict[str, _FakeFunction] = {}
        self.module_installed = True
        import types
        exc_mod = types.ModuleType("modal.exception")
        exc_mod.RetryError = type("RetryError", (Exception,), {})
        self.exception = exc_mod

    class Volume:
        @staticmethod
        def from_name(name: str):
            inst = _FAKE_MODAL_INSTANCE
            if inst is not None and name in inst.volumes:
                return inst.volumes[name]
            return _FakeVolume(name=name)

    class Function:
        @staticmethod
        def from_name(app: str, fn: str):
            inst = _FAKE_MODAL_INSTANCE
            if inst is not None and fn in inst.functions:
                return inst.functions[fn]
            return _FakeFunction()


def _install_fake_modal(fake: _FakeModal):
    sys.modules["modal"] = fake
    sys.modules["modal.exception"] = fake.exception


def _uninstall_fake_modal():
    sys.modules.pop("modal", None)
    sys.modules.pop("modal.exception", None)


def _fresh_modules():
    for name in ("app.services.tts_client", "app.services.voice_clone_task"):
        sys.modules.pop(name, None)


# ═══════════════════════════════════════════════════════════════════
# 桩：cdn_uploader / task_store / manager
# ═══════════════════════════════════════════════════════════════════

class _FakeCDNUploader:
    def __init__(self):
        self.uploads: list[tuple[str, dict]] = []

    async def upload_music_package(self, task_id: str, files: dict[str, str]) -> dict[str, str]:
        self.uploads.append((task_id, files))
        return {k: f"music/{task_id}/{k}" for k in files}

    def get_presigned_download_url(self, key: str, expires_in: int = 600) -> str:
        return f"https://signed.example/{key}?x=1"


def _install_stubs(cdn: _FakeCDNUploader):
    sys.modules["app.services.cdn_uploader"] = types = _make_module({
        "cdn_uploader": cdn,
    })
    return types


def _make_module(attrs: dict):
    import types
    mod = types.ModuleType("fake_stub")
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


@pytest.fixture()
def fake_modal():
    fake = _FakeModal()
    _install_fake_modal(fake)
    yield fake
    _uninstall_fake_modal()


@pytest.fixture()
def stubs():
    cdn = _FakeCDNUploader()
    sys.modules["app.services.cdn_uploader"] = _make_module({"cdn_uploader": cdn})
    yield cdn
    sys.modules.pop("app.services.cdn_uploader", None)


def _load_tts(fake: _FakeModal):
    import app.services.tts_client as tts
    return tts


def _load_task():
    import app.services.voice_clone_task as vct
    return vct


# ═══════════════════════════════════════════════════════════════════
# tts_client 测试
# ═══════════════════════════════════════════════════════════════════

def test_tts_app_and_function_names(fake_modal):
    _fresh_modules()
    tts = _load_tts(fake_modal)
    assert tts._TTS_APP_NAME == "avireon-music-platform-gptsovits"
    assert tts._DATA_VOLUME_NAME == "avireon-music-platform-data-v1"
    assert tts._REF_DIR == "/refs"
    assert tts._GENERATED_DIR == "/generated"


def test_upload_ref_audio_goes_to_refs_and_commits(fake_modal, tmp_path):
    _fresh_modules()
    tts = _load_tts(fake_modal)
    tts._WRITE_COMMIT_WAIT = 0
    vol = _FakeVolume()
    fake_modal.volumes["avireon-music-platform-data-v1"] = vol

    ref = tmp_path / "voice_abc.wav"
    ref.write_bytes(b"\x00" * 1024)

    result = asyncio.run(tts.upload_ref_audio("voice_abc", ref.read_bytes()))
    assert result == "voice_abc.wav"
    assert any("refs/voice_abc.wav" in rp for _, rp in vol._added)
    assert any("generated" in rp for _, rp in vol._added) is False


def test_synthesize_cloned_passes_prompt_text(fake_modal):
    _fresh_modules()
    tts = _load_tts(fake_modal)
    fn = _FakeFunction(remote_result={"wav": "voice_abc.wav"})
    fake_modal.functions["synthesize_cloned"] = fn

    result = asyncio.run(tts.synthesize_cloned(
        ref_filename_in_volume="voice_abc.wav",
        text="你好",
        language="zh",
        prompt_text="参考转写",
        prompt_language="zh",
    ))
    assert result == {"wav": "voice_abc.wav"}
    assert fn.calls, "modal Function.remote 必须被调用"


def test_synthesize_cloned_queue_full_raises(fake_modal):
    _fresh_modules()
    tts = _load_tts(fake_modal)
    from app.services.ace_step_client import QueueFullError
    fake_modal.functions["synthesize_cloned"] = _FakeFunction(raise_queue_full=True)

    with pytest.raises(QueueFullError):
        asyncio.run(tts.synthesize_cloned(
            ref_filename_in_volume="voice_abc.wav",
            text="你好",
            language="zh",
        ))


def test_synthesize_cloned_generic_failure_returns_none(fake_modal):
    _fresh_modules()
    tts = _load_tts(fake_modal)
    fake_modal.functions["synthesize_cloned"] = _FakeFunction(
        raise_other=RuntimeError("boom"),
    )

    result = asyncio.run(tts.synthesize_cloned(
        ref_filename_in_volume="voice_abc.wav",
        text="你好",
        language="zh",
    ))
    assert result is None


# ═══════════════════════════════════════════════════════════════════
# voice_clone_task 测试
# ═══════════════════════════════════════════════════════════════════

def _patch_task_deps(fake_modal, cdn, *, volume_files=None):
    """给 voice_clone_task 注入：tts_client 的 modal 依赖 + cdn_uploader + 参考音频下载。"""
    _fresh_modules()
    tts = _load_tts(fake_modal)

    vol = _FakeVolume()
    fake_modal.volumes["avireon-music-platform-data-v1"] = vol
    if volume_files:
        vol._files = volume_files

    fn = _FakeFunction(remote_result={"wav": "voice_abc.wav"})
    fake_modal.functions["synthesize_cloned"] = fn

    sys.modules["app.services.cdn_uploader"] = _make_module({"cdn_uploader": cdn})
    return tts, fn, vol


def test_voice_clone_success_chain(fake_modal, stubs, tmp_path):
    """成功路径：processing -> generating -> uploading -> completed，并释放锁。"""
    import app.services.task_store as ts
    cdn = stubs
    ref_wav = tmp_path / "ref.wav"
    ref_wav.write_bytes(_WAV)

    _fresh_modules()
    _tts, _fn, _vol = _patch_task_deps(fake_modal, cdn)

    # 参考音频下载 stub：让 _fetch_ref_audio 返回 bytes
    import app.services.voice_clone_task as vct
    async def fake_fetch(url: str):
        return ref_wav.read_bytes()
    vct._fetch_ref_audio = fake_fetch

    # 生成结果本地文件 stub：download_generated 返回一个临时 wav
    async def fake_download(fname, dest_dir=None):
        out = Path(dest_dir or tmp_path) / fname
        out.write_bytes(_WAV)
        return str(out)
    vct.download_generated = fake_download

    task_id = ts.new_task(user_key="userA")
    assert ts.acquire_lock("userA", task_id)

    asyncio.run(vct.run_voice_clone(
        task_id=task_id,
        voice_id="voice_abc",
        text="你好",
        audio_url="https://example.com/ref.wav",
        language="zh",
        prompt_text="参考转写",
        prompt_language="zh",
    ))

    task = ts.get(task_id)
    assert task["state"] == "completed"
    assert task["progress"] == 100
    assert task["audio_url"], "完成时必须签发可播放 URL"
    assert cdn.uploads, "生成音频必须上传 R2"
    assert ts.is_user_busy("userA") is False, "完成后必须释放用户锁"


def test_voice_clone_ref_naming_in_volume(fake_modal, stubs, tmp_path):
    """参考音频必须进入共享卷 refs/{voice_id}.wav 而非 generated。"""
    import app.services.task_store as ts
    cdn = stubs
    _fresh_modules()
    tts, _fn, vol = _patch_task_deps(fake_modal, cdn)

    import app.services.voice_clone_task as vct
    async def fake_fetch(url: str):
        return _WAV
    vct._fetch_ref_audio = fake_fetch
    tts._WRITE_COMMIT_WAIT = 0

    async def fake_download(fname, dest_dir=None):
        out = Path(dest_dir or tmp_path) / fname
        out.write_bytes(_WAV)
        return str(out)
    vct.download_generated = fake_download

    task_id = ts.new_task(user_key="userB")
    ts.acquire_lock("userB", task_id)

    # 成功调用后会写 refs 卷并 commit（upload_ref_audio 内部完成）
    asyncio.run(vct.run_voice_clone(
        task_id=task_id,
        voice_id="voice_xyz",
        text="你好",
        audio_url="https://example.com/ref.wav",
        prompt_text="参考转写",
        prompt_language="zh",
    ))
    assert any("refs/voice_xyz.wav" in rp for _, rp in vol._added)
    assert ts.get(task_id)["state"] == "completed"


def test_voice_clone_queue_full_fails_and_unlocks(fake_modal, stubs):
    """QueueFullError -> failed + 释放用户锁。"""
    import app.services.task_store as ts
    cdn = stubs
    _fresh_modules()
    _tts, _fn, _vol = _patch_task_deps(fake_modal, cdn)

    fake_modal.functions["synthesize_cloned"] = _FakeFunction(raise_queue_full=True)

    import app.services.voice_clone_task as vct
    async def fake_fetch(url: str):
        return _WAV
    vct._fetch_ref_audio = fake_fetch

    task_id = ts.new_task(user_key="userC")
    ts.acquire_lock("userC", task_id)

    asyncio.run(vct.run_voice_clone(
        task_id=task_id,
        voice_id="voice_abc",
        text="你好",
        audio_url="https://example.com/ref.wav",
        prompt_text="参考转写",
        prompt_language="zh",
    ))
    task = ts.get(task_id)
    assert task["state"] == "failed"
    assert task["error"]
    assert ts.is_user_busy("userC") is False


def test_voice_clone_generic_error_fails_and_unlocks(fake_modal, stubs):
    """通用异常 -> failed + 释放用户锁。"""
    import app.services.task_store as ts
    cdn = stubs
    _fresh_modules()
    _tts, _fn, _vol = _patch_task_deps(fake_modal, cdn)

    import app.services.voice_clone_task as vct
    async def fake_fetch(url: str):
        raise RuntimeError("参考音频不可用")
    vct._fetch_ref_audio = fake_fetch

    task_id = ts.new_task(user_key="userD")
    ts.acquire_lock("userD", task_id)

    asyncio.run(vct.run_voice_clone(
        task_id=task_id,
        voice_id="voice_abc",
        text="你好",
        audio_url="https://example.com/ref.wav",
    ))
    task = ts.get(task_id)
    assert task["state"] == "failed"
    assert ts.is_user_busy("userD") is False


# ═══════════════════════════════════════════════════════════════════
# ASR 集成：ASR 结果透传 GPT-SoVITS / ASR 失败阻止调用
# ═══════════════════════════════════════════════════════════════════

class _FakeSeg:
    def __init__(self, text: str):
        self.text = text


class _FakeAsrInfo:
    def __init__(self, language: str):
        self.language = language


class _FakeAsrModel:
    def __init__(self, *, text="你好转写", language="zh", error=None):
        self.text = text
        self.language = language
        self.error = error

    def transcribe(self, audio, **kwargs):
        if self.error:
            raise self.error
        return iter([_FakeSeg(self.text)]), _FakeAsrInfo(self.language)


def _inject_fake_asr(model=None):
    from app.services import asr_client
    asr_client._model = model


def test_voice_clone_asr_passes_prompt_to_gptsovits(fake_modal, stubs, tmp_path):
    """未显式提供 prompt_text/prompt_language 时，ASR 结果透传 synthesize_cloned。"""
    import app.services.task_store as ts
    from app.services import asr_client
    cdn = stubs

    _fresh_modules()
    _tts, fn, _vol = _patch_task_deps(fake_modal, cdn)
    _inject_fake_asr(_FakeAsrModel(text="参考音频转写内容", language="zh"))

    import app.services.voice_clone_task as vct
    async def fake_fetch(url: str):
        return _WAV
    vct._fetch_ref_audio = fake_fetch

    async def fake_download(fname, dest_dir=None):
        out = Path(dest_dir or tmp_path) / fname
        out.write_bytes(_WAV)
        return str(out)
    vct.download_generated = fake_download

    task_id = ts.new_task(user_key="userASR")
    ts.acquire_lock("userASR", task_id)

    asyncio.run(vct.run_voice_clone(
        task_id=task_id,
        voice_id="voice_asr",
        text="你好",
        audio_url="https://example.com/ref.wav",
    ))

    task = ts.get(task_id)
    assert task["state"] == "completed"
    assert fn.calls, "GPT-SoVITS 必须被调用"
    args = fn.calls[0][0]
    # synthesize_cloned(ref_filename, text, language, prompt_text, prompt_language, speed, out_stem)
    assert args[3] == "参考音频转写内容"
    assert args[4] == "zh"
    # ASR 结果写回 VoiceSample（供后续克隆复用）
    assert asr_client._model is not None
    asr_client._model = None


def test_voice_clone_asr_failure_blocks_gptsovits(fake_modal, stubs):
    """ASR 失败 -> failed，不得调用 GPT-SoVITS。"""
    import app.services.task_store as ts
    from app.services import asr_client
    cdn = stubs

    _fresh_modules()
    _tts, fn, _vol = _patch_task_deps(fake_modal, cdn)
    asr_client._model = _FakeAsrModel(error=RuntimeError("asr crash"))

    import app.services.voice_clone_task as vct
    async def fake_fetch(url: str):
        return _WAV
    vct._fetch_ref_audio = fake_fetch

    task_id = ts.new_task(user_key="userASRF")
    ts.acquire_lock("userASRF", task_id)

    asyncio.run(vct.run_voice_clone(
        task_id=task_id,
        voice_id="voice_asr_fail",
        text="你好",
        audio_url="https://example.com/ref.wav",
    ))

    task = ts.get(task_id)
    assert task["state"] == "failed"
    assert "转写" in task["error"]
    assert fn.calls == [], "ASR 失败后禁止调用 GPT-SoVITS"
    assert ts.is_user_busy("userASRF") is False
    asr_client._model = None


def test_voice_clone_empty_ref_rejected(fake_modal, stubs):
    """参考音频为空/无效 -> failed，不得调用 GPT-SoVITS。"""
    import app.services.task_store as ts
    cdn = stubs

    _fresh_modules()
    _tts, fn, _vol = _patch_task_deps(fake_modal, cdn)

    import app.services.voice_clone_task as vct
    async def fake_fetch(url: str):
        return b""
    vct._fetch_ref_audio = fake_fetch

    task_id = ts.new_task(user_key="userEMPTY")
    ts.acquire_lock("userEMPTY", task_id)

    asyncio.run(vct.run_voice_clone(
        task_id=task_id,
        voice_id="voice_empty",
        text="你好",
        audio_url="https://example.com/ref.wav",
    ))

    task = ts.get(task_id)
    assert task["state"] == "failed"
    assert fn.calls == [], "参考音频校验失败后禁止调用 GPT-SoVITS"
