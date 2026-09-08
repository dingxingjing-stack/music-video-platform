"""P0-4 Phase 3 鈥?retry-stems 閰嶉涓庝换鍔℃墍鏈夋潈瀹夊叏娴嬭瘯锛圱1鈥揟10锛夈€?
鑳屾櫙锛堝璁＄‘璁わ級锛?  - retry-stems 鐨?GPU 鍏ュ彛 ace_step_client.separate_only 鍦?ENVIRONMENT=production 鏃?    鐩存帴 return None锛圡odal Spleeter 宸蹭笅绾匡紝鐢熶骇涓诲姏鏄?RunPod锛夛紝鍥犳 retry-stems
    **涓嶄骇鐢熸櫘閫?generation 鐨勭湡瀹?GPU 鎴愭湰锛屼笉搴旂撼鍏?beta/generation 鐢ㄦ埛棰濆害**銆?  - 浣嗗畠浠嶅彲鑳藉惎鍔ㄧ湡瀹?GPU锛堥潪鐢熶骇锛夛紝蹇呴』鍙椾互涓嬩笁閲嶄繚鎶わ細
      1) 韬唤/IDOR锛坱ask.user_key == X-User-ID锛?      2) 鍏ㄥ钩鍙版垚鏈‖鍋?global_hard_stop_reached锛堣鐩?GLOBAL_DAILY_GENERATION_LIMIT + 棰勭畻锛?      3) 娆℃暟涓婇檺 MAX_AUTO_RETRIES + 骞跺彂鍘熷瓙鍗犻攣锛坅cquire_lock锛?"""
import concurrent.futures
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import ai_music
from app.services import ai_limits, task_store


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "retry.db")
    monkeypatch.setattr(ai_limits, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(ai_limits, "_DB_PATH", db_path)
    monkeypatch.setattr(task_store, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(task_store, "_DB_PATH", db_path)
    monkeypatch.setattr(ai_music, "HF_FALLBACK_ENABLED", False)
    return db_path


@pytest.fixture()
def calls(monkeypatch):
    """鏇挎崲 Spleeter GPU 璋冪敤涓鸿鏁?stub锛屼笉鐪熸鍚姩 GPU銆?""
    c = {"separate": []}

    async def _separate(full_wav):
        c["separate"].append(full_wav)
        return {"vocals": "v.wav", "drums": "d.wav", "bass": "b.wav", "other": "o.wav"}

    monkeypatch.setattr(ai_music, "ace_step_separate", _separate)
    return c


def _client():
    app = FastAPI()
    app.include_router(ai_music.router)
    return TestClient(app)


def _make_task(user_key="uA", task_id="t1", state="completed_with_stems_failed", stems_state="failed"):
    tid = task_store.new_task(user_key=user_key, task_id=task_id)
    task_store.update(tid, state=state, progress=100, stems_state=stems_state,
                      volume_files={"full_wav": "song_full.wav"},
                      download={"full_mp3": f"music/{task_id}/full.mp3"})
    return tid


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ T1: 鑷繁鐨?task retry 鈫?鍏佽 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
def test_t1_own_task_retry_allowed(isolated_db, calls):
    c = _client()
    tid = _make_task("uA", "t1")
    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"Authorization": "Bearer uA"})
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ T2: 浠栦汉 task retry 鈫?鎷掔粷 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
def test_t2_other_user_task_retry_denied(isolated_db, calls):
    c = _client()
    tid = _make_task("uA", "t2")
    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"Authorization": "Bearer uB"})
    assert r.status_code == 403, r.text
    assert calls["separate"] == []  # 鏈惎鍔?GPU


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ T3: 鏃?X-User-ID 鈫?鎷掔粷 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
def test_t3_no_x_user_id_denied(isolated_db, calls):
    c = _client()
    tid = _make_task("uA", "t3")
    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems")
    assert r.status_code == 401, r.text
    assert calls["separate"] == []


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ T4: body.user_id 浼€?鈫?浠嶆嫆缁?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
def test_t4_body_user_id_forgery_still_denied(isolated_db, calls):
    """retry-stems 涓嶈鍙?body.user_id锛涜韩浠藉彧鏉ヨ嚜 X-User-ID銆俠ody 浼€犱笉褰卞搷缁撴灉銆?""
    c = _client()
    tid = _make_task("uA", "t4")
    # 鐢?body 浼€?user_id=B锛屼絾 X-User-ID=C锛堥潪 owner锛夆啋 浠嶆嫆缁?    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems",
               headers={"Authorization": "Bearer uC", "Content-Type": "application/json"},
               content='{"user_id": "uA"}')
    assert r.status_code == 403, r.text
    assert calls["separate"] == []


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ T5: retry 涓嶈鍏ョ敤鎴?generation quota 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
def test_t5_retry_does_not_consume_generation_quota(isolated_db, calls, monkeypatch):
    """retry-stems 涓嶆秷鑰?beta/generation 棰濆害锛堢敓浜?Modal Spleeter 涓嬬嚎锛屾棤鏅€?GPU 鎴愭湰锛夈€?""
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")
    c = _client()
    tid = _make_task("uA", "t5")
    # 璇诲彇 retry 鍓?quota
    before = ai_limits._get_session()
    from sqlalchemy import text
    row0 = before.execute(text("SELECT daily_credits_used FROM beta_users WHERE user_id=:u"), {"u": "uA"}).fetchone()
    gu0 = before.execute(text("SELECT daily_count FROM generation_usage WHERE user_id=:u"), {"u": "uA"}).fetchone()
    before.close()

    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"Authorization": "Bearer uA"})
    assert r.status_code == 200

    after = ai_limits._get_session()
    row1 = after.execute(text("SELECT daily_credits_used FROM beta_users WHERE user_id=:u"), {"u": "uA"}).fetchone()
    gu1 = after.execute(text("SELECT daily_count FROM generation_usage WHERE user_id=:u"), {"u": "uA"}).fetchone()
    after.close()
    # beta credits 涓嶅鍔狅紙鍙兘娌℃湁琛?鈫?0锛夛紝generation daily 涓嶅鍔?    assert (row1[0] if row1 else 0) == (row0[0] if row0 else 0)
    assert (gu1[0] if gu1 else 0) == (gu0[0] if gu0 else 0)


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ T6: global hard stop 鈫?鎷掔粷 + GPU=0 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
def test_t6_global_hard_stop_denies_retry(isolated_db, calls, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 1)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")
    c = _client()
    # 鍚冩帀鍞竴鍏ㄥ眬棰濆害锛坓lobal count=1锛?    assert ai_limits.reserve_generation("u-other")["success"] is True
    tid = _make_task("uA", "t6")
    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"Authorization": "Bearer uA"})
    assert r.status_code == 429, r.text
    assert calls["separate"] == []  # 鏈惎鍔?Spleeter GPU


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ T6b: 棰勭畻纭仠涔熸嫆缁?retry锛堝吋瀹规棫璇箟锛?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
def test_t6b_budget_hard_stop_denies_retry(isolated_db, calls, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 1000)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "1")
    c = _client()
    assert ai_limits.reserve_generation("u-other")["success"] is True  # 棰勭畻鐢ㄥ敖
    tid = _make_task("uA", "t6b")
    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"Authorization": "Bearer uA"})
    assert r.status_code == 429, r.text
    assert calls["separate"] == []


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ T7: global hard stop 妫€鏌ュ厛浜?GPU invocation 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
def test_t7_hard_stop_checked_before_gpu(isolated_db, calls, monkeypatch):
    """retry-stems 鍦ㄤ换浣?GPU 宸ヤ綔鍓嶅厛鍋氬叏骞冲彴纭仠妫€鏌ワ紙global_hard_stop_reached锛夈€?""
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 1)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")
    # 鍏ㄥ眬宸叉弧
    assert ai_limits.reserve_generation("u-other")["success"] is True
    assert ai_limits.global_hard_stop_reached() is True
    c = _client()
    tid = _make_task("uA", "t7")
    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"Authorization": "Bearer uA"})
    assert r.status_code == 429
    assert calls["separate"] == []  # 纭仠鍏堜簬 GPU锛宻eparate 浠庢湭琚皟


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ T8: provider failure 璇箟锛坮etry 鏃?reserve 鈫?鏃?refund 閾捐矾锛?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
def test_t8_provider_failure_no_refund_path(isolated_db, calls, monkeypatch):
    """retry-stems 涓?reserve 棰濆害锛屾晠澶辫触鏃舵棤 refund 閾捐矾锛屼篃涓嶄細璇€€鐢ㄦ埛棰濆害銆?
    鍒嗚建澶辫触鍚庝换鍔℃爣璁?completed_with_stems_failed锛屼笉褰卞搷鐢ㄦ埛 beta/generation 棰濆害
    锛堥搴︽湰灏辨湭鎵ｏ紝鏁呮棤闇€涔熸棤浠庨€€娆撅級銆?    """
    async def _fail(full_wav):
        calls["separate"].append(full_wav)
        return None

    import app.services
    monkeypatch.setattr(ai_music, "ace_step_separate", _fail)
    c = _client()
    tid = _make_task("uA", "t8")
    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"Authorization": "Bearer uA"})
    assert r.status_code == 200
    # 绛夊悗鍙板け璐ユ敹鏁?    for _ in range(60):
        st = (task_store.get(tid) or {}).get("state")
        if st == "completed_with_stems_failed":
            break
        time.sleep(0.02)
    assert (task_store.get(tid) or {}).get("state") == "completed_with_stems_failed"


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ T9: timeout/unknown 涓嶉敊璇?refund锛坮etry 鏃?refund 閾捐矾锛?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
def test_t9_timeout_unknown_no_wrong_refund(isolated_db, calls, monkeypatch):
    """retry-stems 鐨?_run_retry_stems 寮傚父鍙洿鏂颁换鍔＄姸鎬侊紝涓嶈皟鐢?refund_generation銆?
    鍥犳涓嶅瓨鍦ㄣ€寀nknown outcome 鍗撮€€娆俱€嶇殑鍏嶈垂鐢熸垚婕忔礊锛涢搴︽湰灏辨湭鎵ｃ€?    """
    # 璁?separate 鎶涘紓甯革紙妯℃嫙 unknown outcome锛屼笉浼氳Е鍙?refund锛?    async def _boom(full_wav):
        calls["separate"].append(full_wav)
        raise RuntimeError("simulated boom")

    monkeypatch.setattr(ai_music, "ace_step_separate", _boom)
    c = _client()
    tid = _make_task("uA", "t9")
    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"Authorization": "Bearer uA"})
    assert r.status_code == 200
    for _ in range(60):
        st = (task_store.get(tid) or {}).get("state")
        if st == "completed_with_stems_failed":
            break
        time.sleep(0.02)
    st = (task_store.get(tid) or {}).get("state")
    assert st == "completed_with_stems_failed"


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ T10: 骞跺彂 retry 涓嶄骇鐢熼噸澶?GPU锛堢姸鎬佽浆鎹㈠師瀛愭€э級 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
def test_t10_concurrent_state_transition_exactly_one(isolated_db, monkeypatch):
    """鏍稿績骞跺彂淇濊瘉锛氬悓涓€ task 鐨?20 涓苟鍙戙€屽彲閲嶈瘯缁堟€佲啋separating銆嶇姸鎬佽浆鎹紝鎭板ソ 1 鎴愬姛銆?
    杩欐槸骞跺彂涓嶈秴杩?1 涓?GPU 鐨勬暟鎹簱绾т繚璇侊細task_store.try_transition_state 鐢?    鏉′欢 UPDATE + rowcount 鍒ゅ畾锛堜笌 reserve_generation 鍚屾瀯锛夛紝涓嶄緷璧?threading.Lock銆?    """
    tid = _make_task("uA", "t10")  # state = completed_with_stems_failed

    def _call(_):
        return task_store.try_transition_state(
            tid, from_states=("completed", "completed_with_stems_failed"), to_state="separating"
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        results = list(ex.map(_call, range(20)))
    assert sum(results) == 1  # 鍙湁绗竴涓垚鍔熸姠鍗?    assert (task_store.get(tid) or {}).get("state") == "separating"


def test_t10b_second_retry_rejected_after_state_transition(isolated_db, calls):
    """鐘舵€佽鎶㈠崰锛堣浆 separating锛夊悗锛屽啀娆?retry 鍚屼竴 task 浼氳 409/429 鎷掔粷锛屼笉鍐嶅惎鍔ㄧ浜屼釜 GPU銆?""
    c = _client()
    tid = _make_task("uA", "t10b")
    # 妯℃嫙宸叉湁骞跺彂 retry 鍦ㄨ繘琛岋細鎶㈠崰鐘舵€?鈫?separating
    assert task_store.try_transition_state(
        tid, from_states=("completed", "completed_with_stems_failed"), to_state="separating"
    ) is True
    # 姝ゆ椂鍐?POST retry-stems锛歴tate 涓嶅啀鏄彲閲嶈瘯缁堟€?鈫?409 鎷掔粷
    r = c.post(f"/api/v1/ai/task/{tid}/retry-stems", headers={"Authorization": "Bearer uA"})
    assert r.status_code == 409, r.text
    assert calls["separate"] == []  # 鏈惎鍔?GPU


# Phase 3B-1锛氳韩浠芥敼涓?Authorization Bearer JWT銆傛祴璇曠幆澧冧笉鑱旂湡瀹?Supabase Auth锛?# 鍥犳 autouse 鎵撴々 resolve_auth_user_id锛屼娇 "Bearer <token>" 鏈夋晥鏃跺彲纭畾鍦拌繑鍥?token 閮ㄥ垎锛?# 涓?"Authorization" 缂哄け/闈?Bearer 杩斿洖 None锛堢瓑浠?fail-closed 401锛夛紝涓嶄緷璧栫幆澧冨彉閲忋€?@pytest.fixture(autouse=True)
def _jwt_identity_stub(monkeypatch):
    from app.services import auth_identity

    def _resolve(auth):
        if isinstance(auth, str) and auth.startswith("Bearer "):
            return auth[len("Bearer "):]
        return None

    monkeypatch.setattr(auth_identity, "resolve_auth_user_id", _resolve)
