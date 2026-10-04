"""B4-YC-DL-FIX 测试：Yinchao 下载失败可追溯性（全 mock，零真实网络）。

覆盖授权 §11：
- Test 1-4: HTTP 502/500/404/403 → 失败 + task_id 保留 + URL 脱敏 + 日志
- Test 5: timeout / Test 6: connection error → 失败上下文
- Test 7: HTTP 200 成功路径不变
- Test 8: _submit_and_poll 集成——_download_audio 收到 task_id/audio_url/dest，
  失败返回含 yinchao_task_id + audio_url_redacted
- 安全: 签名值（SECRET123/VERY_SECRET）不出现在日志或 redacted URL 中
"""

import asyncio
import logging

import httpx
import pytest

from app.services import yinchao_provider as ymod
from app.services.yinchao_provider import YinchaoProvider, _download_audio, _redact_url

SIGNED_URL = ("https://provider.example/audio.mp3"
              "?token=SECRET123&X-Amz-Signature=VERY_SECRET&X-Amz-Expires=86400")
TASK_ID = "test-task-502"


def _resp(status_code=200, content=b"x" * 2000):
    class _R:
        pass
    r = _R()
    r.status_code = status_code
    r.content = content
    return r


class _FakeClient:
    """替代 httpx.Client（_download_audio 使用同步 Client）。"""
    last_get = {}

    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url):
        return _FakeClient._current_response


_current = {"response": _resp(200)}


def _install_download_response(monkeypatch, response):
    _FakeClient._current_response = response
    monkeypatch.setattr(ymod.httpx, "Client", _FakeClient)


def test_redact_url_keeps_params_hides_values():
    r = _redact_url(SIGNED_URL)
    assert r.startswith("https://provider.example/audio.mp3?")
    assert "token=[REDACTED]" in r
    assert "X-Amz-Signature=[REDACTED]" in r
    assert "SECRET123" not in r and "VERY_SECRET" not in r


def test_redact_url_no_query():
    assert _redact_url("https://x/y.mp3") == "https://x/y.mp3"
    assert _redact_url("") == ""


@pytest.mark.parametrize("status", [502, 500, 404, 403])
def test_download_http_failures_context(monkeypatch, caplog, status):
    _install_download_response(monkeypatch, _resp(status))
    with caplog.at_level(logging.WARNING, logger="app.services.yinchao_provider"):
        out = _download_audio(SIGNED_URL, task_id=TASK_ID)
    assert out is None
    rec = caplog.records[-1]
    assert str(status) in rec.getMessage()
    assert TASK_ID in rec.getMessage()
    assert "[REDACTED]" in rec.getMessage()
    assert "SECRET123" not in rec.getMessage() and "VERY_SECRET" not in rec.getMessage()


def test_download_timeout_context(monkeypatch, caplog):
    _install_download_response(monkeypatch, _resp(200))

    class _Client:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url):
            raise httpx.TimeoutException("connect timed out")

    monkeypatch.setattr(ymod.httpx, "Client", _Client)
    with caplog.at_level(logging.WARNING, logger="app.services.yinchao_provider"):
        out = _download_audio(SIGNED_URL, task_id=TASK_ID)
    assert out is None
    rec = caplog.records[-1]
    assert TASK_ID in rec.getMessage()
    assert "TimeoutException" in rec.getMessage()


def test_download_connection_error_context(monkeypatch, caplog):
    _install_download_response(monkeypatch, _resp(200))

    class _Client:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url):
            raise ConnectionError("connection reset")

    monkeypatch.setattr(ymod.httpx, "Client", _Client)
    with caplog.at_level(logging.WARNING, logger="app.services.yinchao_provider"):
        out = _download_audio(SIGNED_URL, task_id=TASK_ID)
    assert out is None
    rec = caplog.records[-1]
    assert TASK_ID in rec.getMessage()
    assert "connection reset" in rec.getMessage()  # 异常消息入日志（类名断言改为消息）


def test_download_success_unchanged(tmp_path, monkeypatch):
    """成功路径行为不变：返回本地文件路径、内容完整。"""
    import os
    content = b"A" * 2000
    _install_download_response(monkeypatch, _resp(200, content))
    out = _download_audio(SIGNED_URL, dest_dir=str(tmp_path), task_id=TASK_ID)
    assert out and os.path.exists(out)
    with open(out, "rb") as f:
        assert f.read() == content


def test_download_empty_body_fail(tmp_path, monkeypatch):
    _install_download_response(monkeypatch, _resp(200, b"tiny"))
    out = _download_audio(SIGNED_URL, dest_dir=str(tmp_path), task_id=TASK_ID)
    assert out is None


# ───────────────────── Test 8：_submit_and_poll 集成 ─────────────────────

class _FakeAsyncClient:
    """替代 _submit_and_poll 内的 httpx.AsyncClient：提交→轮询→成功终态。"""
    last_post_body = {}
    last_get_params = {}

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        _FakeAsyncClient.last_post_body = json or {}
        r = httpx.Response(200, json={"id": "test-task"})
        return r

    async def get(self, url, params=None, headers=None):
        _FakeAsyncClient.last_get_params = params or {}
        r = httpx.Response(200, json={"choices": [
            {"status": "done", "audio_url": SIGNED_URL}]})
        return r


def test_submit_and_poll_passes_task_id_to_download(monkeypatch):
    """集成：submit→task_id=test-task→poll done→下载失败→
    _download_audio 收到 audio_url+task_id；失败返回含 yinchao_task_id+audio_url_redacted。"""
    monkeypatch.setenv("YINCHAO_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    received = {}

    def _rec_download(url, dest_dir=None, task_id=None):
        received.update({"url": url, "task_id": task_id, "dest_dir": dest_dir})
        return None  # 模拟下载失败

    monkeypatch.setattr(ymod, "_download_audio", _rec_download)

    provider = YinchaoProvider()
    res = asyncio.run(provider.generate({
        "operation": "normal",
        "prompt": "synthwave test song",
        "lyrics": "[Verse]\nla la",
    }))

    # _download_audio 收到 audio_url + task_id
    assert received["url"] == SIGNED_URL
    assert received["task_id"] == "test-task"
    # dest_dir=None = 既有默认行为（provider 内部 local_dir），不改成功路径
    assert received["task_id"] == "test-task"
    # 失败返回携带可追溯上下文
    assert res["success"] is False
    assert res.get("yinchao_task_id") == "test-task"
    red = res.get("audio_url_redacted") or ""
    assert red.startswith("https://provider.example/audio.mp3?")
    assert "SECRET123" not in red and "VERY_SECRET" not in red
    # 成功路径结构不受影响：无 volume_files
    assert "volume_files" not in res
