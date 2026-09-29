"""P2-1：Lemon Squeezy webhook 验签与 payload 解析的单元测试。

锁住两类风险，缺一不可：

A. 验签纪律（钱进来之前的第一道门）
   1 正确原始字节 + 正确 secret → PASS
   2 改动 1 个字节 → FAIL
   3 JSON 重新序列化（键序/空白变了）→ FAIL   ← 证明必须用 raw body，不能 request.json() 后再 dumps
   4 错误 secret → FAIL
   5 空 signature → FAIL
   6 None signature → FAIL
   7 畸形 signature → FAIL，且不外泄期望值/secret

B. 解析纪律（实测形状，禁止臆造字段）
   8-15 meta.webhook_id / meta.custom_data.user_id / meta.test_mode / data.type /
        data.id / order 的 first_order_item / invoice 的 subscription_id / billing_reason
   16   残缺与损坏 payload 一律不抛异常
   17   item_id_for_variant() 反向查询
   另加：invoice 上 product_id/variant_id/order_id 必须为空（实测不存在），
        以及 LsEvent 不得提供 interval 字段（实测不存在 ⇒ 只能由服务端配置决定）。
"""

from __future__ import annotations

import json

import pytest

from app.services import lemon_squeezy_service as ls
from tests import ls_payload

SECRET = "ls_test_webhook_secret_0123456789abcdefghij"      # 40 字符内，合成值
OTHER_SECRET = "ls_test_wrong_secret_0123456789abcdefghij"


@pytest.fixture(autouse=True)
def webhook_secret(monkeypatch):
    monkeypatch.setenv("LEMONSQUEEZY_WEBHOOK_SECRET", SECRET)


def _signed(payload: dict) -> tuple[bytes, str]:
    body = ls_payload.encode(payload)
    return body, ls_payload.sign(body, SECRET)


# ── A. 验签 ─────────────────────────────────────────────────────────────
def test_valid_raw_body_and_secret_pass():
    body, sig = _signed(ls_payload.order_payload())
    assert ls.verify_webhook_signature(body, sig) is True


def test_single_byte_change_fails():
    body, sig = _signed(ls_payload.order_payload())
    mid = len(body) // 2
    mutated = body[:mid] + bytes([body[mid] ^ 0x01]) + body[mid + 1:]
    assert mutated != body
    assert ls.verify_webhook_signature(mutated, sig) is False


def test_reserialized_body_fails():
    """把收到的字节解析再序列化，得到的就不是被签名的那份字节 ⇒ 必须失败。

    这条是"绝不能用 request.json() 后重排"的可执行证明。
    """
    body, sig = _signed(ls_payload.order_payload())
    reserialized = json.dumps(json.loads(body), indent=2, sort_keys=True).encode("utf-8")
    assert reserialized != body
    assert ls.verify_webhook_signature(reserialized, sig) is False


def test_wrong_secret_fails(monkeypatch):
    body, _ = _signed(ls_payload.order_payload())
    sig = ls_payload.sign(body, OTHER_SECRET)
    assert ls.verify_webhook_signature(body, sig) is False


def test_empty_signature_fails():
    body, _ = _signed(ls_payload.order_payload())
    assert ls.verify_webhook_signature(body, "") is False


def test_none_signature_fails():
    body, _ = _signed(ls_payload.order_payload())
    assert ls.verify_webhook_signature(body, None) is False


@pytest.mark.parametrize("bad", [
    "deadbeef",                                    # 太短
    "z" * 64,                                      # 非 hex
    "ts=1700000000,h1=" + "a" * 64,                # Paddle 风格头，LS 绝不接受
    "sha256=" + "a" * 64,
    "a" * 63, "a" * 65,
    " " * 64,
])
def test_malformed_signature_fails_without_leaking(bad, caplog):
    body, _ = _signed(ls_payload.order_payload())
    with caplog.at_level("INFO"):
        assert ls.verify_webhook_signature(body, bad) is False
    logged = caplog.text
    assert SECRET not in logged
    assert "a" * 64 not in logged                 # 不回显收到的签名值


def test_missing_secret_fails_closed(monkeypatch):
    monkeypatch.delenv("LEMONSQUEEZY_WEBHOOK_SECRET", raising=False)
    body = ls_payload.encode(ls_payload.order_payload())
    assert ls.verify_webhook_signature(body, ls_payload.sign(body, SECRET)) is False


def test_uppercase_hex_signature_still_passes():
    """十六进制大小写不敏感：放宽形状判断不会让没有 secret 的人蒙对。"""
    body, sig = _signed(ls_payload.order_payload())
    assert ls.verify_webhook_signature(body, sig.upper()) is True


def test_no_paddle_style_mechanics_in_ls_verifier():
    """LS 没有时间戳/nonce/容差 —— 验签函数体里出现这些就说明照抄了 Paddle。

    用 ast 反解析取"纯代码文本"，这样注释与文档里的字样不会误伤，也不会让
    "把 banned 词写进注释"变成一种绕过检查的写法。
    """
    import ast
    import inspect
    import textwrap

    fn = ls.verify_webhook_signature
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    node = tree.body[0]
    if node.body and isinstance(node.body[0], ast.Expr):
        node.body = node.body[1:]              # 去掉 docstring
    code_only = ast.unparse(node)

    assert code_only.strip()
    for banned in ("ts:", "nonce", "max_age", "tolerance", "time()", "h1="):
        assert banned not in code_only
    assert not any(n in fn.__code__.co_names for n in ("time", "datetime", "_parse_signature_header"))


# ── B. 解析：meta 与身份链 ───────────────────────────────────────────────
def test_parser_reads_meta_webhook_id():
    ev = ls.parse_webhook_event(ls_payload.order_payload())
    assert ev.delivery_id == ls_payload.DELIVERY_ID


def test_parser_reads_custom_data_user_id():
    ev = ls.parse_webhook_event(ls_payload.order_payload())
    assert ev.user_id == "2091d35f-4a21-4257-9d8a-67546f988dc0"
    assert isinstance(ev.user_id, str)
    assert ev.kind == "credit_pack"


def test_parser_reads_test_mode():
    assert ls.parse_webhook_event(ls_payload.order_payload()).test_mode is True
    assert ls.parse_webhook_event(
        ls_payload.order_payload(test_mode=False)).test_mode is False


def test_parser_reads_object_type_and_id():
    order = ls.parse_webhook_event(ls_payload.order_payload())
    assert (order.object_type, order.object_id) == ("orders", "9569465")
    sub = ls.parse_webhook_event(ls_payload.subscription_payload())
    assert (sub.object_type, sub.object_id) == ("subscriptions", "2556628")
    inv = ls.parse_webhook_event(ls_payload.invoice_payload())
    assert (inv.object_type, inv.object_id) == ("subscription-invoices", "8554443")


def test_parser_reads_flat_first_order_item():
    """实测 order 没有 order_items / order_item_ids，只有扁平的 first_order_item。"""
    ev = ls.parse_webhook_event(ls_payload.order_payload())
    assert ev.order_item is not None
    assert ev.order_item.variant_id == "2167238"
    assert ev.order_item.product_id == "1387476"
    assert ev.order_item.price_id == "3637193"
    assert ev.order_item.price_cents == 499
    assert ev.order_item.quantity == 1
    assert ev.variant_id == "2167238"          # 提升到事件级，供下游直接用
    assert ev.product_id == "1387476"
    assert ev.order_id == "9569465"
    assert ev.subscription_id == ""            # order 上没有 subscription 字段
    assert ev.invoice_id == ""


def test_parser_reads_invoice_subscription_id_and_billing_reason():
    ev = ls.parse_webhook_event(ls_payload.invoice_payload())
    assert ev.subscription_id == "2556628"
    assert ev.invoice_id == "8554443"
    assert ev.billing_reason == "initial"
    assert ev.total_cents == 499
    assert ev.currency == "USD"
    assert ev.status == "paid"


def test_parser_does_not_invent_invoice_fields():
    """实测 invoice 里没有 product_id / variant_id / order_id / quantity ⇒ 必须为空。"""
    ev = ls.parse_webhook_event(ls_payload.invoice_payload())
    assert ev.product_id == ""
    assert ev.variant_id == ""
    assert ev.price_id == ""
    assert ev.order_id == ""
    assert ev.quantity is None


def test_parser_does_not_guess_billing_interval():
    """实测 subscription 与 invoice 都没有 interval ⇒ 结构里就不该有这个字段。"""
    assert not hasattr(ls.LsEvent, "interval")
    assert not hasattr(ls.parse_webhook_event(ls_payload.subscription_payload()), "interval")


def test_parser_reads_subscription_identity_chain():
    ev = ls.parse_webhook_event(ls_payload.subscription_payload())
    assert ev.subscription_id == "2556628"
    assert ev.order_id == "9569523"
    assert ev.order_item_id == "9493618"
    assert ev.variant_id == "2167193"
    assert ev.product_id == "1387446"
    assert ev.price_id == "3637141"            # 来自 first_subscription_item
    assert ev.quantity == 1
    assert ev.status == "active"
    assert ev.renews_at == "2026-10-25T15:56:05.000000Z"


def test_recovered_event_shares_the_invoice_id():
    """实测：payment_success 与 payment_recovered 指向同一个 invoice id
    ⇒ data.id 不能单独当幂等键（P2-6 用 (subscription_id, invoice_id)）。"""
    success = ls.parse_webhook_event(ls_payload.invoice_payload())
    recovered = ls.parse_webhook_event(
        ls_payload.invoice_payload(event_name="subscription_payment_recovered",
                                   webhook_id="a2d4e261-4762-42b2-aa22-8f79eb8633ac"))
    assert success.invoice_id == recovered.invoice_id
    assert success.event_name != recovered.event_name
    assert success.delivery_id != recovered.delivery_id


@pytest.mark.parametrize("junk", [
    None, [], "", 0, "text", {}, {"meta": None}, {"meta": "x"}, {"data": []},
    {"meta": {"event_name": "order_created"}, "data": {"attributes": None}},
    {"meta": {}, "data": {"type": "orders", "id": "1", "attributes": {"total": "abc"}}},
])
def test_parser_never_raises_on_broken_payload(junk):
    ev = ls.parse_webhook_event(junk)
    assert ev.delivery_id == ""                # 调用方据此"只 ack 不处理"
    assert ev.user_id == ""
    assert ev.test_mode is False


# ── C. Variant 反查 ─────────────────────────────────────────────────────
def test_item_id_for_variant_round_trips(monkeypatch):
    for item_id, env in ls.VARIANT_ENV.items():
        monkeypatch.setenv(env, f"variant_{item_id}")
    assert ls.item_id_for_variant("variant_starter") == "starter"
    assert ls.item_id_for_variant("variant_credits_2800") == "credits_2800"


def test_item_id_for_variant_uses_real_configuration(monkeypatch):
    """不依赖测试自己造的映射：拿 Phase 1 的真实 env 名验证反查方向。"""
    monkeypatch.setenv("LEMONSQUEEZY_VARIANT_ID_CREDITS_200", "2167238")
    assert ls.item_id_for_variant("2167238") == "credits_200"


def test_item_id_for_variant_rejects_unknown_and_blank(monkeypatch):
    monkeypatch.setenv("LEMONSQUEEZY_VARIANT_ID_STARTER", "2167193")
    assert ls.item_id_for_variant("9999999") is None
    assert ls.item_id_for_variant("") is None
    assert ls.item_id_for_variant(None) is None


def test_item_id_for_variant_returns_no_price_truth():
    """反查只给条目 id，绝不返回价格/积分 —— 真值唯一来源仍是 credits_config。"""
    out = ls.item_id_for_variant(ls_payload.PLAN_VARIANT_ID)
    assert out in (None, "starter")
