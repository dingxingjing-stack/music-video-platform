"""绔偣绾ф祦绋嬫祴璇曪細鎻愪氦 -> 杞 -> 瀹屾垚/澶辫触 -> 涓嬭浇 / 閲嶈瘯鍒嗚建 鍏ㄩ摼璺€?
瑕嗙洊鍏祴楠屾敹椤癸細
  1. POST /generate 绔嬪嵆杩斿洖 task_id锛堝紓姝ュ崗璁級
  2. GET /task 杞鍒扮粓鎬侊紙completed/failed锛?  3. completed 杩斿洖瀹屾暣姝屾洸棰勭鍚?URL
  4. completed 杩斿洖 vocals/drums/bass/other 鍥涜建棰勭鍚?  5. 鐢ㄦ埛 A/B 闅旂锛坧oll/download IDOR 403锛?  6. 姣忔棩棰濆害鐪熷疄杩涘叆鐢熶骇璋冪敤閾撅紙POST 鍓嶇疆鍘熷瓙棰勭暀锛?  7. 骞跺彂閿侊細鍚屾椂浠?1 涓换鍔★紙busy 鎷掔粷閲嶅 POST锛?  8. 閲嶅 POST 涓嶇粫杩囷紙鍚屼竴鐢ㄦ埛蹇欑鎷掔粷锛?  9. retry-stems 鎴愬姛 + 娆℃暟涓婇檺锛圡AX_AUTO_RETRIES锛?  10. 鍒嗚建澶辫触鏃跺畬鏁存瓕鏇蹭粛鍙笅杞斤紝鍒嗚建杩斿洖 409
  11. 鍏ㄥ钩鍙版瘡鏃ラ檺棰濋樆鏂柊浠诲姟锛堟垚鏈繚鎶わ級
  13. 涓嬭浇杩斿洖 600s 鐭湡棰勭鍚?URL锛堥潪姘镐箙 URL锛?  15. 鏃堕暱涓婇檺鍦ㄧ绾垮唴閽冲埗锛圡AX_AUDIO_DURATION_SECONDS锛?
娉細TestClient 涓?asyncio.create_task 鐨勫悗鍙颁换鍔′細鍦ㄨ姹傞棿缁х画鎵ц銆?涓洪伩鍏嶃€岀鐐瑰悗鍙颁换鍔°€嶄笌娴嬭瘯鎵嬪姩椹卞姩鐨勭绾垮弻閲嶆墽琛岋紙閰嶉/璁℃暟涓嶄竴鑷达級锛?娴佺▼绫荤敤渚嬮€氳繃 disable_bg 灏嗙鐐瑰悗鍙颁换鍔℃浛鎹负 no-op锛屼粎鐢辨祴璇曢┍鍔ㄥ悓涓€
鐢熶骇绠＄嚎鍑芥暟锛坃run_with_timeout / _run_retry_stems锛夛紱鍏朵綑璧扮湡瀹?HTTP 绔偣銆?"""

import asyncio
import os
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import ai_limits, task_store, provider_registry
from app.routers import ai_music

VOLUME_OK = {
    "full_wav": "song_full.wav",
    "full_mp3": "song_full.mp3",
    "vocals": "vocals.wav",
    "drums": "drums.wav",
    "bass": "bass.wav",
    "other": "other.wav",
}


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """鐙珛 SQLite + 鍏抽棴 HF 鍏滃簳 + 娓呯┖杩涚▼鍐呬换鍔?閿侊紙閬垮厤璺ㄦ祴璇曟薄鏌擄級銆?""
    db_path = str(tmp_path / "flow.db")
    monkeypatch.setattr(ai_limits, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(ai_limits, "_DB_PATH", db_path)
    monkeypatch.setattr(task_store, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(task_store, "_DB_PATH", db_path)
    monkeypatch.setattr(ai_music, "HF_FALLBACK_ENABLED", False)
    return db_path


@pytest.fixture()
def disable_bg(monkeypatch):
    """鎶婄鐐瑰悗鍙颁换鍔℃浛鎹负 no-op锛岃繑鍥炵湡瀹炵绾垮嚱鏁颁緵娴嬭瘯鎵嬪姩椹卞姩銆?""
    real = ai_music._run_with_timeout

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(ai_music, "_run_with_timeout", _noop)
    return real


@pytest.fixture()
def fake_modal(monkeypatch):
    """妯℃嫙 Modal GPU 绔細ACE-Step 鐢熸垚 + Demucs 鍒嗚建 + 鏂囦欢鍙栧洖 + R2 涓婁紶/棰勭鍚嶃€?""
    calls = {"generate": [], "separate": [], "download": []}

    async def _generate(prompt=None, lyrics=None, duration=None, **kwargs):
        calls["generate"].append({"prompt": prompt, "lyrics": lyrics, "duration": duration, **kwargs})
        return dict(VOLUME_OK)

    async def _download(name, local_dir):
        calls["download"].append(name)
        p = os.path.join(local_dir, name)
        with open(p, "w") as f:
            f.write("fake-audio")
        return p

    async def _separate(full_wav):
        calls["separate"].append(full_wav)
        return {"vocals": "vocals.wav", "drums": "drums.wav", "bass": "bass.wav", "other": "other.wav"}

    async def _upload(task_id, files_local):
        out = {}
        for k in files_local:
            ext = "mp3" if k == "full_mp3" else "wav"
            out[k] = f"music/{task_id}/{k}.{ext}"
        return out

    def _presign(key, expires_in=600):
        return f"https://signed/{key}"

    monkeypatch.setattr(provider_registry, "ace_step_generate", _generate)
    # Fal 涓虹敓浜э紝娴嬭瘯闇€鍚屾椂 mock fal 璺緞
    try:
        from app.services import fal_client
        monkeypatch.setattr(fal_client, "generate_via_fal", _generate)
    except Exception:
        pass
    monkeypatch.setattr(ai_music, "ace_step_download", _download)
    monkeypatch.setattr(ai_music, "ace_step_separate", _separate)
    monkeypatch.setattr(ai_music.cdn_uploader, "upload_music_package", _upload)
    monkeypatch.setattr(ai_music.cdn_uploader, "get_presigned_download_url", _presign)
    return calls


def _client():
    app = FastAPI()
    app.include_router(ai_music.router)
    return TestClient(app)


def _run_pipeline(run, task_id, user="uA", prompt="a summer pop song", duration=180):
    req = ai_music.GenerateRequest(prompt=prompt, style="pop", duration=duration, type="song")
    asyncio.run(run(task_id, req, user))


def _wait_terminal(c, task_id, headers, tries=60):
    for _ in range(tries):
        r = c.get(f"/api/v1/ai/task/{task_id}", headers=headers)
        if r.status_code == 200:
            st = r.json()["state"]
            if st in ("completed", "failed", "cancelled"):
                return r.json()
        time.sleep(0.02)
    raise AssertionError("浠诲姟鏈繘鍏ョ粓鎬?)


def _wait_store(task_id, states, tries=60):
    for _ in range(tries):
        st = (task_store.get(task_id) or {}).get("state")
        if st in states:
            return
        time.sleep(0.02)
    raise AssertionError(f"鍚庡彴浠诲姟鏈敹鏁涘埌 {states}")


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ 瀹屾暣閾捐矾 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def test_full_flow_completed(isolated_db, fake_modal, disable_bg):
    """1/2/3/4/6/13: 鎻愪氦杩斿洖 task_id锛涢搴﹀湪 GPU 鍓嶅師瀛愰鐣欙紱瀹屾垚杩斿洖瀹屾暣姝?鍥涜建棰勭鍚嶏紱涓嬭浇涓虹煭鏈熼绛惧悕銆?""
    c = _client()
    r = c.post("/api/v1/ai/generate", json={"prompt": "a summer pop song"}, headers={"Authorization": "Bearer uA"})
    assert r.status_code == 200
    d = r.json()
    assert d["success"] is True and d["task_id"] and d["status_url"]
    tid = d["task_id"]

    # 棰濆害鍦ㄧ绾匡紙GPU锛夎繍琛屽墠宸插師瀛愰鐣?鈥斺€?鐢熶骇璋冪敤閾鹃獙璇侊紙P1锛?    assert ai_limits.reserve_generation("uA")["success"] is False

    _run_pipeline(disable_bg, tid)
    poll = _wait_terminal(c, tid, {"Authorization": "Bearer uA"})
    assert poll["state"] == "completed"
    assert poll["stems_state"] == "ok"
    assert poll["audio_url"].startswith("https://signed/")
    assert set(poll["stems"]) == {"vocals", "drums", "bass", "other"}

    # 涓嬭浇涓?600s 棰勭鍚嶏紝闈炴案涔呭叕寮€ URL
    rdl = c.get(f"/api/v1/ai/task/{tid}/download?file=full", headers={"Authorization": "Bearer uA"})
    assert rdl.status_code == 200
    assert rdl.json()["expires_in"] == 600
    assert rdl.json()["url"].startswith("https://signed/")

    # 鎴愬姛涓嶉€€娆?鈫?褰撴棩棰濆害浠嶈鍗犵敤
    r2 = c.post("/api/v1/ai/generate", json={"prompt": "another song"}, headers={"Authorization": "Bearer uA"})
    assert r2.json()["success"] is False


def test_busy_lock_blocks_duplicate(isolated_db, fake_modal, disable_bg):
    """7/8: 鍚屾椂浠?1 涓换鍔★紱閲嶅 POST 鍦ㄩ攣閲婃斁鍓嶈鎷掔粷銆?""
    c = _client()
    r = c.post("/api/v1/ai/generate", json={"prompt": "a summer pop song"}, headers={"Authorization": "Bearer uB"})
    tid = r.json()["task_id"]
    assert task_store.is_user_busy("uB") is True

    r2 = c.post("/api/v1/ai/generate", json={"prompt": "another song"}, headers={"Authorization": "Bearer uB"})
    assert r2.json()["success"] is False
    assert "姝ｅ湪杩涜" in r2.json()["error"]

    # 閲婃斁閿?+ 鍥為€€棰濆害鍚庡彲鍐嶆鎻愪氦
    task_store.release_lock_for_task(tid)
    ai_limits.refund_generation("uB")
    r3 = c.post("/api/v1/ai/generate", json={"prompt": "another song"}, headers={"Authorization": "Bearer uB"})
    assert r3.json()["success"] is True


def test_global_limit_blocks_new_tasks(isolated_db, fake_modal, disable_bg, monkeypatch):
    """11: 鍏ㄥ钩鍙版瘡鏃ラ檺棰濋樆鏂柊浠诲姟锛堟垚鏈繚鎶わ紝30 -> 1锛夈€?""
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 1)
    c = _client()
    r = c.post("/api/v1/ai/generate", json={"prompt": "song A"}, headers={"Authorization": "Bearer uA"})
    assert r.json()["success"] is True
    r2 = c.post("/api/v1/ai/generate", json={"prompt": "song B"}, headers={"Authorization": "Bearer uB"})
    assert r2.json()["success"] is False
    assert "鍏ㄥ钩鍙? in r2.json()["error"]


def test_duration_clamped(isolated_db, fake_modal, disable_bg, monkeypatch):
    """15: 璇锋眰鏃堕暱瓒呰繃涓婇檺鏃跺湪绠＄嚎鍐呴挸鍒跺埌 MAX_AUDIO_DURATION_SECONDS銆?""
    monkeypatch.setattr(ai_music, "MAX_AUDIO_DURATION_SECONDS", 60)
    c = _client()
    r = c.post("/api/v1/ai/generate", json={"prompt": "a song", "duration": 180}, headers={"Authorization": "Bearer uA"})
    tid = r.json()["task_id"]
    _run_pipeline(disable_bg, tid, duration=180)
    assert fake_modal["generate"][0]["duration"] == 60


def test_auto_retry_on_generate_failure(isolated_db, fake_modal, disable_bg, monkeypatch):
    """MAX_AUTO_RETRIES=1锛氶娆″け璐ヨ嚜鍔ㄩ噸璇曪紝绗簩娆℃垚鍔熷垯瀹屾垚銆?""
    monkeypatch.setattr(ai_music, "MAX_AUTO_RETRIES", 1)
    calls = []

    async def flaky_generate(prompt=None, lyrics=None, duration=None, **kwargs):
        calls.append(duration)
        if len(calls) == 1:
            return None
        return dict(VOLUME_OK)

    monkeypatch.setattr(provider_registry, "ace_step_generate", flaky_generate)
    try:
        from app.services import fal_client
        monkeypatch.setattr(fal_client, "generate_via_fal", flaky_generate)
    except Exception:
        pass
    c = _client()
    r = c.post("/api/v1/ai/generate", json={"prompt": "a song"}, headers={"Authorization": "Bearer uA"})
    tid = r.json()["task_id"]
    _run_pipeline(disable_bg, tid)
    poll = _wait_terminal(c, tid, {"Authorization": "Bearer uA"})
    assert poll["state"] == "completed"
    assert len(calls) == 2  # 1 娆″垵璇?+ 1 娆¤嚜鍔ㄩ噸璇?

def test_failed_flow_refunds_and_marks_failed(isolated_db, fake_modal, disable_bg, monkeypatch):
    """鐢熸垚褰诲簳澶辫触 鈫?浠诲姟 failed + 棰濆害鍥為€€锛堝彲鍐嶆鎻愪氦锛夈€?""
    monkeypatch.setattr(ai_music, "MAX_AUTO_RETRIES", 1)

    async def never(prompt=None, lyrics=None, duration=None, **kwargs):
        return None

    monkeypatch.setattr(provider_registry, "ace_step_generate", never)
    try:
        from app.services import fal_client
        monkeypatch.setattr(fal_client, "generate_via_fal", never)
    except Exception:
        pass
    c = _client()
    r = c.post("/api/v1/ai/generate", json={"prompt": "a song"}, headers={"Authorization": "Bearer uA"})
    tid = r.json()["task_id"]
    _run_pipeline(disable_bg, tid)
    poll = _wait_terminal(c, tid, {"Authorization": "Bearer uA"})
    assert poll["state"] == "failed"
    # 閫€娆剧敓鏁?鈫?鍐嶆鎻愪氦鎴愬姛
    r2 = c.post("/api/v1/ai/generate", json={"prompt": "another"}, headers={"Authorization": "Bearer uA"})
    assert r2.json()["success"] is True


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ 鍒嗚建閲嶈瘯 / 闅旂 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def test_retry_stems_limit(isolated_db, fake_modal, disable_bg, monkeypatch):
    """9/10: 鍒嗚建澶辫触鏃跺畬鏁存瓕鏇蹭粛鍙笅杞斤紙鍒嗚建 409锛夛紱閲嶈瘯杈?MAX_AUTO_RETRIES 涓婇檺琚嫆锛?29锛夈€?""
    async def _fail_separate(full_wav):
        return None

    monkeypatch.setattr(ai_music, "ace_step_separate", _fail_separate)
    c = _client()
    tid = task_store.new_task(user_key="uA", task_id="retry-limit")
    task_store.update(tid, state="completed_with_stems_failed", progress=100, stems_state="failed",
                      volume_files={"full_wav": "song_full.wav"},
                      download={"full_mp3": "music/retry-limit/full.mp3"})

    # 鍒嗚建澶辫触浣嗗畬鏁存瓕鏇蹭粛鍙笅杞斤紙409 vs 200锛?    assert c.get(f"/api/v1/ai/task/{tid}/download?file=vocals", headers={"Authorization": "Bearer uA"}).status_code == 409
    assert c.get(f"/api/v1/ai/task/{tid}/download?file=full", headers={"Authorization": "Bearer uA"}).status_code == 200

    # 绗竴娆￠噸璇曟垚鍔熷彈鐞嗭紙璁℃暟 +1锛?    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"Authorization": "Bearer uA"})
    assert r.status_code == 200, r.text
    assert task_store.get(tid)["stem_retries"] == 1

    # 绛夊悗鍙板け璐ラ噸璇曟敹鏁涳紙鍥炲埌 completed_with_stems_failed锛?    _wait_store(tid, {"completed_with_stems_failed"})

    # 杈?MAX_AUTO_RETRIES=1 鈫?绗簩娆¤鎷掞紙429锛?    r2 = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"Authorization": "Bearer uA"})
    assert r2.status_code == 429, r2.text


def test_retry_stems_success(isolated_db, fake_modal, disable_bg):
    """9: retry-stems 鎴愬姛 鈫?鐘舵€佸洖 completed銆佸洓杞ㄥ彲鐢ㄣ€佸垎杞ㄥ彲涓嬭浇銆?""
    c = _client()
    tid = task_store.new_task(user_key="uA", task_id="retry-ok")
    task_store.update(tid, state="completed_with_stems_failed", progress=100, stems_state="failed",
                      volume_files={"full_wav": "song_full.wav"},
                      download={"full_mp3": "music/retry-ok/full.mp3"})

    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"Authorization": "Bearer uA"})
    assert r.status_code == 200, r.text

    _wait_store(tid, {"completed"})
    poll = c.get(f"/api/v1/ai/task/{tid}", headers={"Authorization": "Bearer uA"}).json()
    assert poll["state"] == "completed"
    assert poll["stems_state"] == "ok"
    assert c.get(f"/api/v1/ai/task/{tid}/download?file=vocals", headers={"Authorization": "Bearer uA"}).status_code == 200


def test_cross_user_isolation_flow(isolated_db, fake_modal, disable_bg):
    """5: 鐢ㄦ埛 B 鏃犳硶璇诲彇 / 涓嬭浇鐢ㄦ埛 A 鐨勪换鍔★紙IDOR 闃叉姢璐┛ poll 涓?download锛夈€?""
    c = _client()
    r = c.post("/api/v1/ai/generate", json={"prompt": "song A"}, headers={"Authorization": "Bearer uA"})
    tid = r.json()["task_id"]
    _run_pipeline(disable_bg, tid)
    poll = _wait_terminal(c, tid, {"Authorization": "Bearer uA"})
    assert poll["state"] == "completed"
    assert c.get(f"/api/v1/ai/task/{tid}", headers={"Authorization": "Bearer uB"}).status_code == 403
    assert c.get(f"/api/v1/ai/task/{tid}/download?file=full", headers={"Authorization": "Bearer uB"}).status_code == 403


# Phase 3B-1锛氳韩浠芥敼涓?Authorization Bearer JWT銆傛祴璇曠幆澧冧笉鑱旂湡瀹?Supabase Auth锛?# 鍥犳 autouse 鎵撴々 resolve_auth_user_id锛屼娇 "Bearer <token>" 鏈夋晥鏃跺彲纭畾鍦拌繑鍥?token 閮ㄥ垎锛?# 涓?"Authorization" 缂哄け/闈?Bearer 杩斿洖 None锛堢瓑浠?fail-closed 401锛夛紝涓嶄緷璧栫幆澧冨彉閲忋€?@pytest.fixture(autouse=True)
def _jwt_identity_stub(monkeypatch):
    from app.services import auth_identity

    def _resolve(auth):
        if isinstance(auth, str) and auth.startswith("Bearer "):
            return auth[len("Bearer "):]
        return None

    monkeypatch.setattr(auth_identity, "resolve_auth_user_id", _resolve)
