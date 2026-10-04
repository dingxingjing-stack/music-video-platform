"""阶段 B 路由实现验证：功能分链 / fallback 协议 / 统一质量门 / 官方合同。

覆盖（23 项，全部本地桩，绝不真实调用任何 Provider API）：
1  三条操作链与生产路由表逐字一致（normal/lyric_to_music/instrumental；reference 已撤销）
2  非生歌 operation（lyric_gen/stems/midi/未知）一律 ValueError，绝不静默落 normal 链
3  路由按 operation 分发且单发（chain_for_operation 只调一次、provider 只调一次、收尾一次）
4  retryable 失败按 MAX_AUTO_RETRIES 打满后切链中下一家
5  non_retryable 不切链、不重试、不走 HF
6  Yinchao 缺 prompt → non_retryable，零提交
7-9 Yinchao Reference 契约测试已随功能撤销删除（Phase A-11）


10 Yinchao normal 提交合同（/api/v1/song/generate, model=v4.0, task_type=normal, 不带 lyric）
11 Yinchao lyric_to_music 提交合同（用户 lyric 原样透传）
12 Yinchao instrumental 提交合同（/api/v1/song/instrumental, 无 task_type）
15 质量门 <MIN=240 → failed + 恰好一次退款 + 无 R2 终对象
16 质量门测不到时长 → failed + 恰好一次退款 + 无 R2 终对象
17 质量门边界 240.0/240.5/300/600 → 放行且不截断（finalize 恰一次、零退款）
18 fallback 切换绝不二次 reserve 额度
19 recovery finalize_stale_task 幂等（CAS 未命中不再退款）
20 timeout 只失败当前任务：不建第二个付费任务、不二次 reserve
21 HF 兜底门：仅 normal/lyric_to_music 尝试，instrumental/reference 跳过
22 reference 路由把 reference_audio/similarity 原样交给 provider
23 链中 provider 未注册则跳过且保持顺序（instrumental 仅 yinchao，绝不落到 tempolor）
"""

import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers import ai_music
from app.services import ai_limits, credits_service, task_store
from app.services.provider_registry import PROVIDER_ENV, ProviderRegistry
from app.services.yinchao_provider import YinchaoProvider
from tests.test_ai_music_flow import isolated_db


# ─────────────────────────────────────────────────────────────────────────────
# 桩与工具
# ─────────────────────────────────────────────────────────────────────────────
class _Resp:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = str(self._json)
        self.content = b"{}" if self._json else b""

    def json(self):
        return self._json


def _install_http(monkeypatch, module, posts=None, gets=None):
    """把模块的 httpx.AsyncClient 换成记录型桩（post/get 按序消费响应，绝不外呼）。"""
    post_q = list(posts or [])
    get_q = list(gets or [])
    log = SimpleNamespace(posts=[], gets=[])

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kw):
            log.posts.append((url, kw))
            return post_q.pop(0) if post_q else _Resp()

        async def get(self, url, **kw):
            log.gets.append((url, kw))
            return get_q.pop(0) if get_q else _Resp()

    monkeypatch.setattr(module.httpx, "AsyncClient", lambda *a, **k: _Client())
    return log


def _forbid_http(monkeypatch, module):
    class _Boom:
        def __init__(self, *a, **k):
            raise AssertionError("测试内绝不允许建立 HTTP 连接")

    monkeypatch.setattr(module.httpx, "AsyncClient", _Boom)


def _capture_yinchao_submit(monkeypatch, result=None):
    calls = []

    async def _fake(self, api_key, payload, submit_url):
        calls.append({"api_key": api_key, "payload": dict(payload), "url": submit_url})
        return result or {"success": True, "volume_files": {"full_wav": "f.wav"},
                          "provider": self.name}

    monkeypatch.setattr(YinchaoProvider, "_submit_and_poll", _fake)
    return calls


def _capture_yinchao_upload(monkeypatch, upload_id="up-42", err=None):
    calls = []

    async def _fake(self, api_key, raw, ext, mime):
        calls.append({"raw": raw, "ext": ext, "mime": mime})
        return upload_id, err

    monkeypatch.setattr(YinchaoProvider, "_upload_reference_audio", _fake)
    return calls


class RecProvider:
    """记录型 provider：按序消费 results，耗尽后按 measured 产出可过门的成功结果。"""

    name = "rec"
    production = True
    provider_type = "api"
    capabilities = []
    max_duration = 0

    def __init__(self, name, results=None, measured=271.0):
        self.name = name
        self.gpu = "none"
        self.requests = []
        self._results = list(results or [])
        self._measured = measured

    async def generate(self, request: dict) -> dict:
        self.requests.append(dict(request))
        if self._results:
            return dict(self._results.pop(0))
        return {"success": True,
                "volume_files": {"full_wav": "x.wav", "_measured_duration_sec": self._measured},
                "provider": self.name}


@pytest.fixture()
def route(monkeypatch, tmp_path):
    """路由级 harness：store/Agnes/退款/收尾/HF 全桩，链由用例配置。"""
    store = MagicMock()
    monkeypatch.setattr(ai_music, "task_store", store)
    monkeypatch.delenv(PROVIDER_ENV, raising=False)
    monkeypatch.setenv("GENERATED_DIR", str(tmp_path))
    monkeypatch.setattr(
        ai_music.agnes_service, "generate_song",
        AsyncMock(return_value=SimpleNamespace(optimized_prompt="p", generated_lyrics="ly")),
    )
    monkeypatch.setattr(ai_music, "_log_generation_cost", MagicMock())
    monkeypatch.setattr(ai_music, "_upload_and_finalize", AsyncMock())
    monkeypatch.setattr(ai_music, "refund_generation", MagicMock(return_value={"refunded": True}))
    monkeypatch.setattr(
        ai_music.credits_service, "refund_generation_credits",
        MagicMock(return_value={"success": True}),
    )
    monkeypatch.setattr(ai_music, "_try_hf_ace_step_fallback", AsyncMock(return_value=None))
    reg = MagicMock()
    monkeypatch.setattr(ai_music, "get_provider_registry", lambda: reg)

    def set_chain(*providers, record_ops=None):
        if record_ops is None:
            reg.chain_for_operation.return_value = list(providers)
        else:
            def _side(effect_op, song_language=None):
                # song_language 由路由按请求传入（hi/id/ar 走天谱乐链首），
                # mock 必须接受该关键字，否则路由调用直接 TypeError。
                record_ops.append(effect_op)
                return list(providers)
            reg.chain_for_operation.side_effect = _side

    return SimpleNamespace(store=store, reg=reg, set_chain=set_chain,
                           finalize=ai_music._upload_and_finalize,
                           hf=ai_music._try_hf_ace_step_fallback,
                           refund=ai_music.refund_generation,
                           credits=ai_music.credits_service.refund_generation_credits)


def _req(**kw):
    kw.setdefault("prompt", "a song about the light")
    kw.setdefault("type", "song")
    return ai_music.GenerateRequest(**kw)


def _states(store):
    return [c.kwargs.get("state") for c in store.update.call_args_list]


# ─────────────────────────────────────────────────────────────────────────────
# 1) 四条操作链 == 生产路由表
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("operation,expected", [
    ("normal", ["yinchao", "tempolor"]),
    ("lyric_to_music", ["yinchao", "tempolor"]),
    ("instrumental", ["yinchao"]),
])
def test_operation_chains_match_route_table(operation, expected):
    reg = ProviderRegistry()
    for n in ("yinchao", "tempolor"):
        reg.register(RecProvider(n))
    chain = reg.chain_for_operation(operation)
    assert [p.name for p in chain] == expected
    if operation == "instrumental":
        assert "tempolor" not in [p.name for p in chain], "instrumental 链绝无 tempolor"


# ─────────────────────────────────────────────────────────────────────────────
# 2) 非生歌 operation 拒绝进链
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("operation", ["lyric_gen", "stems", "midi", "unknown", "", "reference"])
def test_non_generation_operations_rejected(operation):
    reg = ProviderRegistry()
    reg.register(RecProvider("yinchao"))
    with pytest.raises(ValueError, match="不进入生歌链"):
        reg.chain_for_operation(operation)


# ─────────────────────────────────────────────────────────────────────────────
# 3) 路由按 operation 分发 + 单发（无第二段、无重复收尾）
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("request_kwargs,expected_op", [
    ({}, "normal"),
    ({"lyrics": "la la la"}, "lyric_to_music"),
    ({"instrumental": True}, "instrumental"),
    # P4-B2 Phase A-11：reference 已下线，不再参数化
])
async def test_route_dispatches_operation_and_single_shot(route, request_kwargs, expected_op):
    rec = RecProvider("yinchao")
    ops = []
    route.set_chain(rec, record_ops=ops)

    await ai_music._run_generation("disp", _req(**request_kwargs), "uB", 2)

    assert ops == [expected_op], "chain_for_operation 恰好一次、operation 判定正确"
    assert len(rec.requests) == 1, "单次生成：provider 只调一次（无 continuation 第二段）"
    assert rec.requests[0]["operation"] == expected_op
    route.finalize.assert_awaited_once()
    route.refund.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 4) retryable 失败 → 打满重试后切下一家
# ─────────────────────────────────────────────────────────────────────────────
async def test_route_retryable_failover_switches_chain(route):
    a = RecProvider("yinchao", results=[
        {"success": False, "error": "transient 1"},
        {"success": False, "error": "transient 2"},
    ])
    b = RecProvider("tempolor")
    route.set_chain(a, b)

    await ai_music._run_generation("failover", _req(), "uB", 2)

    assert len(a.requests) == 2, "MAX_AUTO_RETRIES=1 → 链首恰 1+1 次"
    assert len(b.requests) == 1, "切换后下一家恰一次即成功"
    route.finalize.assert_awaited_once()
    route.refund.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 5) non_retryable → 不切链、不重试、不走 HF、按 validation_failed 退一次
# ─────────────────────────────────────────────────────────────────────────────
async def test_route_non_retryable_stops_chain_and_skips_hf(route):
    a = RecProvider("yinchao", results=[
        {"success": False, "non_retryable": True, "error": "Yinchao requires prompt"},
    ])
    b = RecProvider("tempolor")
    route.set_chain(a, b)

    await ai_music._run_generation("nonretry", _req(), "uB", 2)

    assert len(a.requests) == 1, "non_retryable 不重试"
    assert b.requests == [], "non_retryable 不切链"
    route.hf.assert_not_called()
    route.finalize.assert_not_called()
    assert "failed" in _states(route.store)
    assert any("Yinchao requires prompt" in str(c.kwargs.get("error"))
               for c in route.store.update.call_args_list)
    route.refund.assert_called_once()
    assert route.refund.call_args.kwargs["reason"] == "validation_failed"
    route.credits.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 6) Yinchao 缺 prompt → non_retryable，零提交
# ─────────────────────────────────────────────────────────────────────────────
async def test_yinchao_missing_prompt_non_retryable(monkeypatch):
    monkeypatch.setattr(YinchaoProvider, "_api_key", lambda self: "test-key")
    import app.services.yinchao_provider as ymod
    _forbid_http(monkeypatch, ymod)

    res = await YinchaoProvider().generate({"prompt": "   ", "operation": "normal"})

    assert res["success"] is False
    assert res.get("non_retryable") is True
    assert "prompt" in res["error"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# 7-9) Yinchao Reference 契约测试已随 Reference/Cover 功能撤销删除（Phase A-11）。
#    _generate_reference/_upload_reference_audio/_decode_reference_audio 已自 provider 移除。


# 10) Yinchao normal 提交合同
# ─────────────────────────────────────────────────────────────────────────────
async def test_yinchao_normal_payload_contract(monkeypatch):
    monkeypatch.setattr(YinchaoProvider, "_api_key", lambda self: "test-key")
    submits = _capture_yinchao_submit(monkeypatch)

    await YinchaoProvider().generate({
        "prompt": "p", "operation": "normal", "lyrics": "用户歌词不应进入 normal",
    })

    payload = submits[0]["payload"]
    assert submits[0]["url"].endswith("/api/v1/song/generate")
    assert payload == {"model": "v4.0", "task_type": "normal", "prompt": "p", "n": 1}, \
        "normal 由音潮自动写词，绝不携带 lyric 字段"


# ─────────────────────────────────────────────────────────────────────────────
# 11) Yinchao lyric_to_music 提交合同（用户 lyric 原样透传）
# ─────────────────────────────────────────────────────────────────────────────
async def test_yinchao_lyric_to_music_payload_contract(monkeypatch):
    monkeypatch.setattr(YinchaoProvider, "_api_key", lambda self: "test-key")
    submits = _capture_yinchao_submit(monkeypatch)

    await YinchaoProvider().generate({
        "prompt": "p", "operation": "lyric_to_music", "lyrics": "第一行\n第二行",
    })

    payload = submits[0]["payload"]
    assert submits[0]["url"].endswith("/api/v1/song/generate")
    assert payload["model"] == "v4.0"
    assert payload["task_type"] == "normal"
    assert payload["lyric"] == "第一行\n第二行"
    assert payload["n"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# 12) Yinchao instrumental 提交合同
# ─────────────────────────────────────────────────────────────────────────────
async def test_yinchao_instrumental_payload_contract(monkeypatch):
    monkeypatch.setattr(YinchaoProvider, "_api_key", lambda self: "test-key")
    submits = _capture_yinchao_submit(monkeypatch)

    await YinchaoProvider().generate({
        "prompt": "soft piano", "operation": "instrumental", "lyrics": "不应出现",
    })

    payload = submits[0]["payload"]
    assert submits[0]["url"].endswith("/api/v1/song/instrumental")
    assert payload == {"model": "v4.0", "prompt": "soft piano", "n": 1}, \
        "instrumental 端点无 task_type、无 lyric"


# ─────────────────────────────────────────────────────────────────────────────
# 15) 质量门 <MIN=240 → failed + 恰好一次退款 + 无 R2 终对象
# ─────────────────────────────────────────────────────────────────────────────
async def test_gate_below_min_fails_without_r2_and_single_refund(route):
    rec = RecProvider("yinchao", measured=239.9)
    route.set_chain(rec)

    await ai_music._run_generation("gatefail", _req(), "uB", 2)

    route.finalize.assert_not_called(), "门失败绝不能产生 R2 终对象"
    assert "failed" in _states(route.store)
    assert "uploading" not in _states(route.store), "门必须在 uploading/R2 之前"
    route.refund.assert_called_once()
    assert route.refund.call_args.kwargs["reason"] == "provider_failed"
    assert route.refund.call_args.kwargs["weight"] == 2, "按 reserve 时透传的权重退，不重算"
    route.credits.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 16) 质量门测不到时长 → failed + 恰好一次退款 + 无 R2 终对象
# ─────────────────────────────────────────────────────────────────────────────
async def test_gate_unmeasurable_fails_without_r2(route):
    rec = RecProvider("yinchao")
    rec._results = [{"success": True,
                     "volume_files": {"full_wav": "ghost.wav"},
                     "provider": "yinchao"}]
    route.set_chain(rec)

    await ai_music._run_generation("gateunmeasured", _req(), "uB", 2)

    route.finalize.assert_not_called()
    assert "failed" in _states(route.store)
    route.refund.assert_called_once()
    route.credits.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 17) 质量门边界放行：240.0 / 240.5 / 300 / 600 均不截断
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("measured", [240.0, 240.5, 300, 600])
async def test_gate_boundaries_pass_to_finalize(route, measured):
    rec = RecProvider("yinchao", measured=measured)
    route.set_chain(rec)

    await ai_music._run_generation(f"gate{int(measured)}", _req(), "uB", 2)

    route.finalize.assert_awaited_once()
    passed = route.finalize.await_args.args[1]
    assert passed["_measured_duration_sec"] == measured, "放行绝不截断/改写时长"
    route.refund.assert_not_called()
    assert "uploading" in _states(route.store)


# ─────────────────────────────────────────────────────────────────────────────
# 18) fallback 切换绝不二次 reserve 额度
# ─────────────────────────────────────────────────────────────────────────────
async def test_fallback_never_second_reserve(route, monkeypatch):
    reserve = MagicMock()
    monkeypatch.setattr(ai_limits, "reserve_generation", reserve)
    a = RecProvider("yinchao", results=[{"success": False, "error": "transient"}])
    b = RecProvider("tempolor")
    route.set_chain(a, b)

    await ai_music._run_generation("noreserve", _req(), "uB", 2)

    reserve.assert_not_called(), "路由/切换阶段绝不二次占用额度"
    route.finalize.assert_awaited_once()


# ─────────────────────────────────────────────────────────────────────────────
# 19) recovery finalize_stale_task 幂等（CAS 未命中不再退款）
# ─────────────────────────────────────────────────────────────────────────────
def test_recovery_finalize_idempotent(isolated_db, monkeypatch):
    from app.services import task_recovery

    quota_spy = MagicMock()
    credits_spy = MagicMock()
    monkeypatch.setattr(ai_limits, "refund_generation", quota_spy)
    monkeypatch.setattr(credits_service, "refund_generation_credits", credits_spy)

    tid = task_store.new_task(user_key="uR", task_id="rec-t1",
                              generation_quota_weight=2)
    task_store.update(tid, state="generating")

    first = task_recovery.finalize_stale_task(tid, reason="测试中断")
    second = task_recovery.finalize_stale_task(tid, reason="测试中断")

    assert first["finalized"] is True and first["refunded"] is True
    assert second["finalized"] is False and second["refunded"] is False, \
        "第二次 CAS 未命中 → 绝不重复退款"
    quota_spy.assert_called_once()
    credits_spy.assert_called_once()
    assert quota_spy.call_args.kwargs.get("reason") == "provider_failed"
    assert quota_spy.call_args.kwargs.get("weight") == 2, "按建任务时持久化的权重退"
    assert task_store.get(tid)["state"] == "failed"


# ─────────────────────────────────────────────────────────────────────────────
# 20) timeout 只失败当前任务：不建第二个付费任务、不二次 reserve
# ─────────────────────────────────────────────────────────────────────────────
async def test_timeout_creates_no_second_paid_task(monkeypatch):
    store = MagicMock()
    monkeypatch.setattr(ai_music, "task_store", store)
    reserve = MagicMock()
    monkeypatch.setattr(ai_limits, "reserve_generation", reserve)
    refund = MagicMock(return_value={"refunded": True})
    monkeypatch.setattr(ai_music, "refund_generation", refund)
    credits_refund = MagicMock(return_value={"success": True})
    monkeypatch.setattr(ai_music.credits_service, "refund_generation_credits", credits_refund)

    async def _slow(*a, **k):
        await asyncio.sleep(10)

    monkeypatch.setattr(ai_music, "_run_generation", _slow)
    monkeypatch.setattr(ai_music, "MAX_TASK_RUNTIME_SECONDS", 0.05)

    await ai_music._run_with_timeout("tmo-1", _req(), "uT", 2)

    store.new_task.assert_not_called(), "timeout 绝不创建第二个付费任务"
    reserve.assert_not_called()
    refund.assert_called_once()
    assert refund.call_args.kwargs["reason"] == "timeout_unknown"
    credits_refund.assert_called_once()
    store.release_lock_for_task.assert_called_once_with("tmo-1")


# ─────────────────────────────────────────────────────────────────────────────
# 21) HF 兜底门：仅 normal/lyric_to_music 尝试
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("operation,request_kwargs,expect_hf", [
    ("normal", {}, True),
    ("lyric_to_music", {"lyrics": "la"}, True),
    ("instrumental", {"instrumental": True}, False),
    # P4-B2 Phase A-11：reference 已下线，不再参数化
])
async def test_hf_fallback_gate_by_operation(route, operation, request_kwargs, expect_hf):
    # 1+MAX_AUTO_RETRIES=2 次尝试全部失败，链才可能走尽进入 HF 门
    route.set_chain(RecProvider("yinchao", results=[
        {"success": False, "error": "down"},
        {"success": False, "error": "down"},
    ]))

    await ai_music._run_generation(f"hf-{operation}", _req(**request_kwargs), "uB", 2)

    if expect_hf:
        route.hf.assert_awaited_once()
    else:
        route.hf.assert_not_called()
    route.refund.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 22) reference 路由测试已随 Reference/Cover 功能撤销删除（Phase A-11）。


# 23) 链中 provider 未注册则跳过且保持顺序（instrumental 仅 yinchao，绝无 tempolor）
# ─────────────────────────────────────────────────────────────────────────────
def test_chain_skips_unregistered_and_never_injects_tempolor():
    reg = ProviderRegistry()
    reg.register(RecProvider("yinchao"))
    reg.register(RecProvider("tempolor"))

    chain = reg.chain_for_operation("instrumental")

    assert [p.name for p in chain] == ["yinchao"], \
        "instrumental 链仅 yinchao 单家，绝不用 tempolor 顶替"
