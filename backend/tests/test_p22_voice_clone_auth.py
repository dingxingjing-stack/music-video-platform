"""P5-B.4：/api/v1/voice/* 端点族退休守卫。

本文件原用于验证 `/api/v1/voice/*`（旧声音克隆 v2）的身份只能来自 Authorization
Bearer JWT。P5-B.4 起整族在 HTTP 边界返回 410 Gone，原因见下：

  - 前端对 /api/v1/voice/* 引用为 0（含 dist 产物）。
  - POST /clone 由 voice_clone_service.clone_voice **恒返回 success=True**，
    audio_url 拼的是第三方教学站 www2.cs.uic.edu/~i101/SoundFiles/ 的演示音频
    （StarWars / PinkPanther / BabyElephantWalk），message 还写"合成成功"。
  - GET /presets 匿名返回同一批第三方样本，并伪装成 created_at 产品资产。
  - 该族从未接入真实 RVC/GPT-SoVITS 能力。

未删除的部分：`app/services/voice_clone_service.py` 仍被
`app/services/voice_clone_task.py` 引用（实验链，faster-whisper 未安装），
其演示样本数据物理清理归 P5-C/P6。

真正的商业声音克隆是另一族 `/api/v1/voice-clone/*`（PoYo），由
`VOICE_CLONE_ENABLED` fail-closed 门禁控制，本文件同时锁定其默认不可用状态。
"""

from __future__ import annotations

import pytest

try:
    from fastapi.testclient import TestClient
    from main import app
except (ImportError, ModuleNotFoundError) as exc:  # pragma: no cover
    pytest.skip(f"Skipping voice retirement tests: {exc}", allow_module_level=True)


BASE = "/api/v1/voice"

# 任何身份头都不应改变结果：端点已退休
_HEADERS = [
    {},
    {"Authorization": "Bearer whatever"},
    {"X-User-ID": "someone"},
    {"Authorization": "Bearer whatever", "X-User-ID": "someone"},
]


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/voices"),
        ("get", "/clone-quota"),
        ("get", "/presets"),
        ("post", "/upload"),
        ("post", "/clone"),
    ],
)
def test_legacy_voice_endpoints_are_retired(client, method, path):
    for headers in _HEADERS:
        resp = client.request(
            method.upper(), BASE + path, headers=headers, json={}
        )
        assert resp.status_code == 410, (
            f"{method.upper()} {path} with {sorted(headers)} -> {resp.status_code}: {resp.text}"
        )


def test_retired_voice_endpoints_never_return_demo_audio(client):
    """410 响应体不得再携带第三方演示音频 URL。"""
    body = client.post(BASE + "/clone", json={"text": "hi", "voice_id": "preset_male_01"}).text
    assert "cs.uic.edu" not in body
    assert "soundhelix" not in body.lower()
    assert "success" not in body.lower() or "False" in body


@pytest.mark.parametrize(
    "path",
    ["/validate", "/generate", "/check", "/regenerate"],
)
def test_poyo_voice_clone_stays_gated(client, path):
    """未退休的 PoYo 族：默认必须仍然是 401（无 JWT）或 503（开关关闭），绝不可 200。"""
    resp = client.post("/api/v1/voice-clone" + path, json={})
    assert resp.status_code in (401, 503), f"{path} -> {resp.status_code}: {resp.text}"
