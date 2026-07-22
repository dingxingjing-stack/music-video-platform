"""音频分离异步网关客户端 - 对接 Modal.com Worker
说明：
- Render 免费实例 不再加载任何 AI 模型
- 所有 4 轨分离推理全部转发至 Modal 免费算力
- 使用 X-API-Key 头部鉴权（密钥在 Modal Secret 与 Render 环境变量中保持一致）
"""
import asyncio
import base64
from typing import Dict
import httpx
from app.core.config import get_settings

settings = get_settings()
MODAL_URL = settings.MODAL_WORKER_URL.rstrip("/")
MODAL_API_KEY = settings.MODAL_WORKER_API_KEY
TIMEOUT = httpx.Timeout(30.0, read=300.0)   # Modal 冷启动可能需要较长时间


class DemucsService:
    """占位类（保留旧 import 路径，实际功能 = HTTP 客户端）"""

    async def call_modal_worker(
        self,
        original_url: str,
        max_retries: int = 3,
        retry_delay: float = 5.0,
    ) -> Dict[str, bytes]:
        """调用 Modal Worker 进行分离，返回 4 轨 WAV bytes
        兼容旧方法名 call_hf_worker（指向同一函数）
        """
        if not MODAL_URL or not MODAL_API_KEY:
            raise RuntimeError("环境变量 MODAL_WORKER_URL / MODAL_WORKER_API_KEY 未配置")

        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                    # 1. 下载原音频
                    print(f"[Modal-Client] 下载原音频: {original_url}")
                    orig_resp = await client.get(original_url)
                    if orig_resp.status_code != 200:
                        raise RuntimeError(f"下载原音频失败: {orig_resp.status_code}")
                    orig_bytes = orig_resp.content
                    file_name = original_url.split("/")[-1] or "audio.wav"
                    mime = orig_resp.headers.get("content-type") or "audio/wav"

                    # 2. POST 至 Modal Worker
                    print(f"[Modal-Client] 调用 Modal {MODAL_URL}/separate (第 {attempt} 次)")
                    resp = await client.post(
                        f"{MODAL_URL}/separate",
                        files={"file": (file_name, orig_bytes, mime)},
                        headers={"X-API-Key": MODAL_API_KEY},
                    )
                    if resp.status_code != 200:
                        raise RuntimeError(f"Modal 返回 {resp.status_code}: {resp.text[:200]}")

                    data = resp.json()
                    if not data.get("success"):
                        raise RuntimeError(f"Modal 失败: {data.get('message', '')}")

                    # 3. base64 → bytes
                    stems_b64 = data.get("stems", {})
                    stems_bytes: Dict[str, bytes] = {}
                    for name in ("vocals", "drums", "bass", "other"):
                        b64 = stems_b64.get(name)
                        if not b64:
                            raise RuntimeError(f"Modal 响应缺少 {name} 轨道")
                        stems_bytes[name] = base64.b64decode(b64)

                    print(f"[Modal-Client] ✅ 收到 {len(stems_bytes)} 个轨道")
                    return stems_bytes

            except (httpx.TimeoutException, httpx.ConnectError, RuntimeError) as e:
                msg = str(e)
                if attempt >= max_retries:
                    raise RuntimeError(f"重试 {max_retries} 次后仍失败: {msg}")
                print(f"[Modal-Client] ⚠️ 第 {attempt} 次失败: {msg}, {retry_delay}s 后重试")
                await asyncio.sleep(retry_delay)
            except Exception as e:
                raise RuntimeError(f"Modal Worker 调用异常: {e}")

    # 兼容原方法名（audio_processing.py 可继续使用旧名）
    async def call_hf_worker(self, *args, **kwargs):
        return await self.call_modal_worker(*args, **kwargs)

    def get_available_models(self):
        return ["htdemucs", "htdemucs_ft", "htdemucs_6s"]


# 全局实例
demucs_service = DemucsService()
