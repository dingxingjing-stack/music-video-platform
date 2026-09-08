"""娴嬭瘯锛欰I 鐢熸垚棰濆害/鎴愭湰淇濇姢 + 鎺堟潈涓嬭浇锛圛DOR 闃叉姢/闄愭祦/瀹¤锛夈€?""

import tempfile

import pytest

from app.services import ai_limits, task_store
from app.routers import ai_music


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """姣忎釜娴嬭瘯浣跨敤鐙珛 SQLite锛岄伩鍏嶆薄鏌?backend/data/beta.db銆?""
    db_path = str(tmp_path / "test_beta.db")
    monkeypatch.setattr(ai_limits, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(ai_limits, "_DB_PATH", db_path)
    monkeypatch.setattr(task_store, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(task_store, "_DB_PATH", db_path)
    return db_path


def _task_for(user: str, task_id: str = "task-test-1") -> str:
    tid = task_store.new_task(user_key=user, task_id=task_id)
    prefix = f"music/{task_id}"
    task_store.update(tid, state="completed", progress=100, stems_state="ok", download={
        "full_mp3": f"{prefix}/full.mp3",
        "full_wav": f"{prefix}/full.wav",
        "vocals": f"{prefix}/vocals.wav",
        "drums": f"{prefix}/drums.wav",
        "bass": f"{prefix}/bass.wav",
        "other": f"{prefix}/other.wav",
    })
    return tid


def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(ai_music.router)
    return TestClient(app)


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ 棰濆害 / 鎴愭湰淇濇姢 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def test_daily_limit_enforced(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 1)
    assert ai_limits.reserve_generation("u1")["success"] is True
    r2 = ai_limits.reserve_generation("u1")
    assert r2["success"] is False
    assert "浠婃棩" in r2["error"]
    ai_limits.refund_generation("u1")
    assert ai_limits.reserve_generation("u1")["success"] is True


def test_monthly_limit_enforced(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 2)
    for _ in range(2):
        assert ai_limits.reserve_generation("u2")["success"] is True
    assert ai_limits.reserve_generation("u2")["success"] is False


def test_global_daily_cost_guard(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 2)
    assert ai_limits.reserve_generation("u3")["success"] is True
    assert ai_limits.reserve_generation("u4")["success"] is True
    blocked = ai_limits.reserve_generation("u5")
    assert blocked["success"] is False
    assert "鍏ㄥ钩鍙? in blocked["error"]
    # 鍏ㄥ眬璁℃暟鍙涓嶅噺锛氬け璐ラ€€娆句笉鍥為€€鍏ㄥ眬锛堥槻"澶辫触鈫掗€€娆锯啋閲嶈瘯"绌鸿浆 GPU锛?    ai_limits.refund_generation("u3")
    assert ai_limits.reserve_generation("u5")["success"] is False


def test_budget_hard_stop(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "1")
    assert ai_limits.reserve_generation("u6")["success"] is True
    blocked = ai_limits.reserve_generation("u7")
    assert blocked["success"] is False
    assert "棰勭畻" in blocked["error"]


def test_refund_never_below_zero(isolated_db):
    ai_limits.refund_generation("ghost")
    assert ai_limits.reserve_generation("ghost")["success"] is True


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ 鎺堟潈涓嬭浇 / IDOR 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def test_download_requires_matching_user(isolated_db, monkeypatch):
    monkeypatch.setattr(
        ai_music.cdn_uploader, "get_presigned_download_url",
        lambda key, expires_in=600: f"https://signed/{key}",
    )
    _task_for("userA", "task-idor-1")

    c = _client()
    # 鐢ㄦ埛 A 鑷繁涓嬭浇 鈫?200 + 棰勭鍚?URL
    r = c.get("/api/v1/ai/task/task-idor-1/download?file=full", headers={"Authorization": "Bearer userA"})
    assert r.status_code == 200, r.text
    assert "https://signed/music/task-idor-1/full.mp3" in r.json()["url"]

    # 鐢ㄦ埛 B 灏濊瘯涓嬭浇鐢ㄦ埛 A 鐨?job 鈫?403锛圛DOR 闃叉姢锛?    r = c.get("/api/v1/ai/task/task-idor-1/download?file=full", headers={"Authorization": "Bearer userB"})
    assert r.status_code == 403

    # 鏃?Authorization 鈫?401锛堜緷璧栧眰 fail-closed锛?    r = c.get("/api/v1/ai/task/task-idor-1/download?file=full")
    assert r.status_code == 401

    # 涓嶅瓨鍦ㄧ殑 job 鈫?404
    r = c.get("/api/v1/ai/task/task-none/download?file=full", headers={"Authorization": "Bearer userA"})
    assert r.status_code == 404


def test_download_full_wav_and_stems(isolated_db, monkeypatch):
    monkeypatch.setattr(
        ai_music.cdn_uploader, "get_presigned_download_url",
        lambda key, expires_in=600: f"https://signed/{key}",
    )
    _task_for("userA", "task-idor-2")
    c = _client()
    r = c.get("/api/v1/ai/task/task-idor-2/download?file=full&fmt=wav", headers={"Authorization": "Bearer userA"})
    assert r.status_code == 200 and "full.wav" in r.json()["url"]
    for stem in ("vocals", "drums", "bass", "other"):
        r = c.get(f"/api/v1/ai/task/task-idor-2/download?file={stem}", headers={"Authorization": "Bearer userA"})
        assert r.status_code == 200, f"{stem}: {r.text}"


def test_stem_download_blocked_when_stems_failed(isolated_db, monkeypatch):
    monkeypatch.setattr(
        ai_music.cdn_uploader, "get_presigned_download_url",
        lambda key, expires_in=600: f"https://signed/{key}",
    )
    tid = task_store.new_task(user_key="userA", task_id="task-stemfail")
    task_store.update(tid, state="completed_with_stems_failed", progress=100, stems_state="failed",
                      download={"full_mp3": "music/x/full.mp3"})
    c = _client()
    r = c.get("/api/v1/ai/task/task-stemfail/download?file=vocals", headers={"Authorization": "Bearer userA"})
    assert r.status_code == 409
    r = c.get("/api/v1/ai/task/task-stemfail/download?file=full", headers={"Authorization": "Bearer userA"})
    assert r.status_code == 200


def test_download_rate_limit(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "DOWNLOAD_RATE_LIMIT", 2)
    monkeypatch.setattr(
        ai_music.cdn_uploader, "get_presigned_download_url",
        lambda key, expires_in=600: f"https://signed/{key}",
    )
    _task_for("userR", "task-rate")
    c = _client()
    assert c.get("/api/v1/ai/task/task-rate/download", headers={"Authorization": "Bearer userR"}).status_code == 200
    assert c.get("/api/v1/ai/task/task-rate/download", headers={"Authorization": "Bearer userR"}).status_code == 200
    assert c.get("/api/v1/ai/task/task-rate/download", headers={"Authorization": "Bearer userR"}).status_code == 429


def test_task_poll_ownership(isolated_db, monkeypatch):
    monkeypatch.setattr(
        ai_music.cdn_uploader, "get_presigned_download_url",
        lambda key, expires_in=600: f"https://signed/{key}",
    )
    _task_for("userA", "task-poll")
    c = _client()
    assert c.get("/api/v1/ai/task/task-poll", headers={"Authorization": "Bearer userA"}).status_code == 200
    assert c.get("/api/v1/ai/task/task-poll", headers={"Authorization": "Bearer userB"}).status_code == 403
    # 鏃?Authorization 鈫?401锛堝垹闄ゅ尶鍚嶆斁琛岋級
    assert c.get("/api/v1/ai/task/task-poll").status_code == 401


# Phase 3B-1锛氳韩浠芥敼涓?Authorization Bearer JWT銆傛祴璇曠幆澧冧笉鑱旂湡瀹?Supabase Auth锛?# 鍥犳 autouse 鎵撴々 resolve_auth_user_id锛屼娇 "Bearer <token>" 鏈夋晥鏃跺彲纭畾鍦拌繑鍥?token 閮ㄥ垎锛?# 涓?"Authorization" 缂哄け/闈?Bearer 杩斿洖 None锛堢瓑浠?fail-closed 401锛夛紝涓嶄緷璧栫幆澧冨彉閲忋€?@pytest.fixture(autouse=True)
def _jwt_identity_stub(monkeypatch):
    from app.services import auth_identity

    def _resolve(auth):
        if isinstance(auth, str) and auth.startswith("Bearer "):
            return auth[len("Bearer "):]
        return None

    monkeypatch.setattr(auth_identity, "resolve_auth_user_id", _resolve)
