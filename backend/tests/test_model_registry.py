"""Phase 2B 测试：天谱乐中国站多模型成本路由（model_registry + provider 集成 + fallback 白名单）。

任务第十九节清单 1-12（选择函数）+ 运行时模型选择 + non_retryable 链行为。
全部 mock，不打真实付费 API，不碰真实数据库。
"""

import asyncio

import pytest

from app.services import tempolor_provider
from app.services.model_registry import (
    MODELS,
    NoValidModelError,
    select_music_model,
)


# ── 选择函数：任务 §19 Tests 1-12 ─────────────────────────────

def test_1_vocal_250s_with_lyrics():
    sel = select_music_model("vocal", 250, lyrics_provided=True)
    assert sel.model.key == "tempolor-latest"
    assert sel.total_cost_cny == 0.30


def test_2_vocal_300s_with_lyrics():
    sel = select_music_model("vocal", 300, lyrics_provided=True)
    assert sel.model.key == "tempolor-latest"
    assert sel.total_cost_cny == 0.30


def test_3_vocal_300s_no_lyrics_includes_lyric_fee():
    """未提供歌词 → 平台自动写词，总成本 ¥0.30 + ¥0.07 = ¥0.37（按最终成本比较！）。"""
    sel = select_music_model("vocal", 300, lyrics_provided=False)
    assert sel.model.key == "tempolor-latest"
    assert sel.total_cost_cny == 0.37


def test_3b_vocal_270s_tempolor_latest():
    """第一版统一目标 270s：vocal 仍走唯一已确认 ID 的 tempolor-latest。"""
    sel = select_music_model("vocal", 270, lyrics_provided=True)
    assert sel.model.key == "tempolor-latest"
    assert sel.total_cost_cny == 0.30


def test_4_instrumental_120s_routed_to_mureka_instr():
    """第一版路线（2026-09-18 批准）：i3 enabled=False，120s 纯音乐也统一 mureka-v9-instr。"""
    sel = select_music_model("instrumental", 120, lyrics_provided=True)
    assert sel.model.key == "mureka-v9-instr"
    assert sel.total_cost_cny == 0.33


def test_5_instrumental_180s_routed_to_mureka_instr():
    """i4 enabled=False → 180s 不再选 i4（Phase 2B 旧规则已被第一版路线覆盖）。"""
    sel = select_music_model("instrumental", 180, lyrics_provided=True)
    assert sel.model.key == "mureka-v9-instr"
    assert sel.total_cost_cny == 0.33


def test_5b_disabled_models_never_selected_and_data_kept():
    """§六：禁用 = 不被选中，但注册数据必须保留（不得删除）。"""
    disabled = {"tempolor-i3", "tempolor-i4", "mureka-v9.5", "minimax-3.0"}
    for key in disabled:
        assert key in MODELS, f"{key} 数据被删除"
        assert MODELS[key].enabled is False, f"{key} 必须 enabled=False"
        assert MODELS[key].api_model_id is None  # 禁用模型也不得偷填猜测 ID
    # 任何可选组合的选择结果都不能落在禁用模型上
    for mt, dur in [("vocal", 120), ("vocal", 270), ("instrumental", 120),
                    ("instrumental", 200), ("instrumental", 270)]:
        assert select_music_model(mt, dur, True).model.key not in disabled


def test_6_instrumental_250s_mureka():
    """便宜但做不到的模型必须被淘汰（§11 核心原则）。"""
    sel = select_music_model("instrumental", 250, lyrics_provided=True)
    assert sel.model.key == "mureka-v9-instr"
    assert sel.total_cost_cny == 0.33


def test_7_instrumental_270s_mureka():
    sel = select_music_model("instrumental", 270, lyrics_provided=True)
    assert sel.model.key == "mureka-v9-instr"
    assert sel.total_cost_cny == 0.33


def test_8_instrumental_300s_no_valid_model():
    """>270s 纯音乐：中国站无 Extend 端点 → NO_VALID_MODEL，禁止选做不到的模型。"""
    with pytest.raises(NoValidModelError) as ei:
        select_music_model("instrumental", 300, lyrics_provided=True)
    assert ei.value.code == "NO_VALID_MODEL"


def test_8b_instrumental_300s_never_picks_i4_or_minimax():
    with pytest.raises(NoValidModelError):
        select_music_model("instrumental", 300, lyrics_provided=True)
    # MiniMax 3.0 纯音乐时长未确认 → 根本不注册为 instrumental 候选
    assert not any(
        s.instrumental and "minimax" in s.key for s in MODELS.values()
    )


def test_9_cover_tempolor_latest():
    sel = select_music_model("vocal", 180, lyrics_provided=True, operation="cover")
    assert sel.model.key == "tempolor-latest-cover"
    assert sel.total_cost_cny == 0.70


def test_9b_cover_instrumental_unsupported():
    with pytest.raises(NoValidModelError) as ei:
        select_music_model("instrumental", 120, lyrics_provided=True, operation="cover")
    assert ei.value.code == "UNSUPPORTED_CAPABILITY"


def test_10_stems_v2_4track():
    sel = select_music_model(stem_count=4, operation="stems")
    assert sel.model.key == "stems-v2"
    assert sel.total_cost_cny == 0.35


def test_11_stems_v3_8track():
    sel = select_music_model(stem_count=8, operation="stems")
    assert sel.model.key == "stems-v3"
    assert sel.total_cost_cny == 1.00


def test_12_midi():
    sel = select_music_model(operation="midi")
    assert sel.model.key == "midi-v1"
    assert sel.total_cost_cny == 2.00


def test_12b_lyrics_operation():
    sel = select_music_model(operation="lyrics")
    assert sel.model.key == "lyric-v1"
    assert sel.total_cost_cny == 0.07


def test_commercial_filter_conservative():
    """商用授权未书面确认前：commercial=True 一律 NO_VALID_MODEL（数据改后即放行）。"""
    with pytest.raises(NoValidModelError) as ei:
        select_music_model("vocal", 250, lyrics_provided=True, commercial=True)
    assert ei.value.code == "NO_VALID_MODEL"


def test_product_cap_270s_constants():
    """第一版产品硬上限 270s：ai_limits 默认值与 ai_music 实际引用值一致。"""
    import os
    from app.services import ai_limits
    from app.routers import ai_music
    assert os.getenv("MAX_AUDIO_DURATION_SECONDS") in (None, "", "270"), \
        "本机测试环境不应设置覆盖值（覆盖时此断言由部署方自行核对）"
    assert ai_limits.MAX_AUDIO_DURATION_SECONDS == 270
    assert ai_music.MAX_AUDIO_DURATION_SECONDS == 270


def test_vocal_330_only_enabled_mureka_v9_survives():
    """>300s 人声：tempolor-latest 被淘汰；V9.5/MiniMax 已禁用 → 只剩 mureka-v9。
    证明 enabled 过滤生效（若 V9.5/MiniMax 仍可选，最低成本也轮不到它们，此断言验证唯一性）。"""
    sel = select_music_model("vocal", 330, lyrics_provided=True)
    assert sel.model.key == "mureka-v9"
    assert sel.model.id_confirmed is False  # 选中但 ID 未确认 → Provider 层仍将零提交拒绝


def test_unconfirmed_ids_flagged():
    """矩阵纪律：除官方逐字示例 tempolor-latest 外，model ID 不得被凭空写死。"""
    for spec in MODELS.values():
        if not spec.id_confirmed:
            assert spec.api_model_id is None, f"{spec.key} 未确认却填了猜测 ID"


# ── Provider 运行时：模型真的按注册表落到出站 payload ──────────────

class _StopResp:
    status_code = 400
    text = "stop-after-capture"


class _CapturingClient:
    def __init__(self, sink: dict):
        self.sink = sink

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        self.sink.setdefault("posts", []).append(json)
        return _StopResp()


def _patch_http(monkeypatch, sink: dict):
    monkeypatch.setattr(tempolor_provider.httpx, "AsyncClient",
                        lambda *a, **k: _CapturingClient(sink))
    monkeypatch.setenv("TEMPOLOR_API_KEY", "test-key")
    monkeypatch.delenv("TEMPOLOR_MODEL", raising=False)
    # Phase 2D：provider 现在要求 callback 配置非空（测试占位域，非生产 URL）
    monkeypatch.setattr(tempolor_provider, "TEMPOLOR_CALLBACK_URL", "https://cb.invalid.test/x")


def test_provider_vocal_payload_uses_registry_model(monkeypatch):
    """人声 300s：出站 model=tempolor-latest（唯一已确认 ID；选择结果与其一致）。"""
    sink: dict = {}
    _patch_http(monkeypatch, sink)
    prov = tempolor_provider.TempolorProvider()
    asyncio.run(prov.generate({
        "prompt": "a pop song", "lyrics": "la la", "duration": 300,
        "is_instrumental": False,
    }))
    assert sink["posts"][0]["model"] == "tempolor-latest"
    assert "instrumental" not in sink["posts"][0]


def test_provider_instrumental_blocks_unconfirmed_id(monkeypatch):
    """纯音乐 120s 选中 i3，但其 API model ID 未联调确认 → 禁止提交、non_retryable、零 HTTP。"""
    sink: dict = {}
    _patch_http(monkeypatch, sink)
    prov = tempolor_provider.TempolorProvider()
    result = asyncio.run(prov.generate({
        "prompt": "piano", "lyrics": "", "duration": 120, "is_instrumental": True,
    }))
    assert result["success"] is False
    assert result.get("non_retryable") is True
    assert "UNCONFIRMED" in result["error"]
    assert "posts" not in sink  # 一次真实提交都没发生


def test_provider_instrumental_over_limit_no_http(monkeypatch):
    """纯音乐 300s：NO_VALID_MODEL 在选择层拦截，不发任何请求。"""
    sink: dict = {}
    _patch_http(monkeypatch, sink)
    prov = tempolor_provider.TempolorProvider()
    result = asyncio.run(prov.generate({
        "prompt": "epic orchestral", "lyrics": "", "duration": 300, "is_instrumental": True,
    }))
    assert result["success"] is False
    assert result.get("non_retryable") is True
    assert "NO_VALID_MODEL" in result["error"]
    assert "posts" not in sink


def test_provider_explicit_model_backcompat(monkeypatch):
    """上层显式传 model（运维手段）仍直通，不受注册表影响。"""
    sink: dict = {}
    _patch_http(monkeypatch, sink)
    prov = tempolor_provider.TempolorProvider()
    asyncio.run(prov.generate({
        "prompt": "x", "lyrics": "y", "duration": 60, "model": "tempolor-latest",
    }))
    assert sink["posts"][0]["model"] == "tempolor-latest"


# ── P3-13：production 选择底线（api_model_id 未确认的规格一律不可选）──────

def test_prod_instrumental_never_selects_unconfirmed_model(monkeypatch):
    """ENVIRONMENT=production：instrumental 不得返回 mureka-v9-instr（ID 未确认，提交不出去）。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(NoValidModelError) as ei:
        select_music_model("instrumental", 180, lyrics_provided=True)
    assert ei.value.code == "NO_VALID_MODEL"


def test_prod_vocal_still_selects_confirmed_tempolor_latest(monkeypatch):
    """正常人声路径不受影响：仍选中唯一已确认 ID 的 tempolor-latest，成本口径不变。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    sel = select_music_model("vocal", 180, lyrics_provided=True)
    assert sel.model.key == "tempolor-latest" and sel.model.id_confirmed
    assert sel.total_cost_cny == 0.30
    sel2 = select_music_model("vocal", 270, lyrics_provided=False)
    assert sel2.model.key == "tempolor-latest"
    assert sel2.total_cost_cny == 0.37


def test_prod_cover_still_selects_confirmed_model(monkeypatch):
    """Cover 同理：已确认 ID 的 tempolor-latest-cover 仍可被选中。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    sel = select_music_model("vocal", 180, lyrics_provided=True, operation="cover")
    assert sel.model.key == "tempolor-latest-cover"
    assert sel.model.id_confirmed and sel.model.api_model_id == "tempolor-latest"


def test_prod_never_returns_any_unconfirmed_model(monkeypatch):
    """穷举：production 下任何被返回的规格都必须已确认，且绝不能是 mureka-v9-instr。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    for music_type in ("vocal", "instrumental"):
        for dur in (60, 120, 180, 250, 270, 300):
            for op in ("song", "cover"):
                try:
                    sel = select_music_model(music_type, dur, lyrics_provided=True, operation=op)
                except NoValidModelError:
                    continue
                assert sel.model.id_confirmed and sel.model.api_model_id
                assert sel.model.key != "mureka-v9-instr"


def test_development_instrumental_selection_unchanged(monkeypatch):
    """第一版路线（2026-09-18 批准）只在非生产保留：开发/测试仍指向 mureka-v9-instr。"""
    monkeypatch.setenv("ENVIRONMENT", "development")
    sel = select_music_model("instrumental", 180, lyrics_provided=True)
    assert sel.model.key == "mureka-v9-instr"
