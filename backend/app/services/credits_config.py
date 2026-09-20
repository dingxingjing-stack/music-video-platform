"""Credits 商业配置 —— 套餐定价 + 信用消耗规则，单一来源。

前端 Pricing 页读取 `GET /api/v1/credits/packages` 的返回（本文件是后端权威来源），
不在多个前端文件中重复书写价格。

信用消耗规则：`CREDIT_COSTS` 集中声明，当前仅 standard_song（一次完整音乐创作 = 30
Credits）已定价并生效，其余类型 credit_cost=0 表示未定价。修改扣费规则只改这里，
不动前端展示逻辑与路由代码。
"""

from __future__ import annotations

import os

# ── 免费赠送（注册后自动发放，总计 100）──
WELCOME_BONUS = 50
EMAIL_VERIFICATION_BONUS = 25
FIRST_SONG_BONUS = 25
FREE_TOTAL = WELCOME_BONUS + EMAIL_VERIFICATION_BONUS + FIRST_SONG_BONUS  # 100

# ── 付费套餐（价格/$，含 Credits）──
# 注意：购买当前未接入支付，POST /purchase 会返回 payment_not_configured，
#       这些价格仅作展示配置，不触发真实扣款。
PACKAGES = [
    {
        "id": "starter",
        "name": "Starter",
        "price_usd": 4.99,
        "credits": 300,
        "description_key": "pricing.starter_desc",   # i18n key
        "badge": None,
    },
    {
        "id": "basic",
        "name": "Basic",
        "price_usd": 7.99,
        "credits": 500,
        "description_key": "pricing.basic_desc",
        "badge": None,
    },
    {
        "id": "pro",
        "name": "Pro",
        "price_usd": 14.99,
        "credits": 1000,
        "description_key": "pricing.pro_desc",
        "badge": "best_value",
    },
    {
        "id": "creator",
        "name": "Creator",
        "price_usd": 34.99,
        "credits": 3000,
        "description_key": "pricing.creator_desc",
        "badge": "maximum_value",
    },
]

# ── 积分补充包（Credit Packs，2026-09-20 定稿）─────────────────────────
# 与上面的 PACKAGES / 会员订阅完全独立：一次性购买（Paddle one-time price），
# 不创建订阅、不改会员等级、不改到期时间、可无限次重复购买，Credits 只累加不覆盖。
#
# 安全约束：credits ↔ paddle_price_id 的映射只存在于后端（环境变量给 Price ID，
# 积分数量由本文件决定）。客户端永远不能声明"我买了 2800"。
# 未配置 Price ID 的包不会出现在 /packs 里 → 前端不渲染，避免假按钮。
# 包 ID 命名与前端 checkout 请求体一致：credits_200 / credits_500 / credits_1200 / credits_2800。
CREDIT_PACKS = [
    {"id": "credits_200", "credits": 200, "price_usd": 4.99, "price_env": "PADDLE_PRICE_ID_CREDITS_200"},
    {"id": "credits_500", "credits": 500, "price_usd": 9.99, "price_env": "PADDLE_PRICE_ID_CREDITS_500"},
    {"id": "credits_1200", "credits": 1200, "price_usd": 19.99, "price_env": "PADDLE_PRICE_ID_CREDITS_1200"},
    {"id": "credits_2800", "credits": 2800, "price_usd": 39.99, "price_env": "PADDLE_PRICE_ID_CREDITS_2800"},
]

CREDIT_PACK_CURRENCY = "USD"


def get_credit_packs() -> list[dict]:
    """已配置 Paddle Price ID 的一次性积分包（前端展示 + 后端下单共用同一来源）。"""
    out: list[dict] = []
    for pack in CREDIT_PACKS:
        price_id = (os.getenv(pack["price_env"]) or "").strip()
        if not price_id:
            continue
        out.append({
            "id": pack["id"],
            "credits": pack["credits"],
            "price_usd": pack["price_usd"],
            "price_cents": round(pack["price_usd"] * 100),
            "currency": CREDIT_PACK_CURRENCY,
            "paddle_price_id": price_id,
            "recurring": False,
        })
    return out


def resolve_pack_by_price_id(price_id: str | None) -> dict | None:
    """Paddle Price ID → 该发多少 Credits。webhook 唯一可信的换算入口。"""
    if not price_id:
        return None
    wanted = str(price_id).strip()
    for pack in CREDIT_PACKS:
        configured = (os.getenv(pack["price_env"]) or "").strip()
        if configured and configured == wanted:
            return {
                "id": pack["id"],
                "credits": pack["credits"],
                "price_usd": pack["price_usd"],
                "price_cents": round(pack["price_usd"] * 100),
                "currency": CREDIT_PACK_CURRENCY,
                "paddle_price_id": configured,
            }
    return None


def get_pack(pack_id: str) -> dict | None:
    """按包 ID 取已配置的包（下单入口用；未配置 Price ID 的包不可下单）。"""
    return next((p for p in get_credit_packs() if p["id"] == pack_id), None)


# ── 会员订阅（Paddle Recurring / Monthly，2026-09-18 定稿价格表）────────
# 数字与 frontend/PricingPage 的 PRICING_V1 一致，本轮未做任何修改。
# 与积分补充包完全独立：订阅只改会员等级/到期时间并按周期发放，
# 补充包只加积分、绝不写这张表里的任何东西。
MEMBERSHIP_PLANS = [
    {"id": "starter", "name": "Starter", "price_usd": 4.99,
     "credits_per_month": 200, "price_env": "PADDLE_PRICE_ID_STARTER"},
    {"id": "basic", "name": "Basic", "price_usd": 9.99,
     "credits_per_month": 500, "price_env": "PADDLE_PRICE_ID_BASIC"},
    {"id": "pro", "name": "Pro", "price_usd": 19.99,
     "credits_per_month": 1200, "price_env": "PADDLE_PRICE_ID_PRO"},
    {"id": "creator", "name": "Creator", "price_usd": 39.99,
     "credits_per_month": 2800, "price_env": "PADDLE_PRICE_ID_CREATOR"},
]

MEMBERSHIP_INTERVAL = "month"


def get_membership_plans() -> list[dict]:
    """已配置 Paddle Recurring Price ID 的会员计划（未配置的不返回，前端不出现假按钮）。"""
    out: list[dict] = []
    for plan in MEMBERSHIP_PLANS:
        price_id = (os.getenv(plan["price_env"]) or "").strip()
        if not price_id:
            continue
        out.append({
            "id": plan["id"],
            "name": plan["name"],
            "price_usd": plan["price_usd"],
            "price_cents": round(plan["price_usd"] * 100),
            "currency": CREDIT_PACK_CURRENCY,
            "credits_per_month": plan["credits_per_month"],
            "interval": MEMBERSHIP_INTERVAL,
            "recurring": True,
            "paddle_price_id": price_id,
        })
    return out


def get_membership_plan(plan_id: str) -> dict | None:
    return next((p for p in get_membership_plans() if p["id"] == plan_id), None)


def resolve_plan_by_price_id(price_id: str | None) -> dict | None:
    """订阅 Price ID → 会员计划（webhook 唯一可信的等级/发放依据）。"""
    if not price_id:
        return None
    wanted = str(price_id).strip()
    for plan in MEMBERSHIP_PLANS:
        configured = (os.getenv(plan["price_env"]) or "").strip()
        if configured and configured == wanted:
            return {
                "id": plan["id"],
                "name": plan["name"],
                "price_usd": plan["price_usd"],
                "price_cents": round(plan["price_usd"] * 100),
                "currency": CREDIT_PACK_CURRENCY,
                "credits_per_month": plan["credits_per_month"],
                "interval": MEMBERSHIP_INTERVAL,
                "recurring": True,
                "paddle_price_id": configured,
            }
    return None


# ── 信用消耗规则（按创作类型）──
# 每项：credit_cost（0 = 表示"未定价/Coming soon"，前端显示 Coming soon）
# standard_song = Pricing v1 唯一生效规则：一次完整音乐创作 30 Credits（与时长无关，≤270s）。
CREDIT_COSTS = {
    "standard_song":    {"credit_cost": 30, "enabled": True,  "description_key": "pricing.cost_standard_song"},
    "long_song":        {"credit_cost": 0, "enabled": True,  "description_key": "pricing.cost_long_song"},
    "instrumental":     {"credit_cost": 0, "enabled": True,  "description_key": "pricing.cost_instrumental"},
    "vocals":           {"credit_cost": 0, "enabled": True,  "description_key": "pricing.cost_vocals"},
    "stem_separation":  {"credit_cost": 0, "enabled": True,  "description_key": "pricing.cost_stems"},
    "midi":             {"credit_cost": 0, "enabled": True,  "description_key": "pricing.cost_midi"},
    "voice_clone":      {"credit_cost": 0, "enabled": False, "description_key": "pricing.cost_voice"},
}

# 允许的 transaction_type（账本语义）
TRANSACTION_TYPES = {
    "welcome_bonus",
    "email_verification_bonus",
    "first_song_bonus",
    "purchase",
    "subscription_grant",
    "generation",
    "refund",
    "referral_bonus",
    "admin_adjustment",
}


def get_credit_cost(creation_type: str, duration: int | None = None) -> int | None:
    """解析某创作类型的 Credit 消耗。

    - 返回 int（>0）：应扣这么多 Credit（当前仅 standard_song=30 生效）。
    - 返回 None：未定价（credit_cost=0 或类型未配置），调用方【禁止】扣费，
      走免费/未定价路径。

    时长分级：long_song 类在定价后，duration > 180 可触发更高档（预留逻辑，
    当前 credit_cost=0，不生效）。
    """
    entry = CREDIT_COSTS.get(creation_type)
    if not entry or not entry.get("enabled"):
        return None
    cost = entry.get("credit_cost")
    if not cost or cost <= 0:
        return None
    return int(cost)