"""TempolorStemsService — 天谱乐 Stems v2 分轨分离服务（4 stems + original）。

P2 正式实施（2026-10-01 授权）：
- Provider：天谱乐 / TemPolor 开放平台（api.tianpuyue.cn），**不传 model**（实测默认档 =
  Stems v2 = 35 创作点 = 4 分离轨 + original）。
- 本服务只负责 provider 交互与产物加工：提交 → 轮询 → 下载 zip → 安全解压 →
  ffprobe 校验 → 上传 R2（私有）→ 返回 manifest。
- **不 reserve / 不 refund / 不改 quota / 不写任务状态**（Credits 与任务状态全部
  在上层 ai_music.py 的既有机制中处理，不创建第二套 Credits/任务系统）。

已实证契约（2026-10-01 真实联调，P2-REAL-PROBE）：
- 创建：POST /open-apis/v1/stems  body={"url": <公网可 GET>, "callback_url": <必填>}
  → HTTP 200 + {"status": 200000, "data": {"item_ids": ["mss_…"]}}；**不传 model**。
- 查询：POST /open-apis/v1/stems/query  body={"item_ids": ["…"]}
  ⚠️ 官方 Apifox 文档写 GET ?item_ids[]=… 但生产实测 GET=405、`item_ids[]` 键名 /
  表单 = 400003，**唯一可用 = POST JSON {"item_ids":[…]}**——禁止按旧文档实现。
  业务码字段名是 `status`（非 `code`），成功 200000。
- 回调 payload：{"stems": [{"item_id", "status", "stems_url"}]}；我方须回字符串 "success"。
- 产物：stems_url 指向 zip（实测 210s 音频 = 81MB），内含 5 个 FLAC：
  originalaudio.flac / originalaudio_vocals.flac / originalaudio_bass.flac /
  originalaudio_drums.flac / originalaudio_other.flac，全部 44.1kHz/2ch/16bit。
- 鉴权：Authorization: <裸 Key>（无 Bearer 前缀，与 tempolor_provider 同款）。
- 任务耗时实测约 1 分钟级（210s 输入）。

状态策略（真实联调仅观测到 succeeded，完整 enum 未知）：
  已知成功 'succeeded' → 明确成功；
  已知失败 {'failed', 'failed_', 'cancelled'} → 明确失败；
  已知进行中 {'pending','queued','running','processing'} → 继续轮询；
  未知状态 → 一律当作潜在非终态继续轮询（受 deadline 约束），超时统一安全失败
  （由上层退款），绝不把未知状态当成功。

安全红线：
- API Key 绝不写入日志（所有日志只打 item_id/字节数/状态码）。
- stems_url 是第三方签名 URL：仅服务端一次性下载，绝不入库为用户可见 URL，
  绝不剥离其 auth_key 查询串（按原样 GET）。
- zip 解压：成员名精确白名单 + 拒绝目录/symlink/绝对路径/..；解压总量硬上限；
  逐成员流式写出（不使用 extractall）→ 天然免疫 zip-slip。
- ffprobe 校验：codec=flac、时长一致性（max-min ≤ 2s）、采样率/声道合理、
  大小与 zip 成员一致、非空。ffprobe 不可用 = 校验失败 = 任务失败（fail-closed）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import stat
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

logger = logging.getLogger(__name__)

# ── 复用既有单一事实源（不修改 tempolor_provider 的 Song 逻辑）──────────────
from app.services.tempolor_provider import (  # noqa: E402
    TEMPOLOR_BASE_URL,
    callback_secret as _song_callback_secret,
)

# ── 配置（全部来自既有环境变量，无新增 env 需求）──────────────────────────
STEMS_TIMEOUT_SECONDS = float(os.getenv("STEMS_TIMEOUT_SECONDS", "480"))
STEMS_FIRST_POLL_DELAY_SECONDS = float(os.getenv("STEMS_FIRST_POLL_DELAY_SECONDS", "20"))
STEMS_POLL_INTERVAL_SECONDS = float(os.getenv("STEMS_POLL_INTERVAL_SECONDS", "3"))

# 输入 URL 的 presigned TTL（授权建议 3600s；R2 客户端已显式 s3v4）
STEMS_INPUT_PRESIGN_TTL_SECONDS = int(os.getenv("STEMS_INPUT_PRESIGN_TTL_SECONDS", "3600"))

# zip 下载/解压硬上限
STEMS_ZIP_MAX_BYTES = 256 * 1024 * 1024        # 压缩包本身
STEMS_UNCOMPRESSED_MAX_BYTES = 512 * 1024 * 1024  # 解压总量（zip bomb 防护）

# ffprobe 时长一致性容差（秒）：实测 5 轨逐样本一致，2s 为安全余量
STEMS_DURATION_TOLERANCE_SECONDS = 2.0

# ── 状态集合（见模块 docstring 的安全策略）────────────────────────────────
_STEMS_SUCCESS_STATUSES = {"succeeded"}
_STEMS_FAILURE_STATUSES = {"failed", "failed_", "cancelled"}
_STEMS_POLLING_STATUSES = {"pending", "queued", "running", "processing"}

# ── 产物成员精确白名单：zip 内成员名 → Melovar manifest 逻辑名 ─────────────
# 授权要求「只接受预期产物」：任何其他成员（多一个都不行）→ 整体失败。
EXPECTED_ZIP_MEMBERS: dict[str, str] = {
    "originalaudio.flac": "original",
    "originalaudio_vocals.flac": "vocals",
    "originalaudio_bass.flac": "bass",
    "originalaudio_drums.flac": "drums",
    "originalaudio_other.flac": "other",
}
# 必需分轨（缺任一 → 任务失败并退款；original 不属于必需分轨，但也必须存在——
# 由 EXPECTED_ZIP_MEMBERS 全集匹配保证）
REQUIRED_STEM_KEYS = ("vocals", "drums", "bass", "other")


class StemsError(Exception):
    """Stems 任务失败（提交/轮询/下载/解压/校验任一环节）。消息可安全上抛（不含 Key）。"""


# ── 鉴权 / 回调 URL ──────────────────────────────────────────────────────

def _api_key() -> str:
    """惰性读取 API Key（env 优先，secrets 兜底；与 tempolor_provider._api_key 同构）。"""
    key = os.getenv("TEMPOLOR_API_KEY")
    if key and key.strip():
        return key.strip()
    try:
        from app.core.secrets import get_secret
        v = get_secret("TEMPOLOR_API_KEY", required=False)
        return (v or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _derive_stems_callback_path(base_url: str) -> str:
    """从 Song callback URL 派生 Stems callback URL（不修改 TEMPOLOR_CALLBACK_URL 语义）。

    Song：…/api/v1/ai/tempolor/callback → Stems：…/api/v1/ai/tempolor/stems/callback
    不匹配 "/callback" 结尾的配置 → fail-closed（拒绝提交，绝不猜 URL）。
    """
    trimmed = base_url.rstrip("/")
    if trimmed.endswith("/callback"):
        return trimmed[: -len("/callback")] + "/stems/callback"
    raise StemsError(
        "TEMPOLOR_CALLBACK_URL 配置无法派生 Stems 回调地址（需以 /callback 结尾），已拒绝提交"
    )


def effective_stems_callback_url() -> str:
    """Stems callback URL = 派生路径 + 共享令牌 query（复用 Song 的 callback_secret）。"""
    base = (os.getenv("TEMPOLOR_CALLBACK_URL") or "").strip()
    if not base:
        return ""
    stems_url = _derive_stems_callback_path(base)
    secret = _song_callback_secret()
    if not secret:
        return stems_url  # 未配密钥：端点侧 fail-closed（503），与 Song 行为一致
    parts = urlsplit(stems_url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "token"]
    query.append(("token", secret))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _headers() -> dict:
    key = _api_key()
    if not key:
        raise StemsError("TEMPOLOR_API_KEY 未配置")
    # 官方鉴权为「裸 API Key」，无 Bearer 前缀
    return {"Authorization": key, "Content-Type": "application/json"}


def _check_business_code(data: dict, context: str) -> None:
    """业务码校验：字段名是 status（非 code！），200000=成功。"""
    biz = data.get("status") if isinstance(data, dict) else None
    if biz is not None and biz != 200000:
        msg = str(data.get("message") or "")[:120]
        raise StemsError(f"Stems API business error status={biz} ({context}) message={msg}")


# ── 提交 ─────────────────────────────────────────────────────────────────

# P4-B2 Phase A-17：Stems v3（8 轨）model 字符串官方文档未给出 ——
# 中国站 /open-apis/v1/stems 创建任务文档（464626891e0）body 仅 url+callback_url，
# 无 model 字段；定价页（8859398m0）确认 v3 档位存在（100 创作点，8 轨）但 API 层
# 未暴露选择方式。按授权铁律：MODEL_ID_UNVERIFIED，禁止写入任何猜测字符串。
# v3 提交的唯一开关 = 环境变量 TEMPOLOR_STEMS_V3_MODEL_ID（官方确认后配置）；
# 未配置时 v3 请求在上层 fail-closed（503 stems_v3_model_unverified），零供应商调用。
STEMS_V3_MODEL_ENV = "TEMPOLOR_STEMS_V3_MODEL_ID"


def stems_v3_model_id() -> str:
    """读取官方确认后的 Stems v3 model 字符串（未配置返回空串 = v3 不可用）。"""
    return (os.getenv(STEMS_V3_MODEL_ENV) or "").strip()


def stems_v3_zip_members() -> dict[str, str]:
    """官方/实测确认后的 V3 zip 成员白名单（"flac名:逻辑名,..." 环境变量解析）。

    V3 的 zip 成员名官方未公布 → 未实测确认前返回空 dict（上层 fail-closed 拒绝
    提交），绝不猜测成员名。配置示例（确认后）：
      TEMPOLOR_STEMS_V3_ZIP_MEMBERS="x_vocals.flac:vocals,x_lead.flac:lead,..."
    """
    raw = (os.getenv("TEMPOLOR_STEMS_V3_ZIP_MEMBERS") or "").strip()
    if not raw:
        return {}
    out: dict[str, str] = {}
    for pair in raw.split(","):
        if ":" in pair:
            member, logical = pair.split(":", 1)
            member = member.strip()
            logical = logical.strip()
            if member and logical:
                out[member] = logical
    return out


async def submit_stems(input_local_path: str, task_id: str,
                       model: Optional[str] = None) -> str:
    """上传输入文件到私有 R2 → 签发 SigV4 presigned GET(3600s) → 提交 Stems 任务。

    model：None/空 = v2 默认档（不传 model，实测契约）；非空 = 显式附带 model 字段
    （仅用于 v3 官方确认后的字符串，禁止猜测值）。任何失败抛 StemsError（上层统一退款）。
    """
    from app.services.cdn_uploader import cdn_uploader

    # 1) 输入文件 → 私有 R2（用户/任务隔离路径 stems/{task_id}/…）
    ext = os.path.splitext(input_local_path)[1].lower() or ".wav"
    input_key = f"stems/{task_id}/input{ext}"
    await cdn_uploader.upload_private(input_local_path, input_key)
    logger.info("[stems] task=%s input uploaded r2_key=%s", task_id, input_key)

    # 2) presigned GET（显式 TTL=3600s；cdn_uploader 的 R2 client 已显式 s3v4）
    input_url = cdn_uploader.get_presigned_download_url(
        input_key, expires_in=STEMS_INPUT_PRESIGN_TTL_SECONDS
    )

    # 3) 提交（v2 默认档不传 model —— 实测默认档即 Stems v2 4 轨）
    callback_url = effective_stems_callback_url()
    if not callback_url:
        raise StemsError("TEMPOLOR_CALLBACK_URL 未配置：callback_url 官方强制非空，已拒绝提交")

    payload = {"url": input_url, "callback_url": callback_url}
    if model and model.strip():
        payload["model"] = model.strip()
    headers = _headers()
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{TEMPOLOR_BASE_URL}/open-apis/v1/stems", headers=headers, json=payload
        )
        if resp.status_code != 200:
            # 不回显 body 全文（防意外泄露），只记状态码与截断片段
            logger.warning("[stems] submit HTTP %s task=%s", resp.status_code, task_id)
            raise StemsError(f"Stems submit HTTP {resp.status_code}")
        data = resp.json() if resp.content else {}
        _check_business_code(data, "submit")
        item_ids = (data.get("data") or {}).get("item_ids") if isinstance(data.get("data"), dict) else None
        if not isinstance(item_ids, list) or not item_ids:
            raise StemsError("Stems submit response missing item_ids")
        item_id = str(item_ids[0])
        logger.info("[stems] task=%s submitted item=%s", task_id, item_id)
        return item_id


# ── 轮询 ─────────────────────────────────────────────────────────────────

async def poll_stems(item_id: str, task_id: str) -> str:
    """轮询 POST /stems/query（禁止 GET）直到已知终态；返回 stems_url。

    - 首查延迟 20s（官方建议），随后 3s 间隔；deadline 内未终态 → StemsError（超时）。
    - 未知状态：按安全策略继续轮询（见模块 docstring），绝不当作成功。
    """
    headers = _headers()
    deadline = time.monotonic() + STEMS_TIMEOUT_SECONDS
    await asyncio.sleep(STEMS_FIRST_POLL_DELAY_SECONDS)
    last_status: Optional[str] = None
    async with httpx.AsyncClient(timeout=60.0) as client:
        while time.monotonic() < deadline:
            resp = await client.post(
                f"{TEMPOLOR_BASE_URL}/open-apis/v1/stems/query",
                headers=headers,
                json={"item_ids": [item_id]},  # ⚠️ 唯一已验证契约：POST JSON
            )
            if resp.status_code != 200:
                logger.warning("[stems] query HTTP %s item=%s", resp.status_code, item_id)
                await asyncio.sleep(STEMS_POLL_INTERVAL_SECONDS)
                continue
            data = resp.json() if resp.content else {}
            try:
                _check_business_code(data, "query")
            except StemsError as exc:
                # 400008/400009 等：作品不存在/状态异常 → 不可恢复，立即失败
                if "status=400008" in str(exc) or "status=400009" in str(exc):
                    raise
                logger.warning("[stems] query transient business error item=%s: %s", item_id, exc)
                await asyncio.sleep(STEMS_POLL_INTERVAL_SECONDS)
                continue
            stems = (data.get("data") or {}).get("stems") if isinstance(data.get("data"), dict) else None
            entry = stems[0] if isinstance(stems, list) and stems and isinstance(stems[0], dict) else {}
            status = entry.get("status")
            last_status = status if isinstance(status, str) else last_status

            if status in _STEMS_SUCCESS_STATUSES:
                stems_url = entry.get("stems_url")
                if not stems_url:
                    raise StemsError("Stems succeeded but response has no stems_url")
                logger.info("[stems] item=%s succeeded", item_id)
                return str(stems_url)
            if status in _STEMS_FAILURE_STATUSES:
                raise StemsError(f"Stems task failed (status={status})")
            # 已知进行中 / 未知状态 → 继续轮询（deadline 兜底）
            await asyncio.sleep(STEMS_POLL_INTERVAL_SECONDS)

    raise StemsError(
        f"Stems polling timeout (last_status={last_status!r}) — 按未知终态安全失败，需人工审计 item={item_id}"
    )


# ── 下载 zip ──────────────────────────────────────────────────────────────

async def download_stems_zip(stems_url: str, dest_dir: str) -> str:
    """流式下载 stems zip（硬上限 256MB）；返回本地 zip 路径。stems_url 按原样使用。"""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    zip_path = dest / "stems_result.zip"
    total = 0
    async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
        async with client.stream("GET", stems_url) as resp:
            if resp.status_code != 200:
                raise StemsError(f"stems zip download HTTP {resp.status_code}")
            declared = resp.headers.get("Content-Length")
            if declared and int(declared) > STEMS_ZIP_MAX_BYTES:
                raise StemsError("stems zip exceeds size cap")
            with open(zip_path, "wb") as fh:
                async for chunk in resp.aiter_bytes(1 << 16):
                    total += len(chunk)
                    if total > STEMS_ZIP_MAX_BYTES:
                        raise StemsError("stems zip exceeds size cap (stream)")
                    fh.write(chunk)
    if total < 1024:
        raise StemsError("stems zip too small / empty")
    logger.info("[stems] task zip downloaded bytes=%d", total)
    return str(zip_path)


# ── 安全解压 + ffprobe 校验 ───────────────────────────────────────────────

def _is_symlink_member(info: zipfile.ZipInfo) -> bool:
    """zip 成员的 unix mode 是否为 symlink（zip-slip / 任意链接写入防护）。"""
    unix_mode = info.external_attr >> 16
    return stat.S_ISLNK(unix_mode) if unix_mode else False


def extract_and_validate_stems(zip_path: str, dest_dir: str,
                               expected_members: Optional[dict[str, str]] = None) -> dict[str, str]:
    """安全解压并校验 FLAC，返回 {逻辑名: 本地文件路径}。

    expected_members：None/空 = V2 官方实测白名单 EXPECTED_ZIP_MEMBERS（5 成员）；
    V3 须传入实测确认后的成员映射（stems_v3_zip_members()），为空时上层已拒绝提交。
    安全规则（任一违反 → StemsError，绝不部分成功）：
    - 成员名必须与期望映射精确相等（多/少/改名都不行）；
    - 拒绝目录条目 / symlink / 绝对路径 / 含 '..' 的成员；
    - 解压总量硬上限 512MB；逐成员流式写出（不用 extractall）；
    - ffprobe：codec=flac、时长>0 且各轨互差 ≤2s、采样率≥8k、声道 1-2、
      解压后大小与成员声明一致且 >0。
    - 必需分轨 = 期望映射中非 "original" 的全部逻辑名，缺任一 → 失败。
    """
    members_map = expected_members or EXPECTED_ZIP_MEMBERS
    # 必需分轨 = 期望映射中非 "original" 的逻辑名（V2: vocals/drums/bass/other）
    required_keys = tuple(v for v in members_map.values() if v != "original")
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        by_name = {i.filename: i for i in infos}
        unexpected = [i.filename for i in infos if i.filename not in members_map]
        if unexpected:
            raise StemsError(f"stems zip contains unexpected members: {unexpected[:3]}")
        missing = [name for name in members_map if name not in by_name]
        if missing:
            raise StemsError(f"stems zip missing expected members: {missing}")

        total_uncompressed = sum(i.file_size for i in infos)
        if total_uncompressed > STEMS_UNCOMPRESSED_MAX_BYTES:
            raise StemsError("stems zip uncompressed total exceeds cap")

        extracted: dict[str, str] = {}
        for member_name, logical in members_map.items():
            info = by_name[member_name]
            if info.is_dir() or _is_symlink_member(info):
                raise StemsError(f"stems zip member is dir/symlink: {member_name}")
            if info.filename.startswith(("/", "\\")) or ".." in info.filename.split("/"):
                raise StemsError(f"stems zip member has unsafe path: {member_name}")
            out_path = dest / member_name  # 精确白名单名，无用户可控成分
            written = 0
            with zf.open(info, "r") as src, open(out_path, "wb") as fh:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > info.file_size:  # 实际写出超出声明 → 异常 zip
                        raise StemsError(f"stems member size mismatch: {member_name}")
                    fh.write(chunk)
            if written != info.file_size or written <= 0:
                raise StemsError(f"stems member empty/short: {member_name}")
            extracted[logical] = str(out_path)

    # ── ffprobe 校验（fail-closed：ffprobe 缺失 = 校验失败）────────────────
    probe_results: dict[str, dict] = {}
    for logical, path in extracted.items():
        probe_results[logical] = _probe_flac(path)

    durations = []
    for logical, meta in probe_results.items():
        if meta.get("codec") != "flac":
            raise StemsError(f"stem {logical} is not FLAC (codec={meta.get('codec')})")
        dur = meta.get("duration") or 0.0
        if not (0 < dur <= 3600):
            raise StemsError(f"stem {logical} invalid duration {dur}")
        if int(meta.get("sample_rate") or 0) < 8000:
            raise StemsError(f"stem {logical} invalid sample_rate")
        if int(meta.get("channels") or 0) not in (1, 2):
            raise StemsError(f"stem {logical} invalid channels")
        durations.append(dur)

    if max(durations) - min(durations) > STEMS_DURATION_TOLERANCE_SECONDS:
        raise StemsError(
            f"stems duration mismatch: max={max(durations):.2f} min={min(durations):.2f}"
        )

    missing_required = [k for k in required_keys if k not in extracted]
    if missing_required:
        raise StemsError(f"required stems missing: {missing_required}")

    logger.info(
        "[stems] extracted+validated 5 flac (duration=%.2f-%.2fs)",
        min(durations), max(durations),
    )
    return extracted


def _probe_flac(path: str) -> dict:
    """ffprobe 单文件元数据（codec/duration/sample_rate/channels）。不可用即抛错。"""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise StemsError("ffprobe not available — 音频校验 fail-closed")
    cmd = [
        ffprobe, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired as exc:
        raise StemsError(f"ffprobe timeout on {os.path.basename(path)}") from exc
    if proc.returncode != 0:
        raise StemsError(f"ffprobe failed on {os.path.basename(path)}")
    try:
        data = json.loads(proc.stdout)
        stream = (data.get("streams") or [{}])[0]
        fmt = data.get("format") or {}
        return {
            "codec": stream.get("codec_name"),
            "duration": float(fmt.get("duration") or stream.get("duration") or 0),
            "sample_rate": int(stream.get("sample_rate") or 0),
            "channels": int(stream.get("channels") or 0),
        }
    except (ValueError, TypeError, IndexError) as exc:
        raise StemsError(f"ffprobe output unparseable for {os.path.basename(path)}") from exc


# ── R2 产物上传 + 清理 ────────────────────────────────────────────────────

async def upload_stems_to_r2(task_id: str, extracted: dict[str, str],
                             include_original: bool = True) -> dict[str, str]:
    """5 个本地 FLAC → 私有 R2（music/{task_id}/{logical}.flac），返回 manifest 片段。

    复用 cdn_uploader.upload_music_package（私有对象 + 预签名下载链路）。
    """
    from app.services.cdn_uploader import cdn_uploader

    files = {k: v for k, v in extracted.items() if include_original or k != "original"}
    manifest = await cdn_uploader.upload_music_package(task_id, files)
    logger.info("[stems] task=%s uploaded r2 keys=%s", task_id, sorted(manifest.keys()))
    return manifest


async def cleanup_stems_input(task_id: str, input_ext: str = ".wav") -> None:
    """删除本次任务的 R2 输入对象（幂等 best-effort，绝不抛出）。"""
    from app.services.cdn_uploader import cdn_uploader
    for ext in {input_ext, ".wav", ".mp3", ".flac"}:
        try:
            cdn_uploader.delete_object(f"stems/{task_id}/input{ext}")
        except Exception:  # noqa: BLE001
            pass


# ── 编排入口 ──────────────────────────────────────────────────────────────

async def run_stems_task(task_id: str, input_local_path: str,
                         include_original: bool = True,
                         model: Optional[str] = None,
                         expected_members: Optional[dict[str, str]] = None) -> dict[str, str]:
    """端到端编排：提交 → 轮询 → 下载 → 解压校验 → 上传 R2 → 清理输入对象。

    model 透传给 submit_stems（v2 不传；v3 仅在官方确认后由上层 env 门禁放行）。
    expected_members 透传给解压校验（V2 默认官方白名单；V3 须实测确认映射）。
    返回 manifest 片段 {logical: R2 key}；任何失败抛 StemsError（上层负责退款与状态）。
    """
    item_id = await submit_stems(input_local_path, task_id, model=model)
    try:
        stems_url = await poll_stems(item_id, task_id)
        with tempfile.TemporaryDirectory(prefix=f"stems_{task_id}_") as tmp:
            zip_path = await download_stems_zip(stems_url, tmp)
            extracted = extract_and_validate_stems(
                zip_path, tmp, expected_members=expected_members,
            )
            manifest = await upload_stems_to_r2(task_id, extracted, include_original=include_original)
    finally:
        # 输入对象无论成败都清理（幂等）
        ext = os.path.splitext(input_local_path)[1].lower() or ".wav"
        await cleanup_stems_input(task_id, ext)
    return manifest
