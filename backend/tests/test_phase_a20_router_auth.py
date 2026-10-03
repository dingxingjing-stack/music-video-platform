"""A-20 安全修复回归测试（路由鉴权 + rhythm 退役）。

覆盖（A20_FINAL_WHITELIST 裁定）：
- rhythm `/api/v1/beat/*` 四端点退役：匿名 → 410；不再存在任何 httpx/librosa/
  临时文件/URL 下载代码路径（源码级断言 + 行为断言）；
- audio_processing `POST /master`：匿名 → 401（鉴权生效）；有效身份 → 不再 401；
- audio_quality `/enhance-prompt`、`/compare`：匿名 → 401；
- bg_removal `/remove`、`/batch`：匿名 → 401；/batch 既有 50 张上限回归；
- authFetch 同步（前端）由 tsc --noEmit 与代码审查覆盖，不在本文件范围。

全部 mock / 本地，零真实供应商、零生产接触。
"""
from __future__ import annotations

import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import (
    audio_processing,
    audio_quality,
    bg_removal,
    rhythm_analysis,
)
from app.services.auth_identity import get_verified_user_id

USER = "a20-auth-user"


@pytest.fixture()
def app():
    app = FastAPI()
    app.include_router(rhythm_analysis.router)
    # audio_processing 的 /api/v1/audio 前缀与生产 main.py 一致，在挂载时添加
    app.include_router(audio_processing.router, prefix="/api/v1/audio")
    app.include_router(audio_quality.router)
    app.include_router(bg_removal.router)
    return app


@pytest.fixture()
def client(app):
    return TestClient(app)


@pytest.fixture()
def authed_client(app):
    app.dependency_overrides[get_verified_user_id] = lambda: USER
    return TestClient(app)


# ── 1) rhythm 四端点退役：匿名 → 410 ─────────────────────────────────────

def test_beat_detect_retired_410(client):
    resp = client.post("/api/v1/beat/detect", json={"audio_url": "https://example.com/a.wav"})
    assert resp.status_code == 410


def test_beat_rhythm_grid_retired_410(client):
    resp = client.post("/api/v1/beat/rhythm-grid", json={"audio_url": "https://example.com/a.wav"})
    assert resp.status_code == 410


def test_beat_tempo_curve_retired_410(client):
    resp = client.post("/api/v1/beat/tempo-curve", json={"audio_url": "https://example.com/a.wav"})
    assert resp.status_code == 410


def test_beat_info_retired_410(client):
    resp = client.get("/api/v1/beat/info/whatever")
    assert resp.status_code == 410


def test_beat_retired_even_with_valid_identity(app):
    """带有效身份同样 410 —— 退役是端点级裁定，与身份无关。"""
    app.dependency_overrides[get_verified_user_id] = lambda: USER
    client = TestClient(app)
    resp = client.post("/api/v1/beat/detect", json={"audio_url": "https://example.com/a.wav"})
    assert resp.status_code == 410


# ── 2) rhythm 源码级断言：SSRF 路径彻底移除 ───────────────────────────────

def test_rhythm_source_has_no_network_download_or_librosa():
    """退役文件不得残留任何网络下载 / 临时文件 / librosa 代码语句（docstring 历史说明除外）。"""
    import inspect
    src = inspect.getsource(rhythm_analysis)
    for banned_stmt in ("import httpx", "import librosa", "tempfile.mkstemp",
                        "client.get(", "temp_path", "AudioSegment"):
        assert banned_stmt not in src, f"退役文件中不得残留代码语句 {banned_stmt}"


def test_rhythm_detect_accepts_no_file_upload_param():
    """退役端点不再接收 UploadFile —— 无上传面即无磁盘写入面。"""
    import inspect
    sig = inspect.signature(rhythm_analysis.detect_beat_endpoint)
    assert "audio_file" not in sig.parameters
    assert "audio_url" not in sig.parameters


# ── 3) /master 鉴权 ──────────────────────────────────────────────────────

def test_master_anonymous_401(client):
    resp = client.post("/api/v1/audio/master",
                       files={"file": ("a.wav", b"RIFF" + b"\x00" * 64, "audio/wav")})
    assert resp.status_code == 401


def test_master_authenticated_no_longer_401(authed_client):
    resp = authed_client.post(
        "/api/v1/audio/master",
        files={"file": ("a.wav", b"RIFF" + b"\x00" * 512, "audio/wav")},
        data={"target_loudness": "-14.0", "stereo_width": "0.3"},
    )
    # 鉴权已过（不再 401）；处理结果取决于本地实现（200/422/500 均可接受，
    # 本测试只验证鉴权边界修复，不验证音频处理本身）。
    assert resp.status_code != 401


# ── 4) audio_quality 鉴权 ────────────────────────────────────────────────

def test_enhance_prompt_anonymous_401(client):
    resp = client.post("/api/v1/audio/enhance-prompt",
                       json={"user_prompt": "a happy song"})
    assert resp.status_code == 401


def test_compare_anonymous_401(client):
    resp = client.post("/api/v1/audio/compare",
                       json={"user_prompt": "a happy song", "num_variants": 2})
    assert resp.status_code == 401


# ── 5) bg_removal 鉴权 + 既有上限回归 ────────────────────────────────────

def test_bg_remove_anonymous_401(client):
    resp = client.post("/api/v1/bg/remove",
                       files={"image": ("a.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "image/png")})
    assert resp.status_code == 401


def test_bg_batch_anonymous_401(client):
    resp = client.post("/api/v1/bg/batch",
                       files=[("images", ("a.png", b"\x00" * 16, "image/png"))])
    assert resp.status_code == 401


def test_bg_batch_fifty_limit_still_enforced(authed_client):
    """既有 50 张/批上限在鉴权之后仍生效（回归）。"""
    files = [("images", (f"img{i}.png", b"\x00" * 16, "image/png")) for i in range(51)]
    resp = authed_client.post("/api/v1/bg/batch", files=files)
    assert resp.status_code == 400
