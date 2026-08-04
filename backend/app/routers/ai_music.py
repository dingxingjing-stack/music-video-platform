"""
AI 音乐生成路由（异步任务架构）

POST /api/v1/ai/generate    提交生成任务，立即返回 task_id
GET  /api/v1/ai/task/{id}   轮询任务状态，completed 时返回 audio_url

降级链：Modal MusicGen (本地开源) -> HF (Hugging Face MusicGen) -> 明确报错（无 Mock）
"""

import asyncio
import os
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.services.musicgen_client import generate_music as musicgen_generate_music
from app.services.agnes_music_service import agnes_service, AgnesSongRequest
from app.services import task_store

router = APIRouter(prefix="/api/v1/ai", tags=["ai-music"])

HF_FALLBACK_ENABLED = os.getenv("HF_FALLBACK", "true").lower() in ("1", "true", "yes")


async def _try_hf_fallback(prompt: str, style: str, duration: Optional[int]) -> Optional[str]:
    """调用 Hugging Face Inference API 的 facebook/musicgen-large 生成音频，失败返回 None。"""
    if not HF_FALLBACK_ENABLED:
        return None

    hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")
    if not hf_token:
        print("[HF 兜底] 未配置 HF_TOKEN / HUGGINGFACE_TOKEN，跳过")
        return None

    tmp_path = None
    try:
        api_url = "https://api-inference.huggingface.co/models/facebook/musicgen-large"
        headers = {"Authorization": f"Bearer {hf_token}"}
        payload = {"inputs": prompt}

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(api_url, headers=headers, json=payload)

        if response.status_code != 200:
            print(f"[HF 兜底] HF API 错误: {response.status_code} - {response.text}")
            return None

        audio_data = response.content
        if not audio_data:
            print("[HF 兜底] HF API 返回空数据")
            return None

        import tempfile
        from app.services.cdn_uploader import CDNUploader

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_data)
            tmp.flush()
            tmp_path = tmp.name

        uploader = CDNUploader()
        cdn_url = await uploader.upload_audio(tmp_path)
        if cdn_url:
            return cdn_url
        print("[HF 兜底] 上传到 CDN 失败（返回空 URL）")
        return None

    except Exception as e:
        print(f"[HF 兜底] 异常: {type(e).__name__}: {e}")
        return None
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


class GenerateRequest(BaseModel):
    """AI 生成请求"""
    prompt: str
    style: str = "pop"
    duration: Optional[int] = None
    type: str = "song"


class GenerateResponse(BaseModel):
    """AI 生成响应（提交成功即返回）"""
    success: bool
    task_id: Optional[str] = None
    status_url: Optional[str] = None
    error: Optional[str] = None


class TaskResponse(BaseModel):
    """任务状态查询响应"""
    task_id: str
    state: str          # pending / processing / completed / failed
    progress: int
    audio_url: Optional[str] = None
    video_url: Optional[str] = None
    ai_provider: Optional[str] = None
    error: Optional[str] = None


async def _run_generation(task_id: str, request: GenerateRequest):
    """后台执行完整生成链路：Agnes 优化 → MusicGen → HF 兜底。"""
    try:
        task_store.update(task_id, state="processing", progress=10)

        agnes_request = AgnesSongRequest(
            prompt=request.prompt,
            style=request.style,
            duration=request.duration or 180,
            type=request.type,
        )
        agnes_result = await agnes_service.generate_song(agnes_request)

        ai_provider = "agnes" if agnes_result.optimized_prompt and agnes_result.optimized_prompt != request.prompt else "gemini"
        task_store.update(task_id, progress=40, ai_provider=f"{ai_provider}")

        final_prompt = agnes_result.optimized_prompt or request.prompt
        if agnes_result.generated_lyrics:
            final_prompt = agnes_result.generated_lyrics

        audio_url = await musicgen_generate_music(
            prompt=final_prompt,
            duration=min(request.duration or 30, 60),
        )
        if audio_url:
            task_store.update(
                task_id, state="completed", progress=100,
                audio_url=audio_url, ai_provider=f"{ai_provider}+musicgen",
            )
            return

        hf_audio = await _try_hf_fallback(
            prompt=final_prompt,
            style=request.style,
            duration=request.duration,
        )
        if hf_audio:
            task_store.update(
                task_id, state="completed", progress=100,
                audio_url=hf_audio, ai_provider=f"{ai_provider}+hf",
            )
            return

        task_store.update(
            task_id, state="failed",
            error="音乐生成失败：MusicGen 与 HF 兜底均不可用（请检查 Modal 部署 / HF_TOKEN 配置）",
        )
    except HTTPException:
        task_store.update(task_id, state="failed", error="请求参数错误")
    except Exception as e:
        import traceback
        print(f"[generate 未捕获异常] {type(e).__name__}: {e}")
        traceback.print_exc()
        task_store.update(task_id, state="failed", error=f"{type(e).__name__}: {e}")


@router.post("/generate", response_model=GenerateResponse)
async def generate_music(request: GenerateRequest):
    """提交 AI 音乐生成任务，立即返回 task_id。"""
    if not request.prompt or len(request.prompt.strip()) < 5:
        raise HTTPException(status_code=400, detail="提示词至少需要 5 个字符")

    task_id = task_store.new_task()
    asyncio.create_task(_run_generation(task_id, request))
    return GenerateResponse(
        success=True,
        task_id=task_id,
        status_url=f"/api/v1/ai/task/{task_id}",
    )


@router.get("/task/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """轮询任务状态；completed 时返回 audio_url。"""
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return TaskResponse(
        task_id=task["task_id"],
        state=task["state"],
        progress=task["progress"],
        audio_url=task.get("audio_url"),
        video_url=task.get("video_url"),
        ai_provider=task.get("ai_provider"),
        error=task.get("error"),
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
