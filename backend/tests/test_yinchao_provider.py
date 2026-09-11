"""YinchaoProvider 单元测试 —— 全部 mock HTTP，绝不真实调用音潮 API。"""

import os

import pytest

from app.services import yinchao_provider
from app.services.yinchao_provider import YinchaoProvider


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
    """只要 post/get，记录提交 payload；get 按顺序消费轮询响应。"""

    def __init__(self, post_resp=None, get_responses=None):
        self._post_resp = post_resp or _Resp()
        self._get_responses = list(get_responses) if get_responses else []
        self._get_idx = 0
        self.sent_payload = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **kw):
        self.sent_payload = kw.get("json") or {}
        return self._post_resp

    async def get(self, url, **kw):
        if self._get_idx < len(self._get_responses):
            r = self._get_responses[self._get_idx]
            self._get_idx += 1
            return r
        return self._get_responses[-1] if self._get_responses else _Resp(status_code=404)


@pytest.fixture()
def have_key(monkeypatch):
    monkeypatch.setattr(YinchaoProvider, "_api_key", lambda self: "test-yinchao-key")
    monkeypatch.setattr(yinchao_provider, "YINCHAO_TIMEOUT_SECONDS", 5.0)
    monkeypatch.setattr(yinchao_provider, "YINCHAO_POLL_INTERVAL_SECONDS", 0.001)


@pytest.fixture()
def no_key(monkeypatch):
    monkeypatch.setattr(YinchaoProvider, "_api_key", lambda self: "")


def _install_client(monkeypatch, post_resp=None, get_responses=None):
    fake = _FakeAsyncClient(post_resp=post_resp, get_responses=get_responses)
    monkeypatch.setattr(yinchao_provider.httpx, "AsyncClient", lambda *a, **k: fake)
    return fake


def _submit_ok(task_id="t-1"):
    return _Resp(200, {"id": task_id})


def _poll(*statuses):
    return [_Resp(200, {"choices": [{"status": s}]}) for s in statuses]


def _done_poll(audio_url="https://cdn.example/song.mp3"):
    return [_Resp(200, {"choices": [{"status": "done", "audio_url": audio_url, "title": "t", "duration": 100}]})]


async def test_1_missing_key(no_key):
    r = await YinchaoProvider().generate({"prompt": "some prompt"})
    assert r["success"] is False
    assert "YINCHAO_API_KEY is not configured" in r["error"]


async def test_2_generate_returns_task_id(have_key, monkeypatch):
    fake = _install_client(monkeypatch, post_resp=_submit_ok(), get_responses=_done_poll())
    monkeypatch.setattr(yinchao_provider, "_download_audio", lambda url: "/fake/generated/song.mp3")
    r = await YinchaoProvider().generate({"prompt": "夏日海边"})
    assert r["success"] is True
    # 提交 payload 使用了正确请求体
    assert fake.sent_payload["model"] == "v4.0"
    assert fake.sent_payload["task_type"] == "normal"
    assert fake.sent_payload["n"] == 1
    assert fake.sent_payload["prompt"] == "夏日海边"


async def test_3_polling_sequence(have_key, monkeypatch):
    fake = _install_client(
        monkeypatch,
        post_resp=_submit_ok(),
        get_responses=[_Resp(200, {"choices": [{"status": "pending"}]}),
                       _Resp(200, {"choices": [{"status": "running"}]}),
                       _Resp(200, {"choices": [{"status": "done", "audio_url": "https://x/s.mp3"}]})],
    )
    monkeypatch.setattr(yinchao_provider, "_download_audio", lambda url: "/fake/generated/s.mp3")
    r = await YinchaoProvider().generate({"prompt": "p"})
    assert r["success"] is True
    assert fake._get_idx == 3  # pending -> running -> done


async def test_4_done_with_audio(have_key, monkeypatch):
    _install_client(monkeypatch, post_resp=_submit_ok(), get_responses=_done_poll())
    monkeypatch.setattr(yinchao_provider, "_download_audio", lambda url: "/fake/generated/song.mp3")
    r = await YinchaoProvider().generate({"prompt": "p"})
    assert r["success"] is True
    assert r["volume_files"]["_local_path"] == "/fake/generated/song.mp3"


async def test_5_fail_status(have_key, monkeypatch):
    _install_client(
        monkeypatch,
        post_resp=_submit_ok(),
        get_responses=[_Resp(200, {"choices": [{"status": "fail", "error_code": 1006, "error": "GENERATED_LYRIC_ERROR"}]})],
    )
    r = await YinchaoProvider().generate({"prompt": "p"})
    assert r["success"] is False
    assert "fail" in r["error"] or "GENERATED_LYRIC_ERROR" in r["error"]


async def test_6_missing_task_id(have_key, monkeypatch):
    _install_client(monkeypatch, post_resp=_Resp(200, {"id": ""}), get_responses=[])
    r = await YinchaoProvider().generate({"prompt": "p"})
    assert r["success"] is False
    assert "task id" in r["error"]


async def test_7_missing_audio_url(have_key, monkeypatch):
    _install_client(monkeypatch, post_resp=_submit_ok(), get_responses=[_Resp(200, {"choices": [{"status": "done"}]})])
    r = await YinchaoProvider().generate({"prompt": "p"})
    assert r["success"] is False
    assert "audio URL" in r["error"]


async def test_8_polling_timeout(have_key, monkeypatch):
    # 一直 pending，超时
    monkeypatch.setattr(yinchao_provider, "YINCHAO_TIMEOUT_SECONDS", 0.5)
    monkeypatch.setattr(yinchao_provider, "YINCHAO_POLL_INTERVAL_SECONDS", 0.2)
    _install_client(monkeypatch, post_resp=_submit_ok(), get_responses=[_Resp(200, {"choices": [{"status": "pending"}]})])
    r = await YinchaoProvider().generate({"prompt": "p"})
    assert r["success"] is False
    assert "timeout" in r["error"]


async def test_9_download_success_returns_local_path(have_key, monkeypatch):
    _install_client(monkeypatch, post_resp=_submit_ok(), get_responses=_done_poll())
    monkeypatch.setattr(yinchao_provider, "_download_audio", lambda url: "C:/abs/generated/yinchao_1.mp3")
    r = await YinchaoProvider().generate({"prompt": "p"})
    assert r["success"] is True
    assert r["volume_files"]["_local_path"] == "C:/abs/generated/yinchao_1.mp3"


async def test_10_download_failure(have_key, monkeypatch):
    _install_client(monkeypatch, post_resp=_submit_ok(), get_responses=_done_poll())
    monkeypatch.setattr(yinchao_provider, "_download_audio", lambda url: None)
    r = await YinchaoProvider().generate({"prompt": "p"})
    assert r["success"] is False
    assert "下载失败" in r["error"]


async def test_11_volume_files_structure(have_key, monkeypatch):
    _install_client(monkeypatch, post_resp=_submit_ok(), get_responses=_done_poll("https://cdn/x/song.mp3"))
    monkeypatch.setattr(yinchao_provider, "_download_audio", lambda url: "/abs/generated/yinchao_123.mp3")
    r = await YinchaoProvider().generate({"prompt": "p"})
    assert r["success"] is True
    vf = r["volume_files"]
    assert "full_mp3" in vf and "full_wav" in vf and "_local_path" in vf
    # 音潮返回 mp3 → full_mp3 应指向真实 mp3 文件名（不伪装 wav）
    assert vf["full_mp3"].endswith(".mp3")


async def test_12_local_path_is_absolute(have_key, monkeypatch):
    _install_client(monkeypatch, post_resp=_submit_ok(), get_responses=_done_poll())
    fake_path = "/abs/path/yinchao_x.mp3"
    monkeypatch.setattr(yinchao_provider, "_download_audio", lambda url: fake_path)
    r = await YinchaoProvider().generate({"prompt": "p"})
    assert r["success"] is True
    assert os.path.isabs(r["volume_files"]["_local_path"])


async def test_13_key_not_in_error_or_payload(have_key, monkeypatch, caplog):
    fake = _install_client(monkeypatch, post_resp=_submit_ok(), get_responses=_done_poll())
    monkeypatch.setattr(yinchao_provider, "_download_audio", lambda url: "/abs/x.mp3")
    _ = await YinchaoProvider().generate({"prompt": "p"})
    # 提交 payload 不含 key
    assert "test-yinchao-key" not in str(fake.sent_payload)
    # 返回结果不含 key
    # （此处再次调用失败分支验证 error 字符串不含 key）
    monkeypatch.setattr(YinchaoProvider, "_api_key", lambda self: "SECRET")
    _install_client(monkeypatch, post_resp=_Resp(500, {"e": "x"}), get_responses=[])
    r2 = await YinchaoProvider().generate({"prompt": "p"})
    assert "SECRET" not in r2.get("error", "")


async def test_http_401_submit_failure(have_key, monkeypatch):
    _install_client(monkeypatch, post_resp=_Resp(401, {}, text="bad"), get_responses=[])
    r = await YinchaoProvider().generate({"prompt": "p"})
    assert r["success"] is False
    assert "401" in r["error"]


def test_registration_present():
    """YinchaoProvider 已注册进 registry 且 production=True。"""
    import app.services.provider_registry as pr
    pr._registry = None
    reg = pr.get_provider_registry()
    assert "yinchao" in reg._providers
    assert reg.get("yinchao").production is True


def test_fallback_chain_production_order():
    """生产 fallback_chain 顺序 = [yinchao, mureka, runpod]。"""
    os.environ["ENVIRONMENT"] = "production"
    try:
        import app.services.provider_registry as pr
        pr._registry = None
        reg = pr.get_provider_registry()
        names = [p.name for p in reg.fallback_chain()]
        # yinchao / mureka 已注册 → 依次在前，runpod 兜底
        assert names[0] == "yinchao"
        assert names[1] == "mureka"
        assert names[2] == "runpod"
    finally:
        os.environ.pop("ENVIRONMENT", None)
        import app.services.provider_registry as pr
        pr._registry = None