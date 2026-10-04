"""P4-B2 Phase 1 字段实现测试：update 白名单 / 歌词持久化 / lyrics_timed 校验 / share 新字段。

覆盖 Gate A 裁定的验收点：
  1. _UPDATABLE_FIELDS：新字段（title/lyrics/lyrics_timed）在白名单；原有合法字段仍在；
     task_id / user_key / created_at / updated_at 被排除
  2. 未知 update 字段必须 raise ValueError（拒绝而非静默忽略）
  3. 歌词持久化（走真实 _run_generation 管线，provider 层桩为必败）：
     - request.lyrics 优先保存
     - agnes_result.generated_lyrics 可保存
     - 两者皆无 → lyrics = NULL
     - final_prompt 只作为 provider 入参兜底，绝不落 ai_tasks.lyrics
       （用桩捕获 provider 实际收到的 lyrics 佐证分离语义）
  4. lyrics_timed 结构校验（Gate A ①）：[{start,end,text}] 合法；
     非 list / 非对象元素 / 缺键 / 类型错误 一律 ValueError
  5. share 公开 API：response 包含 lyrics / lyrics_timed

注：本文件不触碰 title 写入（title source = OPEN / NOT DECIDED）、
不写入 lyrics_timed 生产数据、不修改 continuation_service / TaskResponse。
"""

import asyncio
import os
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import ai_limits, task_store, provider_registry
from app.routers import ai_music, share
from tests.credits_env import install_credits_env


# ────────────────────────── 复用流程测试的隔离基建 ──────────────────────────

@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """独立 SQLite + 关闭 HF 兜底（与 test_ai_music_flow 同模式）。"""
    db_path = str(tmp_path / "p4b2.db")
    monkeypatch.setattr(ai_limits, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(ai_limits, "_DB_PATH", db_path)
    monkeypatch.setattr(task_store, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(task_store, "_DB_PATH", db_path)
    monkeypatch.setattr(ai_music, "HF_FALLBACK_ENABLED", False)
    install_credits_env(monkeypatch, tmp_path, ("uA",))
    return db_path


@pytest.fixture()
def disable_bg(monkeypatch):
    """端点后台任务替换为 no-op，返回真实管线函数供测试手动驱动。"""
    real = ai_music._run_with_timeout

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(ai_music, "_run_with_timeout", _noop)
    return real


def _install_never_provider(monkeypatch, calls):
    """provider 链必败桩：patch get_provider_registry 绕过真实 API key 检查；
    provider.generate 记录收到的入参（含 lyrics）后返回 non_retryable 失败。"""

    class _NeverProvider:
        name = "yinchao"
        gpu = "test"

        async def generate(self, request):
            calls.append({"prompt": request.get("prompt"),
                          "lyrics": request.get("lyrics"),
                          "duration": request.get("duration")})
            return {"success": False, "error": "fake provider failed",
                    "provider": self.name, "non_retryable": True}

    class _Reg:
        def chain_for_operation(self, operation, song_language=None):
            return [_NeverProvider()]

        def select(self, name=None):
            return _NeverProvider()

        def get(self, name):
            return _NeverProvider()

    monkeypatch.setattr(ai_music, "get_provider_registry", lambda: _Reg())


def _client():
    app = FastAPI()
    app.include_router(ai_music.router)
    return TestClient(app)


def _run_pipeline(run, task_id, user="uA", prompt="a summer pop song",
                  duration=180, lyrics=None):
    req = ai_music.GenerateRequest(prompt=prompt, style="pop", duration=duration,
                                   type="song", lyrics=lyrics)
    asyncio.run(run(task_id, req, user))


def _wait_terminal(c, task_id, headers, tries=60):
    for _ in range(tries):
        r = c.get(f"/api/v1/ai/task/{task_id}", headers=headers)
        if r.status_code == 200:
            st = r.json()["state"]
            if st in ("completed", "failed", "cancelled"):
                return r.json()
        time.sleep(0.02)
    raise AssertionError("任务未进入终态")


def _fail_task(c, tid, headers, prompt="just a prompt"):
    r = c.post("/api/v1/ai/generate", json={"prompt": prompt},
               headers=headers)
    assert r.status_code == 200, r.text
    tid_local = r.json()["task_id"]
    return tid_local


# ────────────────────────── 1/2. 白名单 ──────────────────────────

def test_updatable_fields_membership():
    """新字段进入白名单；原有合法字段保留；禁改字段被排除。"""
    f = task_store._UPDATABLE_FIELDS
    # 新字段允许
    assert {"title", "lyrics", "lyrics_timed"} <= f
    # 原有合法字段仍允许
    assert {"progress", "ai_provider", "error", "retries", "stem_retries",
            "volume_files", "download", "stems_state", "stems", "audio_url",
            "video_url", "generation_quota_weight", "refunded_at"} <= f
    # 明确排除
    assert "task_id" not in f
    assert "user_key" not in f
    assert "created_at" not in f
    assert "updated_at" not in f
    # state 走条件更新专用路径，不在普通白名单内
    assert "state" not in f


def test_unknown_update_field_rejected(isolated_db):
    """未知字段必须 raise ValueError，且任务数据不被静默改写。"""
    tid = task_store.new_task(user_key="uA")
    with pytest.raises(ValueError, match="unknown/forbidden"):
        task_store.update(tid, bogus_field="should_fail")
    task = task_store.get(tid)
    assert task is not None
    assert "bogus_field" not in task
    # 既有合法字段依旧可写（白名单不破坏现有调用方）
    task_store.update(tid, progress=55, error="keep-working")
    task = task_store.get(tid)
    assert task["progress"] == 55
    assert task["error"] == "keep-working"


def test_user_key_is_not_updatable(isolated_db):
    """所有权字段 user_key 不得通过 update 改写（IDOR 根基）。"""
    tid = task_store.new_task(user_key="uA")
    with pytest.raises(ValueError, match="unknown/forbidden"):
        task_store.update(tid, user_key="attacker")
    assert task_store.get(tid)["user_key"] == "uA"


# ────────────────────────── 3. 歌词持久化（真实管线） ──────────────────────────

def test_lyrics_persistence_user_lyrics(isolated_db, disable_bg, monkeypatch):
    """用户提供歌词 → 落库；provider 收到的 lyrics 是兜底（无 agnes 时=prompt），
    两者分离：落库值 ≠ provider 入参兜底值。"""
    calls = []
    _install_never_provider(monkeypatch, calls)

    class _StubAgnes:
        async def generate_song(self, request):
            class _R:
                optimized_prompt = None
                generated_lyrics = None
            return _R()

    monkeypatch.setattr(ai_music, "agnes_service", _StubAgnes())

    c = _client()
    r = c.post("/api/v1/ai/generate", json={"prompt": "just a prompt"},
               headers={"Authorization": "Bearer uA"})
    assert r.status_code == 200
    tid = r.json()["task_id"]
    # 歌词经由手动驱动的 GenerateRequest 传入（端点后台已被 no-op）
    _run_pipeline(disable_bg, tid, prompt="just a prompt", lyrics="用户歌词第一行")
    _wait_terminal(c, tid, {"Authorization": "Bearer uA"})

    task = task_store.get(tid)
    assert task["lyrics"] == "用户歌词第一行"
    # provider 入参语义不变：有真实歌词时收到真实歌词（原语义保留）
    assert calls, "provider 桩未被调用"
    assert calls[0]["lyrics"] == "用户歌词第一行"
    # 分离证明：真实歌词存在时，final_prompt（= prompt）既不落库也不是歌词来源
    assert task["lyrics"] != "just a prompt"


def test_lyrics_persistence_agnes_lyrics(isolated_db, disable_bg, monkeypatch):
    """无用户歌词但 Agnes 生成词存在 → 保存 Agnes 歌词。"""
    calls = []
    _install_never_provider(monkeypatch, calls)

    class _StubAgnes:
        async def generate_song(self, request):
            class _R:
                optimized_prompt = "optimized prompt text"
                generated_lyrics = "agnes 生成的歌词"
            return _R()

    monkeypatch.setattr(ai_music, "agnes_service", _StubAgnes())

    c = _client()
    r = c.post("/api/v1/ai/generate", json={"prompt": "just a prompt"},
               headers={"Authorization": "Bearer uA"})
    assert r.status_code == 200
    tid = r.json()["task_id"]
    _run_pipeline(disable_bg, tid, prompt="just a prompt")
    _wait_terminal(c, tid, {"Authorization": "Bearer uA"})

    task = task_store.get(tid)
    assert task["lyrics"] == "agnes 生成的歌词"
    # provider 入参语义不变：有真实歌词（agnes 生成）时收到真实歌词
    assert calls, "provider 桩未被调用"
    assert calls[0]["lyrics"] == "agnes 生成的歌词"
    assert task["lyrics"] == calls[0]["lyrics"]


def test_lyrics_persistence_both_empty_saves_null(isolated_db, disable_bg, monkeypatch):
    """两者皆无 → lyrics = NULL；final_prompt 仅作为 provider 入参，绝不落库。"""
    calls = []
    _install_never_provider(monkeypatch, calls)

    class _StubAgnes:
        async def generate_song(self, request):
            class _R:
                optimized_prompt = None
                generated_lyrics = None
            return _R()

    monkeypatch.setattr(ai_music, "agnes_service", _StubAgnes())

    c = _client()
    r = c.post("/api/v1/ai/generate", json={"prompt": "just a prompt"},
               headers={"Authorization": "Bearer uA"})
    assert r.status_code == 200
    tid = r.json()["task_id"]
    _run_pipeline(disable_bg, tid, prompt="just a prompt")
    _wait_terminal(c, tid, {"Authorization": "Bearer uA"})

    task = task_store.get(tid)
    assert task["lyrics"] is None
    # 两者皆无 → provider 收到 final_prompt 兜底；final_prompt 绝不落 lyrics 字段
    assert calls, "provider 桩未被调用"
    assert calls[0]["lyrics"] == "just a prompt"
    assert task["lyrics"] != calls[0]["lyrics"]


# ────────────────────────── 4. lyrics_timed 结构校验 ──────────────────────────

def test_lyrics_timed_valid_accepted(isolated_db):
    tid = task_store.new_task(user_key="uA")
    valid = [{"start": 0.0, "end": 2.5, "text": "first line"},
             {"start": 2.5, "end": 5.0, "text": "second line"}]
    task_store.update(tid, lyrics_timed=valid)  # 不抛异常即接受
    task_store.update(tid, lyrics_timed=None)   # NULL 合法


@pytest.mark.parametrize("bad", [
    "not-a-list",                              # 非 list
    {"lines": [{"start": 0, "end": 1, "text": "x"}]},  # 禁止 {lines:[...]} 结构
    [42],                                      # 元素非 object
    ["a string"],                              # 元素非 object
    [{"start": 0.0, "end": 1.0}],              # 缺 text
    [{"end": 1.0, "text": "x"}],               # 缺 start
    [{"start": 0.0, "text": "x"}],             # 缺 end
    [{"start": "0", "end": 1.0, "text": "x"}], # start 非 number
    [{"start": 0.0, "end": True, "text": "x"}],# end 为 bool（显式排除）
    [{"start": 0.0, "end": 1.0, "text": 7}],   # text 非 string
])
def test_lyrics_timed_invalid_rejected(isolated_db, bad):
    tid = task_store.new_task(user_key="uA")
    with pytest.raises(ValueError):
        task_store.update(tid, lyrics_timed=bad)
    # 拒绝发生在任何 DB 写入前：字段不被静默改写
    assert task_store.get(tid)["lyrics_timed"] is None


# ────────────────────────── 5. share 公开 API 新字段 ──────────────────────────

@pytest.fixture()
def share_client(monkeypatch, isolated_db):
    monkeypatch.setenv("SHARE_LINK_SECRET", "p4b2-test-secret")
    # 预签名桩：share API 在函数内 `from app.services.cdn_uploader import
    # cdn_uploader` 拿到的是同一实例对象 → patch 实例方法即可生效。
    from app.services.cdn_uploader import cdn_uploader
    monkeypatch.setattr(
        cdn_uploader, "get_presigned_download_url",
        lambda key, expires_in=600: f"https://signed/{key}",
    )
    app = FastAPI()
    app.include_router(share.router)
    return TestClient(app)


def _make_completed_task(lyrics=None, lyrics_timed=None):
    tid = task_store.new_task(user_key="uA")
    task_store.update(
        tid, state="completed", progress=100,
        download={"full_mp3": f"music/{tid}/full.mp3"},
        stems_state="ok", audio_url=None,
        lyrics=lyrics, lyrics_timed=lyrics_timed,
    )
    return tid


def test_share_response_contains_lyrics_and_timed(share_client):
    tid = _make_completed_task(
        lyrics="分享页歌词",
        lyrics_timed=[{"start": 0.0, "end": 1.0, "text": "hi"}],
    )
    token = share.make_token(tid)
    r = share_client.get(f"/api/v1/share/{token}")
    assert r.status_code == 200
    d = r.json()
    assert d["lyrics"] == "分享页歌词"
    assert d["lyrics_timed"] == [{"start": 0.0, "end": 1.0, "text": "hi"}]
    # 既有字段契约不变
    assert d["task_id"] == tid
    assert d["brand"] == "Melovar"
    assert d["audio_url"].startswith("https://signed/")


def test_share_response_lyrics_null_for_legacy_tasks(share_client):
    """历史任务（三字段 NULL）→ lyrics/lyrics_timed 为 null，不伪造。"""
    tid = _make_completed_task()
    token = share.make_token(tid)
    r = share_client.get(f"/api/v1/share/{token}")
    assert r.status_code == 200
    d = r.json()
    assert d["lyrics"] is None
    assert d["lyrics_timed"] is None


def test_share_public_api_no_title_leak_when_absent(share_client):
    """title source 未定 → title 恒空串（现有 fallback 行为不变）。"""
    tid = _make_completed_task(lyrics="some lyrics")
    token = share.make_token(tid)
    d = share_client.get(f"/api/v1/share/{token}").json()
    assert d["title"] == ""
