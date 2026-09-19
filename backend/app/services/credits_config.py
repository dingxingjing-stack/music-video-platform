"""Credits 商业配置 —— 套餐定价 + 信用消耗规则，单一来源。

前端 Pricing 页读取 `GET /api/v1/credits/packages` 的返回（本文件是后端权威来源），
不在多个前端文件中重复书写价格。

信用消耗规则：`CREDIT_COSTS` 集中声明，当前仅 standard_song（一次完整音乐创作 = 30
Credits）已定价并生效，其余类型 credit_cost=0 表示未定价。修改扣费规则只改这里，
不动前端展示逻辑与路由代码。
"""

from __future__ import annotations

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