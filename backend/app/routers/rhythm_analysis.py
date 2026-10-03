"""
节拍检测与分析 API —— 已退役（A-20，2026-10-03 裁定：方案 A）

历史：本模块的 /detect、/rhythm-grid、/tempo-curve 曾实现「服务端下载用户可控
audio_url → 临时文件 → librosa 分析」链路，存在 SSRF、无上限磁盘写入与匿名
CPU/磁盘资源消耗风险（A-19-U-4 审计，P1）。经裁定（方案 A）整体退役：
四个端点统一返回 410 Gone，不再保留任何网络下载、临时文件或 librosa 调用路径。

未来如需节拍分析能力，必须重新设计安全实现（服务端代理白名单化或改为
用户直传文件 + 鉴权 + 大小上限），不得复用本文件的旧实现。

端点（全部 410 Gone）:
- POST /beat/detect
- POST /beat/rhythm-grid
- POST /beat/tempo-curve
- GET  /beat/info/{track_id}
"""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/beat", tags=["节拍检测"])

_RETIRED_DETAIL = (
    "Beat analysis endpoint '{name}' has been retired (A-20, security hardening). "
    "Use POST /api/v1/ai/generate for music generation."
)


def _retired(name: str):
    raise HTTPException(
        status_code=410,
        detail=_RETIRED_DETAIL.format(name=name),
    )


@router.post("/detect")
async def detect_beat_endpoint():
    """已退役（410 Gone）：旧实现存在 SSRF 与匿名资源消耗风险，见模块 docstring。"""
    _retired("detect")


@router.post("/rhythm-grid")
async def generate_rhythm_grid():
    """已退役（410 Gone）：旧实现存在 SSRF 与匿名资源消耗风险，见模块 docstring。"""
    _retired("rhythm-grid")


@router.post("/tempo-curve")
async def analyze_tempo_curve():
    """已退役（410 Gone）：旧实现存在 SSRF 与匿名资源消耗风险，见模块 docstring。"""
    _retired("tempo-curve")


@router.get("/info/{track_id}")
async def get_beat_info(track_id: str):
    """已退役（410 Gone）：见模块 docstring。"""
    _retired("info")
