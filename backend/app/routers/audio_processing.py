"""
音频处理 API 路由
- 音频分离 (Demucs)
- 母带处理
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
import os
import secrets
import tempfile
from pathlib import Path

from app.services.audio_separation_service import demucs_service
from app.services.mastering_service import mastering_service
from app.services.cdn_uploader import cdn_uploader
from app.services.auth_identity import get_verified_user_id

router = APIRouter()


# ========== 上传安全（P0 收口）==========
# 原实现两处致命问题：
#   1. `temp_dir / file.filename` 直接使用客户端文件名 —— 可传 `../../etc/passwd`
#      或绝对路径，造成路径穿越写入；
#   2. `await file.read()` 一次性读入内存且无上限 —— 大文件直接打爆内存（DoS）。
# 收口：随机安全文件名 + 边读边写 + 硬大小上限（超出 413 并删除半成品）。
MAX_UPLOAD_BYTES = int(os.getenv("AUDIO_UPLOAD_MAX_MB", "50")) * 1024 * 1024
_CHUNK = 1024 * 1024  # 1MB


def _safe_upload_name(filename: Optional[str]) -> str:
    """把客户端文件名净化为随机安全文件名（不信任客户端任何路径成分）。

    仅保留一个白名单式扩展名（≤8 位字母数字），主体全部替换为随机串，
    因此 `../`、绝对路径、NUL、超长名等一律失效。
    """
    ext = ""
    if filename:
        base = os.path.basename(str(filename).replace("\\", "/")).strip()
        _, dot, tail = base.rpartition(".")
        if dot and tail and 1 <= len(tail) <= 8 and tail.isalnum():
            ext = "." + tail.lower()
    return f"upload_{secrets.token_hex(16)}{ext or '.bin'}"


async def _save_upload(file: UploadFile, temp_dir: Path, max_bytes: int = MAX_UPLOAD_BYTES) -> Path:
    """流式落盘上传文件：安全文件名 + 硬大小上限。

    - 边读边写，不把整个文件读进内存；
    - 超出 max_bytes → 删除半成品并抛 413；
    - 空文件 → 400。
    """
    temp_dir.mkdir(parents=True, exist_ok=True)
    out_path = temp_dir / _safe_upload_name(file.filename)
    total = 0
    try:
        with open(out_path, "wb") as f:
            while True:
                chunk = await file.read(_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    break
                f.write(chunk)
    except Exception as e:  # noqa: BLE001
        out_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"保存文件失败: {e}")

    if total > max_bytes:
        out_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=413,
            detail=f"文件过大，上限 {max_bytes // (1024 * 1024)} MB",
        )
    if total == 0:
        out_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="空文件")

    return out_path


# ========== 请求模型 ==========

class SeparateRequest(BaseModel):
    """音频分离请求"""
    model: str = "htdemucs"  # 模型选择


class MasteringRequest(BaseModel):
    """母带处理请求"""
    target_loudness: float = -14.0  # LUFS
    stereo_width: float = 0.3  # 立体声增强


# ========== 响应模型 ==========

class SeparateResponse(BaseModel):
    success: bool
    stems: List[str]  # 分离后的文件路径
    duration: float
    message: str
    error_code: Optional[str] = None


class MasteringResponse(BaseModel):
    success: bool
    output_path: str
    loudness_before: float
    loudness_after: float
    peak_before: float
    peak_after: float
    message: str


# ========== API 端点 ==========

@router.get("/separate/models")
async def get_separation_models():
    """获取可用分离模型列表（已禁用：��心��路使用内部 Modal ���用，不走此 HTTP 端点）"""
    raise HTTPException(
        status_code=410,
        detail=(
            "Endpoint '/separate/models' has been retired. "
            "Audio separation is served by POST /api/v1/ai/stems/separate."
        ),
    )


@router.post("/master", response_model=MasteringResponse)
async def master_audio(
    file: UploadFile = File(...),
    target_loudness: float = Form(-14.0),
    stereo_width: float = Form(0.3),
    user_id: str = Depends(get_verified_user_id),
):
    """
    自动母带处理
    
    上传音频文件，返回母带处理后的文件路径和分析数据
    """
    # 保存上传文件（P0 收口：随机安全文件名 + 硬大小上限，杜绝路径穿越与内存打爆）
    temp_dir = Path(tempfile.gettempdir()) / "audio_uploads"
    input_path = await _save_upload(file, temp_dir)

    # 执行母带处理
    result = mastering_service.master(
        str(input_path),
        target_loudness=target_loudness,
        stereo_width=stereo_width,
        progress_callback=lambda p: print(f"母带进度：{p*100:.0f}%")
    )
    
    # 清理上传文件
    input_path.unlink(missing_ok=True)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    
    return MasteringResponse(**result)


@router.post("/separate", response_model=SeparateResponse)
async def separate_audio(
    file: UploadFile = File(...),
    model: str = Form("htdemucs"),
    user_id: str = Depends(get_verified_user_id),
):
    """
    音频分离 (vocals/drums/bass/other)

    上传音频文件，返回 4 轨分离后的文件 URL

    安全：
      - 身份唯一可信来源 = Authorization Bearer JWT → verified auth.users.id（缺 JWT 自动 401）。
        绝不接受 X-User-ID / body.user_id / client.host / IP / anonymous 作为身份。
      - 实际执行 separation（含 mock）前必须先 reserve_generation(user_key)；
        quota 不足 → 429，阻止后续 provider/inference。
    """
    # P2-3 API Retirement：本端点已退休（410 Gone）。旧 Demucs/Spleeter 实现
    # 自此不可达；真实分离 = POST /api/v1/ai/stems/separate（V2=60 / V3=100 Credits）。
    # 下方历史实现体保留为死代码，待独立删除授权收口。
    raise HTTPException(
        status_code=410,
        detail=(
            "Endpoint '/separate' has been retired. "
            "Use POST /api/v1/ai/stems/separate."
        ),
    )

    # 1) 身份认证（依赖层已强制 JWT；user_key = verified auth.users.id）
    user_key = user_id

    # 2) Quota 预留：必须在任何 separation/inference 之前
    from app.services.ai_limits import reserve_generation, refund_generation
    reserved = reserve_generation(user_key)
    if not reserved["success"]:
        raise HTTPException(status_code=429, detail=reserved["error"])

    # 保存上传文件（P0 收口：随机安全文件名 + 硬大小上限）
    # 失败时必须 refund_generation —— 额度已 reserve，不能让用户在失败上被扣费。
    temp_dir = Path(tempfile.gettempdir()) / "audio_uploads"
    try:
        input_path = await _save_upload(file, temp_dir)
    except HTTPException:
        refund_generation(user_key, reason="validation_failed")
        raise
    
    # 执行分离（使用现有的 demucs_service，实际上是 Modal Spleeter）
    result = demucs_service.separate(
        str(input_path),
        model=model,
        progress_callback=lambda p: print(f"分离进度：{p*100:.0f}%")
    )
    
    # 清理上传文件
    try:
        input_path.unlink(missing_ok=True)
    except:
        pass
    
    if not result["success"]:
        refund_generation(user_key, reason="provider_failed")
        return SeparateResponse(
            success=False,
            stems=[],
            duration=0,
            message=result["message"],
            error_code=result.get("error_code")
        )
    
    # result["stems"] 是本地临时文件路径列表
    local_stems = result["stems"]
    cdn_urls = []
    try:
        for stem_path in local_stems:
            # 上传每个 stem 到 CDN/R2
            url = await cdn_uploader.upload_audio(stem_path, content_type="audio/wav")
            cdn_urls.append(url)
    except Exception as e:
        # 上传失败，清理本地 stem 文件并返回错误
        for stem_path in local_stems:
            try:
                Path(stem_path).unlink(missing_ok=True)
            except:
                pass
        refund_generation(user_key, reason="persistence_failed")
        raise HTTPException(status_code=500, detail=f"CDN 上传失败: {e}")
    finally:
        # 清理本地 stem 文件（无论成功失败）
        for stem_path in local_stems:
            try:
                Path(stem_path).unlink(missing_ok=True)
            except:
                pass
    
    # 计算时长？demucs_service.separate 返回 duration 字段（目前是 0）。
    duration = result.get("duration", 0.0)
    
    return SeparateResponse(
        success=True,
        stems=cdn_urls,
        duration=duration,
        message=f"分离成功，{len(cdn_urls)} 轨音频已上传至 CDN"
    )


@router.get("/master/presets")
async def get_mastering_presets():
    """获取母带预设"""
    return {
        "presets": [
            {
                "name": "流媒体标准",
                "target_loudness": -14.0,
                "stereo_width": 0.3,
                "description": "Spotify/Apple Music 标准"
            },
            {
                "name": "YouTube",
                "target_loudness": -13.0,
                "stereo_width": 0.4,
                "description": "YouTube 优化"
            },
            {
                "name": "俱乐部/夜店",
                "target_loudness": -8.0,
                "stereo_width": 0.5,
                "description": "高响度，宽立体声"
            },
            {
                "name": "古典/爵士",
                "target_loudness": -16.0,
                "stereo_width": 0.6,
                "description": "保留动态范围"
            },
            {
                "name": "电子/舞曲",
                "target_loudness": -10.0,
                "stereo_width": 0.7,
                "description": "强劲低音，宽声场"
            }
        ]
    }