"""model_registry — 天谱乐中国站「Provider ≠ Model」数据驱动能力/定价矩阵。

事实来源：https://platform.tianpuyue.cn/docs/8859398m0.md（模型及定价，2026-08 版）
及 /open-apis/v1/song|stems|midi|lyrics 官方 OpenAPI 页。禁止使用海外站价格。

核心原则：
- TemPolor（天谱乐开放平台）是 Provider/聚合层，本表维护其下各 Model 的能力与价格。
- select_music_model() 是纯函数：先按需求过滤（operation/人声/时长/能力/商用），
  再按「最终总成本」取最低——不是单次价格最低，而是满足全部要求后的总成本最低。
- api_model_id 仅有官方文档逐字示例的 tempolor-latest 为已确认；其余模型 ID 字符串
  未经联调确认前一律 None + id_confirmed=False（禁止猜测拼写），由上层决定是否可用。
- 中国站无 Extend 端点（全 13 页文档核实）：target_duration 超过模型上限 = 无解，
  抛 NoValidModelError(NO_VALID_MODEL)，不做假续写、不做本地拼接。
- 商用授权：公开文档无逐字条款（仅 Cover 要求原曲授权），全部标记 unconfirmed；
  commercial=True 的请求当前会得到 NO_VALID_MODEL，待商务书面确认后改数据即可（零代码）。
- 第一版路线（2026-09-18 批准）：产品硬上限 270s（在 ai_limits.MAX_AUDIO_DURATION_SECONDS 钳制）；
  i3/i4 备用未启用、MiniMax 3.0 不接入（enabled=False，数据保留）；
  Mureka 全部条目已删除（2026-10-01 第一阶段重构，Mureka Provider 整体下线）——
  纯音乐生产路由 = Yinchao Provider（/api/v1/song/instrumental），不经本表选择。
  Yinchao Extend = NOT_CONFIRMED，禁止实现任何续写/拼接假说。
"""

from __future__ import annotations

import os

from dataclasses import dataclass
from typing import Optional

# 1 创作点 = ¥0.01（官方定价页 30 点 = 0.3 元 等值核验）
POINTS_TO_CNY = 0.01

# 未提供歌词时平台自动调用 Lyric v1 写词（官方注释逐字），产生额外费用
LYRIC_AUTO_FEE_CNY = 0.07


class NoValidModelError(Exception):
    """无任何模型满足全部需求。code ∈ {NO_VALID_MODEL, UNSUPPORTED_CAPABILITY}."""

    def __init__(self, code: str, reason: str):
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason


@dataclass(frozen=True)
class ModelSpec:
    key: str                    # 矩阵内唯一 id（产品语义，非 API 值）
    operation: str              # song / cover / stems / midi / lyrics
    api_model_id: Optional[str]     # 传给中国站 model 字段的值；None = UNCONFIRMED
    id_confirmed: bool          # api_model_id 是否已获官方文档示例/联调确认
    vocal: bool                 # 能否生成人声歌曲
    instrumental: bool          # 能否生成纯音乐
    max_duration_seconds: Optional[int]   # 单次生成上限（秒）；None = UNCONFIRMED（不设时长过滤）
    price_points: int           # 官方单价（创作点）
    notes: str = ""
    commercial_confirmed: bool = False    # 商用授权是否已获书面确认
    stem_count: Optional[int] = None      # stems 专用：4 / 8
    requires_reference_audio: bool = False  # cover 专用
    # 第一版路线（2026-09-18 指令）：enabled=False 的模型仅保留数据，不参与生产选择。
    # 禁止删除数据；重新启用 = 改回 True（i 系列/MiniMax/V9.5 等待产品再决策）。
    enabled: bool = True


def _cny(points: int) -> float:
    return round(points * POINTS_TO_CNY, 2)


# ── 中国站当前公开模型全集（定价逐字来自官方页）──────────────────────────
MODELS: dict[str, ModelSpec] = {
    # 音乐生成（人声）
    "tempolor-latest": ModelSpec(
        key="tempolor-latest", operation="song",
        api_model_id="tempolor-latest", id_confirmed=True,   # 官方文档示例逐字给出
        vocal=True, instrumental=False, max_duration_seconds=300,   # 5 分钟
        price_points=30, notes="旗舰；35+ 语言；流式",
    ),
    "minimax-3.0": ModelSpec(
        key="minimax-3.0", operation="song",
        api_model_id=None, id_confirmed=False,
        vocal=True, instrumental=False, max_duration_seconds=360,   # 6 分钟
        price_points=80, notes="API model ID 待联调确认",
        enabled=False,  # 第一版不接入（§四）
    ),
    # 纯音乐（官方口径：Tempolor i 系列专门用于纯音乐生成）
    "tempolor-i3": ModelSpec(
        key="tempolor-i3", operation="instrumental",
        api_model_id=None, id_confirmed=False,
        vocal=False, instrumental=True, max_duration_seconds=120,
        price_points=20, notes="生成 <3s；prompt 可精确控制时长；API model ID 待联调确认",
        enabled=False,  # 第一版备用：生产 selector 不得选中（§六）；数据保留
    ),
    "tempolor-i4": ModelSpec(
        key="tempolor-i4", operation="instrumental",
        api_model_id=None, id_confirmed=False,
        vocal=False, instrumental=True, max_duration_seconds=180,
        price_points=30, notes="旗舰纯音乐；API model ID 待联调确认",
        enabled=False,  # 第一版备用：生产 selector 不得选中（§六）；数据保留
    ),
    # 注意：Mureka 模型条目已删除（2026-10-01 第一阶段重构，Mureka Provider 整体下线）。
    # MiniMax 3.0 纯音乐最大时长官方未明示 → 不注册，禁止假设支持 300s。
    # P4-B2 Phase A-11：tempolor-latest-cover 条目已随 Cover/Remix 功能撤销移除
    # （2026-10-02 产品决策：Cover 输出无法稳定满足 ≥240s 交付门，11/11 样本实测）。
    # 音轨分离（POST /open-apis/v1/stems；url ≤50MB）
    "stems-v2": ModelSpec(
        key="stems-v2", operation="stems",
        api_model_id=None, id_confirmed=False,
        vocal=False, instrumental=False, max_duration_seconds=None,
        price_points=35, stem_count=4,
        notes="4 轨：人声/鼓/贝斯/其他；默认模型；请求 model 值字符串待联调确认",
    ),
    "stems-v3": ModelSpec(
        key="stems-v3", operation="stems",
        # A-17：官方 /stems 创建任务文档（464626891e0）body 仅 url+callback_url，
        # 无 model 字段；v3 的 model 字符串官方未给出 → MODEL_ID_UNVERIFIED，
        # 禁止写入猜测值。启用唯一通道：TEMPOLOR_STEMS_V3_MODEL_ID +
        # TEMPOLOR_STEMS_V3_ZIP_MEMBERS 双 env 官方确认后配置（见 tempolor_stems_service）。
        api_model_id=None, id_confirmed=False,
        vocal=False, instrumental=False, max_duration_seconds=None,
        price_points=100, stem_count=8,
        notes="MODEL_ID_UNVERIFIED：8 轨（人声/主唱/和声/吉他/钢琴/鼓/贝斯/其他乐器）；"
              "100 创作点；提交 fail-closed 门禁，未经官方确认不得上线",
    ),
    # 音乐转 MIDI（POST /open-apis/v1/midi；MP3/WAV/FLAC ≤50MB → midi.zip）
    "midi-v1": ModelSpec(
        key="midi-v1", operation="midi",
        api_model_id=None, id_confirmed=False,
        vocal=False, instrumental=False, max_duration_seconds=None,
        price_points=200, notes="输出完整 midi.zip；输入最大 50MB",
    ),
    # 歌词生成（POST /open-apis/v1/lyrics/generate）
    "lyric-v1": ModelSpec(
        key="lyric-v1", operation="lyrics",
        api_model_id=None, id_confirmed=False,
        vocal=False, instrumental=False, max_duration_seconds=None,
        price_points=7, notes="按次；歌曲生成未传歌词时平台自动调用本模型",
    ),
}


@dataclass(frozen=True)
class ModelSelection:
    model: ModelSpec
    total_cost_cny: float       # 最终总成本（含自动写词费）
    extend_required: bool       # 中国站无 extend 端点：恒 False（超过上限直接无解）
    provider: str = "tempolor"


def _matches_operation(spec: ModelSpec, operation: str, music_type: str) -> bool:
    if operation == "song":
        # 纯音乐模型登记在独立 operation="instrumental" 下（Tempolor i 系列专用）
        if music_type == "vocal":
            return spec.operation == "song" and spec.vocal
        return spec.operation == "instrumental" and spec.instrumental
    if operation == "cover":
        return spec.operation == "cover" and (music_type != "instrumental")
    return spec.operation == operation


def select_music_model(
    music_type: str = "vocal",
    target_duration: int = 180,
    lyrics_provided: bool = True,
    operation: str = "song",
    commercial: bool = False,
    stem_count: Optional[int] = None,
) -> ModelSelection:
    """按需求过滤后，选择「最终总成本最低」的合法模型。

    过滤顺序（任务第十节）：operation → vocal/instrumental → 时长 → 能力(stem_count)
    → 商用 → 总成本最低。中国站无 Extend：target 超上限即淘汰该模型，绝不选"便宜
    但做不到"的模型。音乐类型非法/组合不可能（如纯音乐 cover）抛 UNSUPPORTED_CAPABILITY。
    """
    music_type = (music_type or "vocal").lower()
    if music_type not in ("vocal", "instrumental"):
        raise NoValidModelError("UNSUPPORTED_CAPABILITY", f"music_type={music_type}")
    if operation == "cover" and music_type == "instrumental":
        raise NoValidModelError("UNSUPPORTED_CAPABILITY", "tempolor cover 不支持纯音乐")

    candidates = [s for s in MODELS.values() if s.enabled]
    candidates = [s for s in candidates if _matches_operation(s, operation, music_type)]

    # 生产底线：api_model_id 未经确认的规格一律不可选 —— Provider 本就有同款零 HTTP 拒绝，
    # 让 selector 提前拒绝，避免"选中一个提交不出去的目标"被上层误读成可用能力。
    if os.getenv("ENVIRONMENT", "development").lower() == "production":
        confirmed = [s for s in candidates if s.id_confirmed and s.api_model_id]
        if not confirmed:
            raise NoValidModelError(
                "NO_VALID_MODEL",
                f"production has no id-confirmed model: operation={operation} "
                f"type={music_type} duration={target_duration}",
            )
        candidates = confirmed

    # 时长过滤（无 extend 能力 → 单次上限必须 ≥ target；上限未确认的不用于硬性承诺）
    if operation in ("song", "cover"):
        if operation == "song":
            candidates = [
                s for s in candidates
                if s.max_duration_seconds is not None and s.max_duration_seconds >= target_duration
            ]

    # 能力过滤：stems 轨数
    if operation == "stems" and stem_count is not None:
        candidates = [s for s in candidates if s.stem_count == stem_count]

    # 商用过滤：仅放行已书面确认商用的模型（当前全部 unconfirmed → 商务确认后自动放行）
    if commercial:
        candidates = [s for s in candidates if s.commercial_confirmed]

    if not candidates:
        raise NoValidModelError(
            "NO_VALID_MODEL",
            f"operation={operation} type={music_type} duration={target_duration}s "
            f"stem_count={stem_count} commercial={commercial}",
        )

    def total_cost(s: ModelSpec) -> float:
        base = _cny(s.price_points)
        # 官方：人声歌未传歌词 → 平台自动调用 Lyric v1，额外计费（计入总成本比较！）
        if operation == "song" and music_type == "vocal" and not lyrics_provided:
            base += LYRIC_AUTO_FEE_CNY
        return round(base, 2)

    best = min(candidates, key=lambda s: (total_cost(s), -(s.max_duration_seconds or 0)))
    return ModelSelection(
        model=best,
        total_cost_cny=total_cost(best),
        extend_required=False,
    )
