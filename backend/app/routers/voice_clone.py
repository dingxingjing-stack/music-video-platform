"""
声音克隆 API 路由 v2 — 合规版
- /voices         → 分组返回（官方 + 用户私有）
- /upload         → 上传校验 + 月度配额
- /clone          → TTS 合成（含 pitch/speed）
- /clone-quota    → 查询用户本月配额

身份边界（Phase P2-2 加固）：
  凡涉及用户资源/状态/配额（voices / clone-quota / upload / clone）的接口，
  身份唯一可信来源 = X-User-ID（resolve_x_user_id），缺失/空白 → 401。
  绝不接受 query/body user_id、client.host、IP、任意客户端可控字段作为身份。
  /presets 为完全静态公开接口，无需认证。
"""
from fastapi import APIRouter, HTTPException, Query, Header
from typing import List, Optional
from ..services.voice_clone_service import (
    voice_clone_service,
    VoiceSample,
    VoiceCloneRequest,
    VoiceCloneResponse,
    QuotaInfo,
)
from ..services.auth_identity import resolve_x_user_id

router = APIRouter(prefix="/voice", tags=["声音克隆"])


def _require_user(x_user_id: Optional[str]) -> str:
    """从 X-User-ID 解析权威用户身份；缺失/空白 → 401。"""
    uid = resolve_x_user_id(x_user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户标识（X-User-ID）")
    return uid


@router.get("/voices", response_model=List[VoiceSample])
async def list_voices(x_user_id: str = Header(None, alias="X-User-ID")):
    user_key = _require_user(x_user_id)
    return voice_clone_service.list_voices(user_key)

@router.get("/clone-quota", response_model=QuotaInfo)
async def clone_quota(x_user_id: str = Header(None, alias="X-User-ID")):
    user_key = _require_user(x_user_id)
    return voice_clone_service.get_quota(user_key)

@router.post("/upload", response_model=VoiceSample)
async def upload_voice(
    audio_url: str = Query(..., description="音频 URL"),
    name: Optional[str] = Query(None, description="音色名称"),
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    if not audio_url:
        raise HTTPException(400, "audio_url 必填")
    user_key = _require_user(x_user_id)
    try:
        return voice_clone_service.upload_voice(audio_url, name, user_key)
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.post("/clone", response_model=VoiceCloneResponse)
async def clone_voice(
    request: VoiceCloneRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    if not request.text or len(request.text) > 1000:
        raise HTTPException(400, "文本长度必须在 1-1000 字符之间")
    _require_user(x_user_id)  # 身份门控（clone 当前为 mock，真实 GPT-SoVITS 尚未接入）
    return await voice_clone_service.clone_voice(request)

@router.get("/presets", response_model=List[VoiceSample])
async def get_presets():
    return voice_clone_service.presets
