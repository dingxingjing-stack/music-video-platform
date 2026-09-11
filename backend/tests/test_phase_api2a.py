"""Phase API-2A 测试：refund 幂等 + 通用 Provider fallback chain。

覆盖：
  - refund_generation(task_id) 首次/重复/并发/不退款语义
  - provider_registry.fallback_chain() 生产/非生产顺序
  - ai_music._run_generation 的 fallback 循环（A success / A fail→B / 全部 fail→退款一次）

额度断言全部走同步 reserve_generation 成败（与现有测试一致），不依赖 async 状态查询。
"""

import asyncio
import os
import threading

import pytest

from app.services import ai_limits, task_store
from app.routers import ai_music


# ═══════════════════════════════════════════════════════════════
# 基础设施
# ═══════════════════════════════════════════════════════════════

@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_beta.db")
    monkeypatch.setattr(ai_limits, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(ai_limits, "_DB_PATH", db_path)
    monkeypatch.setattr(task_store, "_DB_DIR", str(tmp_path))
    monkeypatch.setattr(task_store, "_DB_PATH", db_path)
    return db_path


@pytest.fixture()
def quota_loose(isolated_db, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "MONTHLY_GENERATION_LIMIT", 100)
    monkeypatch.setattr(ai_limits, "GLOBAL_DAILY_GENERATION_LIMIT", 1000)
    monkeypatch.setattr(ai_limits, "MODAL_BUDGET_DAILY", "")
    return isolated_db


def _make_task(user: str, task_id: str) -> str:
    return task_store.new_task(user_key=user, task_id=task_id)


# ═══════════════════════════════════════════════════════════════
# 一、refund_generation 幂等
# ═══════════════════════════════════════════════════════════════

def test_refund_first_then_second_idempotent(quota_loose):
    user = "u-first"
    tid = "task-first"
    assert ai_limits.reserve_generation(user, 60)["success"] is True
    _make_task(user, tid)

    r1 = ai_limits.refund_generation(user, 60, reason="provider_failed", task_id=tid)
    assert r1["success"] is True and r1["refunded"] is True and r1["already_refunded"] is False

    r2 = ai_limits.refund_generation(user, 60, reason="provider_failed", task_id=tid)
    assert r2["success"] is True and r2["refunded"] is False and r2["already_refunded"] is True

    # 只退一次 → 额度恢复，可再次 reserve
    assert ai_limits.reserve_generation(user, 60)["success"] is True


def test_refund_task_not_found_safe_fail(quota_loose, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 1)
    user = "u-missing"
    assert ai_limits.reserve_generation(user, 60)["success"] is True
    r = ai_limits.refund_generation(user, 60, reason="provider_failed", task_id="task-nonexistent")
    assert r["success"] is False and r["refunded"] is False
    # task 不存在 → 未退款 → 额度仍占用
    assert ai_limits.reserve_generation(user, 60)["success"] is False


def test_refund_concurrent_only_one_wins(quota_loose):
    user = "u-conc"
    tid = "task-conc"
    assert ai_limits.reserve_generation(user, 60)["success"] is True
    _make_task(user, tid)

    barrier = threading.Barrier(2)
    results = []

    def _worker():
        barrier.wait()
        r = ai_limits.refund_generation(user, 60, reason="provider_failed", task_id=tid)
        results.append(r)

    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 恰好一个 refunded=True（原子抢占 rowcount==1 只允许一个赢家）
    refunded_true = [r for r in results if r.get("refunded") is True]
    assert len(refunded_true) == 1, results


def test_refund_timeout_unknown_no_refund(quota_loose, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 1)
    user = "u-timeout"
    tid = "task-timeout"
    assert ai_limits.reserve_generation(user, 60)["success"] is True
    _make_task(user, tid)
    r = ai_limits.refund_generation(user, 60, reason="timeout_unknown", task_id=tid)
    assert r["refunded"] is False
    # 未退款 → 额度仍占用 → 再次 reserve 失败
    assert ai_limits.reserve_generation(user, 60)["success"] is False


def test_refund_persistence_failed_no_refund(quota_loose, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 1)
    user = "u-persist"
    tid = "task-persist"
    assert ai_limits.reserve_generation(user, 60)["success"] is True
    _make_task(user, tid)
    r = ai_limits.refund_generation(user, 60, reason="persistence_failed", task_id=tid)
    assert r["refunded"] is False
    assert ai_limits.reserve_generation(user, 60)["success"] is False


def test_refund_provider_failed_final_once(quota_loose, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 1)
    user = "u-pf"
    tid = "task-pf"
    assert ai_limits.reserve_generation(user, 60)["success"] is True
    _make_task(user, tid)
    for _ in range(3):
        ai_limits.refund_generation(user, 60, reason="provider_failed", task_id=tid)
    # 只退一次 → 额度恢复 → 再次 reserve 成功
    assert ai_limits.reserve_generation(user, 60)["success"] is True


# ═══════════════════════════════════════════════════════════════
# 二、fallback_chain() 顺序
# ═══════════════════════════════════════════════════════════════

@pytest.fixture()
def isolated_env(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("AI_GENERATION_PROVIDER", raising=False)
    import app.services.provider_registry as pr
    pr._registry = None
    yield
    pr._registry = None


def test_fallback_chain_production_without_mureka(isolated_env):
    """生产环境且 Mureka 未注册 → 跳过 mureka，保留 [yinchao, runpod]（验证缺席跳过分支）。

    API-2B 后 registry 默认注册 yinchao/mureka（真实 Provider），
    故此处临时移除 mureka 以覆盖「mureka 不可用」的降级路径。
    """
    os.environ["ENVIRONMENT"] = "production"
    import app.services.provider_registry as pr
    reg = pr.get_provider_registry()
    reg._providers.pop("mureka", None)
    chain = reg.fallback_chain()
    assert [p.name for p in chain] == ["yinchao", "runpod"]


def test_fallback_chain_production_with_mureka(isolated_env):
    os.environ["ENVIRONMENT"] = "production"
    import app.services.provider_registry as pr

    reg = pr.get_provider_registry()
    chain = reg.fallback_chain()
    assert [p.name for p in chain] == ["yinchao", "mureka", "runpod"]


def test_fallback_chain_development_keeps_fal(isolated_env):
    os.environ["ENVIRONMENT"] = "development"
    import app.services.provider_registry as pr
    reg = pr.get_provider_registry()
    chain = reg.fallback_chain()
    assert [p.name for p in chain] == ["fal_stable_audio"]


# ═══════════════════════════════════════════════════════════════
# 三、ai_music._run_generation 的 fallback 循环
# ═══════════════════════════════════════════════════════════════

class _FakeProvider:
    def __init__(self, name, result: dict | None):
        self.name = name
        self.gpu = "test"
        self._result = result
        self.calls = 0

    async def generate(self, request):
        self.calls += 1
        return self._result


def _install_chain(monkeypatch, providers, hf_result=None):
    class _Reg:
        def fallback_chain(self, name=None):
            return providers
    monkeypatch.setattr(ai_music, "get_provider_registry", lambda: _Reg())

    async def _agnes(req):
        class _R:
            pass
        r = _R()
        r.optimized_prompt = req.prompt
        r.generated_lyrics = None
        return r
    monkeypatch.setattr(ai_music.agnes_service, "generate_song", _agnes)

    async def _hf(*a, **k):
        return hf_result
    monkeypatch.setattr(ai_music, "_try_hf_ace_step_fallback", _hf)

    async def _upload(task_id, volume_result):
        return None
    monkeypatch.setattr(ai_music, "_upload_and_finalize", _upload)


def _run(monkeypatch, task_id, user, providers, hf_result=None):
    monkeypatch.setattr(ai_music, "MAX_AUTO_RETRIES", 0)
    _install_chain(monkeypatch, providers, hf_result=hf_result)
    req = ai_music.GenerateRequest(prompt="test song", style="pop", duration=60, type="song")
    asyncio.run(ai_music._run_generation(task_id, req, user))


def test_fallback_a_success_b_not_called(quota_loose, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 1)
    user = "u-fb-ok"
    assert ai_limits.reserve_generation(user, 60)["success"] is True
    tid = _make_task(user, "task-fb-ok")

    A = _FakeProvider("mureka", {"success": True, "volume_files": {"full_wav": "a.wav", "full_mp3": "a.mp3"}})
    B = _FakeProvider("runpod", {"success": True, "volume_files": {"full_wav": "b.wav", "full_mp3": "b.mp3"}})

    _run(monkeypatch, tid, user, [A, B])

    assert A.calls == 1 and B.calls == 0
    # 成功不退款 → 额度仍占用 → 再次 reserve 失败
    assert ai_limits.reserve_generation(user, 60)["success"] is False


def test_fallback_a_fail_b_success(quota_loose, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 1)
    user = "u-fb-b"
    assert ai_limits.reserve_generation(user, 60)["success"] is True
    tid = _make_task(user, "task-fb-b")

    A = _FakeProvider("mureka", {"success": False, "error": "fail", "provider": "mureka"})
    B = _FakeProvider("runpod", {"success": True, "volume_files": {"full_wav": "b.wav", "full_mp3": "b.mp3"}})

    _run(monkeypatch, tid, user, [A, B])

    assert A.calls == 1 and B.calls == 1
    # 链最终成功 → 不退款 → 额度仍占用
    assert ai_limits.reserve_generation(user, 60)["success"] is False


def test_fallback_both_fail_refund_once(quota_loose, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 1)
    user = "u-fb-ff"
    assert ai_limits.reserve_generation(user, 60)["success"] is True
    tid = _make_task(user, "task-fb-ff")

    A = _FakeProvider("mureka", {"success": False, "error": "fail", "provider": "mureka"})
    B = _FakeProvider("runpod", {"success": False, "error": "fail", "provider": "runpod"})

    _run(monkeypatch, tid, user, [A, B], hf_result=None)

    assert A.calls == 1 and B.calls == 1
    assert task_store.get(tid)["state"] == "failed"
    # 退款一次 → 额度恢复 → 再次 reserve 成功
    assert ai_limits.reserve_generation(user, 60)["success"] is True


def test_fallback_exception_no_double_refund(quota_loose, monkeypatch):
    monkeypatch.setattr(ai_limits, "DAILY_GENERATION_LIMIT", 1)
    user = "u-fb-exc"
    assert ai_limits.reserve_generation(user, 60)["success"] is True
    tid = _make_task(user, "task-fb-exc")

    class _Boom:
        name = "mureka"
        gpu = "test"

        async def generate(self, request):
            raise RuntimeError("boom")

    B = _FakeProvider("runpod", {"success": False, "error": "fail", "provider": "runpod"})
    _install_chain(monkeypatch, [_Boom(), B], hf_result=None)
    monkeypatch.setattr(ai_music, "MAX_AUTO_RETRIES", 0)
    req = ai_music.GenerateRequest(prompt="test song", style="pop", duration=60, type="song")
    asyncio.run(ai_music._run_generation(tid, req, user))

    assert task_store.get(tid)["state"] == "failed"
    # 退款恰好一次 → 额度恢复 → 再次 reserve 成功
    assert ai_limits.reserve_generation(user, 60)["success"] is True