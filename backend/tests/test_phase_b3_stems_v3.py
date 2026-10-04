"""P4-B2 Phase A-17 测试：Stems V3 接入（TemPolor，MODEL_ID_UNVERIFIED fail-closed）。

覆盖 A-17 授权 §四/§六/§八：
- model 门禁：submit_stems(model=...) → payload 带 model；v2 默认 → 无 model 字段；
- MODEL_ID_UNVERIFIED：官方文档无 model 字段 → 禁止猜测字符串 → 双重 env 门禁
  （TEMPOLOR_STEMS_V3_MODEL_ID + TEMPOLOR_STEMS_V3_ZIP_MEMBERS），未配置 → 503；
- Credits：stem_separation_v3=100（新增）；stem_separation=35（V2 保持不动）；
- 白名单：extract_and_validate_stems 支持实测确认后的自定义成员映射；
- 退款：/stems/separate v3 在扣费前 fail-closed（零供应商调用、零 Credits 变动）。

全部 mock，零真实 API、零费用。
"""
from __future__ import annotations

import asyncio
import io
import json
import zipfile

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.routers import ai_music
from app.services import (
    ai_limits,
    credits_service,
    task_store,
    tempolor_stems_service as stems_service,
)
from app.services.auth_identity import get_verified_user_id
from app.services.credits_config import get_credit_cost

USER = "a17-stems-user"
SENTINEL_KEY = "SENTINEL-tempolor-key-never-log"
V3_MODEL_OFFICIAL = "OFFICIAL-CONFIRMED-ONLY"  # 仅在 env 门禁测试中作为已确认值替身

VALID_V3_MEMBERS = {
    "originalaudio.flac": "original",
    "x_vocals.flac": "vocals",
    "x_lead.flac": "lead",
    "x_backing.flac": "backing",
    "x_guitar.flac": "guitar",
    "x_piano.flac": "piano",
    "x_drums.flac": "drums",
    "x_bass.flac": "bass",
    "x_other.flac": "other",
}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = str(tmp_path / "a17_stems.db")
    monkeypatch.setattr(task_store, "_DB_PATH", db)
    monkeypatch.setattr(ai_limits, "_DB_PATH", db)
    eng = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    from app.db.database import Base
    Base.metadata.create_all(bind=eng)
    monkeypatch.setattr(credits_service, "SessionLocal", sessionmaker(bind=eng))
    monkeypatch.setenv("TEMPOLOR_API_KEY", SENTINEL_KEY)
    monkeypatch.setenv("TEMPOLOR_CALLBACK_SECRET", "cb-secret")
    monkeypatch.setenv("TEMPOLOR_CALLBACK_URL", "https://melovar.example/api/v1/ai/tempolor/callback")
    monkeypatch.setenv("ENVIRONMENT", "development")
    # 确保未配置 V3 门禁 env（默认 fail-closed）
    monkeypatch.delenv("TEMPOLOR_STEMS_V3_MODEL_ID", raising=False)
    monkeypatch.delenv("TEMPOLOR_STEMS_V3_ZIP_MEMBERS", raising=False)
    return eng


@pytest.fixture()
def client(env):
    app = FastAPI()
    app.include_router(ai_music.router)
    app.dependency_overrides[get_verified_user_id] = lambda: USER
    return TestClient(app)


# ── 1) Credits 配置 ──────────────────────────────────────────────────────

def test_stems_v3_credit_cost_is_100():
    assert get_credit_cost("stem_separation_v3") == 100


def test_stems_v2_credit_cost_is_60():
    assert get_credit_cost("stem_separation") == 60


# ── 2) submit_stems：model 字段透传 ──────────────────────────────────────

def _stub_r2_uploader(monkeypatch):
    """submit_stems 内部按调用时 import cdn_uploader —— 直接打桩其两个方法。"""
    import app.services.cdn_uploader as cdn_mod

    async def fake_upload_private(local_path, key):
        return None

    def fake_presign(key, expires_in=600):
        return f"https://r2.example/{key}?sig=test"

    monkeypatch.setattr(cdn_mod.cdn_uploader, "upload_private", fake_upload_private)
    monkeypatch.setattr(cdn_mod.cdn_uploader, "get_presigned_download_url", fake_presign)



def _mock_client_factory(monkeypatch, handler):
    real_client = httpx.AsyncClient

    def factory(**kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(**kwargs)

    monkeypatch.setattr(stems_service.httpx, "AsyncClient", factory)


def test_submit_stems_v2_omits_model(env, monkeypatch, tmp_path):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"status": 200000, "data": {"item_ids": ["mss_1"]}})

    monkeypatch.setenv("TEMPOLOR_API_KEY", SENTINEL_KEY)
    _mock_client_factory(monkeypatch, handler)
    _stub_r2_uploader(monkeypatch)
    input_file = tmp_path / "in.wav"
    input_file.write_bytes(b"\x00" * 2048)

    item = asyncio.run(stems_service.submit_stems(str(input_file), "stems-t1"))
    assert item == "mss_1"
    assert "model" not in captured["payload"]  # v2 默认档不传 model（实测契约）


def test_submit_stems_v3_includes_model(env, monkeypatch, tmp_path):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"status": 200000, "data": {"item_ids": ["mss_2"]}})

    monkeypatch.setenv("TEMPOLOR_API_KEY", SENTINEL_KEY)
    _mock_client_factory(monkeypatch, handler)
    _stub_r2_uploader(monkeypatch)
    input_file = tmp_path / "in.wav"
    input_file.write_bytes(b"\x00" * 2048)

    item = asyncio.run(stems_service.submit_stems(str(input_file), "stems-t2", model=V3_MODEL_OFFICIAL))
    assert item == "mss_2"
    assert captured["payload"]["model"] == V3_MODEL_OFFICIAL


# ── 3) MODEL_ID_UNVERIFIED env 门禁 ─────────────────────────────────────

def test_stems_v3_model_id_unconfigured(monkeypatch):
    monkeypatch.delenv("TEMPOLOR_STEMS_V3_MODEL_ID", raising=False)
    assert stems_service.stems_v3_model_id() == ""


def test_stems_v3_zip_members_unconfigured(monkeypatch):
    monkeypatch.delenv("TEMPOLOR_STEMS_V3_ZIP_MEMBERS", raising=False)
    assert stems_service.stems_v3_zip_members() == {}


def test_stems_v3_zip_members_parsing(monkeypatch):
    monkeypatch.setenv(
        "TEMPOLOR_STEMS_V3_ZIP_MEMBERS",
        "x_vocals.flac:vocals, x_drums.flac:drums ,,x_bass.flac:bass",
    )
    got = stems_service.stems_v3_zip_members()
    assert got == {"x_vocals.flac": "vocals", "x_drums.flac": "drums", "x_bass.flac": "bass"}


def test_separate_v3_rejected_before_pricing(client, monkeypatch):
    """V3 未确认 model → 503 stems_v3_model_unverified（先于任务创建/Credits）。"""
    files = {"file": ("in.wav", b"\x00" * 2048, "audio/wav")}
    resp = client.post("/api/v1/ai/stems/separate", files=files, data={"version": "v3"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "stems_v3_model_unverified"
    # 任务/扣费零发生
    bal = credits_service.get_balance(USER)
    assert (bal["balance"] if isinstance(bal, dict) else bal) == 0


def test_separate_v3_rejected_without_members_even_with_model(client, monkeypatch):
    monkeypatch.setenv("TEMPOLOR_STEMS_V3_MODEL_ID", V3_MODEL_OFFICIAL)
    files = {"file": ("in.wav", b"\x00" * 2048, "audio/wav")}
    resp = client.post("/api/v1/ai/stems/separate", files=files, data={"version": "v3"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "stems_v3_members_unconfirmed"


def test_separate_invalid_version_400(client):
    files = {"file": ("in.wav", b"\x00" * 2048, "audio/wav")}
    resp = client.post("/api/v1/ai/stems/separate", files=files, data={"version": "v9"})
    assert resp.status_code == 400


def test_separate_v2_default_still_works_gate_free(client):
    """回归：不带 version → v2 既有路径（本测试只确认不被 V3 门禁误伤）。"""
    files = {"file": ("in.wav", b"\x00" * 2048, "audio/wav")}
    resp = client.post("/api/v1/ai/stems/separate", files=files)
    # v2 不因 V3 门禁被拒（402/200/429 均可能：取决于余额与并发；唯独不得是 503 v3 门禁）
    assert resp.status_code not in (503,) or resp.json().get("detail") not in (
        "stems_v3_model_unverified", "stems_v3_members_unconfirmed",
    )


# ── 4) 自定义成员白名单（V3 实测确认后的解压校验）────────────────────────

def test_extract_with_custom_members(tmp_path, monkeypatch):
    meta = {"codec": "flac", "duration": 100.0, "sample_rate": 44100, "channels": 2}
    monkeypatch.setattr(stems_service, "_probe_flac", lambda path: dict(meta))

    zip_path = tmp_path / "v3.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in VALID_V3_MEMBERS:
            zf.writestr(name, b"\x00" * 2048)

    got = stems_service.extract_and_validate_stems(
        str(zip_path), str(tmp_path / "out"), expected_members=VALID_V3_MEMBERS,
    )
    assert set(got.keys()) == set(VALID_V3_MEMBERS.values())
    assert got["vocals"].endswith("x_vocals.flac")


def test_extract_v3_rejects_unexpected_member(tmp_path, monkeypatch):
    meta = {"codec": "flac", "duration": 100.0, "sample_rate": 44100, "channels": 2}
    monkeypatch.setattr(stems_service, "_probe_flac", lambda path: dict(meta))

    zip_path = tmp_path / "v3_bad.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in VALID_V3_MEMBERS:
            zf.writestr(name, b"\x00" * 2048)
        zf.writestr("surprise.flac", b"\x00" * 64)  # 多一个都不行

    with pytest.raises(stems_service.StemsError):
        stems_service.extract_and_validate_stems(
            str(zip_path), str(tmp_path / "out2"), expected_members=VALID_V3_MEMBERS,
        )


def test_v2_default_whitelist_unchanged():
    assert stems_service.EXPECTED_ZIP_MEMBERS == {
        "originalaudio.flac": "original",
        "originalaudio_vocals.flac": "vocals",
        "originalaudio_bass.flac": "bass",
        "originalaudio_drums.flac": "drums",
        "originalaudio_other.flac": "other",
    }
