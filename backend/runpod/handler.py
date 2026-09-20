"""RunPod Serverless Worker Handler — HeartMuLa 真实音乐生成（本地 GPU）。

链路：
  RunPod job {input:{prompt,lyrics,duration}}
  → HeartMuLaRequest
  → HeartMuLaService.generate_music()  (heartmula_service._generate_local)
       → HeartMuLaLocalService.generate → generate_sync → HeartMuLaGenPipeline → WAV bytes
       → cdn_uploader.upload_private('heartmula/<uuid>.wav')   // 私有 R2
       → get_presigned_download_url(key, expires_in=3600)      // 预签名
  → 返回 {"output": {"audio_url": <presigned http(s)>}}

说明：
- handler 保持同步 `def handler(job)`；内部用 `asyncio.run()` 包 async service（Serverless
  handler 在无运行中 event loop 的主线程被调用，asyncio.run 安全）。
- worker 环境需设 HEARTMULA_LOCAL_ENABLED=true（在 RunPod worker 配置，非 Render）。
- 不重新实现 HeartMuLa / R2 任何逻辑，全部复用现有 app.services。
"""

import asyncio
import traceback

import runpod


def _heartmula_request(inputs: dict):
    from app.services.heartmula_service import HeartMuLaRequest

    prompt = str(inputs.get("prompt") or "").strip()
    # lyrics 允许为 None；duration 转 int（clamp/时长上限由 service 内部处理）
    try:
        duration = int(inputs.get("duration") or 180)
    except (TypeError, ValueError):
        duration = 180
    return HeartMuLaRequest(
        prompt=prompt,
        lyrics=inputs.get("lyrics"),  # 可为 None
        duration=duration,
    )


def handler(job: dict) -> dict:
    """RunPod Serverless handler 入口。

    输入格式：
        {"input": {"prompt": "...", "lyrics": "...", "duration": 180}}
    返回（与 backend/app/services/runpod_client.py 解析契约兼容）：
        {"output": {"audio_url": "https://...presigned..."}}
    """
    try:
        inputs = job.get("input", {}) if isinstance(job, dict) else {}
        request = _heartmula_request(inputs)

        from app.services.heartmula_service import get_heartmula_service

        svc = get_heartmula_service()
        if svc is None:
            return {
                "success": False,
                "error": (
                    "HeartMuLa service unavailable. Worker 需设置 HEARTMULA_LOCAL_ENABLED=true "
                    "（RunPod worker 配置，非 Render）。"
                ),
            }

        result = asyncio.run(svc.generate_music(request))
        audio_url = result.get("audio_url")
        if not result.get("success") or not audio_url:
            return {"success": False, "error": result.get("error", "HeartMuLa generation failed")}

        return {"output": {"audio_url": audio_url}}

    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


# RunPod Serverless 入口点 — 模块顶层，供 RunPod SDK 识别
runpod.serverless.start({"handler": handler})