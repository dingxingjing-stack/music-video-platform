"""B4 娴嬭瘯锛歁odal GPU 姣忔棩棰勭畻纭仠绾匡紙鏈嶅姟绔湡瀹炵‖闄愬埗锛岄潪鍓嶇鎻愮ず锛夈€?
瑕嗙洊锛?  1. 鏈揪鍒伴绠?鈫?鍙互鍒涘缓浠诲姟
  2. 杈惧埌棰勭畻 鈫?闃绘鏂颁换鍔★紙鏄庣‘闄愰閿欒锛?  3. 闃绘鏃朵笉浼氬惎鍔?GPU锛堜笉璋冪敤 ace_step_generate锛?  4. 閲嶅璇锋眰涓嶄細缁曡繃棰勭畻
  5. 骞跺彂涓嶄細缁曡繃棰勭畻锛堟潯浠惰嚜澧炲師瀛愭€э級
  6. retry-stems锛圖emucs GPU锛変笉浼氱粫杩囬绠?  7. 鏈嶅姟閲嶅惎鍚庨绠楃姸鎬佷笉涓㈠け锛圫QLite 鎸佷箙鍖栵級
"""

import concurrent.futures

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import ai_music
from app.services import ai_limits, task_store, provider_registry


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """鐙珛 SQLite + 娓呯┖杩涚▼鍐呬换鍔?閿侊紝閬垮厤璺ㄦ祴璇曟薄鏌撱€?""
    db_path = str(tmp_path / "budget.db")
    monkeypatch.setattr(ai_limits, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(ai_limits, "_DB_PATH", db_path)
    monkeypatch.setattr(task_store, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(task_store, "_DB_PATH", db_path)
    monkeypatch.setattr(ai_music, "HF_FALLBACK_ENABLED", False)
    return db_path


@pytest.fixture()
def disable_bg(monkeypatch):
    """绔偣鍚庡彴浠诲姟鏇挎崲涓?no-op锛岄伩鍏嶆祴璇曢┍鍔ㄤ笌鍚庡彴閲嶅鎵ц銆?""

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(ai_music, "_run_with_timeout", _noop)


@pytest.fixture()
def fake_modal(monkeypatch):
    """璁板綍 GPU 璋冪敤锛坓enerate=ACE-Step, separate=Demucs锛夛紝榛樿涓嶇湡姝ｈ繍琛屻€?""
    calls = {"generate": [], "separate": []}

    async def _generate(prompt=None, lyrics=None, duration=None):
        calls["generate"].append(duration)
        return {"full_wav": "song_full.wav"}

    async def _separate(full_wav):
        calls["separate"].append(full_wav)
        return {"vocals": "v.wav", "drums": "d.wav", "bass": "b.wav", "other": "o.wav"}

    monkeypatch.setattr(provider_registry, "ace_step_generate", _generate)
    monkeypatch.setattr(ai_music, "ace_step_separate", _separate)
    return calls


def _client():
    app = FastAPI()
    app.include_router(ai_music.router)
    return TestClient(app)


def _no_user_limits(monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 1000)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 1000)


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ 棰勭畻纭仠绾?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def test_under_budget_can_create_task(isolated_db, fake_modal, disable_bg, monkeypatch):
    """1: 鏈揪鍒伴绠?鈫?鍙垱寤轰换鍔★紙reserve 鎴愬姛锛屼换鍔″叆闃燂級銆?""
    _no_user_limits(monkeypatch)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "5")
    r = ai_limits.reserve_generation("u1")
    assert r["success"] is True
    assert r["budget_daily_used"] == 1 and r["budget_daily_limit"] == 5

    c = _client()
    rr = c.post("/api/v1/ai/generate", json={"prompt": "a song"}, headers={"Authorization": "Bearer u2"})
    assert rr.status_code == 200 and rr.json()["success"] is True
    # 浠诲姟宸插垱寤猴紝閫氳繃 is_user_busy 楠岃瘉
    assert task_store.is_user_busy("u2") is True


def test_at_budget_blocks_new_task(isolated_db, monkeypatch):
    """2: 杈惧埌棰勭畻 鈫?闃绘鏂颁换鍔★紝杩斿洖鏄庣‘闄愰閿欒銆?""
    _no_user_limits(monkeypatch)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "1")
    assert ai_limits.reserve_generation("u1")["success"] is True
    r = ai_limits.reserve_generation("u2")
    assert r["success"] is False
    assert "棰勭畻" in r["error"]


def test_blocked_does_not_start_gpu(isolated_db, fake_modal, disable_bg, monkeypatch):
    """3: 棰勭畻鐢ㄥ敖琚嫆鏃朵笉浼氬惎鍔?GPU锛堜笉璋冪敤 ace_step_generate锛屼笉鍒涘缓浠诲姟锛夈€?""
    _no_user_limits(monkeypatch)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "1")
    assert ai_limits.reserve_generation("u1")["success"] is True  # 棰勭畻鐢ㄥ敖

    c = _client()
    r = c.post("/api/v1/ai/generate", json={"prompt": "a song"}, headers={"Authorization": "Bearer u2"})
    assert r.status_code == 429  # 棰勭畻纭仠绾匡細GPU 鍚姩鍓?429
    assert r.json()["success"] is False
    assert "棰勭畻" in r.json()["error"]
    assert fake_modal["generate"] == []  # 鏈惎鍔?ACE-Step GPU
    # 浠诲姟鏈垱寤猴紝is_user_busy 搴斾负 False
    assert task_store.is_user_busy("u2") is False


def test_repeat_requests_cannot_bypass_budget(isolated_db, monkeypatch):
    """4: 棰勭畻鐢ㄥ敖鍚庤繛缁噸澶嶈姹傚潎琚嫆缁濄€?""
    _no_user_limits(monkeypatch)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "1")
    assert ai_limits.reserve_generation("u1")["success"] is True
    for i in range(5):
        assert ai_limits.reserve_generation(f"u{i + 2}")["success"] is False


def test_concurrency_cannot_bypass_budget(isolated_db, monkeypatch):
    """5: 骞跺彂璇锋眰鏃犳硶瓒婅繃棰勭畻锛堟潯浠惰嚜澧炲師瀛愭€э紝鎭板ソ鍙垚鍔?budget 娆★級銆?""
    _no_user_limits(monkeypatch)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "3")

    def _call(i):
        return ai_limits.reserve_generation(f"conc-{i}")["success"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        results = list(ex.map(_call, range(40)))
    assert sum(results) == 3
    assert ai_limits.budget_hard_stop_reached() is True


def test_retry_stems_gated_by_budget(isolated_db, fake_modal, disable_bg, monkeypatch):
    """6: 棰勭畻鐢ㄥ敖鍚?retry-stems锛圖emucs GPU锛夎 429 鎷掔粷锛屼笉鍚姩 Demucs銆?""
    _no_user_limits(monkeypatch)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "1")
    assert ai_limits.reserve_generation("u1")["success"] is True  # 棰勭畻鐢ㄥ敖

    tid = task_store.new_task(user_key="uA", task_id="budget-retry")
    task_store.update(
        tid, state="completed_with_stems_failed", progress=100, stems_state="failed",
        volume_files={"full_wav": "song_full.wav"},
        download={"full_mp3": "music/budget-retry/full.mp3"},
    )
    c = _client()
    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"Authorization": "Bearer uA"})
    assert r.status_code == 429
    assert "棰勭畻" in r.json()["detail"]
    assert fake_modal["separate"] == []  # 鏈惎鍔?Demucs GPU


def test_budget_state_persists_across_restart(isolated_db, monkeypatch):
    """7: 棰勭畻鐘舵€佹寔涔呭寲鍦?SQLite锛涙湇鍔￠噸鍚悗渚濇棫纭€ф嫆缁濄€?""
    _no_user_limits(monkeypatch)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "1")
    assert ai_limits.reserve_generation("u1")["success"] is True
    assert ai_limits.budget_hard_stop_reached() is True

    # 妯℃嫙鏈嶅姟閲嶅惎锛氶噸鏂版墦寮€杩炴帴 + 閲嶈窇寤鸿〃锛堟暟鎹湪 SQLite 鏂囦欢锛屼笉涓㈠け锛?    conn = ai_limits._get_conn()
    try:
        ai_limits._init_db(conn)
        g = conn.execute(
            "SELECT count FROM global_usage WHERE date=?", (ai_limits._today(),)
        ).fetchone()
        assert g and g["count"] == 1
    finally:
        conn.close()

    assert ai_limits.reserve_generation("u2")["success"] is False
    assert "棰勭畻" in ai_limits.reserve_generation("u3")["error"]


def test_budget_status_exposes_used_and_limit(isolated_db, monkeypatch):
    """棰濆锛?limits 杩斿洖棰勭畻浣跨敤涓庨檺棰濓紙渚涘墠绔?杩愯惀鏌ョ湅锛岀湡瀹炴湇鍔＄鏁版嵁锛夈€?""
    _no_user_limits(monkeypatch)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "4")
    ai_limits.reserve_generation("u1")
    import asyncio

    st = asyncio.run(ai_limits.generation_usage_status("u1"))
    assert st["budget_daily_limit"] == 4
    assert st["budget_daily_used"] == 1


# Phase 3B-1锛氳韩浠芥敼涓?Authorization Bearer JWT銆傛祴璇曠幆澧冧笉鑱旂湡瀹?Supabase Auth锛?# 鍥犳 autouse 鎵撴々 resolve_auth_user_id锛屼娇 "Bearer <token>" 鏈夋晥鏃跺彲纭畾鍦拌繑鍥?token 閮ㄥ垎锛?# 涓?"Authorization" 缂哄け/闈?Bearer 杩斿洖 None锛堢瓑浠?fail-closed 401锛夛紝涓嶄緷璧栫幆澧冨彉閲忋€?@pytest.fixture(autouse=True)
def _jwt_identity_stub(monkeypatch):
    from app.services import auth_identity

    def _resolve(auth):
        if isinstance(auth, str) and auth.startswith("Bearer "):
            return auth[len("Bearer "):]
        return None

    monkeypatch.setattr(auth_identity, "resolve_auth_user_id", _resolve)
