"""YinchaoProvider — 音潮开放平台（open.yinchaoyongxian.com）音乐生成 Provider。

阶段 B：按 operation 功能化为四种提交模式（合同均来自官方文档只读抓取，
零猜测、零真实 API 调用验证于本阶段）：
    normal          → POST /api/v1/song/generate        task_type=normal   model=v4.0
    lyric_to_music  → POST /api/v1/song/generate        task_type=normal   model=v4.0 + lyric（用户歌词原样透传）
    instrumental    → POST /api/v1/song/instrumental    model=v4.0（官方指南：/docs/guides/instrumental-generate）
    reference       → POST /api/v1/file/upload (upload_type=reference) → id
                      → POST /api/v1/song/generate      task_type=reference model=v3.5
                        reference_audio={audio_type:upload_id, audio_content:id}
                        similarity∈[0.2,0.8,1.3,1.5]（缺省 0.8；官方 /docs/guides/reference-generate）

职责边界（严格，与 MurekaProvider 一致）：
- 只负责音潮官方 API 两段式调用：
    提交（上列端点之一）→ task_id → GET /api/v1/task/query?task_id= 轮询 → 下载音频
- 失败/未知状态一律返回 success=False，交由上层 chain_for_operation() 链与
  ai_music.py 依次接管；参数/认证/内容类错误标 non_retryable（禁止切换 Provider）。
- **不 reserve / 不 refund / 不修改 quota**（额度全在上层 ai_limits）。
- **不实现跨 Provider fallback**。
- **不发送 duration**（音潮 generate 系端点无 duration 参数；时长由官方模型决定）。
- 不把音潮第三方 audio_url 返回给前端；本地下载后仅暴露 _local_path 给上层 R2 流程。

本文件不依赖 yinchao_test.py；二者各自独立。
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from app.services.provider_registry import BaseProvider

logger = logging.getLogger(__name__)

# ── 环境变量（不做模块级 required，避免缺 Key 导致启动失败）──
YINCHAO_BASE_URL = (os.getenv("YINCHAO_API_BASE_URL") or "https://open.yinchaoyongxian.com").rstrip("/")
YINCHAO_TIMEOUT_SECONDS = float(os.getenv("YINCHAO_TIMEOUT_SECONDS", "240"))
YINCHAO_POLL_INTERVAL_SECONDS = float(os.getenv("YINCHAO_POLL_INTERVAL_SECONDS", "3"))

# 官方 task 状态（choices[0].status；来自真实 API 实测）
_POLLING_STATUSES = {"pending", "running", "stream"}
_SUCCESS_STATUSES = {"done"}
_FAILURE_STATUSES = {"fail"}

# 参考音频上传官方限制（/docs/api-reference/file/file-upload-post：仅 MP3/WAV，≤10MB）
_REFERENCE_UPLOAD_MAX_BYTES = 10 * 1024 * 1024
# similarity 官方枚举（/docs/api-reference/song/song-generate-post：[0.2, 0.8, 1.3, 1.5]）
_REFERENCE_SIMILARITY_VALUES = (0.2, 0.8, 1.3, 1.5)
_DEFAULT_SIMILARITY = 0.8


def local_dir() -> str:
    """与 mureka_provider / runpod_client / fal_client 一致的生成目录（GENERATED_DIR）。"""
    return os.getenv(
        "GENERATED_DIR",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "generated"),
    )


def _download_audio(url: str, dest_dir: Optional[str] = None) -> Optional[str]:
    """下载音潮音频 URL 到本地生成目录，返回本地绝对路径；失败返回 None。

    不假设文件格式，按 URL 后缀保留真实扩展名；不把一种格式改名成另一种。
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
    out_path = dest / f"yinchao_{int(time.time() * 1000)}{suffix}"
    try:
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            resp = client.get(url)
        if resp.status_code != 200:
            logger.warning("[yinchao] 音频下载失败: HTTP %s", resp.status_code)
            return None
        data = resp.content
        if not data or len(data) < 1000:
            logger.warning("[yinchao] 音频过小或为空 (%d bytes)", len(data) if data else 0)
            return None
        out_path.write_bytes(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[yinchao] 音频下载异常: %s", exc)
        return None
    logger.info("[yinchao] 音频已下载: %s (%d bytes)", out_path, out_path.stat().st_size)
    return str(out_path)


def _decode_reference_audio(ref: str) -> Optional[tuple[bytes, str, str]]:
    """把请求里的 base64 参考音频解码为 (bytes, 扩展名, mime)；失败返回 None。

    支持 data URL 前缀与裸 base64；格式按 magic bytes 识别（RIFF/WAVE → wav，
    ID3/MPEG 帧同步 → mp3），识别不了时以 octet-stream + .bin 提交（由官方
    upload 端点裁决格式，不在本地臆造格式）。
    """
    s = (ref or "").strip()
    if s.lower().startswith("data:"):
        comma = s.find(",")
        if comma == -1:
            return None
        s = s[comma + 1:]
    if not s:
        return None
    try:
        raw = base64.b64decode(s, validate=False)
    except Exception:  # noqa: BLE001
        return None
    if not raw:
        return None
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WAVE":
        return raw, "wav", "audio/wav"
    if raw[:3] == b"ID3" or (len(raw) >= 2 and raw[0] == 0xFF and (raw[1] & 0xE0) == 0xE0):
        return raw, "mp3", "audio/mpeg"
    return raw, "bin", "application/octet-stream"


class YinchaoProvider(BaseProvider):
    """音潮开放平台 API Provider（阶段 B：normal / lyric_to_music / instrumental / reference）。"""

    name = "yinchao"
    provider_type = "api"
    capabilities = ["text_to_music", "lyrics_to_music", "instrumental", "audio2audio"]
    # 音潮 V4.0 generate 无 duration 参数，不声明 max_duration（保留基类默认 0）。
    gpu = "yinchao-cloud"
    production = True

    # ── 内部工具 ────────────────────────────────────────────

    def _api_key(self) -> str:
        """惰性读取 API Key（缺 Key 不崩溃，返回空串交由 generate 判空）。"""
        key = os.getenv("YINCHAO_API_KEY")
        if key and key.strip():
            return key.strip()
        try:
            from app.core.secrets import get_secret
            v = get_secret("YINCHAO_API_KEY", required=False)
            return (v or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    async def health_check(self) -> dict:
        return {"healthy": bool(self._api_key()), "provider": self.name}

    # ── 主逻辑 ──────────────────────────────────────────────

    async def generate(self, request: dict) -> dict:
        """按 operation 调用音潮生成歌曲；失败一律返回 success=False，由上层 fallback 接管。

        参数/认证/内容类错误标 non_retryable：同错必现，切换 Provider 只会徒耗其额度。
        """
        api_key = self._api_key()
        if not api_key:
            # 认证配置错误 → 禁止 fallback（阶段 B 路由协议）
            return {"success": False, "non_retryable": True,
                    "error": "YINCHAO_API_KEY is not configured", "provider": self.name}

        prompt = (request.get("prompt") or "").strip()
        if not prompt:
            # 缺 prompt → non_retryable（官方 400「歌词和提示词不能均为空值」同错必现）
            return {"success": False, "non_retryable": True,
                    "error": "Yinchao requires prompt", "provider": self.name}

        operation = str(request.get("operation") or "normal").strip() or "normal"
        lyrics = (request.get("lyrics") or "").strip()

        if operation == "reference":
            return await self._generate_reference(api_key, prompt, lyrics, request)
        if operation == "instrumental":
            # 官方指南 /docs/guides/instrumental-generate：POST /api/v1/song/instrumental
            payload: dict[str, Any] = {"model": "v4.0", "prompt": prompt, "n": 1}
            submit_url = f"{YINCHAO_BASE_URL}/api/v1/song/instrumental"
        elif operation == "lyric_to_music":
            # 用户歌词原样透传（lyric 字段，官方 API 参考）；不切 AI 写词
            payload = {"model": "v4.0", "task_type": "normal",
                       "prompt": prompt, "n": 1}
            if lyrics:
                payload["lyric"] = lyrics
            submit_url = f"{YINCHAO_BASE_URL}/api/v1/song/generate"
        elif operation == "normal":
            # 既有固定提交：task_type=normal 由音潮自动写词，不映射 lyrics
            payload = {"model": "v4.0", "task_type": "normal",
                       "prompt": prompt, "n": 1}
            submit_url = f"{YINCHAO_BASE_URL}/api/v1/song/generate"
        else:
            # 未知 operation：零猜测提交，直接判错
            return {"success": False, "non_retryable": True,
                    "error": f"Yinchao unsupported operation: {operation}", "provider": self.name}

        return await self._submit_and_poll(api_key, payload, submit_url)

    async def _generate_reference(
        self, api_key: str, prompt: str, lyrics: str, request: dict,
    ) -> dict:
        """仿写（reference）：官方合同（/docs/guides/reference-generate，只读抓取）。

        - similarity：官方枚举 [0.2, 0.8, 1.3, 1.5]；缺省填 0.8；显式非法 →
          non_retryable，零提交。
        - 参考音频：base64 → POST /api/v1/file/upload（upload_type=reference）→ id
          → reference_audio={audio_type: "upload_id", audio_content: id}。
        - 上传或提交的参数/认证类错误 → non_retryable；超时/5xx → 可重试可切换。
        """
        similarity = request.get("similarity")
        if similarity is None or similarity == "":
            similarity = _DEFAULT_SIMILARITY
        else:
            try:
                similarity_f = float(similarity)
            except (TypeError, ValueError):
                return {"success": False, "non_retryable": True,
                        "error": f"Yinchao similarity 非法：{similarity!r}", "provider": self.name}
            if similarity_f not in _REFERENCE_SIMILARITY_VALUES:
                return {"success": False, "non_retryable": True,
                        "error": f"Yinchao similarity 无效：{similarity_f}（官方枚举 0.2/0.8/1.3/1.5）",
                        "provider": self.name}
            similarity = similarity_f

        ref = request.get("reference_audio")
        if not isinstance(ref, str) or not ref.strip():
            return {"success": False, "non_retryable": True,
                    "error": "Yinchao reference 缺少 reference_audio", "provider": self.name}
        decoded = _decode_reference_audio(ref)
        if decoded is None:
            return {"success": False, "non_retryable": True,
                    "error": "Yinchao reference_audio base64 解码失败", "provider": self.name}
        raw, ext, mime = decoded
        if len(raw) > _REFERENCE_UPLOAD_MAX_BYTES:
            return {"success": False, "non_retryable": True,
                    "error": "Yinchao reference_audio 超过官方 10MB 上传限制", "provider": self.name}

        upload_id, upload_err = await self._upload_reference_audio(api_key, raw, ext, mime)
        if upload_err is not None:
            return upload_err

        payload: dict[str, Any] = {
            "model": "v3.5",
            "task_type": "reference",
            "prompt": prompt,
            "reference_audio": {"audio_type": "upload_id", "audio_content": upload_id},
            "similarity": similarity,
            "n": 1,
        }
        if lyrics:
            payload["lyric"] = lyrics
        submit_url = f"{YINCHAO_BASE_URL}/api/v1/song/generate"
        return await self._submit_and_poll(api_key, payload, submit_url)

    async def _upload_reference_audio(
        self, api_key: str, raw: bytes, ext: str, mime: str,
    ) -> tuple[Optional[str], Optional[dict]]:
        """POST /api/v1/file/upload（upload_type=reference）→ (upload_id, error_result)。

        恰好返回一个非 None：成功给 upload_id，失败给 provider error dict。
        """
        url = f"{YINCHAO_BASE_URL}/api/v1/file/upload"
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    url, headers=headers,
                    data={"upload_type": "reference"},
                    files={"file": (f"reference.{ext}", raw, mime)},
                )
        except httpx.TimeoutException:
            # TODO(阶段 B 后续)：上传超时不存在已建生成任务，可安全重试/切换
            return None, {"success": False, "error": "Yinchao 参考音频上传超时", "provider": self.name}
        except Exception as exc:  # noqa: BLE001
            logger.warning("[yinchao] 参考音频上传异常: %s", exc)
            return None, {"success": False, "error": f"Yinchao 参考音频上传异常: {exc}", "provider": self.name}

        if resp.status_code != 200:
            logger.warning("[yinchao] 参考音频上传失败 http=%s", resp.status_code)
            err = {"success": False, "error": f"Yinchao 参考音频上传 HTTP {resp.status_code}", "provider": self.name}
            if resp.status_code == 400:
                err["non_retryable"] = True
                err["error"] = "Yinchao 参考音频上传参数错误（400：仅支持 MP3/WAV 且 ≤10MB）"
            elif resp.status_code in (401, 403):
                err["non_retryable"] = True
                err["error"] = f"Yinchao 参考音频上传认证/权限错误（{resp.status_code}）"
            return None, err

        try:
            data = resp.json() if resp.content else {}
        except Exception:  # noqa: BLE001
            data = {}
        upload_id = data.get("id") if isinstance(data, dict) else None
        if not upload_id:
            logger.warning("[yinchao] 上传响应缺少 id: %s", str(data)[:300])
            return None, {"success": False, "error": "Yinchao 上传响应缺少文件 id", "provider": self.name}
        logger.info("[yinchao] 参考音频已上传 upload_id=%s", upload_id)
        return str(upload_id), None

    async def _submit_and_poll(self, api_key: str, payload: dict, submit_url: str) -> dict:
        """通用两段式：提交 → 轮询 /api/v1/task/query → 下载（normal/instrumental/reference 共用）。"""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # 1) 提交
                resp = await client.post(submit_url, headers=headers, json=payload)
                if resp.status_code != 200:
                    return self._map_submit_error(resp)

                data = resp.json() if resp.content else {}
                task_id = data.get("id") if isinstance(data, dict) else None
                if not task_id:
                    logger.warning("[yinchao] 提交响应缺少 id: %s", str(data)[:300])
                    return {"success": False, "error": "Yinchao 提交响应缺少 task id", "provider": self.name}

                logger.info("[yinchao] task=%s 已提交", task_id)

                # 2) 轮询
                query_url = f"{YINCHAO_BASE_URL}/api/v1/task/query"
                deadline = time.monotonic() + YINCHAO_TIMEOUT_SECONDS
                while time.monotonic() < deadline:
                    await asyncio.sleep(YINCHAO_POLL_INTERVAL_SECONDS)
                    q = await client.get(query_url, params={"task_id": task_id}, headers=headers)
                    if q.status_code != 200:
                        logger.warning("[yinchao] query HTTP %s", q.status_code)
                        continue
                    qd = q.json() if q.content else {}
                    choices = qd.get("choices") if isinstance(qd, dict) else None
                    choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
                    status = choice.get("status")

                    if status in _SUCCESS_STATUSES:
                        audio_url = choice.get("audio_url")
                        if not audio_url:
                            return {"success": False, "error": "Yinchao response contains no downloadable audio URL", "provider": self.name}
                        local_path = await asyncio.to_thread(_download_audio, audio_url)
                        if not local_path:
                            return {"success": False, "error": "Yinchao 音频下载失败", "provider": self.name}
                        fname = os.path.basename(local_path)
                        return {
                            "success": True,
                            "volume_files": {
                                # 音潮实际返回 mp3：full_mp3/full_wav 均指向真实文件，
                                # 不伪造 WAV、不改扩展名；上层 _upload_and_finalize 优先用 _local_path。
                                "full_mp3": fname,
                                "full_wav": fname,
                                "_local_path": local_path,
                                "_yinchao_url": audio_url,
                            },
                            "provider": self.name,
                        }

                    if status in _FAILURE_STATUSES:
                        err_code = choice.get("error_code")
                        err = choice.get("error") or "task failed"
                        logger.warning("[yinchao] task=%s fail code=%s error=%s", task_id, err_code, err)
                        return {
                            "success": False,
                            "error": f"Yinchao task failed ({err_code} {err})" if err_code else f"Yinchao task failed: {err}",
                            "provider": self.name,
                        }

                    if status in _POLLING_STATUSES:
                        continue

                    # 未知 status：停止轮询，不当作进行态（与 MurekaProvider 同策略）
                    logger.warning("[yinchao] task=%s 未知 status=%s → 停止轮询", task_id, status)
                    return {"success": False, "error": f"Yinchao unknown task status: {status}", "provider": self.name}

                # TODO(阶段 B 后续)：轮询超时可能已建付费任务；按协议保持现安全行为
                #（不标 non_retryable、不新增退款语义），待引入「任务已建→禁止切换」探测。
                return {"success": False, "error": "Yinchao polling timeout", "provider": self.name}

        except httpx.TimeoutException:
            # TODO(阶段 B 后续)：提交/轮询超时可能已建任务；保持现安全行为（可重试/可切换）。
            return {"success": False, "error": "Yinchao request timeout", "provider": self.name}
        except Exception as exc:  # noqa: BLE001
            # 绝不把 API Key / Authorization 写入日志；exc 本身不含 Key
            logger.warning("[yinchao] 生成异常: %s", exc)
            return {"success": False, "error": f"Yinchao generation error: {exc}", "provider": self.name}

    def _map_submit_error(self, resp: httpx.Response) -> dict:
        """把提交阶段 HTTP 错误映射为 provider failure（不内部无限 retry，不泄露 Secret）。"""
        err = f"Yinchao submit HTTP {resp.status_code}"
        try:
            body = resp.text[:300]
        except Exception:  # noqa: BLE001
            body = ""
        # quota_exhausted：额度/配额类耗尽。与 non_retryable 不同 —— 它只表示
        # 「在本 Provider 上重试无意义」，上层会立即切到链中下一个 Provider
        # （天谱乐），实现「音潮额度用完 → 走天谱乐」。绝不标 non_retryable，
        # 否则会中止整条链、连天谱乐都到不了。
        quota_exhausted = False
        if resp.status_code == 401:
            err = "YINCHAO_API_KEY 无效或未授权（401）"
        elif resp.status_code == 400:
            err = "Yinchao 请求参数错误（400）"
        elif resp.status_code == 403:
            err = "Yinchao 区域/权限限制（403）"
        elif resp.status_code == 402:
            err = "Yinchao 余额不足（402）"
            quota_exhausted = True
        elif resp.status_code == 429:
            low = body.lower()
            if any(k in low for k in ("quota", "credit", "balance", "余额", "额度")):
                err = "Yinchao 配额耗尽（429 quota）"
                quota_exhausted = True
            else:
                err = "Yinchao 限流（429 rate limit）"
        elif resp.status_code == 503:
            err = "Yinchao 引擎过载（503）"
        # 不把完整 body 写日志（可能含敏感内容），只记录状态码
        logger.warning("[yinchao] submit 失败 http=%s", resp.status_code)
        result = {"success": False, "error": err, "provider": self.name}
        if resp.status_code == 400:
            # 参数类错误：不得 fallback 到其他 Provider（同错必现、徒耗其额度）
            result["non_retryable"] = True
        elif resp.status_code in (401, 403):
            # 认证/权限配置错误（阶段 B）：切换 Provider 属于掩盖配置问题 → 禁止 fallback
            result["non_retryable"] = True
        if quota_exhausted:
            result["quota_exhausted"] = True
        return result