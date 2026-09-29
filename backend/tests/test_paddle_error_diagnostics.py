"""Paddle 错误诊断的回归测试：账户级失败必须以原始机器码浮出来。

背景（2026-09-22 生产事故）：Paddle 生产账户未完成 onboarding，建单被拒
`transaction_checkout_not_enabled`，但后端只记了一句
"Paddle create returned status 400"，把 Paddle 明确给出的 code/detail 全丢了，
导致排查方向被一路带到 Price ID、Supabase 与 Nginx 上。

本文件锁住修好的三件事：
  1. `describe_paddle_error()` 只取 code/detail/request_id，并对 detail 里的邮箱打码 + 截断；
  2. 建单被拒时 `PaddleError` 携带 `code`/`status`，且日志里不出现 API key；
  3. 账户级 code → HTTP 503 + 原始 code 回传；其它失败保持既有 502 语义。
零网络：Paddle 响应由桩提供。
"""

from __future__ import annotations

import asyncio
import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.routers import credits as credits_router
from app.services import (
    credit_pack_service,
    credits_service,
    membership_service,
    paddle_service,
)
from app.services.auth_identity import get_verified_user_id

API_KEY = "pdl_live_secret_apikey_never_log_me"
USER = "diag-user-1"

CHECKOUT_DISABLED_ENVELOPE = {
    "error": {
        "type": "request_error",
        "code": "transaction_checkout_not_enabled",
        "detail": ("Checkouts aren't enabled for this account. This typically means that "
                   "you haven't fully completed the Paddle onboarding process."),
    },
    "meta": {"request_id": "b9a1c2d3-4455-6677-8899-aabbccddeeff"},
}

EMAIL_LEAK_ENVELOPE = {
    "error": {
        "type": "request_error",
        "code": "browser_data_incorrect",
        "detail": "customer.email buyer@example.com is not acceptable",
    },
    "meta": {},
}

PLAN_ENVS = {
    "PADDLE_PRICE_ID_STARTER": "pri_plan_starter",
    "PADDLE_PRICE_ID_BASIC": "pri_plan_basic",
    "PADDLE_PRICE_ID_PRO": "pri_plan_pro",
    "PADDLE_PRICE_ID_CREATOR": "pri_plan_creator",
}
PACK_ENVS = {
    "PADDLE_PRICE_ID_CREDITS_200": "pri_pack_200",
    "PADDLE_PRICE_ID_CREDITS_500": "pri_pack_500",
    "PADDLE_PRICE_ID_CREDITS_1200": "pri_pack_1200",
    "PADDLE_PRICE_ID_CREDITS_2800": "pri_pack_2800",
}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = str(tmp_path / "diag.db")
    eng = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    from app.db.database import Base
    Base.metadata.create_all(bind=eng)
    monkeypatch.setattr(credits_service, "SessionLocal", sessionmaker(bind=eng))
    monkeypatch.setattr(credit_pack_service, "SessionLocal", sessionmaker(bind=eng))
    monkeypatch.setattr(membership_service, "SessionLocal", sessionmaker(bind=eng))
    monkeypatch.setenv("PADDLE_WEBHOOK_SECRET", "pdl_ntfset_diag_test")
    monkeypatch.setenv("PADDLE_ENV", "production")
    monkeypatch.setenv("PADDLE_API_KEY", API_KEY)
    monkeypatch.setenv("PADDLE_CLIENT_TOKEN", "live_diag_token_value")
    for k, v in {**PLAN_ENVS, **PACK_ENVS}.items():
        monkeypatch.setenv(k, v)
    credits_service.add_credits(USER, 0, "admin_adjustment", description="open row")
    return eng


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(credits_router.router)
    app.dependency_overrides[get_verified_user_id] = lambda: USER
    return TestClient(app)


def _balance() -> int:
    sess = credits_service.SessionLocal()
    try:
        return int(sess.execute(text("select balance from user_credits where user_id = :u"),
                               {"u": USER}).scalar() or 0)
    finally:
        sess.close()


class _StubResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _StubClient:
    """替掉 httpx.AsyncClient：记录请求头，返回预置的 Paddle 响应。"""

    payload = CHECKOUT_DISABLED_ENVELOPE
    status = 400
    seen_headers: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        type(self).seen_headers = dict(headers or {})
        return _StubResponse(type(self).status, type(self).payload)


# ── 1. describe_paddle_error：只取安全字段、detail 打码与截断 ─────────
def test_describe_paddle_error_extracts_code_detail_request_id():
    code, detail, request_id = paddle_service.describe_paddle_error(CHECKOUT_DISABLED_ENVELOPE)
    assert code == "transaction_checkout_not_enabled"
    assert detail and "onboarding" in detail
    assert request_id == "b9a1c2d3-4455-6677-8899-aabbccddeeff"


def test_describe_paddle_error_redacts_email_in_detail():
    _, detail, request_id = paddle_service.describe_paddle_error(EMAIL_LEAK_ENVELOPE)
    assert "buyer@example.com" not in (detail or "")
    assert "[redacted]" in (detail or "")
    assert request_id is None


def test_describe_paddle_error_truncates_and_degrades():
    long_env = {"error": {"code": "x", "detail": "y" * 5000}}
    _, detail, _ = paddle_service.describe_paddle_error(long_env)
    assert detail is not None and len(detail) <= 200
    # 非 JSON / 缺 error / 非 dict 一律退化成空，不抛异常
    assert paddle_service.describe_paddle_error(None) == (None, None, None)
    assert paddle_service.describe_paddle_error({"data": {}}) == (None, None, None)
    assert paddle_service.describe_paddle_error(json) == (None, None, None)


# ── 2. 建单被拒：PaddleError 必须带上 code/status，且不外泄密钥 ────────
def test_create_transaction_carries_paddle_code(env, monkeypatch, caplog):
    monkeypatch.setattr(paddle_service.httpx, "AsyncClient", _StubClient)
    _StubClient.payload = CHECKOUT_DISABLED_ENVELOPE
    _StubClient.status = 400

    with caplog.at_level(logging.WARNING, logger="app.services.paddle_service"):
        with pytest.raises(paddle_service.PaddleError) as exc_info:
            asyncio.run(paddle_service.create_checkout_transaction(
                price_id="pri_plan_starter", custom_data={"user_id": USER, "kind": "membership"}))

    assert exc_info.value.code == "transaction_checkout_not_enabled"
    assert exc_info.value.status == 400
    assert "transaction_checkout_not_enabled" in caplog.text
    assert "b9a1c2d3" in caplog.text
    # 凭据与 Authorization 头一个字节都不能进日志
    assert API_KEY not in caplog.text
    assert API_KEY not in str(exc_info.value)
    assert _StubClient.seen_headers.get("Authorization", "").startswith("Bearer ")


def test_create_transaction_survives_non_json_body(env, monkeypatch):
    class _Broken(_StubClient):
        async def post(self, url, headers=None, json=None):
            class R:
                status_code = 502

                def json(self):
                    raise ValueError("not json")
            return R()

    monkeypatch.setattr(paddle_service.httpx, "AsyncClient", _Broken)
    with pytest.raises(paddle_service.PaddleError) as exc_info:
        asyncio.run(paddle_service.create_checkout_transaction(
            price_id="pri_plan_starter", custom_data={}))
    assert exc_info.value.code is None
    assert exc_info.value.status == 502


# ── 3. 路由层：账户级 code → 503 原样回传；其它 → 保持 502 ────────────
def test_checkout_maps_account_precondition_to_503_with_code(env, monkeypatch):
    async def _raise(**kwargs):
        raise paddle_service.PaddleError(
            "payment provider rejected the order (status 400)",
            code="transaction_checkout_not_enabled", status=400)

    monkeypatch.setattr(paddle_service, "create_checkout_transaction", _raise)
    r = _client().post("/api/v1/credits/checkout", json={"plan_id": "starter"})
    assert r.status_code == 503
    assert r.json()["detail"] == "transaction_checkout_not_enabled"
    assert _balance() == 0, "诊断改进不得改变任何资金语义：一条 Credits 都不能发"


def test_checkout_keeps_502_for_other_paddle_errors(env, monkeypatch):
    async def _raise(**kwargs):
        raise paddle_service.PaddleError("payment provider rejected the order (status 404)",
                                         code="price_not_found", status=404)

    monkeypatch.setattr(paddle_service, "create_checkout_transaction", _raise)
    r = _client().post("/api/v1/credits/checkout", json={"pack_id": "credits_200"})
    assert r.status_code == 502
    assert r.json()["detail"] == "price_not_found"
    assert _balance() == 0
