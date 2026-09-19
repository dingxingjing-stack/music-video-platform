"""TempolorProvider — 天谱乐开放平台（api.tianpuyue.cn）音乐生成 Provider。

Phase：将 TemPolor v4.7（tempolor-latest）接入 Provider 抽象，供枚举选择与
生产切换使用，默认不改动现有 fallback 链（RunPod/Fal 仍为兜底）。

职责边界（与 YinchaoProvider / MurekaProvider 一致，严格）：
- 只负责天谱乐官方 API 两段式调用：
    POST /open-apis/v1/song/generate  → 提交，拿到 data.item_ids[]
    POST /open-apis/v1/song/query     → 轮询，直到终态 → 下载 mp3/wav
- 失败/未知状态一律返回 success=False，交由上层 ProviderRegistry /
  ai_music.py 依次接管，**不实现跨 Provider fallback**。
- **不 reserve / 不 refund / 不修改 quota**（额度全在上层 ai_limits）。
- **不发送 duration**（官方 generate 无 duration 参数，长度由歌词/模型决定）。
- 不把第三方 audio_url 直接暴露给前端；本地下载后仅暴露 _local_path 给上层 R2 流程，
  保持现有 `Provider URL → 下载 → R2 → 预签名` 的既有链路不变。

天谱乐官方契约（以 platform.tianpuyue.cn/docs 为准）：
- 鉴权：`Authorization: <api_key>`（裸 Key，无 Bearer 前缀）。
- 提交响应：`{status:200000, message:"success", request_id, data:{item_ids:[...]}}`
- 查询：POST body `{"item_ids": [...]}` → `data.songs[]`，每首含
  status / audio_url(mp3,3天) / audio_hi_url(wav) / duration / item_id。
- 状态全集：running / main_succeeded / succeeded / failed / part_failed。
- callback_url 为必填字段；本 Provider 依赖轮询时仍需传该字段（由环境变量提供），
  但结果以 query 轮询为准，不依赖外部回调。

本文件不引用 legacy 服务，二者独立。
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from app.services.provider_registry import BaseProvider
from app.services.model_registry import NoValidModelError, select_music_model

logger = logging.getLogger(__name__)

# ── 环境变量（不做模块级 required，避免缺 Key 导致启动失败）──
# 官方固定地址；Base URL 不做无谓的 env 化。
TEMPOLOR_BASE_URL = (os.getenv("TEMPOLOR_BASE_URL") or "https://api.tianpuyue.cn").rstrip("/")
TEMPOLOR_MODEL = os.getenv("TEMPOLOR_MODEL", "tempolor-latest")
TEMPOLOR_TIMEOUT_SECONDS = float(os.getenv("TEMPOLOR_TIMEOUT_SECONDS", "360"))
TEMPOLOR_POLL_INTERVAL_SECONDS = float(os.getenv("TEMPOLOR_POLL_INTERVAL_SECONDS", "3"))
# callback_url 官方强制非空（2026-09-18 中国站实测：空串被 HTTP 200 + 业务码 400003
# "callback_url not blank" 拒绝）。未配置时 generate() 直接返回明确配置缺失错误，
# 零 HTTP 提交、绝不发送占位假 URL。
TEMPOLOR_CALLBACK_URL = (os.getenv("TEMPOLOR_CALLBACK_URL") or "").strip()

# 官方歌词/提示词上限（超出安全截断）
PROMPT_MAX_CHARS = 1000
LYRICS_MAX_CHARS = 3000

# 歌曲语言 code → 英文语言名（Prompt 指令用）。
# 来源：天谱乐 TemPolor 官方文档明确列出的支持语种；仅收录官方明确列出的 11 种，
# 不自行猜测其他语种。code 与前端 frontend/src/config/songLanguages.ts 保持一致。
_SONG_LANGUAGE_NAMES: dict[str, str] = {
    "zh": "Chinese",
    "yue": "Cantonese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "ru": "Russian",
    "es": "Spanish",
    "de": "German",
    "fr": "French",
    "it": "Italian",
    "pt": "Portuguese",
}

# 官方 task 状态（data.songs[] 中 status；来源 platform.tianpuyue.cn/docs）
_POLLING_STATUSES = {"running", "pending", "queued", "preparing"}
_SUCCESS_STATUSES = {"succeeded", "main_succeeded"}
_FAILURE_STATUSES = {"failed", "failed_", "cancelled"}


def local_dir() -> str:
    """与 yinchao_provider / mureka_provider / runpod_client 一致的生成目录（GENERATED_DIR）。"""
    return os.getenv(
        "GENERATED_DIR",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "generated"),
    )


def _download_audio(url: str, dest_dir: Optional[str] = None) -> Optional[str]:
    """下载天谱乐音频 URL 到本地生成目录，返回本地绝对路径；失败返回 None。

    按 URL 后缀保留真实扩展名（mp3 优先，wav 次之），不把一种格式改名成另一种。
    """
    dest = Path(dest_dir or local_dir())
    dest.mkdir(parents=True, exist_ok=True)
    suffix = ".mp3"
    if url:
        low = url.lower().split("?")[0]
        for ext in (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"):
            if low.endswith(ext):
                suffix = ext
                break
    out_path = dest / f"tempolor_{int(time.time() * 1000)}{suffix}"
    try:
        # 天谱乐音频 URL 带 auth_key 签名；按原样 GET，不得剥离查询串。
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            resp = client.get(url)
        if resp.status_code != 200:
            logger.warning("[tempolor] 音频下载失败: HTTP %s", resp.status_code)
            return None
        data = resp.content
        if not data or len(data) < 1000:
            logger.warning("[tempolor] 音频过小或为空 (%d bytes)", len(data) if data else 0)
            return None
        out_path.write_bytes(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[tempolor] 音频下载异常: %s", exc)
        return None
    logger.info("[tempolor] 音频已下载: %s (%d bytes)", out_path, out_path.stat().st_size)
    return str(out_path)


class TempolorProvider(BaseProvider):
    """天谱乐（TemPolor）官方 API Provider（text_to_music / lyrics_to_music）。"""

    name = "tempolor"
    provider_type = "api"
    capabilities = ["text_to_music", "lyrics_to_music", "instrumental"]
    # 官方最新模型对 prompt 生歌最长 5 分钟；但单次实际长度由歌词结构决定，
    # max_duration 仅作能力上界声明，不参与计价/截断。
    max_duration = 300
    gpu = "tempolor-cloud"
    production = True

    # ── 内部工具 ────────────────────────────────────────────

    def _api_key(self) -> str:
        """惰性读取 API Key（缺 Key 不崩溃，返回空串交由 generate 判空）。"""
        key = os.getenv("TEMPOLOR_API_KEY")
        if key and key.strip():
            return key.strip()
        try:
            from app.core.secrets import get_secret
            v = get_secret("TEMPOLOR_API_KEY", required=False)
            return (v or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    async def health_check(self) -> dict:
        return {"healthy": bool(self._api_key()), "provider": self.name}

    # ── 主逻辑 ──────────────────────────────────────────────

    async def generate(self, request: dict) -> dict:
        """调用天谱乐生成歌曲；失败一律返回 success=False，由上层 fallback 接管。"""
        api_key = self._api_key()
        if not api_key:
            return {"success": False, "error": "TEMPOLOR_API_KEY 未配置", "provider": self.name}

        prompt = (request.get("prompt") or "").strip()
        if not prompt:
            return {"success": False, "error": "Tempolor requires prompt", "provider": self.name}

        # callback_url 官方校验非空；配置缺失属于我方部署问题，明确报错、零提交、不发假 URL
        if not TEMPOLOR_CALLBACK_URL:
            return {"success": False, "non_retryable": True,
                    "error": "TEMPOLOR_CALLBACK_URL 未配置：天谱乐官方要求 callback_url 非空（实测空串返回 400003）。请配置 Zyvexo 生产回调地址",
                    "provider": self.name}

        # ── 歌曲语言（独立于 UI locale）：TemPolor 无 language API 参数，
        #    故把 song_language 映射为该语言英文名，拼到 prompt 作为语言指令。
        #    绝不修改/翻译用户提供的 lyrics（lyrics 是什么语言就唱什么语言）。──
        song_language = (request.get("song_language") or "").strip()
        if song_language:
            lang_name = _SONG_LANGUAGE_NAMES.get(song_language.lower())
            if lang_name:
                prompt = f"{prompt}\n\nSong language: {lang_name}"

        prompt = prompt[:PROMPT_MAX_CHARS]

        lyrics = (request.get("lyrics") or "").strip()
        lyrics = lyrics[:LYRICS_MAX_CHARS]

        # ── 模型选择（Phase 2B：Provider ≠ Model，数据驱动最低总成本路由）──
        # 官方口径：Tempolor i 系列专门用于纯音乐生成；tempolor-latest 面向人声。
        # 中国站无 Extend 端点：目标时长超过模型上限直接失败（NO_VALID_MODEL），
        # 不做假续写。api model ID 未确认的模型禁止提交（不猜字符串）。
        is_instrumental = bool(request.get("is_instrumental")) or (
            str(request.get("type", "")).lower() in ("music", "bgm", "instrumental")
        )
        model = (request.get("model") or "").strip()
        model_cost_cny: Optional[float] = None
        model_key: Optional[str] = None
        if not model:
            env_override = os.getenv("TEMPOLOR_MODEL")
            if env_override and not is_instrumental:
                model = env_override
            else:
                try:
                    sel = select_music_model(
                        music_type="instrumental" if is_instrumental else "vocal",
                        target_duration=int(request.get("duration") or 180),
                        lyrics_provided=bool(lyrics),
                    )
                except NoValidModelError as exc:
                    return {"success": False, "non_retryable": True,
                            "error": f"Tempolor {exc}", "provider": self.name}
                if not sel.model.id_confirmed or not sel.model.api_model_id:
                    return {"success": False, "non_retryable": True,
                            "error": f"Tempolor model {sel.model.key} api id UNCONFIRMED（待联调确认）",
                            "provider": self.name}
                model = sel.model.api_model_id
                model_key = sel.model.key
                model_cost_cny = sel.total_cost_cny

        # 提交请求体（官方 contract）
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "callback_url": TEMPOLOR_CALLBACK_URL,
        }
        if lyrics:
            payload["lyrics"] = lyrics
        if is_instrumental:
            payload["instrumental"] = True

        # 天谱乐官方鉴权为「裸 API Key」，无 Bearer 前缀
        headers = {
            "Authorization": api_key,
            "Content-Type": "application/json",
        }

        submit_url = f"{TEMPOLOR_BASE_URL}/open-apis/v1/song/generate"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # 1) 提交
                resp = await client.post(submit_url, headers=headers, json=payload)
                if resp.status_code != 200:
                    return self._map_submit_error(resp)

                data = resp.json() if resp.content else {}
                # HTTP 200 ≠ 成功：官方在响应体内返回业务码（200000=成功，4000xx=失败）。
                # 不解析会把 400002/400003 等伪装成"提交响应缺少 item id"。
                biz = data.get("status") if isinstance(data, dict) else None
                if biz is not None and biz != 200000:
                    return self._map_business_error(biz, data.get("message"))
                item_ids = data.get("data", {}).get("item_ids") if isinstance(data.get("data"), dict) else None
                if not item_ids:
                    item_ids = data.get("item_ids")
                if not isinstance(item_ids, list) or not item_ids:
                    logger.warning("[tempolor] 提交响应缺少 item_ids: %s", str(data)[:300])
                    return {"success": False, "error": "Tempolor 提交响应缺少 item id", "provider": self.name}
                item_id = item_ids[0]
                logger.info("[tempolor] item=%s 已提交 (model=%s)", item_id, model)

                # 2) 轮询（POST /song/query，body item_ids 列表）
                query_url = f"{TEMPOLOR_BASE_URL}/open-apis/v1/song/query"
                deadline = time.monotonic() + TEMPOLOR_TIMEOUT_SECONDS
                while time.monotonic() < deadline:
                    await asyncio.sleep(TEMPOLOR_POLL_INTERVAL_SECONDS)
                    q = await client.post(
                        query_url,
                        headers=headers,
                        json={"item_ids": [item_id]},
                    )
                    if q.status_code != 200:
                        logger.warning("[tempolor] query HTTP %s", q.status_code)
                        continue
                    qdata = q.json() if q.content else {}
                    # 查询同样先验业务码（如 400002 Key 失效 / 400008 作品不存在），
                    # 不解析会把终态错误拖到轮询超时才暴露
                    qbiz = qdata.get("status") if isinstance(qdata, dict) else None
                    if qbiz is not None and qbiz != 200000:
                        return self._map_business_error(qbiz, qdata.get("message"))
                    songs = qdata.get("data", {}).get("songs") if isinstance(qdata.get("data"), dict) else None
                    song = songs[0] if isinstance(songs, list) and songs and isinstance(songs[0], dict) else {}
                    status = song.get("status")

                    if status in _SUCCESS_STATUSES:
                        audio_url = song.get("audio_url") or song.get("audio_hi_url")
                        if not audio_url:
                            return {"success": False, "error": "Tempolor 响应无可用音频 URL", "provider": self.name}
                        local_path = await asyncio.to_thread(_download_audio, audio_url)
                        if not local_path:
                            return {"success": False, "error": "Tempolor 音频下载失败", "provider": self.name}
                        fname = os.path.basename(local_path)
                        return {
                            "success": True,
                            "volume_files": {
                                "full_mp3": fname,
                                "full_wav": fname,
                                "_local_path": local_path,
                                "_tempolor_url": audio_url,
                                "_item_id": item_id,
                                "_duration": song.get("duration"),
                                "_model": model,
                                "_model_key": model_key,
                                "_model_cost_cny": model_cost_cny,
                            },
                            "provider": self.name,
                        }

                    if status in _FAILURE_STATUSES:
                        err = song.get("error") or "task failed"
                        logger.warning("[tempolor] item=%s fail error=%s", item_id, err)
                        return {"success": False, "error": f"Tempolor task failed: {err}", "provider": self.name}

                    if status in _POLLING_STATUSES:
                        continue

                    # 未知 status：停止轮询，不当作进行态（与 Mureka/Yinchao 同策略）
                    logger.warning("[tempolor] item=%s 未知 status=%s → 停止轮询", item_id, status)
                    return {"success": False, "error": f"Tempolor unknown task status: {status}", "provider": self.name}

                return {"success": False, "error": "Tempolor polling timeout", "provider": self.name}

        except httpx.TimeoutException:
            return {"success": False, "error": "Tempolor request timeout", "provider": self.name}
        except Exception as exc:  # noqa: BLE001
            # 绝不把 API Key / Authorization 写入日志
            logger.warning("[tempolor] 生成异常: %s", exc)
            return {"success": False, "error": f"Tempolor generation error: {exc}", "provider": self.name}

    # HTTP 200 业务错误码 → (中文语义, 是否 non_retryable/禁止切 Provider)。
    # 码表逐字依据 platform.tianpuyue.cn/docs/8859400m0.md（2026-09-18 核验）。
    # 400005/400006/400007 属可恢复/资源类错误：不标 non_retryable，维持既有上层
    # retry 与 fallback 语义（本轮不改动策略）。
    _BUSINESS_ERRORS: dict[int, tuple[str, bool]] = {
        400002: ("API Key 校验失败", True),
        400003: ("请求参数错误", True),
        400004: ("内容违规，已拒绝", True),
        400005: ("余额/创作点不足", False),
        400006: ("服务器繁忙", False),
        400007: ("并行任务超限", False),
        400008: ("作品不存在", True),
        400009: ("作品状态异常", True),
        400010: ("当前模型不支持此功能", True),
        400011: ("当前作品不支持续写", True),
    }

    def _map_business_error(self, code, message=None) -> dict:
        """HTTP 200 + JSON 业务码错误的明确识别（禁止伪装成 missing item id）。"""
        known = self._BUSINESS_ERRORS.get(code) if isinstance(code, int) else None
        if known:
            zh, non_retryable = known
            err = f"Tempolor API error code={code}: {zh}"
        else:
            err = f"Tempolor API error code={code}"
            non_retryable = False
        # 不回显完整 body（与既有安全策略一致），message 仅截断透传
        if message:
            err += f" message={str(message)[:120]}"
        logger.warning("[tempolor] %s", err)
        result = {"success": False, "error": err, "provider": self.name}
        if isinstance(code, int):
            result["error_code"] = code
        if non_retryable:
            result["non_retryable"] = True
        return result

    def _map_submit_error(self, resp: httpx.Response) -> dict:
        """把提交阶段 HTTP 错误映射为 provider failure（不内部无限 retry，不泄露 Secret）。"""
        err = f"Tempolor submit HTTP {resp.status_code}"
        try:
            body = resp.text[:300]
        except Exception:  # noqa: BLE001
            body = ""
        if resp.status_code == 400:
            err = "Tempolor 请求参数错误（400）"
        elif resp.status_code == 401:
            err = "TEMPOLOR_API_KEY 无效或未授权（401）"
        elif resp.status_code == 403:
            err = "Tempolor 区域/权限限制（403）"
        elif resp.status_code == 402 or resp.status_code == 429:
            low = body.lower()
            if any(k in low for k in ("quota", "credit", "balance", "余额", "额度", "points")):
                err = "Tempolor 余额/配额不足（402/429 quota）"
            else:
                err = "Tempolor 限流（429 rate limit）"
        elif resp.status_code == 503:
            err = "Tempolor 引擎过载（503）"
        result = {"success": False, "error": err, "provider": self.name}
        if resp.status_code == 400:
            # 参数类错误：换 Provider 同样会被判错、徒耗其额度 → 标记不可重试/不可切换
            result["non_retryable"] = True
        logger.warning("[tempolor] %s", err)
        return result