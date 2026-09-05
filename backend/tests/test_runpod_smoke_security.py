"""P0-4 Phase 4 — RunPod Smoke Test 安全审计测试（T1–T10 + 并发）。

审计结论（ai_music.py:885/runpod-smoke-test）：
  - access-token = X-RunPod-Smoke-Token Header，仅与 RUNPOD_SMOKE_TEST_TOKEN 严格比较。
  - token 校验（401/503）发生在任何对 api.runpod.ai 的 submit 之前。
  - 不读取 X-User-ID / body / query 中的 token，普通用户无法代替 token。
  - 拒绝路径 GPU invocation = 0。

本测试用 _FakeRunPodClient 计数对 RunPod 的 POST submit，证明：
  - all denied → submit 调用数 = 0
  - 正确 token → 按设计走到 submit（后续在真实环境由 RunPod 决定）
"""
import concurrent.futures
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import ai_music


# ── 计数 RunPod 提交的 fake 客户端 ──
class _SubmitCount:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.n = 0

    async def inc(self):
        async with self.lock:
            self.n += 1


class _FakeResp:
    def __init__(self, status_code=202, body=None):
        self.status_code = status_code
        self._body = body or {"id": "fake-job-1"}

    def json(self):
        return self._body

    @property
    def text(self):
        import json
        return json.dumps(self._body)


class _FakeRunPodClient:
    """替换 httpx.AsyncClient；post 到 api.runpod.ai 即视为一次 GPU submit。"""

    def __init__(self, submit_counter, submit_status=202):
        self.submit_counter = submit_counter
        self.submit_status = submit_status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, *a, **k):
        if "runpod" in url or "/run" in url:
            await self.submit_counter.inc()
        return _FakeResp(status_code=self.submit_status)

    async def get(self, url, *a, **k):
        # 轮询直接返回 completed，避免深入 RunPod 交互
        return _FakeResp(status_code=200, body={
            "status": "COMPLETED", "worker_id": "w1",
            "output": {"success": True, "output": {"gpu_info": {"cuda_available": True}}},
        })


@pytest.fixture()
def smoke_env(monkeypatch):
    """配置 RunPod smoke 所需环境变量，返回 submit 计数器与 client 替换。"""
    monkeypatch.setenv("RUNPOD_SMOKE_TEST_TOKEN", "the-secret-token")
    monkeypatch.setenv("RUNPOD_API_KEY", "sk-fake")
    monkeypatch.setenv("RUNPOD_ENDPOINT_ID", "endpoint-fake")
    counter = _SubmitCount()
    monkeypatch.setattr(ai_music.httpx, "AsyncClient",
                        lambda *a, **k: _FakeRunPodClient(counter))
    return counter


def _client():
    app = FastAPI()
    app.include_router(ai_music.router)
    return TestClient(app)


async def _counter_n(counter):
    return counter.n


# ───────────── T1: 正确 token → 允许走到 submit ─────────────
def test_t1_correct_token_allowed(smoke_env):
    c = _client()
    r = c.post("/api/v1/ai/runpod-smoke-test", headers={"X-RunPod-Smoke-Token": "the-secret-token"})
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert smoke_env.n >= 1  # 已 submit


# ───────────── T2: 错误 token → 拒绝，GPU=0 ─────────────
def test_t2_wrong_token_denied(smoke_env):
    c = _client()
    r = c.post("/api/v1/ai/runpod-smoke-test", headers={"X-RunPod-Smoke-Token": "wrong"})
    assert r.status_code == 401
    assert smoke_env.n == 0


# ───────────── T3: 缺失 token → 拒绝，GPU=0 ─────────────
def test_t3_missing_token_denied(smoke_env):
    c = _client()
    r = c.post("/api/v1/ai/runpod-smoke-test")
    assert r.status_code == 401
    assert smoke_env.n == 0


# ───────────── T4: 空 token → 拒绝，GPU=0 ─────────────
def test_t4_empty_token_denied(smoke_env):
    c = _client()
    r = c.post("/api/v1/ai/runpod-smoke-test", headers={"X-RunPod-Smoke-Token": ""})
    assert r.status_code == 401
    assert smoke_env.n == 0


# ───────────── T5: body token spoof → 不能绕过，GPU=0 ─────────────
def test_t5_body_token_spoof_not_bypass(smoke_env):
    c = _client()
    # 用 body 伪造 token（可信 token 在 Header 缺失/错误时仍拒绝）
    r = c.post("/api/v1/ai/runpod-smoke-test", json={"token": "the-secret-token"})
    assert r.status_code == 401  # 未带正确 Header → 401
    assert smoke_env.n == 0


# ───────────── T6: query token spoof → 不能绕过，GPU=0 ─────────────
def test_t6_query_token_spoof_not_bypass(smoke_env):
    c = _client()
    r = c.post("/api/v1/ai/runpod-smoke-test?token=the-secret-token")
    assert r.status_code == 401  # query token 无效，需 Header
    assert smoke_env.n == 0


# ───────────── T7: X-User-ID 代替 token → 不能绕过，GPU=0 ─────────────
def test_t7_x_user_id_not_substitute(smoke_env):
    c = _client()
    r = c.post("/api/v1/ai/runpod-smoke-test", headers={"X-User-ID": "admin", "X-RunPod-Smoke-Token": "wrong"})
    assert r.status_code == 401
    assert smoke_env.n == 0


# ───────────── T8: 普通用户 + 错误 token → 拒绝，GPU=0 ─────────────
def test_t8_normal_user_wrong_token_denied(smoke_env):
    c = _client()
    r = c.post("/api/v1/ai/runpod-smoke-test", headers={"X-User-ID": "user-123", "X-RunPod-Smoke-Token": "wrong"})
    assert r.status_code == 401
    assert smoke_env.n == 0


# ───────────── T9: production 缺少 token → fail closed (503)，GPU=0 ─────────────
def test_t9_production_missing_token_fail_closed(monkeypatch):
    # production 环境但未配置 smoke token → 503，且不 submit
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("RUNPOD_SMOKE_TEST_TOKEN", raising=False)
    counter = _SubmitCount()
    monkeypatch.setattr(ai_music.httpx, "AsyncClient", lambda *a, **k: _FakeRunPodClient(counter))
    c = _client()
    r = c.post("/api/v1/ai/runpod-smoke-test", headers={"X-RunPod-Smoke-Token": ""})
    assert r.status_code == 503
    assert counter.n == 0


# ───────────── T10: token 校验先于 GPU invocation ─────────────
def test_t10_auth_before_gpu(smoke_env):
    """错误 token 时 submit 计数为 0，证明鉴权发生在任何 RunPod 调用之前。"""
    c = _client()
    r = c.post("/api/v1/ai/runpod-smoke-test", headers={"X-RunPod-Smoke-Token": "wrong"})
    assert r.status_code == 401
    assert smoke_env.n == 0  # 鉴权失败 → submit 未被调用


# ───────────── T11: 并发 smoke-test 不绕过鉴权 ─────────────
def test_t11_concurrent_no_auth_bypass(smoke_env):
    """20 并发请求（mix 错误/缺失 token）→ 全部 4xx/503 拒绝，GPU submit = 0。

    证明并发不会绕过 token，也不会让未认证请求进入 RunPod。
    """
    c = _client()

    def _call(i):
        if i % 2 == 0:
            headers = {"X-RunPod-Smoke-Token": "wrong"}
        else:
            headers = {"X-RunPod-Smoke-Token": ""}
        r = c.post("/api/v1/ai/runpod-smoke-test", headers=headers)
        return r.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        codes = list(ex.map(_call, range(20)))
    # 全部必须被拒（401，因错误/空 token）—— 不含 200
    assert all(code != 200 for code in codes), f"存在未认证通过: {codes}"
    assert smoke_env.n == 0  # 任何未认证请求都未触发 RunPod submit


# ───────────── T12: 并发中正确 token 仍按设计工作 ─────────────
def test_t12_concurrent_wrong_and_correct_mixed(smoke_env):
    """20 并发：18 个错误 token + 2 个正确 token → 错误全拒、正确能 submit（按设计）。"""
    c = _client()

    def _call(i):
        headers = {"X-RunPod-Smoke-Token": "the-secret-token" if i < 2 else "wrong"}
        return c.post("/api/v1/ai/runpod-smoke-test", headers=headers).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        codes = list(ex.map(_call, range(20)))
    ok = codes.count(200)
    denied = codes.count(401)
    assert ok == 2, f"正确 token 应全部成功, got {codes}"
    assert denied == 18
    assert smoke_env.n == 2  # 只有正确 token 触发了 submit