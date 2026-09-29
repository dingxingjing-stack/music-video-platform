"""P2-3：Lemon Squeezy webhook 路由骨架的测试。

本阶段唯一的业务链路是"验签 → 解析 → 投递台账 → 响应"，所以测试分三组：

  一 验签边界：正确 raw body 才放行；改 1 个字节 / 重新序列化 / 错密钥 / 空头 /
    缺头 全部 401，且**一条投递都不落库**（401 之前不允许有任何写操作）。
  二 结构边界：签名正确但 body 不是合法 JSON、或不是 webhook 形状 ⇒ 400，
    且不回显 body、不抛 traceback。
  三 零发放：order / subscription / invoice 三类真实事件都只允许往
    lemonsqueezy_webhook_deliveries 写一行；purchases / memberships / grants
    必须恒为 0 行 —— 这是 P2-3 的验收底线，用"运行时行数 + 源码静态扫描"
    两条独立证据同时锁。

全程 tmp_path 临时 SQLite，绝不碰开发库。
"""

from __future__ import annotations

import ast
import inspect
import json
import logging
import pathlib
import textwrap

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db import database as db
from app.db.database import (
    Base,
    LemonSqueezyMembership,
    LemonSqueezyMembershipGrant,
    LemonSqueezyPurchase,
    LemonSqueezyWebhookDelivery,
)
from app.routers import lemon_squeezy as ls_router
from tests import ls_payload

SECRET = "ls_test_webhook_secret_0123456789abcdefghij"
WRONG_SECRET = "ls_test_wrong_secret_0123456789abcdefgh"
WEBHOOK_URL = "/api/v1/credits/lemonsqueezy/webhook"

BUSINESS_MODELS = (LemonSqueezyPurchase, LemonSqueezyMembership, LemonSqueezyMembershipGrant)


@pytest.fixture()
def maker(monkeypatch, tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'ls.webhook.db'}",
                        connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    monkeypatch.setattr(db, "engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng))
    return sessionmaker(bind=eng)


@pytest.fixture()
def client(maker, monkeypatch):
    monkeypatch.setenv("LEMONSQUEEZY_WEBHOOK_SECRET", SECRET)
    app = FastAPI()
    app.include_router(ls_router.router)
    return TestClient(app)


def _count(maker, model) -> int:
    sess = maker()
    try:
        return sess.scalar(select(func.count()).select_from(model.__table__)) or 0
    finally:
        sess.close()


def _deliveries(maker):
    sess = maker()
    try:
        return sess.scalars(select(LemonSqueezyWebhookDelivery)).all()
    finally:
        sess.close()


def _post(client, body: bytes, signature):
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Signature"] = signature
    return client.post(WEBHOOK_URL, content=body, headers=headers)


def _send(client, payload: dict, *, secret: str = SECRET, signature=None):
    """按 LS 的真实投递方式发送：签名针对即将发出的那一份字节。"""
    body = ls_payload.encode(payload)
    sig = ls_payload.sign(body, secret) if signature is None else signature
    return _post(client, body, sig)


# ── 一. 验签边界 ────────────────────────────────────────────────────────
def test_valid_delivery_returns_200_and_is_recorded(client, maker):
    res = _send(client, ls_payload.order_payload())
    assert res.status_code == 200, res.text
    assert res.json() == {"received": True, "duplicate": False}
    rows = _deliveries(maker)
    assert len(rows) == 1
    row = rows[0]
    assert row.ls_event_id == ls_payload.DELIVERY_ID
    assert row.event_name == "order_created"
    assert row.object_type == "orders"
    assert row.object_id == "9569465"
    assert row.test_mode is True
    assert row.created_at is not None and row.updated_at is not None


def test_single_byte_change_is_401(client, maker):
    payload = ls_payload.order_payload()
    body = ls_payload.encode(payload)
    sig = ls_payload.sign(body, SECRET)
    mid = len(body) // 2
    mutated = body[:mid] + bytes([body[mid] ^ 0x01]) + body[mid + 1:]
    assert _post(client, mutated, sig).status_code == 401
    assert _count(maker, LemonSqueezyWebhookDelivery) == 0     # 401 之前不得有任何写入


def test_reserialized_body_is_401(client, maker):
    """签名对应原字节；把同一份 JSON 换个字节表示再发 ⇒ 必须 401。

    这条是"验签基于 raw body"的可执行证明：任何在中间做 json.loads→dumps 的
    实现都会在这里变成"居然通过了"。
    """
    payload = ls_payload.order_payload()
    body = ls_payload.encode(payload)
    sig = ls_payload.sign(body, SECRET)
    reserialized = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    assert reserialized != body
    assert _post(client, reserialized, sig).status_code == 401
    assert _count(maker, LemonSqueezyWebhookDelivery) == 0


def test_signature_from_wrong_secret_is_401(client, maker):
    res = _send(client, ls_payload.order_payload(), secret=WRONG_SECRET)
    assert res.status_code == 401
    assert _count(maker, LemonSqueezyWebhookDelivery) == 0


def test_empty_signature_is_401(client, maker):
    assert _send(client, ls_payload.order_payload(), signature="").status_code == 401


def test_missing_signature_header_is_401(client, maker):
    body = ls_payload.encode(ls_payload.order_payload())
    assert _post(client, body, None).status_code == 401


def test_401_response_and_logs_leak_nothing(client, maker, caplog):
    body = ls_payload.encode(ls_payload.order_payload())
    with caplog.at_level(logging.DEBUG):
        res = _post(client, body, "a" * 64)
    assert res.status_code == 401
    text = res.text + caplog.text
    assert SECRET not in text
    assert "expected" not in text.lower()
    assert "hmac" not in text.lower()
    assert "ls.wh.probe@example.com" not in text          # 失败路径也不回显买家邮箱


def test_missing_secret_fails_closed_503(client, maker, monkeypatch):
    monkeypatch.delenv("LEMONSQUEEZY_WEBHOOK_SECRET", raising=False)
    assert _send(client, ls_payload.order_payload()).status_code == 503
    assert _count(maker, LemonSqueezyWebhookDelivery) == 0


# ── 二. 结构边界 ────────────────────────────────────────────────────────
def test_invalid_json_with_valid_signature_is_400(client, maker):
    body = b'{"meta": {"event_name": '
    res = _post(client, body, ls_payload.sign(body, SECRET))
    assert res.status_code == 400
    assert _count(maker, LemonSqueezyWebhookDelivery) == 0
    assert ls_payload.ORDER_UUID not in res.text          # 不回显 body 内容


@pytest.mark.parametrize("shape", [
    {"hello": "world"},                                  # 合法 JSON，不是 webhook
    {"meta": {"event_name": "order_created"}, "data": {"type": "orders", "id": "1"}},   # 缺 webhook_id
    {"meta": {"webhook_id": "x", "custom_data": {}}, "data": {"id": "1"}},              # 缺 event/type
    [1, 2, 3],                                           # 顶层不是对象
])
def test_valid_signature_but_bad_webhook_structure_is_400(client, maker, shape):
    res = _send(client, shape)
    assert res.status_code == 400
    assert _count(maker, LemonSqueezyWebhookDelivery) == 0
    for model in BUSINESS_MODELS:                        # 结构错误也不能产生业务记录
        assert _count(maker, model) == 0


def test_top_level_json_array_is_400(client, maker):
    body = b'[{"meta": {}}]'
    assert _post(client, body, ls_payload.sign(body, SECRET)).status_code == 400


# ── 三. 三类真实事件：只允许投递台账 ────────────────────────────────────
@pytest.mark.parametrize("factory", [
    ls_payload.order_payload, ls_payload.subscription_payload, ls_payload.invoice_payload,
])
def test_events_record_delivery_only(client, maker, factory):
    res = _send(client, factory())
    assert res.status_code == 200, res.text
    assert _count(maker, LemonSqueezyWebhookDelivery) == 1
    for model in BUSINESS_MODELS:
        assert _count(maker, model) == 0, f"{model.__tablename__} 在 P2-3 不该有行"


def test_order_event_creates_no_purchase_row(client, maker):
    assert _send(client, ls_payload.order_payload()).status_code == 200
    assert _count(maker, LemonSqueezyPurchase) == 0


def test_subscription_event_creates_no_membership_row(client, maker):
    assert _send(client, ls_payload.subscription_payload()).status_code == 200
    assert _count(maker, LemonSqueezyMembership) == 0


def test_invoice_event_creates_no_grant_row(client, maker):
    assert _send(client, ls_payload.invoice_payload()).status_code == 200
    assert _count(maker, LemonSqueezyMembershipGrant) == 0


# ── 四. 重复投递 ────────────────────────────────────────────────────────
def test_duplicate_delivery_is_absorbed_not_500(client, maker):
    payload = ls_payload.order_payload()
    first = _send(client, payload)
    second = _send(client, payload)
    assert first.status_code == 200 and first.json()["duplicate"] is False
    assert second.status_code == 200, "重投不能变 500，否则 LS 会一直重试"
    assert second.json()["duplicate"] is True
    assert _count(maker, LemonSqueezyWebhookDelivery) == 1     # 数据库 UNIQUE 挡住第二条
    for model in BUSINESS_MODELS:
        assert _count(maker, model) == 0


def test_different_delivery_ids_for_same_object_are_both_recorded(client, maker):
    """同一 order 的两个不同事件（如 order_created 与 order_refunded）各有投递行。"""
    assert _send(client, ls_payload.order_payload()).status_code == 200
    refunded = ls_payload.order_payload(event_name="order_refunded",
                                        webhook_id="a2d4e999-1111-2222-3333-444455556666")
    assert _send(client, refunded).status_code == 200
    assert _count(maker, LemonSqueezyWebhookDelivery) == 2


def test_ledger_failure_returns_500_for_retry(client, maker, monkeypatch):
    """台账写不进去时必须让 LS 重投，而不是假装处理成功。"""
    def _boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(db, "SessionLocal", _boom)
    assert _send(client, ls_payload.order_payload()).status_code == 500


# ── 五. test_mode 落库 ──────────────────────────────────────────────────
def test_test_mode_true_is_stored(client, maker):
    assert _send(client, ls_payload.order_payload(test_mode=True)).status_code == 200
    assert _deliveries(maker)[0].test_mode is True


def test_live_mode_false_is_stored(client, maker):
    assert _send(client, ls_payload.order_payload(test_mode=False,
                                                  webhook_id="a2d4e000-0000-0000-0000-000000000002"
                                                  )).status_code == 200
    assert _deliveries(maker)[0].test_mode is False


def test_test_mode_comes_from_payload_not_from_host_or_env(client, maker, monkeypatch):
    """test_mode 只能取 meta.test_mode：改 ENVIRONMENT / host 都不许影响它。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert _send(client, ls_payload.order_payload(test_mode=True)).status_code == 200
    assert _deliveries(maker)[0].test_mode is True


# ── 六. PII 与零发放的静态证据 ──────────────────────────────────────────
def test_full_payload_never_written_to_logs(client, caplog):
    with caplog.at_level(logging.DEBUG):
        assert _send(client, ls_payload.order_payload()).status_code == 200
        assert _send(client, ls_payload.subscription_payload()).status_code == 200
        assert _send(client, ls_payload.invoice_payload()).status_code == 200
    text = caplog.text
    assert "ls.wh.probe@example.com" not in text
    assert "LS WH Probe" not in text
    assert '"custom_data"' not in text
    assert "first_order_item" not in text


def test_no_logger_call_passes_the_raw_body_or_payload(client):
    """AST 级检查：任何 logger.*(...) 都不允许把 body/payload 变量当参数传进去。"""
    src = pathlib.Path(ls_router.__file__).read_text(encoding="utf-8")
    banned_names = {"raw_body", "payload", "body_text", "payload_text"}
    for node in ast.walk(ast.parse(src)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if not (isinstance(node.func.value, ast.Name) and node.func.value.id == "logger"):
            continue
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            names = {n.id for n in ast.walk(arg) if isinstance(n, ast.Name)}
            assert not (names & banned_names), f"日志可能泄漏原始 payload：line {node.lineno}"


def test_router_source_contains_no_fulfillment_calls():
    """P2-3 的"零发放"不能只靠行数断言 —— 源码里根本不许出现发放相关的名字。"""
    src = inspect.getsource(ls_router)
    for banned in ("add_credits", "credit_pack_service", "membership_service",
                   "credits_service", "CreditPackPurchase", "grant_pack_credits",
                   "grant_period_credits", "LemonSqueezyPurchase", "LemonSqueezyMembership",
                   "LemonSqueezyMembershipGrant", "lemonsqueezy_purchases",
                   "lemonsqueezy_memberships", "lemonsqueezy_membership_grants"):
        assert banned not in src, f"router 里出现了发放相关名字：{banned}"


def test_webhook_route_is_mounted_on_the_existing_router():
    """不新建第二个 router：路径复用既有 prefix，与 Paddle 回调同构。"""
    paths = {getattr(r, "path", "") for r in ls_router.router.routes}
    assert paths == {"/api/v1/credits/lemonsqueezy/status",
                     "/api/v1/credits/lemonsqueezy/checkout",
                     "/api/v1/credits/lemonsqueezy/webhook"}


def test_webhook_uses_the_ls_verifier_and_not_paddles():
    """两条独立证据：① router 不 import 任何 paddle 模块；② 处理函数只调
    `ls.verify_webhook_signature`，且不在 router 里重新实现 HMAC。
    """
    tree = ast.parse(pathlib.Path(ls_router.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not [m for m in imported if "paddle" in m.lower()], imported

    src = inspect.getsource(ls_router.lemonsqueezy_webhook)
    assert "ls.verify_webhook_signature" in src

    # 用 AST 取"纯代码"再查禁用机制：否则"文档里写了 nonce"也会被判失败，
    # 那种检查只会逼人把注释删掉，反而丢掉约束的说明。
    tree = ast.parse(textwrap.dedent(src))
    fn = tree.body[0]
    if fn.body and isinstance(fn.body[0], ast.Expr):
        fn.body = fn.body[1:]
    code_only = ast.unparse(fn)
    assert code_only.strip()
    assert "compare_digest" not in code_only and "sha256" not in code_only
    for banned in ("max_age", "tolerance", "nonce", "time()"):
        assert banned not in code_only
