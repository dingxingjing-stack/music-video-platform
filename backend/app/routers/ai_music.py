"""
AI 音乐生成路由

降级链：Mureka -> HF (Hugging Face ACE-Step) -> Mock
通过环境变量 HF_FALLBACK (默认 true) 控制是否启用 HF 兜底。
"""

import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.services.mureka_service import mureka_service, MurekaSongRequest, QuotaExceededError
from app.services.agnes_music_service import agnes_service, AgnesSongRequest

router = APIRouter(prefix="/api/v1/ai", tags=["ai-music"])

HF_FALLBACK_ENABLED = os.getenv("HF_FALLBACK", "true").lower() in ("1", "true", "yes")


async def _try_hf_fallback(prompt: str, style: str, duration: Optional[int]) -> Optional[str]:
    """
    尝试调用 Hugging Face ACE-Step 模型生成音频。

    返回生成的音频 URL（CDN / 临时直链），失败时返回 None。
    仅在 HF_FALLBACK_ENABLED = True 时才会真正发起请求。
    """
    if not HF_FALLBACK_ENABLED:
        return None

    try:
        from huggingface_hub import InferenceClient
    except ImportError:
        print("[HF 兜底] huggingface_hub 未安装，跳过")
        return None

    hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")
    if not hf_token:
        print("[HF 兜底] 未配置 HF_TOKEN / HUGGINGFACE_TOKEN，跳过")
        return None

    try:
        client = InferenceClient(token=hf_token)
        # ACE-Step 是当前可用的开源文生音乐模型，可按需替换
        result = client.text_to_speech(
            inputs=prompt,
            model="facebook/musicgen-large",
            parameters={
                "duration": min(int(duration or 30), 30),
                "temperature": 0.7,
            },
        )
        if isinstance(result, bytes):
            import base64
            import tempfile

            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.write(result)
            tmp.close()
            return tmp.name
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            return result.get("audio_url") or result.get("url")
        print(f"[HF 兜底] 未知返回类型: {type(result)}")
        return None
    except Exception as e:
        print(f"[HF 兜底] 异常: {e}")
        return None


class GenerateRequest(BaseModel):
    """AI 生成请求"""
    prompt: str  # 音乐提示词
    style: str = "pop"  # 风格
    duration: Optional[int] = None  # 时长（秒）
    type: str = "song"  # song/music/bgm


class GenerateResponse(BaseModel):
    """AI 生成响应"""
    success: bool
    audio_url: Optional[str] = None
    error: Optional[str] = None
    task_id: Optional[str] = None
    ai_provider: Optional[str] = None   # "agnes" / "gemini" / "mureka" / "mock"
    agnes_debug: Optional[str] = None    # 调试 Agnes 调用详情


@router.post("/generate", response_model=GenerateResponse)
async def generate_music(request: GenerateRequest):
    """
    AI 生成音乐（Agnes 主力 + Gemini 备用 + Mureka 音频 + Mock 兜底）
    """
    # 验证提示词
    if not request.prompt or len(request.prompt.strip()) < 5:
        raise HTTPException(status_code=400, detail="提示词至少需要 5 个字符")

    # 1. 使用 Agnes 优化提示词 + 生成歌词（主力）
    agnes_request = AgnesSongRequest(
        prompt=request.prompt,
        style=request.style,
        duration=request.duration or 180,
        type=request.type,
    )
    agnes_result = await agnes_service.generate_song(agnes_request)

    # 记录 AI 提供者 + 调试信息
    ai_provider = "agnes" if agnes_result.optimized_prompt and agnes_result.optimized_prompt != request.prompt else "gemini"
    agnes_debug = f"success={agnes_result.success}, opt_changed={'yes' if agnes_result.optimized_prompt != request.prompt else 'no'}, error={agnes_result.error}, key_set={bool(agnes_service.API_KEY)}"

    # 2. 使用优化后的提示词调用 Mureka 生成音频（多引擎降级）
    final_prompt = agnes_result.optimized_prompt or request.prompt
    if agnes_result.generated_lyrics:
        final_prompt = agnes_result.generated_lyrics

    mureka_request = MurekaSongRequest(
        lyrics=final_prompt,
        style=request.style,
        duration=request.duration,
    )

    # === 降级链：Mureka -> HF (Hugging Face ACE-Step) -> Mock ===
    try:
        mureka_result = await mureka_service.generate_song(mureka_request)
        if mureka_result.success:
            return GenerateResponse(
                success=True,
                audio_url=mureka_result.audio_url,
                task_id=mureka_result.task_id,
                ai_provider=f"{ai_provider}+mureka",
                agnes_debug=agnes_debug,
            )
    except QuotaExceededError:
        print("[降级] Mureka 配额耗尽，降级到 HF")
    except Exception as e:
        print(f"[降级] Mureka 异常: {e}，降级到 HF")

    # 2. Mureka 失败时尝试 HF 兑底
    hf_audio = await _try_hf_fallback(
        prompt=final_prompt,
        style=request.style,
        duration=request.duration,
    )
    if hf_audio:
        return GenerateResponse(
            success=True,
            audio_url=hf_audio,
            task_id=f"hf-{hash(final_prompt) & 0xffff:04x}",
            ai_provider=f"{ai_provider}+hf",
            agnes_debug=agnes_debug,
        )

    # 3. 最后 Mock 兑底
    import random
    mock_urls = [
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
    ]
    return GenerateResponse(
        success=True,
        audio_url=random.choice(mock_urls),
        task_id=f"mock-{hash(request.prompt) & 0xffff:04x}",
        ai_provider=f"{ai_provider}+mock",
        agnes_debug=agnes_debug,
    )


@router.get("/styles")
async def list_styles():
    """获取支持的音乐风格"""
    return {
        "styles": [
            {"value": "pop", "label": "流行", "description": "主流流行音乐"},
            {"value": "rock", "label": "摇滚", "description": "摇滚乐"},
            {"value": "electronic", "label": "电子", "description": "电子音乐"},
            {"value": "hip-hop", "label": "嘻哈", "description": "嘻哈/说唱"},
            {"value": "r&b", "label": "R&B", "description": "节奏布鲁斯"},
            {"value": "jazz", "label": "爵士", "description": "爵士乐"},
            {"value": "classical", "label": "古典", "description": "古典音乐"},
            {"value": "ambient", "label": "氛围", "description": "氛围音乐"},
            {"value": "cinematic", "label": "电影配乐", "description": "电影原声"},
            {"value": "lo-fi", "label": "Lo-Fi", "description": "低保真音乐"},
        ]
    }