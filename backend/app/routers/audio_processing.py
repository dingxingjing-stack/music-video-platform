"""
音轨处理 API·异步网关版
POST /api/v1/audio/separate               接受上传，立即返回 task_id
GET  /api/v1/audio/separate/status/{id}  轮询获取结果

业务逻辑：
1. 验证上传文件类型、大小
2. 将原始音频上传到 Supabase Storage (audio-originals) 服务
3. 在 audio_separate_tasks 创建任务记录
4. 立即返回 task_id (避开 Render 90秒网关超时)
5. 在后台任务中调用 HF Worker 获取 4 轨 -> 上传 Supabase (audio-stems)
6. 更新任务状态为 completed / failed
"""

import base64
import uuid
import asyncio
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client

from app.core.config import get_settings
from app.services.audio_separation_service import demucs_service

router = APIRouter()
settings = get_settings()
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

BUCKET_ORIGINAL = "audio-originals"
BUCKET_STEMS = "audio-stems"


# === 响应模型 ===
class TaskCreateResponse(BaseModel):
    task_id: str
    status: str


class StemInfo(BaseModel):
    vocals: str
    drums: str
    bass: str
    other: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str  # pending / processing / completed / failed
    stems: Optional[StemInfo] = None
    error_message: Optional[str] = None


# === 路由 ===
@router.post("/separate", response_model=TaskCreateResponse)
async def separate_audio(
    file: UploadFile = File(...),
    model: str = Form("htdemucs"),  # 保持接口兼容，不再本地使用
):
    """
    异步分离任务创建

    1. 验证上传文件 (类型 + 大小)
    2. 上传原始音频到 Supabase
    3. 写入 task 记录 (status=pending)
    4. 立即返回 task_id (<1秒)
    5. 后台异步发起 HF Worker 请求，轮询使用 asyncio.create_task
    """
    # === 1. 基础校验 ===
    if file.content_type not in {"audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp3"}:
        raise HTTPException(status_code=400, detail="不支持的音频类型，仅限 wav/mp3")
    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件过大，上限 20MB")
    if len(contents) < 1024:
        raise HTTPException(status_code=400, detail="文件过小")

    # === 2. 上传原始音频到 Supabase ===
    file_name = f"{uuid.uuid4()}_{file.filename or 'audio.wav'}"
    try:
        upload_res = supabase.storage.from_(BUCKET_ORIGINAL).upload(file_name, contents)
        if hasattr(upload_res, "error") and upload_res.error:
            raise RuntimeError(f"上传原始音频失败: {upload_res.error}")
        original_url = supabase.storage.from_(BUCKET_ORIGINAL).get_public_url(file_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"存储上传失败: {e}")

    # === 3. 写入任务记录 ===
    task_id = str(uuid.uuid4())
    try:
        ins = supabase.table("audio_separate_tasks").insert({
            "task_id": task_id,
            "user_id": None,
            "audio_origin_url": original_url,
            "status": "pending",
        }).execute()
        if hasattr(ins, "error") and ins.error:
            raise RuntimeError(f"插入任务记录失败: {ins.error}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"任务记录创建失败: {e}")

    # === 4. 后台异步任务 ===
    async def _process_task(tid: str, orig_url: str):
        """后台调用 HF Worker -> 接收 4 轨 -> 上传 Supabase -> 更新任务状态"""
        try:
            # 更新状态 → processing
            supabase.table("audio_separate_tasks").update({"status": "processing"}).eq("task_id", tid).execute()

            # 调用 HF Worker （带鉴权 X-API-Key）
            stems_bytes = await demucs_service.call_hf_worker(orig_url)
            # stems_bytes: dict[stem_name, bytes] for vocals/drums/bass/other

            # 上传每个分轨到 Supabase 并收集 URL
            stem_urls = {}
            for stem_name in ["vocals", "drums", "bass", "other"]:
                wav_bytes = stems_bytes.get(stem_name)
                if not wav_bytes:
                    raise RuntimeError(f"HF 响应缺少 {stem_name} 轨道")
                stem_file = f"{tid}_{stem_name}.wav"
                up = supabase.storage.from_(BUCKET_STEMS).upload(stem_file, wav_bytes)
                if hasattr(up, "error") and up.error:
                    raise RuntimeError(f"上传 {stem_name} 失败: {up.error}")
                stem_urls[stem_name] = supabase.storage.from_(BUCKET_STEMS).get_public_url(stem_file)

            # 更新任务记录 → completed
            supabase.table("audio_separate_tasks").update({
                "status": "completed",
                "vocals_url": stem_urls["vocals"],
                "drums_url": stem_urls["drums"],
                "bass_url": stem_urls["bass"],
                "other_url": stem_urls["other"],
                "finished_at": "now()",
            }).eq("task_id", tid).execute()

            print(f"[Gateway] ✅ 任务 {tid} 完成")
        except Exception as e:
            err_msg = str(e)[:500]
            print(f"[Gateway] ❌ 任务 {tid} 失败: {err_msg}")
            try:
                supabase.table("audio_separate_tasks").update({
                    "status": "failed",
                    "error_message": err_msg,
                    "finished_at": "now()",
                }).eq("task_id", tid).execute()
            except Exception as db_err:
                print(f"[Gateway] ⚠️ 更新失败状态出错: {db_err}")

    # ✅ 启动后台任务（注意：Render 休眠/崩溃会造成丢失，仅适合中小负载）
    asyncio.create_task(_process_task(task_id, original_url))

    # === 5. 立即返回 ===
    return TaskCreateResponse(task_id=task_id, status="pending")


@router.get("/separate/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """轮询任务状态"""
    try:
        res = supabase.table("audio_separate_tasks").select("*").eq("task_id", task_id).single().execute()
        if hasattr(res, "error") and res.error:
            raise HTTPException(status_code=404, detail="任务不存在")
        getattr(res, "data", None)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")

    if not res.data:
        raise HTTPException(status_code=404, detail="任务不存在")

    data = res.data
    status = data.get("status", "unknown")
    resp = TaskStatusResponse(task_id=task_id, status=status)

    if status == "completed":
        resp.stems = StemInfo(
            vocals=data.get("vocals_url", ""),
            drums=data.get("drums_url", ""),
            bass=data.get("bass_url", ""),
            other=data.get("other_url", ""),
        )
    elif status == "failed":
        resp.error_message = data.get("error_message", "未知错误")

    return resp
