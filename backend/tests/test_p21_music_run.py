"""P2-1 修复验证：POST /api/v1/music/run 无条件 410。

验证（无论 WORKFLOW_MODE=mock/real）：
  - 返回 410 Gone
  - 不调用 reserve_generation
  - 不调用任何真实 provider / 推理（factory.create、run_musicgen_and_save）
  - 不创建任务 / 不产生 quota 消耗
  - /api/v1/ai/generate 不受影响（仍有保留测试）
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import main as main_mod
from app.services import ai_limits


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    """记录是否被调用：reserve / factory.create / run_musicgen_and_save。"""
    calls = {"reserve": 0, "create": 0, "musicgen_save": 0}

    monkeypatch.setattr(ai_limits, "reserve_generation",
                        lambda *a, **k: calls.__setitem__("reserve", calls["reserve"] + 1) or {"success": True})

    def _create(*a, **k):
        calls["create"] += 1
        return object()

    monkeypatch.setattr(main_mod.factory, "create", _create)

    async def _save(*a, **k):
        calls["musicgen_save"] += 1
        return None

    monkeypatch.setattr(main_mod, "run_musicgen_and_save", _save)
    return calls


@pytest.fixture()
def client():
    return TestClient(main_mod.app)


@pytest.mark.parametrize("mode", ["mock", "real"])
def test_music_run_returns_410_and_no_inference(client, _patch, monkeypatch, mode):
    monkeypatch.setattr(main_mod, "WORKFLOW_MODE", mode)
    r = client.post("/api/v1/music/run", json={"prompt": "a song"}, headers={"X-User-ID": "u1"})
    assert r.status_code == 410
    # 关键：不触发任何 quota / provider / 推理
    assert _patch["reserve"] == 0, "410 路径不得调用 reserve_generation"
    assert _patch["create"] == 0, "410 路径不得创建 service"
    assert _patch["musicgen_save"] == 0, "410 路径不得运行真实推理"


def test_music_run_no_quota_consume(client, monkeypatch):
    """410 不消耗 quota（不调用 reserve，也无 refund）。"""
    monkeypatch.setattr(main_mod, "WORKFLOW_MODE", "real")
    from app.services import ai_limits as _al
    reserve_hits = []
    monkeypatch.setattr(_al, "reserve_generation",
                        lambda *a, **k: reserve_hits.append(1) or {"success": True})
    monkeypatch.setattr(main_mod.factory, "create", lambda *a, **k: object())
    r = client.post("/api/v1/music/run", json={"prompt": "x"})
    assert r.status_code == 410
    assert reserve_hits == []