"""Commit 7 测试：production 禁止 HF Ace-Step fallback，development/test 保留。

生产策略（Yinchao + TemPolor only）：
  Yinchao → TemPolor → 最终失败（不再进 HF），development/test 的既有
  HF fallback 行为保持不变。

全部 HTTP 均为 mock，不触碰真实 HF 网络、真实 Token 与真实计费。
"""

import os

import pytest

from app.routers import ai_music


@pytest.fixture()
def _hf_flag_on(monkeypatch):
    """HF flag 开启 + 假 Token，排除 flag/缺 Token 提前返回的干扰。"""
    monkeypatch.setattr(ai_music, "HF_FALLBACK_ENABLED", True)
    monkeypatch.setenv("HF_TOKEN", "fake-token-for-test-only")
    monkeypatch.delenv("HUGGINGFACE_TOKEN", raising=False)


class _NoNetwork:
    """production 断言 helper：任何网络访问企图直接爆炸。"""

    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("production 禁止访问 HF（不允许任何 HTTP 请求）")


async def test_production_skips_hf_without_network(_hf_flag_on, monkeypatch):
    """ENVIRONMENT=production → 直接返回 None，且零 HTTP 请求。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    guard = _NoNetwork()
    monkeypatch.setattr(ai_music, "httpx", type("FakeHttpx", (), {"AsyncClient": guard})())

    result = await ai_music._try_hf_ace_step_fallback("a test song prompt", "lyrics", 60)

    assert result is None
    assert guard.calls == []


class _Resp500:
    status_code = 500

    def json(self):
        return {}


class _DevFakeClient:
    """development 用假客户端：记录 post 调用，返回 500 让函数走失败分支。"""

    def __init__(self, calls):
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        self._calls.append({"url": url, "headers": kwargs.get("headers")})
        return _Resp500()


async def test_development_still_attempts_hf(_hf_flag_on, monkeypatch):
    """ENVIRONMENT=development → 仍尝试原有 HF fallback（post 被调用）。"""
    monkeypatch.setenv("ENVIRONMENT", "development")
    calls: list = []

    def _factory(*args, **kwargs):
        return _DevFakeClient(calls)

    monkeypatch.setattr(ai_music.httpx, "AsyncClient", _factory)

    result = await ai_music._try_hf_ace_step_fallback("a test song prompt", "lyrics", 60)

    # 500 → 函数返回 None，但必须证明它确实尝试了 HF 请求
    assert result is None
    assert len(calls) == 1
    assert "ace-step-ace-step.hf.space" in calls[0]["url"]
    assert calls[0]["headers"]["Authorization"] == "Bearer fake-token-for-test-only"


async def test_production_gate_ignores_hf_fallback_flag_off_path(_hf_flag_on, monkeypatch):
    """production gate 优先级：即使 flag 被关，production 同样返回 None（不抛异常）。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr(ai_music, "HF_FALLBACK_ENABLED", False)
    guard = _NoNetwork()
    monkeypatch.setattr(ai_music, "httpx", type("FakeHttpx", (), {"AsyncClient": guard})())

    assert await ai_music._try_hf_ace_step_fallback("a test song prompt", "lyrics", 60) is None
    assert guard.calls == []


def test_ai_music_does_not_read_environment_at_import():
    """ai_music 模块顶层不得缓存 ENVIRONMENT（gate 必须函数内动态读取）。"""
    import pathlib

    src = pathlib.Path(ai_music.__file__).read_text(encoding="utf-8")
    assert 'os.getenv("ENVIRONMENT"' in src
    # 模块级只允许 HF_FALLBACK 常量，禁止模块级 ENVIRONMENT 快照
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("ENVIRONMENT") and "=" in stripped and "os.getenv" in stripped:
            raise AssertionError("禁止模块级缓存 ENVIRONMENT")
