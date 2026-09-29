"""P5-B 端点退休与安全收口回归守卫。

覆盖 P5-A 判定为"假成功 / 匿名敏感 / 已退休脚手架"的端点族，锁死以下不变量：

  1. subtitles recognize/align 不再返回 HTTP 200 + success=True 的 mock 字幕。
  2. /api/v1/export/stems/{track_id} 不再对任意 id 恒报 status=completed。
  3. /api/v1/services/status 在 production 不可读（不泄露 Secret 变量名与配置指纹）。
  4. /api/v1/llm/health 在 production 不可读，且**不会**触发任何 provider 初始化。
  5. /api/v1/llm/generate 与 /stream 匿名一律 401。
  6. docs/redoc/openapi 仅在非 production 暴露。
  7. retry-stems（仍在使用的真实能力）未被误伤。
"""

from __future__ import annotations

import pytest

try:
    from fastapi.testclient import TestClient
    import main as main_mod
    from main import app
except (ImportError, ModuleNotFoundError) as exc:  # pragma: no cover
    pytest.skip(f"Skipping P5-B guards: {exc}", allow_module_level=True)


@pytest.fixture
def client():
    return TestClient(app)


# ------------------------------------------------------ 1. subtitles
@pytest.mark.parametrize("path", ["/recognize", "/align"])
def test_subtitle_endpoints_are_retired(client, path):
    resp = client.post("/api/v1/subtitles" + path, data={})
    assert resp.status_code == 410, f"{path} -> {resp.status_code}: {resp.text}"
    assert "success" not in resp.text.lower() or "True" not in resp.text


def test_subtitle_health_still_reports_unavailable(client):
    """/health 是这一族里唯一诚实的端点，必须保留并如实报告不可用。"""
    resp = client.get("/api/v1/subtitles/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["mode"] == "mock"


def test_whisper_is_not_installed_anywhere_in_process():
    """守卫前提：若哪天真的装了 whisper，本文件的假成功断言需随之重写。"""
    import sys

    assert "whisper" not in sys.modules
    assert "faster_whisper" not in sys.modules


# ------------------------------------------------------ 2. stems fake status
def test_stems_export_fake_status_is_retired(client):
    resp = client.get("/api/v1/export/stems/whatever-track-id")
    assert resp.status_code == 410, resp.text
    assert "completed" not in resp.text


def test_stems_export_post_is_retired(client):
    resp = client.post("/api/v1/export/stems", json={"audio_url": "https://x/a.wav"})
    assert resp.status_code == 410, resp.text
    assert "soundhelix" not in resp.text.lower()


# ------------------------------------------------------ 3/4. ops endpoints
def test_services_status_rejected_in_production(client, monkeypatch):
    monkeypatch.setattr(main_mod, "_IS_PRODUCTION", True)
    assert client.get("/api/v1/services/status").status_code == 404


def test_services_status_readable_outside_production(client, monkeypatch):
    monkeypatch.setattr(main_mod, "_IS_PRODUCTION", False)
    assert client.get("/api/v1/services/status").status_code == 200


def test_llm_health_rejected_in_production_without_touching_providers(
    client, monkeypatch
):
    """production 下必须 404，且绝不进入 provider 初始化（外部请求数 = 0）。"""
    monkeypatch.setattr(main_mod, "_IS_PRODUCTION", True)

    def _boom(*a, **k):  # pragma: no cover
        raise AssertionError("P5-B.2 违规：production 下不得初始化 LLM provider")

    monkeypatch.setattr(main_mod.llm_factory, "_ensure_initialized", _boom)
    assert client.get("/api/v1/llm/health").status_code == 404


def test_llm_generate_and_stream_require_identity(client):
    for path in ("/api/v1/llm/generate", "/api/v1/llm/stream"):
        resp = client.post(path, json={"messages": [{"role": "user", "content": "hi"}]})
        assert resp.status_code == 401, f"{path} -> {resp.status_code}: {resp.text}"


# ------------------------------------------------------ 6. docs surface
def test_docs_surface_follows_environment():
    paths = {getattr(r, "path", "") for r in app.routes}
    assert (("/docs" in paths) == (not main_mod._IS_PRODUCTION)), sorted(paths)
    assert (("/openapi.json" in paths) == (not main_mod._IS_PRODUCTION))


def test_openapi_self_description_no_longer_advertising_hf_spaces():
    spec = app.openapi()
    desc = spec["info"].get("description", "")
    title = spec["info"].get("title", "")
    assert "HF Spaces" not in desc
    assert "Inference Service API" != title


# ------------------------------------------------------ 7. live capability intact
def test_retry_stems_not_swept_up_by_retirement(client):
    """retry-stems 仍在用：匿名必须是 401（鉴权拦截），而不是 410（退休）。"""
    resp = client.post("/api/v1/ai/task/nope/retry-stems")
    assert resp.status_code == 401, resp.text
