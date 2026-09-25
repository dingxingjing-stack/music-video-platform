"""Lemon Squeezy 阶段一（服务端建单）的回归测试。零网络：httpx 由桩替掉。

锁住的六件事，全部是"新增 provider 不能引入新风险"的底线：
  1. 缺 LEMONSQUEEZY_API_KEY → 安全失败（503），不建单、不发放；
  2. 缺 LEMONSQUEEZY_STORE_ID → 同上；
  3. 建单成功时只把 checkout_url 交给前端，且上游请求带正确的 JSON:API 头与
     store/variant relationships；
  4. LS 返回错误时，响应体与日志里都不得出现 API Key；
  5. 客户端不能自行指定价格；
  6. 客户端不能靠改 credits/数量篡改购买档位。
另附：custom 归因字段只能由服务端生成。
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import lemon_squeezy as ls_router
from app.services import lemon_squeezy_service as ls
from app.services.auth_identity import get_verified_user_id

API_KEY = "ls_test_secret_key_never_log_me"
STORE = "482388"
VARIANT = "11223"
USER = "ls-user-1"

CHECKOUT_OK = {
    "data": {
        "type": "checkouts",
        "id": "ac470bd4-7c41-474d-b6cd-0f296f5be02a",
        "attributes": {
            "store_id": 1,
            "variant_id": 1,
            "test_mode": True,
            "url": "https://melovar.lemonsqueezy.com/checkout/custom/ac470bd4"
                   "?signature=abc123",
        },
    }
}

# LS 的 detail 是人话，可能顺带复述我们提交的字段；错误信封本身不含密钥，
# 但这条测试要证明的是：无论上游回什么，我们的 key 都不会外泄。
LS_ERROR = {
    "errors": [
        {"code": "invalid_variant", "detail": f"variant {VARIANT} not found for store {STORE}"},
    ]
}


@pytest.fixture()
def base_env(monkeypatch):
    monkeypatch.setenv("LEMONSQUEEZY_API_KEY", API_KEY)
    monkeypatch.setenv("LEMONSQUEEZY_STORE_ID", STORE)
    monkeypatch.setenv("LEMONSQUEEZY_WEBHOOK_SECRET", "ls_whsec_placeholder")
    monkeypatch.setenv("LEMONSQUEEZY_VARIANT_ID_CREDITS_200", VARIANT)
    monkeypatch.delenv("LEMONSQUEEZY_REDIRECT_URL", raising=False)


class _StubResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _StubClient:
    """替掉 httpx.AsyncClient：记录请求，返回预置响应。"""

    payload = CHECKOUT_OK
    status = 201
    seen_headers: dict = {}
    seen_body: dict = {}
    seen_url: str = ""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        type(self).seen_url = url
        type(self).seen_headers = dict(headers or {})
        type(self).seen_body = dict(json or {})
        return _StubResponse(type(self).status, type(self).payload)


@pytest.fixture()
def stub(monkeypatch):
    _StubClient.payload = CHECKOUT_OK
    _StubClient.status = 201
    _StubClient.seen_headers = {}
    _StubClient.seen_body = {}
    _StubClient.seen_url = ""
    monkeypatch.setattr(ls.httpx, "AsyncClient", _StubClient)
    return _StubClient


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(ls_router.router)
    app.dependency_overrides[get_verified_user_id] = lambda: USER
    return TestClient(app)


# ── 1 & 2. 缺凭据必须 fail-closed ────────────────────────────────────
def test_missing_api_key_fails_closed(base_env, stub, monkeypatch):
    monkeypatch.delenv("LEMONSQUEEZY_API_KEY")
    assert ls.checkout_enabled() is False
    r = _client().post("/api/v1/credits/lemonsqueezy/checkout", json={"pack_id": "credits_200"})
    assert r.status_code == 503
    assert r.json()["detail"] == "lemonsqueezy_not_configured"
    assert stub.seen_url == ""  # 一次上游请求都没发出去


def test_missing_store_id_fails_closed(base_env, stub, monkeypatch):
    monkeypatch.delenv("LEMONSQUEEZY_STORE_ID")
    r = _client().post("/api/v1/credits/lemonsqueezy/checkout", json={"pack_id": "credits_200"})
    assert r.status_code == 503
    assert r.json()["detail"] == "lemonsqueezy_not_configured"
    assert stub.seen_url == ""


def test_missing_variant_for_item_fails_closed(base_env, stub, monkeypatch):
    # 商店与 key 都配了，但这一档没配 Variant：不能拿别的档位的 Variant 顶替
    monkeypatch.delenv("LEMONSQUEEZY_VARIANT_ID_CREDITS_200")
    r = _client().post("/api/v1/credits/lemonsqueezy/checkout", json={"pack_id": "credits_200"})
    assert r.status_code == 503
    assert r.json()["detail"] == "lemonsqueezy_variant_not_configured"
    assert stub.seen_url == ""


# ── 3. 成功路径：只回 checkout_url，请求形状符合官方 JSON:API ─────────
def test_checkout_success_returns_only_url(base_env, stub):
    r = _client().post("/api/v1/credits/lemonsqueezy/checkout", json={"pack_id": "credits_200"})
    assert r.status_code == 200
    body = r.json()
    assert body == {"checkout_url": CHECKOUT_OK["data"]["attributes"]["url"]}
    # 绝不把 key / store id / variant id 透给前端
    flat = json.dumps(body)
    assert API_KEY not in flat and STORE not in flat and VARIANT not in flat


def test_checkout_request_uses_documented_auth_and_relationships(base_env, stub):
    _client().post("/api/v1/credits/lemonsqueezy/checkout", json={"pack_id": "credits_200"})
    assert stub.seen_url == "https://api.lemonsqueezy.com/v1/checkouts"
    h = stub.seen_headers
    assert h["Authorization"] == f"Bearer {API_KEY}"
    assert h["Accept"] == "application/vnd.api+json"
    assert h["Content-Type"] == "application/vnd.api+json"
    rel = stub.seen_body["data"]["relationships"]
    assert rel["store"]["data"] == {"type": "stores", "id": STORE}
    assert rel["variant"]["data"] == {"type": "variants", "id": VARIANT}
    assert stub.seen_body["data"]["type"] == "checkouts"


def test_custom_attribution_is_server_generated(base_env, stub):
    _client().post("/api/v1/credits/lemonsqueezy/checkout", json={"pack_id": "credits_200"})
    custom = stub.seen_body["data"]["attributes"]["checkout_data"]["custom"]
    assert custom == {"user_id": USER, "kind": "credit_pack",
                      "pack_id": "credits_200", "credits": "200"}


def test_membership_plan_maps_to_its_own_variant(base_env, stub, monkeypatch):
    monkeypatch.setenv("LEMONSQUEEZY_VARIANT_ID_PRO", "99999")
    _client().post("/api/v1/credits/lemonsqueezy/checkout", json={"plan_id": "pro"})
    rel = stub.seen_body["data"]["relationships"]
    assert rel["variant"]["data"]["id"] == "99999"
    custom = stub.seen_body["data"]["attributes"]["checkout_data"]["custom"]
    assert custom["kind"] == "membership" and custom["plan_id"] == "pro"
    assert custom["credits_per_month"] == "1200"


# ── 4. 上游报错时不得泄露 key ────────────────────────────────────────
def test_upstream_error_does_not_leak_api_key(base_env, stub, caplog):
    stub.payload = LS_ERROR
    stub.status = 422
    with caplog.at_level("WARNING"):
        r = _client().post("/api/v1/credits/lemonsqueezy/checkout", json={"pack_id": "credits_200"})
    assert r.status_code == 502
    assert r.json()["detail"] == "invalid_variant"
    assert API_KEY not in r.text
    assert API_KEY not in caplog.text


def test_describe_ls_error_redacts_email_and_key(base_env):
    # 必须带 base_env：key 打码依赖 LEMONSQUEEZY_API_KEY 已配置，没配就没有"要藏起来的东西"
    code, detail = ls.describe_ls_error({
        "errors": [{"code": "x", "detail": f"bad buyer@example.com {API_KEY}"}]
    })
    assert code == "x"
    assert "buyer@example.com" not in detail and "[redacted]" in detail
    assert API_KEY not in detail


def test_network_failure_is_generic(base_env, monkeypatch):
    class _Boom:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            raise RuntimeError("socket exploded with " + API_KEY)

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(ls.httpx, "AsyncClient", _Boom)
    with pytest.raises(ls.LemonSqueezyError) as ei:
        import asyncio
        asyncio.run(ls.create_checkout(variant_id=VARIANT, custom={"user_id": USER}))
    assert API_KEY not in str(ei.value)
    assert ei.value.code == "ls_network_error"


# ── 5 & 6. 客户端不得指定价格 / 不得篡改档位 ─────────────────────────
def test_client_cannot_inject_price(base_env, stub):
    r = _client().post("/api/v1/credits/lemonsqueezy/checkout",
                       json={"pack_id": "credits_200", "price": 1, "custom_price": 1})
    assert r.status_code == 422
    assert stub.seen_url == ""


def test_client_cannot_override_credits_quantity(base_env, stub):
    # 想花 200 档的钱拿 2800 积分：credits 字段根本不受理
    r = _client().post("/api/v1/credits/lemonsqueezy/checkout",
                       json={"pack_id": "credits_200", "credits": 2800})
    assert r.status_code == 422
    assert stub.seen_url == ""


def test_client_cannot_supply_variant_id(base_env, stub):
    r = _client().post("/api/v1/credits/lemonsqueezy/checkout",
                       json={"pack_id": "credits_200", "variant_id": "1"})
    assert r.status_code == 422
    assert stub.seen_url == ""


def test_both_or_neither_item_rejected(base_env, stub):
    c = _client()
    assert c.post("/api/v1/credits/lemonsqueezy/checkout",
                  json={"pack_id": "credits_200", "plan_id": "pro"}).status_code == 422
    assert c.post("/api/v1/credits/lemonsqueezy/checkout", json={}).status_code == 422


def test_unknown_item_404(base_env, stub):
    r = _client().post("/api/v1/credits/lemonsqueezy/checkout", json={"pack_id": "credits_99999"})
    assert r.status_code == 404
    assert stub.seen_url == ""


# ── 状态端点：不得泄露任何凭据 ───────────────────────────────────────
def test_status_exposes_no_secrets(base_env):
    r = _client().get("/api/v1/credits/lemonsqueezy/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True and "credits_200" in body["items"]
    assert API_KEY not in r.text and STORE not in r.text and VARIANT not in r.text
