"""Credits v1 —— 「一次完整音乐创作 = 30 Credits」端到端落账规则。

契约（与前端 CreateMusic / Pricing v1 展示同一口径）：
- 提交时（Provider 调用前）原子扣 30；余额不足直接拒绝，不创建任务、不调用 Provider。
- 成功：消费这 30，不再叠加任何奖励（旧「首歌 +25」自动发放已移除）。
- 失败 / 未捕获异常 / 超时 / 上传失败：自动退回 30，同一 task 幂等只退一次。
- 扣费与时长无关（60s/180s/240s/270s 均为 30），与 ai_limits 的每日次数是两条独立线。

全部使用临时 SQLite + fake provider：不触真实 API、不产生真实计费、不碰开发库。
"""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.routers import ai_music
from app.services import ai_limits, credits_service, task_store
from app.services import provider_registry as pr
from app.services.auth_identity import get_verified_user_id
from app.services.credits_config import get_credit_cost
from app.services.provider_registry import BaseProvider

USER = "credits-v1-user"
COST = 30


class FakeProvider(BaseProvider):
    """单 Provider，按 mode 决定成功/失败/抛异常/抛超时/挂起。"""

    provider_type = "api"
    capabilities = ["text_to_music"]
    production = True

    def __init__(self, mode: str = "ok", name: str = "tempolor"):
        self.name = name
        self.mode = mode
        self.calls = 0

    async def generate(self, request: dict) -> dict:
        self.calls += 1
        if self.mode == "fail":
            return {"success": False, "error": "provider down", "provider": self.name}
        if self.mode == "raise":
            raise RuntimeError("boom")
        if self.mode == "timeout":
            raise asyncio.TimeoutError()
        if self.mode == "hang":
            await asyncio.sleep(30)
            return {"success": False, "error": "unreachable", "provider": self.name}
        return {
            "success": True,
            "volume_files": {"full_wav": "fake.wav", "_local_path": "nonexistent-local-path"},
            "provider": self.name,
        }


@pytest.fixture()
def cdb(tmp_path, monkeypatch):
    """隔离 ai_limits / task_store / credits 三套存储，并桩掉生成链路的重 IO。"""
    db_path = str(tmp_path / "flow.db")
    monkeypatch.setattr(ai_limits, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(ai_limits, "_DB_PATH", db_path)
    monkeypatch.setattr(task_store, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(task_store, "_DB_PATH", db_path)
    monkeypatch.setattr(ai_music, "HF_FALLBACK_ENABLED", False)

    eng = create_engine(
        f"sqlite:///{tmp_path / 'credits.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=eng)
    monkeypatch.setattr(credits_service, "SessionLocal", sessionmaker(bind=eng))

    # 次数/预算线放到不会干扰的位置，本文件只验 Credits 线
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 1000)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 1000)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")

    async def _agnes(_req):
        return SimpleNamespace(optimized_prompt="optimized", generated_lyrics=None)

    monkeypatch.setattr(ai_music.agnes_service, "generate_song", _agnes)
    return tmp_path


@pytest.fixture()
def no_bg(monkeypatch):
    """端点后台任务替换为 no-op，由测试手动驱动同一条生产管线。"""

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(ai_music, "_run_with_timeout", _noop)


def _install(monkeypatch, provider: FakeProvider, upload_error: bool = False):
    reg = pr.ProviderRegistry()
    reg.register(provider)
    monkeypatch.setattr(ai_music, "get_provider_registry", lambda: reg)

    async def _upload(task_id, volume_result):
        if upload_error:
            raise RuntimeError("R2 上传失败")
        task_store.update(task_id, state="completed", progress=100)

    monkeypatch.setattr(ai_music, "_upload_and_finalize", _upload)
    return provider


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(ai_music.router)
    # 身份直接固定为测试用户：不依赖「dev 模式 Bearer 即 user_id」的退化语义，
    # 否则其他模块 import main 后注入 SUPABASE_* 会让本组用例变 401。
    app.dependency_overrides[get_verified_user_id] = lambda: USER
    return TestClient(app)


def _seed(amount: int):
    assert credits_service.add_credits(USER, amount, "admin_adjustment")["success"] is True


def _ledger() -> list[tuple]:
    sess = credits_service.SessionLocal()
    try:
        return [
            (row[0], row[1], row[2])
            for row in sess.execute(
                text("SELECT transaction_type, amount, reference_id FROM credits_transactions ORDER BY id")
            ).fetchall()
        ]
    finally:
        sess.close()


def _request(duration: int = 240) -> ai_music.GenerateRequest:
    return ai_music.GenerateRequest(prompt="a synthwave track", duration=duration)


def _submit(c: TestClient, duration: int = 240) -> dict:
    r = c.post("/api/v1/ai/generate", json={"prompt": "a synthwave track", "duration": duration})
    assert r.status_code == 200
    return r.json()


def _run(task_id: str, duration: int = 240):
    asyncio.run(ai_music._run_generation(task_id, _request(duration), USER))


# ────────────────────────── 规则 A：定价 30，与时长无关 ──────────────────────────

def test_1_standard_song_priced_30_regardless_of_duration():
    assert get_credit_cost("standard_song", 60) == COST
    assert get_credit_cost("standard_song", 180) == COST
    assert get_credit_cost("standard_song", 270) == COST


def test_1b_other_types_remain_unpriced():
    """本轮只给完整歌曲定价，其余类型不得被顺带扣费（返回 None = 禁止扣费）。"""
    assert get_credit_cost("stem_separation") is None
    assert get_credit_cost("instrumental") is None


# ────────────────────────── 提交即扣 30 ──────────────────────────

def test_2_endpoint_deducts_30_at_submit(cdb, no_bg):
    _seed(100)
    body = _submit(_client())
    assert body["success"] is True
    assert credits_service.get_balance(USER) == 70
    assert ("generation", -COST, body["task_id"]) in _ledger()


def test_3_success_consumes_30_and_grants_no_bonus(cdb, no_bg, monkeypatch):
    _install(monkeypatch, FakeProvider("ok"))
    _seed(100)
    body = _submit(_client())
    _run(body["task_id"])
    assert (task_store.get(body["task_id"]) or {}).get("state") == "completed"
    assert credits_service.get_balance(USER) == 70
    summary = credits_service.get_credit_summary(USER)
    assert summary["first_song_bonus_claimed"] is False
    assert summary["lifetime_spent"] == COST
    assert [row for row in _ledger() if row[0] == "first_song_bonus"] == []


def test_4_exact_balance_is_consumed_to_zero(cdb, no_bg, monkeypatch):
    _install(monkeypatch, FakeProvider("ok"))
    _seed(COST)
    body = _submit(_client())
    assert body["success"] is True
    assert credits_service.get_balance(USER) == 0
    _run(body["task_id"])
    assert credits_service.get_balance(USER) == 0


# ────────────────────────── 规则 B：失败/异常/超时自动退 30 ──────────────────────────

def test_5_provider_failure_refunds_30(cdb, no_bg, monkeypatch):
    _install(monkeypatch, FakeProvider("fail"))
    _seed(100)
    body = _submit(_client())
    _run(body["task_id"])
    assert (task_store.get(body["task_id"]) or {}).get("state") == "failed"
    assert credits_service.get_balance(USER) == 100
    assert [row for row in _ledger() if row[0] == "refund"] == [("refund", COST, body["task_id"])]


def test_6_uncaught_exception_refunds_30(cdb, no_bg, monkeypatch):
    _install(monkeypatch, FakeProvider("raise"))
    _seed(100)
    body = _submit(_client())
    _run(body["task_id"])
    assert (task_store.get(body["task_id"]) or {}).get("state") == "failed"
    assert credits_service.get_balance(USER) == 100


def test_7_inner_timeout_refunds_30(cdb, no_bg, monkeypatch):
    """Provider 抛 TimeoutError → _run_generation 内层 timeout 分支（历史上漏退 Credits）。"""
    _install(monkeypatch, FakeProvider("timeout"))
    _seed(100)
    body = _submit(_client())
    _run(body["task_id"])
    assert credits_service.get_balance(USER) == 100
    assert ("refund", COST, body["task_id"]) in _ledger()


def test_8_wrapper_timeout_refunds_30(cdb, monkeypatch):
    """整任务超时 → _run_with_timeout 外层 timeout 分支（历史上另一处漏退）。"""
    _install(monkeypatch, FakeProvider("hang"))
    _seed(100)
    monkeypatch.setattr(ai_music, "MAX_TASK_RUNTIME_SECONDS", 0.2)
    tid = task_store.new_task(user_key=USER)
    assert task_store.acquire_lock(USER, tid)
    # 复刻端点提交时的扣费（此处不走 HTTP，只为拿到已扣 30 的起始态）
    assert credits_service.reserve_generation_credits(USER, tid, COST)["success"] is True
    assert credits_service.get_balance(USER) == 70
    asyncio.run(ai_music._run_with_timeout(tid, _request(), USER))
    assert (task_store.get(tid) or {}).get("state") == "failed"
    assert credits_service.get_balance(USER) == 100
    assert ("refund", COST, tid) in _ledger()


def test_9_upload_failure_refunds_30(cdb, no_bg, monkeypatch):
    """生成成功但产物上传/落库失败 → 仍按失败处理，退 30。"""
    _install(monkeypatch, FakeProvider("ok"), upload_error=True)
    _seed(100)
    body = _submit(_client())
    _run(body["task_id"])
    assert credits_service.get_balance(USER) == 100


# ────────────────────────── 规则 C：余额不足拒绝 + 退款幂等 ──────────────────────────

def test_10_insufficient_credits_rejects_before_provider(cdb, no_bg, monkeypatch):
    provider = _install(monkeypatch, FakeProvider("ok"))
    _seed(29)
    body = _submit(_client())
    assert body["success"] is False
    assert body["error"] == "insufficient_credits"
    assert credits_service.get_balance(USER) == 29
    assert provider.calls == 0
    assert task_store.is_user_busy(USER) is False


def test_11_double_refund_credits_only_once(cdb, no_bg, monkeypatch):
    _install(monkeypatch, FakeProvider("fail"))
    _seed(100)
    body = _submit(_client())
    tid = body["task_id"]
    _run(tid)
    _run(tid)  # 重放同一任务失败路径
    assert credits_service.get_balance(USER) == 100
    assert [row for row in _ledger() if row[0] == "refund"] == [("refund", COST, tid)]


def test_12_refund_never_grants_free_credits(cdb, no_bg, monkeypatch):
    """退款金额 = 原扣款金额：未扣费的 task 不得凭空退 30。"""
    _install(monkeypatch, FakeProvider("fail"))
    _seed(100)
    tid = task_store.new_task(user_key=USER)
    assert credits_service.refund_generation_credits(USER, tid)["success"] is True
    assert credits_service.get_balance(USER) == 100
