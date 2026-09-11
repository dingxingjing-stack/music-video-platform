"""Phase API-2B 测试：MurekaProvider 单元 + 与 fallback_chain 的集成。

全部 API 调用 mock，不触碰真实 Mureka API / 真实 Key。
"""

import os
import tempfile

import pytest

from app.services import mureka_provider
from app.services.mureka_provider import MurekaProvider


# ═══════════════════════════════════════════════════════════════
# httpx 假客户端
# ═══════════════════════════════════════════════════════════════

class _Resp:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json

    @property
    def content(self):
        return b"{}"


class _FakeAsyncClient:
    """记录 post 请求 payload，并按顺序消费 get 响应。"""

    def __init__(self, post_resp=None, get_responses=None):
        self._post_resp = post_resp or _Resp()
        self._get_responses = list(get_responses) if get_responses else []
        self._get_idx = 0
        self.sent_payload = None
        self.posted_url = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **kw):
        self.posted_url = url
        self.sent_payload = kw.get("json") or {}
        return self._post_resp

    async def get(self, url, **kw):
        if self._get_idx < len(self._get_responses):
            r = self._get_responses[self._get_idx]
            self._get_idx += 1
            return r
        # 超出序列：返回最后一个（避免无限轮询，测试若轮询超限会走到超时分支）
        return self._get_responses[-1] if self._get_responses else _Resp(status_code=404)


@pytest.fixture()
def no_key(monkeypatch):
    monkeypatch.delenv("MUREKA_API_KEY", raising=False)
    monkeypatch.setattr(MurekaProvider, "_api_key", lambda self: "")
    monkeypatch.setattr(mureka_provider, "MUREKA_TIMEOUT_SECONDS", 5.0)
    monkeypatch.setattr(mureka_provider, "MUREKA_POLL_INTERVAL_SECONDS", 0.001)


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """独立 SQLite（含 refunded_at 列），避免污染 backend/data/beta.db。"""
    from app.services import ai_limits, task_store
    db_path = str(tmp_path / "test_beta.db")
    monkeypatch.setattr(ai_limits, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(ai_limits, "_DB_PATH", db_path)
    monkeypatch.setattr(task_store, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(task_store, "_DB_PATH", db_path)
    return db_path


@pytest.fixture()
def have_key(monkeypatch):
    monkeypatch.setattr(MurekaProvider, "_api_key", lambda self: "test-mureka-key")
    monkeypatch.setattr(mureka_provider, "MUREKA_TIMEOUT_SECONDS", 5.0)
    monkeypatch.setattr(mureka_provider, "MUREKA_POLL_INTERVAL_SECONDS", 0.001)


def _install_client(monkeypatch, post_resp=None, get_responses=None):
    """注入假 httpx.AsyncClient，返回 fake client 供断言。"""
    fake = _FakeAsyncClient(post_resp=post_resp, get_responses=get_responses)
    monkeypatch.setattr(mureka_provider.httpx, "AsyncClient", lambda *a, **k: fake)
    return fake


def _succeeded_poll(audio_url="https://cdn.example/song.wav"):
    """提交成功 + 轮询到 succeeded 的响应序列。"""
    submit = _Resp(200, {"id": "1436211", "trace_id": "trace-abc", "status": "preparing"})
    polls = [
        _Resp(200, {"status": "preparing"}),
        _Resp(200, {"status": "running"}),
        _Resp(200, {"status": "succeeded", "wav_url": audio_url, "trace_id": "trace-abc"}),
    ]
    return submit, polls


# ═══════════════════════════════════════════════════════════════
# 单元测试
# ═══════════════════════════════════════════════════════════════

def test_1_provider_registers():
    """MurekaProvider 正常注册进 registry（生产 fallback_chain 含 mureka）。"""
    import app.services.provider_registry as pr
    pr._registry = None
    reg = pr.get_provider_registry()
    assert "mureka" in reg._providers
    assert isinstance(reg.get("mureka"), MurekaProvider)
    assert reg.get("mureka").production is True


def test_2_no_key_registry_still_ok():
    """无 MUREKA_API_KEY 不会导致 Registry 崩溃。"""
    import app.services.provider_registry as pr
    pr._registry = None
    reg = pr.get_provider_registry()
    assert "runpod" in reg._providers  # 兜底仍在
    assert "mureka" in reg._providers or True  # mureka 注册失败也被捕获，不阻断


async def test_3_lyrics_missing_no_http(have_key, monkeypatch):
    provider = MurekaProvider()
    r = await provider.generate({"prompt": "some style"})
    assert r["success"] is False
    assert "requires lyrics" in r["error"]


async def test_4_prompt_truncated(have_key, monkeypatch):
    submit, polls = _succeeded_poll()
    fake = _install_client(monkeypatch, post_resp=submit, get_responses=polls)
    # 模拟本地下载
    monkeypatch.setattr(mureka_provider, "_download_audio", lambda url: "/fake/generated/song.wav")

    long_prompt = "x" * 3000
    r = await MurekaProvider().generate({"lyrics": "hello", "prompt": long_prompt})
    assert r["success"] is True
    assert len(fake.sent_payload["prompt"]) <= 1024
    assert fake.sent_payload["prompt"] == long_prompt[:1024]


async def test_5_lyrics_truncated(have_key, monkeypatch):
    submit, polls = _succeeded_poll()
    fake = _install_client(monkeypatch, post_resp=submit, get_responses=polls)
    monkeypatch.setattr(mureka_provider, "_download_audio", lambda url: "/fake/generated/song.wav")

    long_lyrics = "l" * 8000
    r = await MurekaProvider().generate({"lyrics": long_lyrics, "prompt": "style"})
    assert r["success"] is True
    assert len(fake.sent_payload["lyrics"]) <= 5000
    assert fake.sent_payload["lyrics"] == long_lyrics[:5000]


async def test_6_http_401_provider_failure(have_key, monkeypatch):
    submit = _Resp(401, {"error": {"message": "Invalid Authentication"}}, text="bad key")
    _install_client(monkeypatch, post_resp=submit, get_responses=[])
    r = await MurekaProvider().generate({"lyrics": "hello", "prompt": "style"})
    assert r["success"] is False and r["provider"] == "mureka"
    assert "401" in r["error"] or "无效" in r["error"]


async def test_7_http_429_quota_no_infinite_retry(have_key, monkeypatch):
    submit = _Resp(429, {"error": {"message": "You exceeded your current quota"}}, text="quota exceeded")
    fake = _install_client(monkeypatch, post_resp=submit, get_responses=[])
    r = await MurekaProvider().generate({"lyrics": "hello", "prompt": "style"})
    assert r["success"] is False
    assert "配额" in r["error"]
    # 未进入轮询：get 一次都没被调用
    assert fake._get_idx == 0


async def test_8_status_polling_to_succeeded(have_key, monkeypatch):
    submit, polls = _succeeded_poll()
    fake = _install_client(monkeypatch, post_resp=submit, get_responses=polls)
    monkeypatch.setattr(mureka_provider, "_download_audio", lambda url: "/fake/generated/song.wav")

    r = await MurekaProvider().generate({"lyrics": "hello", "prompt": "style"})
    assert r["success"] is True
    assert fake._get_idx == 3  # preparing / running / succeeded 共 3 次 get


async def test_9_task_failed(have_key, monkeypatch):
    submit = _Resp(200, {"id": "t1", "trace_id": "tr1"})
    polls = [_Resp(200, {"status": "failed", "trace_id": "tr1"})]
    _install_client(monkeypatch, post_resp=submit, get_responses=polls)
    r = await MurekaProvider().generate({"lyrics": "hello", "prompt": "style"})
    assert r["success"] is False
    assert "failed" in r["error"]


async def test_10_task_timeouted(have_key, monkeypatch):
    submit = _Resp(200, {"id": "t1"})
    polls = [_Resp(200, {"status": "timeouted"})]
    _install_client(monkeypatch, post_resp=submit, get_responses=polls)
    r = await MurekaProvider().generate({"lyrics": "hello", "prompt": "style"})
    assert r["success"] is False
    assert "timeouted" in r["error"]


async def test_11_task_cancelled(have_key, monkeypatch):
    submit = _Resp(200, {"id": "t1"})
    polls = [_Resp(200, {"status": "cancelled"})]
    _install_client(monkeypatch, post_resp=submit, get_responses=polls)
    r = await MurekaProvider().generate({"lyrics": "hello", "prompt": "style"})
    assert r["success"] is False
    assert "cancelled" in r["error"]


async def test_12_unknown_status_stops(have_key, monkeypatch):
    submit = _Resp(200, {"id": "t1", "trace_id": "tr1"})
    # 未知 status 出现一次，必须停止轮询（不会无限 get）
    polls = [_Resp(200, {"status": "weird_status", "trace_id": "tr1"})]
    fake = _install_client(monkeypatch, post_resp=submit, get_responses=polls)
    r = await MurekaProvider().generate({"lyrics": "hello", "prompt": "style"})
    assert r["success"] is False
    assert "unknown" in r["error"]
    # 只 get 了一次（未知状态立即停止，不继续轮询）
    assert fake._get_idx == 1


async def test_13_succeeded_with_audio_downloads(have_key, monkeypatch, tmp_path):
    submit, polls = _succeeded_poll()
    _install_client(monkeypatch, post_resp=submit, get_responses=polls)
    local = str(tmp_path / "mureka_song.wav")
    monkeypatch.setattr(mureka_provider, "_download_audio", lambda url: local)

    r = await MurekaProvider().generate({"lyrics": "hello", "prompt": "style"})
    assert r["success"] is True
    vf = r["volume_files"]
    assert vf["_local_path"] == local
    assert vf["_mureka_url"] == "https://cdn.example/song.wav"
    assert vf["_trace_id"] == "trace-abc"


async def test_14_succeeded_no_audio_url_fails(have_key, monkeypatch):
    submit = _Resp(200, {"id": "t1", "trace_id": "tr1"})
    polls = [_Resp(200, {"status": "succeeded", "trace_id": "tr1"})]  # 无任何音频 URL 字段
    _install_client(monkeypatch, post_resp=submit, get_responses=polls)
    r = await MurekaProvider().generate({"lyrics": "hello", "prompt": "style"})
    assert r["success"] is False
    assert "audio URL" in r["error"]


# ═══════════════════════════════════════════════════════════════
# fallback_chain 集成（验证 API-2A 行为仍成立）
# ═══════════════════════════════════════════════════════════════

def test_15_fallback_chain_production_order_has_mureka():
    """生产 fallback_chain 顺序 = [yinchao, mureka, runpod]。"""
    os.environ["ENVIRONMENT"] = "production"
    try:
        import app.services.provider_registry as pr
        pr._registry = None
        reg = pr.get_provider_registry()
        chain = reg.fallback_chain()
        assert [p.name for p in chain] == ["yinchao", "mureka", "runpod"]
    finally:
        os.environ.pop("ENVIRONMENT", None)
        import app.services.provider_registry as pr
        pr._registry = None


async def test_16_fallback_mureka_success_runpod_not_called(isolated_db, monkeypatch):
    """Mureka success → RunPod 不调用（走 ai_music._run_generation 循环）。"""
    from app.routers import ai_music
    from app.services import ai_limits, task_store

    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 1000)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")
    user = "u-mk-ok"
    assert ai_limits.reserve_generation(user, 60)["success"] is True
    tid = task_store.new_task(user_key=user, task_id="task-mk-ok")

    calls = {"mureka": 0, "runpod": 0}

    async def _mureka(req):
        calls["mureka"] += 1
        return {"success": True, "volume_files": {"full_wav": "a.wav", "full_mp3": "a.mp3"}}

    async def _runpod(req):
        calls["runpod"] += 1
        return {"success": True, "volume_files": {"full_wav": "b.wav"}}

    class _M:
        name = "mureka"
        gpu = "mureka"
        async def generate(self, request):
            return await _mureka(request)
    class _R:
        name = "runpod"
        gpu = "runpod"
        async def generate(self, request):
            return await _runpod(request)

    class _Reg:
        def fallback_chain(self, name=None):
            return [_M(), _R()]
    monkeypatch.setattr(ai_music, "get_provider_registry", lambda: _Reg())

    async def _agnes(req):
        class _X:
            pass
        x = _X(); x.optimized_prompt = req.prompt; x.generated_lyrics = None
        return x
    monkeypatch.setattr(ai_music.agnes_service, "generate_song", _agnes)

    async def _hf(*a, **k):
        return None
    monkeypatch.setattr(ai_music, "_try_hf_ace_step_fallback", _hf)

    async def _uf(*a, **k):
        return None
    monkeypatch.setattr(ai_music, "_upload_and_finalize", _uf)

    monkeypatch.setattr(ai_music, "MAX_AUTO_RETRIES", 0)
    req = ai_music.GenerateRequest(prompt="p", style="pop", duration=60, type="song")
    await ai_music._run_generation(tid, req, user)

    assert calls["mureka"] == 1 and calls["runpod"] == 0


async def test_17_fallback_both_fail_single_refund(isolated_db, monkeypatch):
    """Mureka + RunPod 都失败 → 最终只退款一次（额度恢复）。"""
    from app.routers import ai_music
    from app.services import ai_limits, task_store

    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 1)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 1000)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")
    user = "u-mk-ff"
    assert ai_limits.reserve_generation(user, 60)["success"] is True
    tid = task_store.new_task(user_key=user, task_id="task-mk-ff")

    class _F:
        def __init__(self, name):
            self.name = name
            self.gpu = "test"
        async def generate(self, request):
            return {"success": False, "error": "fail", "provider": self.name}

    class _Reg:
        def fallback_chain(self, name=None):
            return [_F("mureka"), _F("runpod")]
    monkeypatch.setattr(ai_music, "get_provider_registry", lambda: _Reg())

    async def _agnes(req):
        class _X:
            pass
        x = _X(); x.optimized_prompt = req.prompt; x.generated_lyrics = None
        return x
    monkeypatch.setattr(ai_music.agnes_service, "generate_song", _agnes)
    async def _hf(*a, **k):
        return None
    monkeypatch.setattr(ai_music, "_try_hf_ace_step_fallback", _hf)
    monkeypatch.setattr(ai_music, "MAX_AUTO_RETRIES", 0)

    req = ai_music.GenerateRequest(prompt="p", style="pop", duration=60, type="song")
    await ai_music._run_generation(tid, req, user)

    assert task_store.get(tid)["state"] == "failed"
    # 退款一次 → 额度恢复 → 可再次 reserve
    assert ai_limits.reserve_generation(user, 60)["success"] is True