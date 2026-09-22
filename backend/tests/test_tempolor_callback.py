"""天谱乐（TemPolor）音乐生成回调端点回归测试。

覆盖：公网路径必须精确、恒返回纯文本 success、不可信输入（空/畸形/缺字段/超长/
控制字符）、绝不改 ai_tasks、绝不改 Credits、日志绝不出现任何 Secret。

全部使用临时 SQLite + 本地 FastAPI 实例：不发真实 TemPolor 请求、不产生任何第三方费用。
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.routers import ai_music
from app.services import ai_limits, credits_service, task_store

CALLBACK_PATH = "/api/v1/ai/tempolor/callback"
CB_LOGGER = "app.routers.ai_music.tempolor_callback"
USER = "tempolor-cb-user"

# 哨兵值：不是任何真实凭据，只用于证明这些字符串绝不会进日志
SENTINELS = {
    "TEMPOLOR_API_KEY": "SENTINEL-tempolor-api-key-never-log",
    "PADDLE_WEBHOOK_SECRET": "SENTINEL-paddle-webhook-never-log",
    "SUPABASE_SERVICE_ROLE_KEY": "SENTINEL-service-role-never-log",
    "CLOUDFLARE_R2_SECRET_KEY": "SENTINEL-r2-secret-never-log",
}

MP3_CB = {"songs": [{"item_id": "item-aaa", "status": "main_succeeded", "event": "mp3_complete"}]}
WAV_CB = {"songs": [{"item_id": "item-bbb", "status": "succeeded", "event": "wav_complete"}]}
LYRICS_CB = {"songs": [{"item_id": "item-aaa", "status": "succeeded", "event": "lrcsections_complete"}]}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = str(tmp_path / "tempolor_cb.db")
    monkeypatch.setattr(task_store, "_DB_PATH", db)
    monkeypatch.setattr(ai_limits, "_DB_PATH", db)
    eng = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})

    from app.db.database import Base

    Base.metadata.create_all(bind=eng)
    monkeypatch.setattr(credits_service, "SessionLocal", sessionmaker(bind=eng))
    credits_service.add_credits(USER, 1000, "admin_adjustment", description="grant")
    for key, value in SENTINELS.items():
        monkeypatch.setenv(key, value)
    return eng


@pytest.fixture()
def client(env):
    app = FastAPI()
    app.include_router(ai_music.router)
    return TestClient(app)


def _post(client, payload, **kw):
    if isinstance(payload, (bytes, bytearray)):
        return client.post(CALLBACK_PATH, content=payload, **kw)
    return client.post(CALLBACK_PATH, json=payload, **kw)


def _snapshot(eng, table):
    with eng.connect() as conn:
        rows = conn.execute(text(f"SELECT * FROM {table}")).mappings().all()
    return sorted(json.dumps(dict(r), sort_keys=True, default=str) for r in rows)


def _logged(caplog):
    return "\n".join(r.getMessage() for r in caplog.records if r.name == CB_LOGGER)


def _balance(user_id: str):
    """credits_service.get_balance 在 int/dict 两种形态间都出现过，与 p0 测试同法兼容。"""
    raw = credits_service.get_balance(user_id)
    return raw["balance"] if isinstance(raw, dict) else raw


def _assert_acked(resp):
    assert resp.status_code == 200, resp.text
    assert resp.text == "success"
    assert resp.headers["content-type"].startswith("text/plain")


# ── 路由必须精确落在公网路径上（防止被 nginx SPA 回退吞掉）──────────────
def test_route_registered_at_exact_public_path(client):
    paths = {r.path for r in client.app.routes}
    assert CALLBACK_PATH in paths
    # 这两个形态会被 nginx 的 SPA fallback 接管，绝不能成为实际路径
    assert "/tempolor/callback" not in paths
    assert "/callback" not in paths


# ── 正常回调：200 + 纯文本 success ────────────────────────────────────
def test_valid_callback_returns_plain_text_success(client):
    _assert_acked(_post(client, MP3_CB))


def test_callback_requires_no_auth(client):
    # 天谱乐不携带我们的 JWT；本端点只留痕、不改状态，故必须匿名可达
    resp = client.post(CALLBACK_PATH, json=MP3_CB)
    _assert_acked(resp)
    assert resp.status_code != 401


# ── 不可信输入：一律确认收到，不得 500 ────────────────────────────────
@pytest.mark.parametrize(
    "payload",
    [
        b"",                                   # 空 body
        b"   ",                                # 只有空白
        b"not json at all",                    # 非 JSON
        b"{",                                  # 截断 JSON
        b'{"songs": [',                        # 截断数组
        b"\xff\xfe\x00\x01binary",             # 非法 UTF-8
        b"[1,2,3]",                            # 顶层是数组
        b'"just a string"',                    # 顶层是字符串
        b"123",                                # 顶层是数字
        {"songs": None},                       # songs 为 null
        {"songs": "item-aaa"},                 # songs 为字符串
        {"songs": {}},                         # songs 为对象
        {"songs": []},                         # songs 为空数组
        {"songs": [None, 1, "x", []]},         # songs 元素类型杂乱
        {"songs": [{"status": "succeeded"}]},  # 缺 item_id
        {"songs": [{"item_id": ""}]},          # item_id 空串
        {"songs": [{"item_id": None}]},        # item_id null
        {"songs": [{"item_id": 12345}]},       # item_id 非字符串
        {},                                    # 完全空对象
    ],
)
def test_malformed_or_missing_fields_still_acked(client, payload):
    _assert_acked(_post(client, payload))


def test_multiple_songs_and_repeat_callbacks(client, caplog):
    caplog.set_level("INFO", logger=CB_LOGGER)
    for body in (MP3_CB, WAV_CB, LYRICS_CB, {"songs": [
        {"item_id": "item-ccc"}, {"item_id": "item-ddd"}, {"item_id": "item-eee"},
    ]}):
        _assert_acked(_post(client, body))
    text_logged = _logged(caplog)
    assert "3 个 item_id" in text_logged      # 一次收到 3 首
    assert "1 个 item_id" in text_logged      # 前三次各 1 首


def test_item_id_control_chars_stripped_and_truncated(client, caplog):
    forgery = "ok\x1b[31m\n2999-01-01 [ERROR] fake line\n"
    long_id = "L" * 500
    caplog.set_level("INFO", logger=CB_LOGGER)
    _assert_acked(_post(client, {"songs": [{"item_id": forgery}, {"item_id": long_id}]}))
    logged = _logged(caplog)
    assert "\n2999-01-01" not in logged, "控制字符必须被剥掉，不得伪造日志行"
    assert "\x1b" not in logged
    assert "L" * 65 not in logged, "超长 item_id 必须截断"
    assert "L" * 64 in logged


def test_oversized_body_skipped_but_acked(client, caplog):
    caplog.set_level("INFO", logger=CB_LOGGER)
    huge = b'{"songs":[{"item_id":"' + b"H" * (300 * 1024) + b'"}]}'
    _assert_acked(_post(client, huge))
    assert "过大" in _logged(caplog)


# ── 不得改 ai_tasks / Credits ────────────────────────────────────────
def test_callback_does_not_modify_ai_tasks(client, env, caplog):
    tid = task_store.new_task(user_key=USER)
    assert task_store.acquire_lock(USER, tid) is True
    with env.begin() as conn:
        conn.execute(text("UPDATE ai_tasks SET state='generating', progress=30 WHERE task_id=:t"),
                     {"t": tid})
    before_tasks = _snapshot(env, "ai_tasks")
    before_locks = _snapshot(env, "task_locks")

    caplog.set_level("INFO", logger=CB_LOGGER)
    # 官方一次生成回调 3 次；这里连发终态与非终态，观测本端点是否越权改状态
    for body in (MP3_CB, WAV_CB, LYRICS_CB,
                 {"songs": [{"item_id": tid, "status": "succeeded", "event": "wav_complete"}]}):
        _assert_acked(_post(client, body))
    # 即便回调里的 item_id 恰好等于本地 task_id，也不得被当作终态来源
    assert _snapshot(env, "ai_tasks") == before_tasks, "回调不得改 ai_tasks"
    assert _snapshot(env, "task_locks") == before_locks, "回调不得动任务锁"
    with env.connect() as conn:
        state = conn.execute(text("SELECT state FROM ai_tasks WHERE task_id=:t"),
                             {"t": tid}).scalar()
    assert state == "generating", "终态必须仍由轮询决定"


def test_callback_does_not_modify_credits(client, env):
    tid = task_store.new_task(user_key=USER)
    assert credits_service.reserve_generation_credits(USER, tid, 30)["success"] is True
    balance_before = _balance(USER)
    assert balance_before == 970, "前置：预留 30 后应为 970，否则本用例没有断到东西"
    tx_before = _snapshot(env, "credits_transactions")
    usage_before = _snapshot(env, "generation_usage")

    for body in (MP3_CB, WAV_CB, LYRICS_CB, b"garbage"):
        _assert_acked(_post(client, body))

    assert _balance(USER) == balance_before, "回调不得发放/扣除 Credits"
    assert _snapshot(env, "credits_transactions") == tx_before
    assert _snapshot(env, "generation_usage") == usage_before


# ── 日志不得出现任何 Secret ───────────────────────────────────────────
def test_logs_never_contain_secrets(client, caplog):
    caplog.set_level("DEBUG")
    _assert_acked(_post(client, MP3_CB))
    # 攻击者可控：把哨兵塞进非 item_id 字段，并伪装 Authorization 头
    _assert_acked(_post(
        client,
        {"songs": [{"item_id": "item-aaa", "audio_url": SENTINELS["TEMPOLOR_API_KEY"],
                    "authorization": SENTINELS["PADDLE_WEBHOOK_SECRET"],
                    "service_role": SENTINELS["SUPABASE_SERVICE_ROLE_KEY"]}],
         "api_key": SENTINELS["CLOUDFLARE_R2_SECRET_KEY"]},
        headers={"Authorization": "Bearer " + SENTINELS["TEMPOLOR_API_KEY"],
                 "X-Webhook-Signature": SENTINELS["PADDLE_WEBHOOK_SECRET"]},
    ))
    dumped = "\n".join(r.getMessage() for r in caplog.records)
    for name, value in SENTINELS.items():
        assert value not in dumped, f"{name} 泄漏进了日志"


def test_endpoint_module_has_no_database_or_credit_side_effects(client, env):
    """结构性兜底：处理回调路径上不允许出现任何 DB 写入依赖。"""
    src = __import__("inspect").getsource(ai_music.tempolor_callback)
    for forbidden in ("task_store.", "credits_service", "ai_limits", "SessionLocal",
                      "UPDATE ", "INSERT ", "DELETE ", "requests", "httpx"):
        assert forbidden not in src, f"回调实现不应引用 {forbidden}"
