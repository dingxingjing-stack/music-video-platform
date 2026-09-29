"""
声音克隆 API 路由 v2 — RETIRED (P5-B.4)

P5-A 实测：前端对 /api/v1/voice/* 引用为 0。
原 POST /clone 由 voice_clone_service.clone_voice 恒返回 success=True，
audio_url 拼的是第三方教学站 www2.cs.uic.edu/~i101/SoundFiles/ 的演示音频
（含 StarWars / PinkPanther / BabyElephantWalk），presets 亦为该站样本，
既无 RVC/GPT-SoVITS 真实能力，又把他人版权录音当产品资产展示给用户。
整族改为 410 Gone；真实克隆能力属于 /api/v1/voice-clone/*（PoYo，
VOICE_CLONE_ENABLED fail-closed 门禁），本文件与其无关，未做任何改动。
"""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/voice", tags=["声音克隆"])


def _retired(name: str):
    raise HTTPException(
        status_code=410,
        detail=(
            f"Voice endpoint '{name}' has been retired (no real voice-clone backend). "
            "See POST /api/v1/voice-clone/validate.",
        ),
    )


@router.get("/voices")
async def list_voices():
    """P5-B.4：已退休（410 Gone）。"""
    _retired("voices")


@router.get("/clone-quota")
async def clone_quota():
    """P5-B.4：已退休（410 Gone）。"""
    _retired("clone-quota")


@router.post("/upload")
async def upload_voice():
    """P5-B.4：已退休（410 Gone）。"""
    _retired("upload")


@router.post("/clone")
async def clone_voice():
    """P5-B.4：已退休（410 Gone，原先恒返回 mock 成功 + 第三方演示音频）。"""
    _retired("clone")


@router.get("/presets")
async def get_presets():
    """P5-B.4：已退休（410 Gone，原先匿名返回第三方教学站音频）。"""
    _retired("presets")