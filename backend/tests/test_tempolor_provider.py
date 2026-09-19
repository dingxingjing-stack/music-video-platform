"""Phase 2D：TemPolor Provider — callback 配置预检 + HTTP 200 业务码解析测试。

全部 mock httpx，零真实 API、零扣费。业务码逐字取自中国站通用错误码文档
（platform.tianpuyue.cn/docs/8859400m0.md），行为依据 2026-09-18 真实联调结论
（空 callback_url → 200 + 400003 "callback_url not blank"）。
"""

import asyncio
import json

import pytest

from app.services import tempolor_provider as tp

TEST_CB = "https://callback.invalid.test/zyvexo-tempolor"  # 测试占位域，非生产 URL


class FakeResp:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.content = json.dumps(payload).encode()
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeClient:
    """按 URL 分发预置响应；记录全部出站请求（可断言零提交）。"""

    def __init__(self, responses: dict):
        self.responses = responses
        self.posts: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        self.posts.append((url, json or {}))
        kind = "submit" if "generate" in url else "query"
        r = self.responses[kind]
        if isinstance(r, list):
            r = r.pop(0)
        return FakeResp(r)


@pytest.fixture()
def wired(monkeypatch):
    """key + callback + 轮询加速 + 下载桩。返回工厂：注入 submit/query 响应。"""
    monkeypatch.setenv("TEMPOLOR_API_KEY", "test-key-not-real")
    monkeypatch.delenv("TEMPOLOR_MODEL", raising=False)
    monkeypatch.setattr(tp, "TEMPOLOR_CALLBACK_URL", TEST_CB)
    monkeypatch.setattr(tp, "TEMPOLOR_POLL_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(tp, "_download_audio", lambda url: "/tmp/fake_tempolor.mp3")
    holder: dict = {}

    def build(submit, query):
        fc = FakeClient({"submit": submit, "query": query})
        monkeypatch.setattr(tp.httpx, "AsyncClient", lambda *a, **k: fc)
        return fc
    holder["build"] = build
    return build


OK_SUBMIT = {"status": 200000, "message": "success", "data": {"item_ids": ["t2m_test1"]}}
OK_DONE = {"status": 200000, "data": {"songs": [{
    "item_id": "t2m_test1", "status": "succeeded",
    "audio_url": "https://data-sz.tianpuyue.cn/x.mp3?auth_key=fake",
    "duration": 192, "model": "Mureka V9",
}]}}


def _req(**kw):
    r = {"prompt": "a pop song", "lyrics": "la la", "duration": 120, "is_instrumental": False}
    r.update(kw)
    return r


def test_1_http200_biz_200000_with_item_id_success(wired):
    """成功必须同时满足：HTTP 200 + 业务码 200000 + 有效 item_id。"""
    wired(OK_SUBMIT, OK_DONE)
    out = asyncio.run(tp.TempolorProvider().generate(_req()))
    assert out["success"] is True
    assert out["volume_files"]["_model"] == "tempolor-latest"


@pytest.mark.parametrize("code,msg", [
    (400002, "invalid api key~"),
    (400003, "Bad Parameter."),
    (400004, "Content violation"),
    (400005, "Insufficient points."),
    (400010, "The current model does not support this feature"),
])
def test_2_to_5_business_codes_identified_not_missing_item(wired, code, msg):
    """HTTP 200 + 业务错误码：必须报 TemPolor API error code=XXXXXX，绝不伪装 missing item id。"""
    fc = wired({"status": code, "message": msg}, OK_DONE)
    out = asyncio.run(tp.TempolorProvider().generate(_req()))
    assert out["success"] is False
    assert out["error_code"] == code
    assert f"code={code}" in out["error"]
    assert "missing item id" not in out["error"] and "缺少 item id" not in out["error"]
    assert len(fc.posts) == 1  # 提交即识别，未进入轮询


def test_3_400003_non_retryable(wired):
    wired({"status": 400003, "message": "Bad Parameter:callback_url not blank"}, OK_DONE)
    out = asyncio.run(tp.TempolorProvider().generate(_req()))
    assert out.get("non_retryable") is True and out["error_code"] == 400003


def test_400010_non_retryable(wired):
    wired({"status": 400010, "message": "The current model does not support this feature"}, OK_DONE)
    out = asyncio.run(tp.TempolorProvider().generate(_req()))
    assert out.get("non_retryable") is True and out["error_code"] == 400010


def test_400005_not_non_retryable_keeps_existing_fallback_semantics(wired):
    """余额不足按 §三 保持既有可重试/可切换语义：识别错误但不标 non_retryable。"""
    wired({"status": 400005, "message": "Insufficient points."}, OK_DONE)
    out = asyncio.run(tp.TempolorProvider().generate(_req()))
    assert out["success"] is False and out["error_code"] == 400005
    assert out.get("non_retryable") is not True


def test_query_stage_business_code_fails_fast(wired):
    """轮询阶段业务码（如 400008 作品不存在）立即失败，不拖到 360s 超时。"""
    fc = wired(OK_SUBMIT, {"status": 400008, "message": "The work does not exist"})
    out = asyncio.run(tp.TempolorProvider().generate(_req()))
    assert out["success"] is False
    assert out["error_code"] == 400008
    assert out.get("non_retryable") is True
    assert len(fc.posts) == 2  # 1 submit + 1 query，立即终止


def test_6_missing_callback_config_zero_submission(monkeypatch):
    """callback 未配置：明确配置缺失错误 + non_retryable + 零 HTTP（绝不发占位假 URL）。"""
    monkeypatch.setenv("TEMPOLOR_API_KEY", "test-key-not-real")
    monkeypatch.setattr(tp, "TEMPOLOR_CALLBACK_URL", "")
    fc = FakeClient({"submit": OK_SUBMIT, "query": OK_DONE})
    monkeypatch.setattr(tp.httpx, "AsyncClient", lambda *a, **k: fc)
    out = asyncio.run(tp.TempolorProvider().generate(_req()))
    assert out["success"] is False
    assert out.get("non_retryable") is True
    assert "TEMPOLOR_CALLBACK_URL 未配置" in out["error"]
    assert fc.posts == []  # 一次请求都没发出


def test_callback_sent_when_configured(wired):
    """配置存在时 payload.callback_url 必须原样非空发送。"""
    fc = wired(OK_SUBMIT, OK_DONE)
    asyncio.run(tp.TempolorProvider().generate(_req()))
    _, payload = fc.posts[0]
    assert payload["callback_url"] == TEST_CB
