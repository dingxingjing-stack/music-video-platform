"""P0 安全修复回归测试（本轮 7 项）。

覆盖策略：
- 能用真实调用路径验证的（鉴权门、锁、退款、孤儿对账、webhook 验签、素材下载）→ 真跑。
- main.py 内联端点不在此导入（导入 main 会带来全局副作用与 env 污染，见 test_p21 历史问题），
  因此 /api/v1/audio/trim 的「必须鉴权 + 先校验后执行」用源码契约断言 + 校验器单测组合覆盖。

全部使用临时 SQLite + 假依赖：不触真实 API、不产生任何第三方费用。
"""

from __future__ import annotations

import hashlib
import hmac
import time

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.routers import asset_store, auth as auth_router, subscription
from app.services import ai_limits, credits_service, task_recovery, task_store
from app.services.auth_identity import get_verified_user_id
from app.services.audio_trim import resolve_safe_media_source

USER = "p0-security-user"
OTHER = "p0-security-other"


# ── fixtures：把三套持久化都指向临时库 ────────────────────────────────
@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = str(tmp_path / "p0.db")
    monkeypatch.setattr(task_store, "_DB_PATH", db)
    monkeypatch.setattr(ai_limits, "_DB_PATH", db)
    eng = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    from app.db.database import Base

    Base.metadata.create_all(bind=eng)
    monkeypatch.setattr(credits_service, "SessionLocal", sessionmaker(bind=eng))
    for u in (USER, OTHER):
        credits_service.add_credits(u, 1000, "admin_adjustment", description="grant")
    return eng


def _balance(user_id: str) -> int:
    return credits_service.get_balance(user_id)["balance"] if isinstance(
        credits_service.get_balance(user_id), dict
    ) else credits_service.get_balance(user_id)


# ── P0-1 auth/credits/add：管理员令牌 ─────────────────────────────────
def _auth_client() -> TestClient:
    app = FastAPI()
    app.include_router(auth_router.router)
    return TestClient(app)


def test_credits_add_disabled_when_admin_token_not_configured(env, monkeypatch):
    monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)
    r = _auth_client().post(f"/api/v1/auth/credits/add?user_id={USER}&amount=500",
                            headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 503, r.text


def test_credits_add_rejects_wrong_or_missing_admin_token(env, monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "s3cret-admin-token")
    c = _auth_client()
    assert c.post(f"/api/v1/auth/credits/add?user_id={USER}&amount=500").status_code == 403
    assert c.post(f"/api/v1/auth/credits/add?user_id={USER}&amount=500",
                  headers={"X-Admin-Token": "wrong"}).status_code == 403
    # 普通用户 JWT 头不足以授权
    assert c.post(f"/api/v1/auth/credits/add?user_id={USER}&amount=500",
                  headers={"Authorization": "Bearer user-jwt"}).status_code == 403


def test_credits_add_validates_amount_bounds(env, monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "s3cret-admin-token")
    calls: list = []
    monkeypatch.setattr(auth_router, "increment_user_credits",
                        lambda u, a: calls.append((u, a)) or 1)
    monkeypatch.setattr(auth_router, "log_activity", lambda **kw: None)
    c = _auth_client()
    h = {"X-Admin-Token": "s3cret-admin-token"}
    assert c.post(f"/api/v1/auth/credits/add?user_id={USER}&amount=0", headers=h).status_code == 400
    assert c.post(f"/api/v1/auth/credits/add?user_id={USER}&amount=-5", headers=h).status_code == 400
    assert c.post(f"/api/v1/auth/credits/add?user_id={USER}&amount=999999", headers=h).status_code == 400
    assert calls == []
    assert c.post(f"/api/v1/auth/credits/add?user_id={USER}&amount=100", headers=h).status_code == 200
    assert calls == [(USER, 100)]


# ── P0-2 audio/trim：SSRF / 本地文件 白名单 ───────────────────────────
@pytest.mark.parametrize("bad", [
    "/etc/passwd",
    "../../data/beta.db",
    "file:///etc/passwd",
    "http://169.254.169.254/latest/meta-data/",
    "https://169.254.169.254/latest/meta-data/",
    "https://127.0.0.1:8000/x.mp3",
    "https://localhost/a.mp3",
    "https://10.0.0.5/a.mp3",
    "https://evil.example.com/a.mp3",
    "https://attacker.test:8443/a.mp3",
    "",
])
def test_trim_rejects_unsafe_sources(bad, monkeypatch):
    monkeypatch.delenv("AUDIO_TRIM_EXTRA_HOSTS", raising=False)
    with pytest.raises(ValueError):
        resolve_safe_media_source(bad)


def test_trim_accepts_allowlisted_hosts(monkeypatch):
    monkeypatch.setenv("AUDIO_TRIM_EXTRA_HOSTS", "cdn.example.test")
    monkeypatch.setattr("app.services.audio_trim.socket.getaddrinfo",
                        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    assert resolve_safe_media_source("https://abc.r2.cloudflarestorage.com/music/t/full.mp3")
    assert resolve_safe_media_source("https://cdn.example.test/a.mp3")


def test_trim_endpoint_contract_is_authenticated_and_validated_first():
    """main.py 的 trim 端点：必须有 verified 身份依赖，且校验发生在 ffmpeg 调用之前。"""
    import pathlib
    import re

    src = pathlib.Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
    m = re.search(r'@app\.get\("/api/v1/audio/trim".*?\n@app\.', src, re.S)
    assert m, "trim endpoint block not found"
    block = m.group(0)
    assert "Depends(get_verified_user_id)" in block, "trim 必须要求已验证身份"
    assert block.index("resolve_safe_media_source") < block.index("await trim_audio"), \
        "必须先做来源白名单校验，再调用 trim_audio"
    assert 'status_code=403' in block


# ── P0-3 task_locks：不再 500、不再吞 Credits ─────────────────────────
def test_acquire_lock_is_idempotent_and_never_raises(env):
    t1 = task_store.new_task(user_key=USER)
    assert task_store.acquire_lock(USER, t1) is True
    t2 = task_store.new_task(user_key=USER)
    # 旧实现在这里会撞主键抛 IntegrityError → 现在必须是 False，且不抛
    assert task_store.acquire_lock(USER, t2) is False
    assert task_store.is_user_busy(USER) is True


def test_stale_lock_is_reclaimed_without_manual_cleanup(env):
    t1 = task_store.new_task(user_key=USER)
    assert task_store.acquire_lock(USER, t1) is True
    # 任务已终态（例如人工置 completed）→ 锁应被自动回收，不再需要重启才恢复
    sess = env.connect()
    sess.execute(text("UPDATE ai_tasks SET state='completed' WHERE task_id=:t"), {"t": t1})
    sess.commit()
    sess.close()
    t2 = task_store.new_task(user_key=USER)
    assert task_store.acquire_lock(USER, t2) is True


def test_lock_failure_happens_before_any_credit_charge(env, monkeypatch):
    """锁拿不到 → 不得扣 Credits、不得预留日额度、不得留残留任务行。"""
    from app.routers import ai_music

    charged: list = []
    reserved: list = []
    monkeypatch.setattr(ai_music.credits_service, "reserve_generation_credits",
                        lambda u, tid, cost: charged.append((u, tid)) or {"success": True})
    monkeypatch.setattr(ai_music, "reserve_generation",
                        lambda u, d=None: reserved.append(u) or {"success": True})
    monkeypatch.setattr(ai_music.task_store, "acquire_lock", lambda u, tid: False)
    monkeypatch.setattr(ai_music.asyncio, "create_task", lambda coro: coro.close())

    app = FastAPI()
    app.include_router(ai_music.router)
    app.dependency_overrides[get_verified_user_id] = lambda: USER
    r = TestClient(app).post("/api/v1/ai/generate", json={"prompt": "p0 order test", "duration": 270})

    assert r.status_code == 200, r.text
    assert r.json()["success"] is False
    assert charged == [], "锁失败路径不得扣 Credits"
    assert reserved == [], "锁失败路径不得预留日额度"
    assert task_store.list_user_tasks(USER) == [], "不得留下空任务行"


# ── P0-4 孤儿任务：可审计退款 ─────────────────────────────────────────
def test_finalize_stale_task_refunds_credits_exactly_once(env):
    tid = task_store.new_task(user_key=USER)
    assert credits_service.reserve_generation_credits(USER, tid, 30)["success"] is True
    assert task_store.acquire_lock(USER, tid) is True
    before = _balance(USER)
    assert before == 970

    sess = env.connect()
    sess.execute(text("UPDATE ai_tasks SET state='generating' WHERE task_id=:t"), {"t": tid})
    sess.commit()
    sess.close()

    assert task_recovery.finalize_stale_task(tid, reason="test")["finalized"] is True
    assert _balance(USER) == 1000, "孤儿任务必须退回 30 Credits"
    # 第二次调用不得再退（状态 CAS 未命中 + 流水查重双重保证）
    assert task_recovery.finalize_stale_task(tid, reason="test")["finalized"] is False
    assert _balance(USER) == 1000
    sess = env.connect()
    state = sess.execute(text("SELECT state FROM ai_tasks WHERE task_id=:t"), {"t": tid}).scalar()
    locks = sess.execute(text("SELECT COUNT(*) FROM task_locks WHERE task_id=:t"), {"t": tid}).scalar()
    sess.commit()
    sess.close()
    assert state == "failed"
    assert locks == 0, "终态化必须释放用户锁"


def test_completed_task_is_never_finalized(env):
    tid = task_store.new_task(user_key=USER)
    sess = env.connect()
    sess.execute(text("UPDATE ai_tasks SET state='completed' WHERE task_id=:t"), {"t": tid})
    sess.commit()
    sess.close()
    assert task_recovery.finalize_stale_task(tid)["finalized"] is False


def test_restart_reconciliation_recovers_all_orphans(env):
    ids = []
    for _ in range(2):
        tid = task_store.new_task(user_key=USER)
        credits_service.reserve_generation_credits(USER, tid, 30)
        task_store.acquire_lock(USER, tid)
        ids.append(tid)
    assert _balance(USER) == 940
    assert task_recovery.reconcile_orphans_after_restart() == 2
    assert _balance(USER) == 1000
    for tid in ids:
        sess = env.connect()
        assert sess.execute(text("SELECT state FROM ai_tasks WHERE task_id=:t"), {"t": tid}).scalar() == "failed"
        sess.commit()
        sess.close()


def test_stale_task_get_marks_without_silent_state_flip(env):
    """task_store.get() 只标记超时，退款由唯一出口负责（避免「判失败但没退款」）。"""
    tid = task_store.new_task(user_key=USER)
    sess = env.connect()
    sess.execute(text("UPDATE ai_tasks SET state='generating', updated_at=:old WHERE task_id=:t"),
                 {"old": time.time() - 10_000, "t": tid})
    sess.commit()
    sess.close()
    got = task_store.get(tid)
    assert got["stale_timed_out"] is True
    assert got["state"] == "generating"
    sess = env.connect()
    assert sess.execute(text("SELECT state FROM ai_tasks WHERE task_id=:t"), {"t": tid}).scalar() == "generating"
    sess.commit()
    sess.close()


# ── P0-5 subscription/webhook：HMAC 验签 ─────────────────────────────
def _sub_client() -> TestClient:
    app = FastAPI()
    app.include_router(subscription.router)
    return TestClient(app)


def _sign(secret: str, query: str, body: bytes = b"") -> str:
    return "sha256=" + hmac.new(secret.encode(), f"{query}\n".encode() + body, hashlib.sha256).hexdigest()


def test_webhook_fails_closed_without_secret(monkeypatch):
    monkeypatch.delenv("SUBSCRIPTION_WEBHOOK_SECRET", raising=False)
    subscription.subscriptions_db.clear()
    subscription.subscriptions_db[USER] = {"status": subscription.SubscriptionStatus.TRIAL}
    c = _sub_client()
    q = f"event_type=payment.completed&payment_id=p1&user_id={USER}&amount=9.9"
    r = c.post(f"/api/v1/subscription/webhook?{q}", headers={"X-Webhook-Signature": "sha256=whatever"})
    assert r.status_code == 503
    assert subscription.subscriptions_db[USER]["status"] == subscription.SubscriptionStatus.TRIAL


def test_webhook_rejects_missing_or_forged_signature(monkeypatch):
    monkeypatch.setenv("SUBSCRIPTION_WEBHOOK_SECRET", "wh-sec")
    subscription.subscriptions_db.clear()
    subscription.subscriptions_db[USER] = {"status": subscription.SubscriptionStatus.TRIAL}
    c = _sub_client()
    q = f"event_type=payment.completed&payment_id=p1&user_id={USER}&amount=9.9"
    assert c.post(f"/api/v1/subscription/webhook?{q}").status_code == 403
    assert c.post(f"/api/v1/subscription/webhook?{q}",
                  headers={"X-Webhook-Signature": "sha256=deadbeef"}).status_code == 403
    # 换签名密钥串也必须是 403（不可猜测）
    assert c.post(f"/api/v1/subscription/webhook?{q}",
                  headers={"X-Webhook-Signature": _sign("wrong-secret", q)}).status_code == 403
    assert subscription.subscriptions_db[USER]["status"] == subscription.SubscriptionStatus.TRIAL, \
        "未通过验签的请求不得改变订阅状态"


def test_webhook_accepts_valid_signature_and_activates(monkeypatch):
    monkeypatch.setenv("SUBSCRIPTION_WEBHOOK_SECRET", "wh-sec")
    subscription.subscriptions_db.clear()
    subscription.subscriptions_db[USER] = {"status": subscription.SubscriptionStatus.TRIAL,
                                           "trial_days_left": 7}
    q = f"event_type=payment.completed&payment_id=p1&user_id={USER}&amount=9.9"
    r = _sub_client().post(f"/api/v1/subscription/webhook?{q}",
                           headers={"X-Webhook-Signature": _sign("wh-sec", q)})
    assert r.status_code == 200, r.text
    assert subscription.subscriptions_db[USER]["status"] == subscription.SubscriptionStatus.ACTIVE
    assert subscription.subscriptions_db[USER]["trial_days_left"] is None


# ── P0-6 asset_store：付费素材不可绕过 ────────────────────────────────
def _store_client(authenticated: bool = True, user: str = USER) -> TestClient:
    app = FastAPI()
    app.include_router(asset_store.router)
    if authenticated:
        app.dependency_overrides[get_verified_user_id] = lambda: user
    return TestClient(app)


def _priced_asset():
    return next(a for a in asset_store.ASSETS if a.price > 0)


def _free_asset():
    return next((a for a in asset_store.ASSETS if a.price == 0), None)


def test_store_purchase_requires_identity():
    a = _priced_asset()
    r = _store_client(authenticated=False).post("/api/v1/store/purchase",
                                                json={"user_id": OTHER, "asset_id": a.id})
    assert r.status_code == 401, "未登录不得购买/获取下载地址"


def test_paid_asset_cannot_be_purchased_or_downloaded(env):
    a = _priced_asset()
    c = _store_client()
    r = c.post("/api/v1/store/purchase", json={"user_id": OTHER, "asset_id": a.id})
    assert r.status_code == 501, "支付未接入时必须明确拒绝，而不是伪造已购买"
    assert a.id not in getattr(c, "_dummy", [])
    d = c.get(f"/api/v1/store/download/{a.id}")
    assert d.status_code == 403, "无购买记录不得拿到付费素材地址"
    # 关键：客户端传的 user_id 一律无效，不能冒充他人
    assert asset_store.purchases_db.get(OTHER) in (None, [])


def test_paid_download_cannot_be_unlocked_by_claiming_another_user(env):
    a = _priced_asset()
    asset_store.purchases_db.clear()
    c = _store_client(user=USER)
    assert c.get(f"/api/v1/store/download/{a.id}").status_code == 403
    # 即使把"受害者"账户写进购买记录，攻击者以自己身份也不能取
    asset_store.purchases_db[OTHER] = [a.id]
    assert c.get(f"/api/v1/store/download/{a.id}").status_code == 403
    owner = _store_client(user=OTHER)
    assert owner.get(f"/api/v1/store/download/{a.id}").status_code == 200


def test_free_asset_still_downloadable():
    a = _free_asset()
    if a is None:
        pytest.skip("素材清单无免费项")
    r = _store_client().get(f"/api/v1/store/download/{a.id}")
    assert r.status_code == 200


# ── P0-7 runpod smoke test：默认关闭 ─────────────────────────────────
def test_runpod_smoke_test_is_disabled_by_default(monkeypatch):
    from app.routers import ai_music

    monkeypatch.delenv("ENABLE_RUNPOD_SMOKE_TEST", raising=False)
    monkeypatch.setenv("RUNPOD_SMOKE_TEST_TOKEN", "tok")
    app = FastAPI()
    app.include_router(ai_music.router)
    r = TestClient(app).post("/api/v1/ai/runpod-smoke-test",
                             headers={"X-RunPod-Smoke-Token": "tok"})
    assert r.status_code == 404, "未显式启用时对外表现为不存在（也不得触达 RunPod）"


def test_runpod_smoke_test_still_token_gated_when_enabled(monkeypatch):
    from app.routers import ai_music

    monkeypatch.setenv("ENABLE_RUNPOD_SMOKE_TEST", "true")
    monkeypatch.setenv("RUNPOD_SMOKE_TEST_TOKEN", "expected-token")
    app = FastAPI()
    app.include_router(ai_music.router)
    c = TestClient(app)
    assert c.post("/api/v1/ai/runpod-smoke-test").status_code == 401
    assert c.post("/api/v1/ai/runpod-smoke-test",
                  headers={"X-RunPod-Smoke-Token": "wrong"}).status_code == 401
    monkeypatch.delenv("RUNPOD_SMOKE_TEST_TOKEN")
    assert c.post("/api/v1/ai/runpod-smoke-test",
                  headers={"X-RunPod-Smoke-Token": "wrong"}).status_code == 503


# ── F2：_run_generation 的退款权重必须来自权威值，不得由 duration 重推 ──
class _F2FailingProvider:
    name = "f2-fake"
    gpu = "none"

    async def generate(self, request):
        return {"success": False, "error": "forced failure for F2", "provider": self.name}


class _F2Registry:
    def fallback_chain(self):
        return [_F2FailingProvider()]

    def select(self, name=None):
        return _F2FailingProvider()


def _f2_full_failure_chain(env, monkeypatch, duration, expected_weight):
    """真实失败链：reserve → 权重落库 → _run_with_timeout → _run_generation 全链失败 → 退款。

    直接断言传给 refund_generation() 的 weight，并用账本余额证明「退的==扣的」：
    先给用户留下 expected 之外的既有消耗，失败后必须分毫不差地回到那个起点。
    """
    import asyncio
    from types import SimpleNamespace

    from app.routers import ai_music

    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 5)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 20)
    # 让 _run_generation 走「Provider 链全部失败」这条真实退款分支（非 mock 退款本身）
    monkeypatch.setattr(ai_music, "get_provider_registry", lambda: _F2Registry())
    monkeypatch.setattr(ai_music, "MAX_AUTO_RETRIES", 0)
    monkeypatch.setenv("AI_GENERATION_PROVIDER", "")

    async def _agnes(req):
        return SimpleNamespace(optimized_prompt="opt", generated_lyrics="lyr")

    monkeypatch.setattr(ai_music.agnes_service, "generate_song", _agnes)

    async def _no_hf(*a, **k):
        return None

    monkeypatch.setattr(ai_music, "_try_hf_ace_step_fallback", _no_hf)

    seen: list = []
    real_refund = ai_limits.refund_generation

    def _spy(user_id, dur=None, reason="provider_failure", task_id=None, weight=None):
        res = real_refund(user_id, dur, reason=reason, task_id=task_id, weight=weight)
        seen.append({"reason": reason, "weight": weight, "duration_arg": dur, "res": res})
        return res

    monkeypatch.setattr(ai_music, "refund_generation", _spy)

    # 起点：先制造「与本任务无关」的既有消耗，这样多退/少退都会留在账上
    assert ai_limits.reserve_generation(USER, 60 if expected_weight == 2 else 180)["success"] is True
    baseline_used = _daily_used(env)
    baseline_gen = _gen_usage(env)

    # 复刻 generate_music 的权威口径：weight → new_task → reserve（三者必须一致）
    quota_weight = ai_music.get_duration_weight(duration)
    assert quota_weight == expected_weight
    tid = task_store.new_task(user_key=USER, generation_quota_weight=quota_weight)
    reserved = ai_limits.reserve_generation(USER, duration)
    assert reserved["success"] is True and reserved["weight"] == expected_weight
    assert _task_weight(env, tid) == expected_weight
    assert _daily_used(env) == baseline_used + expected_weight

    req = ai_music.GenerateRequest(prompt="f2 failure chain probe", duration=duration)
    asyncio.run(ai_music._run_with_timeout(tid, req, USER, quota_weight))

    # 1) 状态：真实失败
    assert _task_state(env, tid) == "failed"
    # 2) 直接断言退款调用用的是权威权重，且不再传 duration
    quota_refunds = [c for c in seen if c["res"].get("refunded")]
    assert len(quota_refunds) == 1, f"应恰好退一次日额度，实际：{seen}"
    assert quota_refunds[0]["weight"] == expected_weight, "refund weight 必须等于 reserve weight"
    assert quota_refunds[0]["duration_arg"] is None, "不得再把 duration 传给 refund_generation"
    assert quota_refunds[0]["res"]["weight"] == expected_weight
    # 3) 账本：扣多少退多少，起点余额分毫不差
    assert _daily_used(env) == baseline_used, "日额度必须精确复原（多退会低于起点）"
    assert _gen_usage(env) == baseline_gen, "日/月生成数必须精确复原"
    return seen


def test_f2_duration_none_refunds_one_not_two(env, monkeypatch):
    """duration 省略：reserve=1 → 落库=1 → 退款必须=1（历史上会退 2，抹掉别人的消耗）。"""
    _f2_full_failure_chain(env, monkeypatch, None, 1)


def test_f2_duration_180_refunds_two(env, monkeypatch):
    """duration=180：reserve=2 → 落库=2 → 退款必须=2（历史 finalize 路径只退 1）。"""
    _f2_full_failure_chain(env, monkeypatch, 180, 2)


# ── F9：已交付主音频的任务在分轨重试槽位里被 stale recovery 误判 ──────
def _make_delivered_task(env, monkeypatch, *, deliver: bool, weight: int = 2) -> str:
    """复刻"歌已生成、用户已付费、正处在 retry_stems 的 separating 槽位"的真实数据形态。"""
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 5)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 20)
    tid = task_store.new_task(user_key=USER, generation_quota_weight=weight)
    assert ai_limits.reserve_generation(USER, 180 if weight == 2 else 60)["weight"] == weight
    assert credits_service.reserve_generation_credits(USER, tid, 30)["success"] is True
    assert task_store.acquire_lock(USER, tid) is True          # 让"锁必须被释放"可被断言
    if deliver:
        _scalar(env, "UPDATE ai_tasks SET state='completed', progress=100, "
                     "audio_url='https://r2.example.com/song.mp3', download='{\"full_wav\":\"song.wav\"}', "
                     "stems_state='failed' WHERE task_id=:t", t=tid)
        # retry_stems 的真实入口：completed → separating（数据库条件更新）
        assert task_store.try_transition_state(
            tid, ("completed", "completed_with_stems_failed"), "separating") is True
    else:
        _scalar(env, "UPDATE ai_tasks SET state='separating', progress=85 WHERE task_id=:t", t=tid)
    return tid


def _lock_count(env, tid: str) -> int:
    return int(_scalar(env, "SELECT COUNT(*) FROM task_locks WHERE task_id=:t", t=tid) or 0)


def test_f9_delivered_separating_stale_does_not_refund_or_lose_song(env, monkeypatch):
    """Test A：主音频已交付 → 收敛 completed_with_stems_failed，不退款、不丢歌、释放锁。"""
    tid = _make_delivered_task(env, monkeypatch, deliver=True, weight=2)
    before_balance = _balance(USER)          # 970（已扣 30）
    before_used = _daily_used(env)           # 2
    before_gen = _gen_usage(env)             # (2, 2)
    assert before_balance == 970 and before_used == 2 and before_gen == (2, 2)

    res = task_recovery.finalize_stale_task(tid, reason="服务重启导致任务中断，已自动退款")
    assert res["finalized"] is True
    assert res["refunded"] is False, "已交付任务不得进入退款分支"
    assert res.get("delivered") is True

    t = task_store.get(tid)
    assert t["state"] == "completed_with_stems_failed"
    assert t["state"] != "failed"
    # Library 判据（MyWorks isDone）仍然成立 → 歌曲不消失
    assert t["state"] in ("completed", "completed_with_stems_failed")
    assert t["audio_url"] == "https://r2.example.com/song.mp3", "audio_url 必须保留"
    assert t["download"], "download 清单必须保留"
    # 钱：Credits 与日/月额度分毫不动
    assert _balance(USER) == before_balance, "Credits 不得从 970 变回 1000"
    assert _daily_used(env) == before_used, "daily_credits_used 不得变化"
    assert _gen_usage(env) == before_gen, "daily_count / monthly_count 不得被清零"
    assert _refund_txns(env, tid) == 0, "不得产生任何退款流水"
    assert _scalar(env, "SELECT refunded_at FROM ai_tasks WHERE task_id=:t", t=tid) is None, \
        "不得抢占退款标记"
    # 锁：必须仍然被释放
    assert _lock_count(env, tid) == 0


def test_f9_undelivered_separating_stale_keeps_old_failure_path(env, monkeypatch):
    """Test B：没有交付物的 separating 仍按原 stale 逻辑 → failed + 全额退款。"""
    tid = _make_delivered_task(env, monkeypatch, deliver=False, weight=2)
    assert _balance(USER) == 970 and _daily_used(env) == 2

    res = task_recovery.finalize_stale_task(tid, reason="生成超时（服务未收到结果），已自动退款")
    assert res["finalized"] is True and res["refunded"] is True and res["quota_weight"] == 2

    t = task_store.get(tid)
    assert t["state"] == "failed"
    assert _balance(USER) == 1000, "未交付任务必须退 30 Credits（既有行为）"
    assert _daily_used(env) == 0 and _gen_usage(env) == (0, 0), "未交付任务必须退回额度（既有行为）"
    assert _refund_txns(env, tid) == 1
    assert _lock_count(env, tid) == 0


def test_f9_repeated_recovery_never_creates_second_refund(env, monkeypatch):
    """Test C：重复 recovery —— 已交付恒为 0 笔退款，未交付恒为 1 笔。"""
    delivered = _make_delivered_task(env, monkeypatch, deliver=True, weight=2)
    assert task_recovery.finalize_stale_task(delivered)["refunded"] is False
    again = task_recovery.finalize_stale_task(delivered)
    assert again["finalized"] is False, "第二次不得再判为已终态化（CAS 未命中）"
    assert _refund_txns(env, delivered) == 0
    assert _balance(USER) == 970
    assert _task_state(env, delivered) == "completed_with_stems_failed"

    undelivered = _make_delivered_task(env, monkeypatch, deliver=False, weight=1)
    assert task_recovery.finalize_stale_task(undelivered)["refunded"] is True
    assert task_recovery.finalize_stale_task(undelivered)["finalized"] is False
    assert _refund_txns(env, undelivered) == 1, "重复 recovery 不得产生第二笔退款"


# ── 读取辅助：直接查临时库，避免依赖服务层返回值 ─────────────────────
def _scalar(env, sql, **params):
    """跑一条语句并返回首列值；UPDATE/INSERT 这类无结果集的语句返回 None。"""
    sess = env.connect()
    try:
        res = sess.execute(text(sql), params)
        try:
            value = res.scalar()
        except Exception:
            value = None
        sess.commit()
        return value
    finally:
        sess.close()


def _daily_used(env, user: str = USER) -> int:
    return int(_scalar(env, "SELECT daily_credits_used FROM beta_users WHERE user_id=:u", u=user) or 0)


def _gen_usage(env, user: str = USER) -> tuple[int, int]:
    sess = env.connect()
    try:
        row = sess.execute(text("SELECT daily_count, monthly_count FROM generation_usage WHERE user_id=:u"),
                           {"u": user}).fetchone()
        sess.commit()
        return (int(row[0] or 0), int(row[1] or 0)) if row else (0, 0)
    finally:
        sess.close()


def _task_weight(env, tid: str):
    return _scalar(env, "SELECT generation_quota_weight FROM ai_tasks WHERE task_id=:t", t=tid)


def _task_state(env, tid: str) -> str:
    return _scalar(env, "SELECT state FROM ai_tasks WHERE task_id=:t", t=tid)


def _set_state(env, tid: str, state: str) -> None:
    sess = env.connect()
    try:
        sess.execute(text("UPDATE ai_tasks SET state=:s WHERE task_id=:t"), {"s": state, "t": tid})
        sess.commit()
    finally:
        sess.close()


def _refund_txns(env, tid: str) -> int:
    return int(_scalar(
        env,
        "SELECT COUNT(*) FROM credits_transactions WHERE reference_id=:r AND transaction_type='refund'",
        r=tid,
    ) or 0)


def _real_generate(monkeypatch, duration: int) -> str:
    """走真实 POST /generate：预留/扣费/建任务全部真跑，只掐掉后台协程（不产生任何付费调用）。"""
    from app.routers import ai_music

    monkeypatch.setattr(ai_music.asyncio, "create_task", lambda coro: coro.close())
    app = FastAPI()
    app.include_router(ai_music.router)
    app.dependency_overrides[get_verified_user_id] = lambda: USER
    r = TestClient(app).post("/api/v1/ai/generate",
                             json={"prompt": "quota weight persistence probe", "duration": duration})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True, body
    return body["task_id"]


# ── Daily quota 权重持久化：reserve == 落库 == 退款 ───────────────────
@pytest.mark.parametrize("duration,expected_weight", [(180, 2), (120, 1), (270, 2)])
def test_reserve_weight_equals_persisted_weight_equals_refund_weight(env, monkeypatch,
                                                                    duration, expected_weight):
    assert _daily_used(env) == 0
    tid = _real_generate(monkeypatch, duration)

    # 1) reserve_generation 实际扣减的权重
    assert _daily_used(env) == expected_weight
    daily, monthly = _gen_usage(env)
    assert (daily, monthly) == (expected_weight, expected_weight)
    # 2) 任务行持久化的权重
    assert _task_weight(env, tid) == expected_weight
    # 3) 终态化退款必须按同一权重退回（此前 180s 只退 1，留下 1 的缺口）
    res = task_recovery.finalize_stale_task(tid, reason="test")
    assert res["finalized"] is True
    assert res["quota_weight"] == expected_weight
    assert _daily_used(env) == 0, "日额度必须完全复原"
    assert _gen_usage(env) == (0, 0), "日/月生成数必须完全复原"
    assert _balance(USER) == 1000, "Credits 同步退回"


def test_legacy_task_without_weight_refunds_conservative_one(env):
    """字段上线前的旧任务：weight 列为 NULL，无法得知当年实际预留值 → 保守退 1，绝不多退。"""
    tid = task_store.new_task(user_key=USER)          # 不传权重 → NULL
    assert _task_weight(env, tid) is None
    ai_limits.reserve_generation(USER, 180)            # 真实预留了 2
    assert _daily_used(env) == 2
    assert task_store.acquire_lock(USER, tid) is True

    res = task_recovery.finalize_stale_task(tid, reason="test")
    assert res["finalized"] is True
    assert res["quota_weight"] == 1, "NULL 必须按保守值 1 退"
    assert _daily_used(env) == 1, "少退可接受（宁可少退），绝不允许退成 0 之外倒扣"


# ── F1：终态不可逆 ───────────────────────────────────────────────────
def test_late_provider_completion_cannot_overwrite_terminal_state(env):
    tid = task_store.new_task(user_key=USER, generation_quota_weight=2)
    assert credits_service.reserve_generation_credits(USER, tid, 30)["success"] is True
    assert task_store.acquire_lock(USER, tid) is True
    _set_state(env, tid, "processing")

    assert task_recovery.finalize_stale_task(tid, reason="test")["finalized"] is True
    assert _task_state(env, tid) == "failed"
    assert _balance(USER) == 1000

    # Provider 迟到成功：任何携带 state 的写入都必须整笔作废
    task_store.update(tid, state="completed", progress=100,
                      audio_url="https://cdn.example.com/late.mp3",
                      download={"full_mp3": "late-key"}, stems_state="ok")

    assert _task_state(env, tid) == "failed", "failed 不得被改回 completed"
    assert _balance(USER) == 1000, "余额不得二次变化"
    assert _refund_txns(env, tid) == 1, "不得产生第二笔退款"
    late = task_store.get(tid)
    assert late["audio_url"] is None and late["download"] is None, "不得留下第二个完成结果"
    assert _scalar(env, "SELECT COUNT(*) FROM task_locks WHERE task_id=:t", t=tid) == 0


def test_finalize_and_late_update_never_both_succeed(env):
    """真并发（两个线程各自独立 session）：终态与退款必须二选一，绝不出现 failed+退款后被改成 completed。"""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    tid = task_store.new_task(user_key=USER, generation_quota_weight=2)
    assert credits_service.reserve_generation_credits(USER, tid, 30)["success"] is True
    assert task_store.acquire_lock(USER, tid) is True
    _set_state(env, tid, "processing")

    barrier = threading.Barrier(2)

    def _finalize():
        barrier.wait()
        try:
            return bool(task_recovery.finalize_stale_task(tid, reason="race")["finalized"])
        except Exception as exc:  # pragma: no cover - 并发下 SQLite 可能报锁冲突
            return f"error:{type(exc).__name__}"

    def _late_update():
        barrier.wait()
        try:
            task_store.update(tid, state="completed", progress=100,
                              audio_url="https://cdn.example.com/late.mp3")
            return "written"
        except Exception as exc:
            return f"rejected:{type(exc).__name__}"

    with ThreadPoolExecutor(max_workers=2) as pool:
        fin = pool.submit(_finalize)
        late = pool.submit(_late_update)
        fin_res = fin.result(timeout=30)
        late.result(timeout=30)

    state = _task_state(env, tid)
    refunds = _refund_txns(env, tid)
    # 只允许两种合法结局：钱与歌永远不可能同时到手。
    # （并发下 SQLite 可能让其中一方拿到锁失败，那属于"被拒"，不是资金问题）
    assert refunds <= 1, "同一任务退款至多一次"
    if state == "failed":
        assert fin_res is True and refunds == 1
        assert (task_store.get(tid) or {}).get("audio_url") is None, "终态后不得留下可播放结果"
    else:
        assert state == "completed"
        assert fin_res is not True, "不得出现「已判 failed 并退款」后又被回写成 completed"
        assert refunds == 0, "completed 的任务绝不能带退款"
