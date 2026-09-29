"""上线前零成本体检（只读，不产生任何生成费用，不写数据库）。

跑法： python scripts/preflight_check.py

覆盖 7 组检查：环境变量、Provider 连通性、路由矩阵、回调签名、分享令牌、
生产库列、前端构建产物。任一项 FAIL 则退出码 1 —— 可以直接接进 CI。

设计原则：
- 连通性探针只查「不存在的任务」：能区分 401（密钥错）与 404（密钥对、任务不存在），
  且不会触发任何生歌计费。
- 生产库检查只在 DATABASE_URL 是 PostgreSQL 时执行；本地 sqlite 直接 SKIP，
  因为本地库结构与生产不等价，查了反而误导。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env")

PASS, FAIL, WARN, SKIP = "PASS", "FAIL", "WARN", "SKIP"
_RESULTS: list[tuple[str, str, str]] = []


def rec(name: str, status: str, detail: str = "") -> None:
    _RESULTS.append((name, status, detail))


def env(name: str) -> str:
    return (os.getenv(name) or "").strip()


# ── 1. 环境变量 ────────────────────────────────────────────────────────
# required = 缺了对应能力会 fail-closed（能察觉）；secret = 必须存在且不能进 git
REQUIRED = [
    "DATABASE_URL", "YINCHAO_API_KEY", "TEMPOLOR_API_KEY",
    "TEMPOLOR_CALLBACK_URL", "TEMPOLOR_CALLBACK_SECRET", "SHARE_LINK_SECRET",
]
OPTIONAL_BUT_EXPECTED = [
    "MUREKA_API_KEY", "PADDLE_API_KEY", "PADDLE_WEBHOOK_SECRET",
    "LEMONSQUEEZY_API_KEY", "LEMONSQUEEZY_WEBHOOK_SECRET", "ADMIN_API_TOKEN",
]


def check_env() -> None:
    missing = [k for k in REQUIRED if not env(k)]
    rec("env/required", FAIL if missing else PASS,
        f"缺 {missing}" if missing else f"{len(REQUIRED)} 项齐全")

    weak = [k for k in OPTIONAL_BUT_EXPECTED if not env(k)]
    if weak:
        rec("env/optional", WARN, f"未配置 {weak}（对应能力会 fail-closed）")
    else:
        rec("env/optional", PASS, "全部已配置")

    # Lemon Squeezy 的半配置状态最危险：能收钱但发不了货
    if env("LEMONSQUEEZY_API_KEY") and not env("LEMONSQUEEZY_WEBHOOK_SECRET"):
        rec("env/ls_half_configured", WARN,
            "LS 有 API key 但无 webhook secret —— 建单入口已 fail-closed，但不如直接补上")
    else:
        rec("env/ls_half_configured", PASS, "无半配置状态")

    ignored = os.popen(f"git -C {BACKEND.parent} check-ignore -v backend/.env").read().strip()
    rec("env/gitignored", PASS if ignored else FAIL,
        ".env 已被忽略" if ignored else ".env 未被 gitignore 忽略（有泄密风险）")


# ── 2. Provider 连通性（零费用，只查不存在的任务）────────────────────────
async def _probe_yinchao() -> tuple[str, str]:
    import httpx  # noqa: WPS433
    base = env("YINCHAO_API_BASE_URL") or "https://open.yinchaoyongxian.com"
    key = env("YINCHAO_API_KEY")
    if not key:
        return SKIP, "YINCHAO_API_KEY 未配置"
    headers = {"Authorization": f"Bearer {key}"}
    ghost = str(uuid.uuid4())
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(f"{base}/api/v1/task/query",
                            params={"task_id": ghost}, headers=headers)
            # 控制组：无效 key 应当 401，用来证明上面的 404 真的代表"鉴权通过"
            bad = await c.get(f"{base}/api/v1/task/query",
                              params={"task_id": ghost},
                              headers={"Authorization": "Bearer invalid_key_probe"})
    except Exception as exc:  # noqa: BLE001
        return FAIL, f"网络异常 {type(exc).__name__}: {exc}"
    if r.status_code == 404 and bad.status_code == 401:
        return PASS, "鉴权通过（404 任务不存在 vs 无效 key 401），零费用"
    if r.status_code == 401:
        return FAIL, "密钥被拒（401）—— key 无效或已过期"
    return WARN, f"无法判定：真实 key -> {r.status_code}，无效 key -> {bad.status_code}"


async def _probe_tempolor() -> tuple[str, str]:
    import httpx  # noqa: WPS433
    base = env("TEMPOLOR_BASE_URL") or "https://api.tianpuyue.cn"
    key = env("TEMPOLOR_API_KEY")
    if not key:
        return SKIP, "TEMPOLOR_API_KEY 未配置"
    headers = {"Authorization": key}
    ghost = str(uuid.uuid4())
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(f"{base}/open-apis/v1/song/query",
                             headers=headers, json={"item_ids": [ghost]})
            body = r.json() if r.content else {}
    except Exception as exc:  # noqa: BLE001
        return FAIL, f"网络异常 {type(exc).__name__}: {exc}"
    if r.status_code == 200 and str(body.get("status")) == "200000":
        return PASS, "鉴权通过（status 200000），零费用"
    return FAIL, f"HTTP {r.status_code} status={body.get('status')} msg={body.get('message')}"


async def check_providers() -> None:
    st, detail = await _probe_yinchao()
    rec("provider/yinchao", st, detail)
    st, detail = await _probe_tempolor()
    rec("provider/tempolor", st, detail)


# ── 3. 路由矩阵 ────────────────────────────────────────────────────────
def check_routing() -> None:
    try:
        from app.services.provider_registry import get_provider_registry
    except Exception as exc:  # noqa: BLE001
        rec("routing/matrix", FAIL, f"导入 provider_registry 失败: {exc}")
        return
    reg = get_provider_registry()
    # 期望：hi/id/ar 把 tempolor 提到链首；其它语言保持 yinchao 优先；instrumental 永不见 tempolor
    cases = [
        ("normal", "hi", "tempolor"), ("normal", "id", "tempolor"),
        ("normal", "ar", "tempolor"), ("normal", "en", "yinchao"),
        ("lyric_to_music", "hi", "tempolor"), ("lyric_to_music", "en", "yinchao"),
        ("reference", "ar", "tempolor"),
    ]
    bad = []
    for op, lang, want in cases:
        chain = reg.chain_for_operation(op, song_language=lang)
        got = [p.name for p in chain]
        if not got or got[0] != want:
            bad.append(f"{op}/{lang}: 期望链首 {want}，实际 {got}")
    for op in ("normal", "lyric_to_music", "instrumental", "reference"):
        chain = [p.name for p in reg.chain_for_operation(op, song_language="en")]
        if op == "instrumental" and "tempolor" in chain:
            bad.append(f"instrumental 链出现 tempolor（明令禁止）: {chain}")
    rec("routing/matrix", FAIL if bad else PASS,
        " | ".join(bad) if bad else "7 组语言分流 + instrumental 隔离均正确")


# ── 4. 回调签名自检 ────────────────────────────────────────────────────
def check_callback() -> None:
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.routers import ai_music
    except Exception as exc:  # noqa: BLE001
        rec("callback/signature", FAIL, f"导入失败: {exc}")
        return
    app = FastAPI()
    app.include_router(ai_music.router)
    c = TestClient(app)
    url = "/api/v1/ai/tempolor/callback"
    good = c.post(url + f"?token={env('TEMPOLOR_CALLBACK_SECRET')}", json={"songs": []}).status_code
    bad = c.post(url + "?token=wrong", json={"songs": []}).status_code
    none = c.post(url, json={"songs": []}).status_code
    saved = os.environ.pop("TEMPOLOR_CALLBACK_SECRET", None)
    unset = c.post(url + "?token=x", json={"songs": []}).status_code
    if saved is not None:
        os.environ["TEMPOLOR_CALLBACK_SECRET"] = saved
    ok = (good, bad, none, unset) == (200, 401, 401, 503)
    rec("callback/signature", PASS if ok else FAIL,
        f"正确={good} 错令牌={bad} 无令牌={none} 未配置={unset}（应为 200/401/401/503）")


# ── 5. 分享令牌 ────────────────────────────────────────────────────────
def check_share() -> None:
    try:
        from app.routers.share import make_token, parse_token
    except Exception as exc:  # noqa: BLE001
        rec("share/token", FAIL, f"导入失败: {exc}")
        return
    if not env("SHARE_LINK_SECRET"):
        rec("share/token", SKIP, "SHARE_LINK_SECRET 未配置，端点会 503")
        return
    tok = make_token("task-preflight-0001")
    got = parse_token(tok)
    tampered = parse_token(tok[:-1] + ("a" if tok[-1] != "a" else "b"))
    ok = got == "task-preflight-0001" and tampered is None
    rec("share/token", PASS if ok else FAIL,
        "签名可往返解析且篡改被拒" if ok else f"往返={got} 篡改后={tampered}")


# ── 6. 生产库列（仅 PostgreSQL）─────────────────────────────────────────
def check_db() -> None:
    url = env("DATABASE_URL")
    if not url.lower().startswith(("postgres://", "postgresql://")):
        rec("db/refund_columns", SKIP,
            f"本地库是 {url.split(':')[0]}，结构不等价，跳过（请在生产连接串下重跑）")
        return
    try:
        from sqlalchemy import create_engine, text
        eng = create_engine(url, pool_pre_ping=True)
        with eng.connect() as c:
            cols = {r[0] for r in c.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='ai_tasks'"))}
            idx = c.execute(text(
                "SELECT 1 FROM pg_indexes WHERE indexname='uq_credits_refund_once'")).fetchone()
        need = {"refunded_at", "generation_quota_weight"}
        missing = sorted(need - cols)
        rec("db/ai_tasks_columns", FAIL if missing else PASS,
            f"缺列 {missing}（跑 scripts/supabase_add_refund_idempotency.sql）" if missing
            else "refunded_at / generation_quota_weight 已存在")
        rec("db/refund_unique_index", PASS if idx else FAIL,
            "uq_credits_refund_once 已存在" if idx else "缺唯一索引，并发退款无硬兜底")
    except Exception as exc:  # noqa: BLE001
        rec("db/refund_columns", FAIL, f"查询失败: {type(exc).__name__}: {exc}")


# ── 7. 前端构建产物 ────────────────────────────────────────────────────
def check_frontend() -> None:
    dist = BACKEND.parent / "frontend" / "dist" / "assets" / "js"
    if not dist.is_dir():
        rec("frontend/build", WARN, "未找到 frontend/dist，先跑 npm run build")
        return
    names = {p.name for p in dist.glob("*.js")}
    missing = [l for l in ("hi", "id", "ar") if not any(n.startswith(l + "-") for n in names)]
    rec("frontend/build", FAIL if missing else PASS,
        f"缺语言分包 {missing}" if missing else "hi/id/ar 三个语言分包均已产出")


def main() -> int:
    check_env()
    asyncio.run(check_providers())
    check_routing()
    check_callback()
    check_share()
    check_db()
    check_frontend()

    print("\n上线前体检（零成本，不产生生歌费用）")
    print("=" * 78)
    width = max(len(n) for n, _, _ in _RESULTS)
    for name, status, detail in _RESULTS:
        print(f"  [{status}] {name:<{width}}  {detail}")
    print("=" * 78)
    counts = {s: sum(1 for _, st, _ in _RESULTS if st == s) for s in (PASS, FAIL, WARN, SKIP)}
    print("  " + "  ".join(f"{k}={v}" for k, v in counts.items()))
    return 1 if counts[FAIL] else 0


if __name__ == "__main__":
    sys.exit(main())
