"""PoYo Voice Clone 独立路由 —— /api/v1/voice-clone

PoYo(Suno) 歌唱声音克隆，只服务 Voice Clone，绝不进入 AI Music Generation fallback chain。

流程（分步，天然 exactly-once）：
    POST /validate   → 上传参考人声 URL，返回 validate task_id + 验证短语
    POST /generate   → 用 validate 的 task_id + 用户朗读短语的录音 URL，创建 voice_id
    POST /check      → 检查 voice_id 是否仍可用
    POST /regenerate → 短语失效时重新索取验证短语

开关：VOICE_CLONE_ENABLED 默认 false（商业授权确认前不开放）。
身份：所有端点要求 Authorization: Bearer JWT（get_verified_user_id）。
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.auth_identity import get_verified_user_id
from app.services.poyo_voice_clone_provider import (
    PoYoVoiceCloneError,
    poyo_voice_clone_provider,
)

router = APIRouter(prefix="/api/v1/voice-clone", tags=["voice-clone"])

# 默认 false：PoYo/Suno 商业授权未确认前，不得在生产自动开放。
VOICE_CLONE_ENABLED = os.getenv("VOICE_CLONE_ENABLED", "false").lower() in ("1", "true", "yes")


class ValidateRequest(BaseModel):
    voice_url: str
    vocal_start_s: int
    vocal_end_s: int
    language: str = "en"


class GenerateRequest(BaseModel):
    task_id: str
    verify_url: str
    voice_name: Optional[str] = None


class TaskIdRequest(BaseModel):
    task_id: str


def _guard_enabled() -> None:
    if not VOICE_CLONE_ENABLED:
        raise HTTPException(503, "voice clone 尚未开放（商业授权未确认）")


@router.post("/validate")
async def voice_validate(req: ValidateRequest, _user: str = Depends(get_verified_user_id)):
    _guard_enabled()
    try:
        return await poyo_voice_clone_provider.validate(
            req.voice_url, req.vocal_start_s, req.vocal_end_s, req.language
        )
    except PoYoVoiceCloneError as e:
        raise HTTPException(502, str(e))


@router.post("/generate")
async def voice_generate(req: GenerateRequest, _user: str = Depends(get_verified_user_id)):
    _guard_enabled()
    if not req.task_id:
        raise HTTPException(400, "task_id 必填（validate 返回的任务 ID）")
    if not req.verify_url:
        raise HTTPException(400, "verify_url 必填（朗读验证短语的录音 URL）")
    try:
        return await poyo_voice_clone_provider.generate(req.task_id, req.verify_url, req.voice_name)
    except PoYoVoiceCloneError as e:
        raise HTTPException(502, str(e))


@router.post("/check")
async def voice_check(req: TaskIdRequest, _user: str = Depends(get_verified_user_id)):
    _guard_enabled()
    try:
        return await poyo_voice_clone_provider.check(req.task_id)
    except PoYoVoiceCloneError as e:
        raise HTTPException(502, str(e))


@router.post("/regenerate")
async def voice_regenerate(req: TaskIdRequest, _user: str = Depends(get_verified_user_id)):
    _guard_enabled()
    try:
        return await poyo_voice_clone_provider.regenerate(req.task_id)
    except PoYoVoiceCloneError as e:
        raise HTTPException(502, str(e))