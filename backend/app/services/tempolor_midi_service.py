"""TempolorMidiService — 天谱乐 MIDI 转换服务（midi v1：音频 → midi.zip）。

P4-B2 Phase A-17 正式接入（2026-10-02 授权；此前 registry-only）：

- Provider：天谱乐 / TemPolor 开放平台（api.tianpuyue.cn）。
- 官方契约（2026-10-03 以 platform.tianpuyue.cn 当前文档重新核验）：
  * 创建：POST /open-apis/v1/midi  body={"url": <公网可 GET, ≤50MB>, "callback_url": <必填>}
    → HTTP 200 + {"status": 200000, "data": {"item_ids": [...]}}
  * 查询：POST /open-apis/v1/midi/query  body={"item_ids": [...]}（官方：最大 10）
    → data.midis[] 每项含 item_id / status / midi_url / stems_url
  * 回调：{"midis": [{"item_id", "status": "succeeded", "midi_url", "stems_url"}]}，
    我方须回字符串 "success"（与 stems 回调同构；结果以 query 轮询为准）。
  * 业务码字段名 status（非 code），成功 200000；鉴权裸 Key 无 Bearer（与 stems 同款）。
- 价格：midi v1 = 200 创作点（¥2.00）/次（官方定价页 8859398m0，2026-10-03 重新核实）。
- 产物：midi_url 指向完整 midi.zip。**非音频** → 不适用 240s 时长门（§九 仅约束
  音乐生成类交付）；zip 落 R2 私有，经既有预签名链路交付。
- **不 reserve / 不 refund / 不写任务状态**（Credits 与任务状态全在上层 ai_music.py
  既有机制中处理，与 tempolor_stems_service 同边界）。
- Credits：CREDIT_COSTS["midi"] 当前 credit_cost=0 = 未定价 → 上层 fail-closed
  （503 midi_not_priced），绝不免费放行、绝不猜价；产品定价后改 credits_config 自动激活。

安全红线（与 tempolor_stems_service 一致）：
- API Key 绝不写入日志；midi_url/stems_url 是第三方签名 URL：仅服务端一次性下载，
  绝不入库为用户可见 URL，绝不剥离其查询串（按原样 GET）。
- zip 下载硬上限；zipfile 完整性校验 + 成员清单记录（midi.zip 内部结构官方未公布，
  不做成员白名单——真实联调后按实测产物补充，本轮不猜）。
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

logger = logging.getLogger(__name__)

# ── 复用既有单一事实源（与 stems 服务同构）──────────────────────────────────
from app.services.tempolor_provider import (  # noqa: E402
    TEMPOLOR_BASE_URL,
    callback_secret as _song_callback_secret,
)

# ── 配置（全部来自既有环境变量，无新增 env 需求）──────────────────────────
MIDI_TIMEOUT_SECONDS = float(os.getenv("MIDI_TIMEOUT_SECONDS", "480"))
MIDI_FIRST_POLL_DELAY_SECONDS = float(os.getenv("MIDI_FIRST_POLL_DELAY_SECONDS", "15"))
MIDI_POLL_INTERVAL_SECONDS = float(os.getenv("MIDI_POLL_INTERVAL_SECONDS", "3"))

# 输入 URL 的 presigned TTL（与 stems 同口径）
MIDI_INPUT_PRESIGN_TTL_SECONDS = int(os.getenv("MIDI_INPUT_PRESIGN_TTL_SECONDS", "3600"))

# midi.zip 下载硬上限（官方未公布产物大小；50MB 输入的 MIDI 包远小于该值）
MIDI_ZIP_MAX_BYTES = 256 * 1024 * 1024

# ── 状态集合（与 stems 同策略：未知状态一律当作潜在非终态继续轮询）──────────
_MIDI_SUCCESS_STATUSES = {"succeeded"}
_MIDI_FAILURE_STATUSES = {"failed", "failed_", "cancelled"}
_MIDI_POLLING_STATUSES = {"pending", "queued", "running", "processing"}


class MidiError(Exception):
    """MIDI 任务失败（提交/轮询/下载/校验任一环节）。消息可安全上抛（不含 Key）。"""


# ── 鉴权 / 回调 URL（与 stems 同构）──────────────────────────────────────

def _api_key() -> str:
    key = os.getenv("TEMPOLOR_API_KEY")
    if key and key.strip():
        return key.strip()
    try:
        from app.core.secrets import get_secret
        v = get_secret("TEMPOLOR_API_KEY", required=False)
        return (v or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _derive_midi_callback_path(base_url: str) -> str:
    """从 Song callback URL 派生 MIDI callback URL。

    Song：…/api/v1/ai/tempolor/callback → MIDI：…/api/v1/ai/tempolor/midi/callback
    （官方回调示例路径为 /midi/callback；不匹配 "/callback" 结尾 → fail-closed。）
    """
    trimmed = base_url.rstrip("/")
    if trimmed.endswith("/callback"):
        return trimmed[: -len("/callback")] + "/midi/callback"
    raise MidiError(
        "TEMPOLOR_CALLBACK_URL 配置无法派生 MIDI 回调地址（需以 /callback 结尾），已拒绝提交"
    )


def effective_midi_callback_url() -> str:
    """MIDI callback URL = 派生路径 + 共享令牌 query（复用 Song 的 callback_secret）。"""
    base = (os.getenv("TEMPOLOR_CALLBACK_URL") or "").strip()
    if not base:
        return ""
    midi_url = _derive_midi_callback_path(base)
    secret = _song_callback_secret()
    if not secret:
        return midi_url  # 未配密钥：端点侧 fail-closed（503），与 Song/Stems 行为一致
    parts = urlsplit(midi_url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "token"]
    query.append(("token", secret))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _headers() -> dict:
    key = _api_key()
    if not key:
        raise MidiError("TEMPOLOR_API_KEY 未配置")
    # 官方鉴权为「裸 API Key」，无 Bearer 前缀
    return {"Authorization": key, "Content-Type": "application/json"}


def _check_business_code(data: dict, context: str) -> None:
    """业务码校验：字段名是 status（非 code！），200000=成功。"""
    biz = data.get("status") if isinstance(data, dict) else None
    if biz is not None and biz != 200000:
        msg = str(data.get("message") or "")[:120]
        raise MidiError(f"MIDI API business error status={biz} ({context}) message={msg}")


# ── 提交 ─────────────────────────────────────────────────────────────────

async def submit_midi(input_local_path: str, task_id: str) -> str:
    """上传输入文件到私有 R2 → 签发 presigned GET(3600s) → 提交 MIDI 任务。

    返回 provider item_id。任何失败抛 MidiError（由上层统一退款）。
    """
    from app.services.cdn_uploader import cdn_uploader

    ext = os.path.splitext(input_local_path)[1].lower() or ".mp3"
    input_key = f"midi/{task_id}/input{ext}"
    await cdn_uploader.upload_private(input_local_path, input_key)
    logger.info("[midi] task=%s input uploaded r2_key=%s", task_id, input_key)

    input_url = cdn_uploader.get_presigned_download_url(
        input_key, expires_in=MIDI_INPUT_PRESIGN_TTL_SECONDS
    )

    callback_url = effective_midi_callback_url()
    if not callback_url:
        raise MidiError("TEMPOLOR_CALLBACK_URL 未配置：callback_url 官方强制非空，已拒绝提交")

    payload = {"url": input_url, "callback_url": callback_url}
    headers = _headers()
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{TEMPOLOR_BASE_URL}/open-apis/v1/midi", headers=headers, json=payload
        )
        if resp.status_code != 200:
            logger.warning("[midi] submit HTTP %s task=%s", resp.status_code, task_id)
            raise MidiError(f"MIDI submit HTTP {resp.status_code}")
        data = resp.json() if resp.content else {}
        _check_business_code(data, "submit")
        item_ids = (data.get("data") or {}).get("item_ids") if isinstance(data.get("data"), dict) else None
        if not isinstance(item_ids, list) or not item_ids:
            raise MidiError("MIDI submit response missing item_ids")
        item_id = str(item_ids[0])
        logger.info("[midi] task=%s submitted item=%s", task_id, item_id)
        return item_id


# ── 轮询 ─────────────────────────────────────────────────────────────────

async def poll_midi(item_id: str, task_id: str) -> str:
    """轮询 POST /midi/query（官方契约，body {"item_ids": [...]}）直到终态；返回 midi_url。

    - 首查延迟 15s，随后 3s 间隔；deadline 内未终态 → MidiError（超时，安全失败）。
    - 未知状态：继续轮询（deadline 兜底），绝不当作成功。
    """
    headers = _headers()
    deadline = time.monotonic() + MIDI_TIMEOUT_SECONDS
    await asyncio.sleep(MIDI_FIRST_POLL_DELAY_SECONDS)
    last_status: Optional[str] = None
    async with httpx.AsyncClient(timeout=60.0) as client:
        while time.monotonic() < deadline:
            resp = await client.post(
                f"{TEMPOLOR_BASE_URL}/open-apis/v1/midi/query",
                headers=headers,
                json={"item_ids": [item_id]},
            )
            if resp.status_code != 200:
                logger.warning("[midi] query HTTP %s item=%s", resp.status_code, item_id)
                await asyncio.sleep(MIDI_POLL_INTERVAL_SECONDS)
                continue
            data = resp.json() if resp.content else {}
            try:
                _check_business_code(data, "query")
            except MidiError as exc:
                # 400008/400009 等：作品不存在/状态异常 → 不可恢复，立即失败
                if "status=400008" in str(exc) or "status=400009" in str(exc):
                    raise
                logger.warning("[midi] query transient business error item=%s: %s", item_id, exc)
                await asyncio.sleep(MIDI_POLL_INTERVAL_SECONDS)
                continue
            midis = (data.get("data") or {}).get("midis") if isinstance(data.get("data"), dict) else None
            entry = midis[0] if isinstance(midis, list) and midis and isinstance(midis[0], dict) else {}
            status = entry.get("status")
            last_status = status if isinstance(status, str) else last_status

            if status in _MIDI_SUCCESS_STATUSES:
                midi_url = entry.get("midi_url")
                if not midi_url:
                    raise MidiError("MIDI succeeded but response has no midi_url")
                logger.info("[midi] item=%s succeeded", item_id)
                return str(midi_url)
            if status in _MIDI_FAILURE_STATUSES:
                raise MidiError(f"MIDI task failed (status={status})")
            # 已知进行中 / 未知状态 → 继续轮询（deadline 兜底）
            await asyncio.sleep(MIDI_POLL_INTERVAL_SECONDS)

    raise MidiError(
        f"MIDI polling timeout (last_status={last_status!r}) — 按未知终态安全失败，需人工审计 item={item_id}"
    )


# ── 下载 zip ──────────────────────────────────────────────────────────────

async def download_midi_zip(midi_url: str, dest_dir: str) -> str:
    """流式下载 midi.zip（硬上限 256MB）；返回本地 zip 路径。midi_url 按原样使用。"""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    zip_path = dest / "midi_result.zip"
    total = 0
    async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
        async with client.stream("GET", midi_url) as resp:
            if resp.status_code != 200:
                raise MidiError(f"midi zip download HTTP {resp.status_code}")
            declared = resp.headers.get("Content-Length")
            if declared and int(declared) > MIDI_ZIP_MAX_BYTES:
                raise MidiError("midi zip exceeds size cap")
            with open(zip_path, "wb") as fh:
                async for chunk in resp.aiter_bytes(1 << 16):
                    total += len(chunk)
                    if total > MIDI_ZIP_MAX_BYTES:
                        raise MidiError("midi zip exceeds size cap (stream)")
                    fh.write(chunk)
    if total < 512:
        raise MidiError("midi zip too small / empty")
    # zip 完整性校验（非音频 → 不做 ffprobe；成员白名单待真实联调后补充，本轮不猜）
    with zipfile.ZipFile(zip_path) as zf:
        names = [i.filename for i in zf.infolist() if not i.is_dir()]
        bad = [n for n in names if n.startswith(("/", "\\")) or ".." in n.split("/")]
        if bad:
            raise MidiError(f"midi zip contains unsafe member names: {bad[:3]}")
        if not names:
            raise MidiError("midi zip has no files")
        logger.info("[midi] task zip downloaded bytes=%d members=%d", total, len(names))
    return str(zip_path)


# ── R2 产物上传 + 清理 ────────────────────────────────────────────────────

async def upload_midi_to_r2(task_id: str, zip_path: str) -> dict[str, str]:
    """midi.zip → 私有 R2（music/{task_id}/midi.zip），返回 manifest 片段。"""
    from app.services.cdn_uploader import cdn_uploader

    key = f"music/{task_id}/midi.zip"
    await cdn_uploader.upload_private(zip_path, key)
    logger.info("[midi] task=%s uploaded r2_key=%s", task_id, key)
    return {"midi_zip": key}


async def cleanup_midi_input(task_id: str, input_ext: str = ".mp3") -> None:
    """删除本次任务的 R2 输入对象（幂等 best-effort，绝不抛出）。"""
    from app.services.cdn_uploader import cdn_uploader
    for ext in {input_ext, ".wav", ".mp3", ".flac"}:
        try:
            cdn_uploader.delete_object(f"midi/{task_id}/input{ext}")
        except Exception:  # noqa: BLE001
            pass


# ── 编排入口 ──────────────────────────────────────────────────────────────

async def run_midi_task(task_id: str, input_local_path: str) -> dict[str, str]:
    """端到端编排：提交 → 轮询 → 下载 → zip 校验 → 上传 R2 → 清理输入对象。

    返回 manifest 片段（含 "midi_zip": R2 key）；任何失败抛 MidiError
    （上层负责退款与状态，与 run_stems_task 同边界）。
    """
    item_id = await submit_midi(input_local_path, task_id)
    try:
        midi_url = await poll_midi(item_id, task_id)
        with tempfile.TemporaryDirectory(prefix=f"midi_{task_id}_") as tmp:
            zip_path = await download_midi_zip(midi_url, tmp)
            manifest = await upload_midi_to_r2(task_id, zip_path)
    finally:
        # 输入对象无论成败都清理（幂等）
        ext = os.path.splitext(input_local_path)[1].lower() or ".mp3"
        await cleanup_midi_input(task_id, ext)
    return manifest
