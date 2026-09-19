# Mureka API 契约审计与 Phase API-2 实施方案

> 生成时间：本次会话
> 权威来源：`https://platform.mureka.ai/docs`（Quickstart、Error codes、FAQ、Changelog、各 Operation 页面）
> **本文件是本项目 Mureka 集成的唯一契约基准**。
> 仓库内 `mureka_service.py` 与 `inference/mureka.py` 仅供参考，不得作为契约来源。

---

## A. 官方 API 契约结论

### A.1 基础信息

| 项 | 值 | 来源 |
|----|----|------|
| **Base URL** | `https://api.mureka.ai` | Quickstart "Servers" 明确写出 |
| **认证方式** | `Authorization: Bearer <MUREKA_API_KEY>` | Quickstart curl 示例 |
| **内容类型** | `Content-Type: application/json` | Quickstart curl 示例 |
| **生成模式** | **异步任务**：提交 → 轮询查询 | Quickstart + Changelog "streaming mode" |

### A.2 核心端点

| 用途 | 方法/路径 | 说明 |
|------|-----------|------|
| **歌词生成歌曲** | `POST /v1/song/generate` | 主力：lyrics（必填）+ prompt/model（可选） |
| **纯器乐生成** | `POST /v1/instrumental/generate` | 仅 prompt/style |
| **任务轮询** | `GET /v1/song/query/{task_id}` | task_id = 生成接口返回的 `id` |
| **歌词生成** | `POST /v1/lyrics/generate` | 仅歌词 |
| **延长/识别/描述/转写/分轨/区域编辑/Remix** | `POST /v1/song/{extend,recognize,describe,transcribe,stem,region-edit,remix}` | 扩展功能 |
| **人声克隆** | `POST /v1/song/vocal-clone` | reference_id + vocal_id |
| **配乐/音轨** | `POST /v1/soundtrack/generate`, `POST /v1/track/generate` | 视频/音轨 |
| **音乐视频/歌词视频** | `POST /v1/video/generate`, `POST /v1/lyrics-video/generate` | 视频生成 |
| **TTS/播客** | `POST /v1/tts/generate`, `POST /v1/tts/podcast` | 语音 |
| **账单查询** | `GET /v1/account/billing` | 余额/用量 |

> 注：Prompt-to-song 的具体 endpoint 本阶段不视为已确认契约；后续如使用 Prompt-to-song，需要单独审计当前官方 Operation schema。

### A.3 请求字段（`/v1/song/generate`）

| 字段 | 类型 | 必填 | 说明 | 来源 |
|------|------|------|------|------|
| `lyrics` | string | ✅ 必填 | 歌词，含 `[Verse]`/`[Chorus]` 段落标记 | Quickstart |
| `model` | string | ⚠️ 可选，默认 `auto` | 模型名；可选 `auto`、`mureka-7.6`、`mureka-o2`、`mureka-8`、`mureka-9`、`mureka-9.5`；`auto` 用于选择最新 regular model | Quickstart + Changelog |
| `prompt` | string | ⚠️ 可选 | 风格/情绪提示词（如 `r&b, slow, passionate, male vocal`） | Quickstart |
| `n` | integer | ❌ | 输出数量（默认 2，最大 3） | Changelog 2025.9.1 |
| `gender` | string | ❌ | `male`/`female`（人声性别） | Changelog 2026.6.25 |
| `reference_id` | string | ❌ | 参考音频 ID（与 vocal_id 可同时使用） | Changelog 2025.4.18 |
| `vocal_id` | string | ❌ | 人声 ID（可与 prompt 同时控制） | Changelog 2026.1.5 |
| `melody_id` | string | ❌ | 旋律/伴奏 ID（midi 支持） | Changelog 2025.6.4 "melody purpose" |
| `stream` | boolean | ❌ | 是否启用流式返回 | Changelog 2025.7.29 "Streaming mode" |
| `duration` | integer | ❓ | **官方文档未出现**；Changelog 无记录 → **暂定不支持，实测确认** | — |

### A.4 生成响应（提交阶段）

```json
{
  "id": "1436211",
  "created_at": 1677610602,
  "model": "mureka-6",
  "status": "preparing",
  "trace_id": "1e94aba5a2de4cc4bff54a2813c8d36c"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | **任务 ID**，用于轮询 `/v1/song/query/{task_id}` |
| `created_at` | integer | Unix 时间戳（秒） |
| `model` | string | 实际使用模型名 |
| `status` | string | 初始状态，通常 `preparing` |
| `trace_id` | string | **必须记录**，供生产排查/支持 |

### A.5 轮询响应（`GET /v1/song/query/{task_id}`）

> 官方 SSR 将 schema 渲染为折叠控件，静态 HTML 无字段文本。Changelog 确认返回字段含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` / `created_at` / `model` / `status` / `trace_id` | 同上 | 同提交响应 |
| `wav_url` | string | **WAV 音频下载 URL**（Changelog 2025.12.9 "added a new field: wav_url"） |
| `audio_url` | string | MP3 音频下载 URL（同期同条） |
| `choices` | array | ✅ 官方确认：`choices: object[]`，成功状态时包含生成歌曲；具体音频 URL 嵌套结构当前实现采用防御性解析，最终字段结构留待实际 API 响应进一步确认 |
| `status` 终态值 | string | 官方确认状态：`preparing`, `queued`, `running`, `streaming`, `succeeded`, `failed`, `timeouted`, `cancelled` |

### A.6 流式模式（可选）

- `stream: true` 时返回 SSE，含 `stream_url`（生成结束后有效期再延 5 分钟，Changelog 2025.10.27）

### A.7 错误码（Error codes 页面权威）

| HTTP | 错误码/消息 | 含义 | 处理 |
|------|-------------|------|------|
| 400 | Invalid Request | 参数错误 | 修正请求参数 |
| 401 | Invalid Authentication | Key 无效/缺失 | 检查 `MUREKA_API_KEY` |
| 403 | Forbidden | 区域不支持 | 确保调用地域受支持 |
| 429 | Rate limit reached for requests | 并发/频率限制 | 按定价层并发限制降速重试 |
| 429 | You exceeded your current quota | 余额/额度耗尽 | 充值/购买更多 credits |
| 500 | Server error | 服务端异常 | 退避重试，必要时联系支持 |
| 503 | The engine is currently overloaded | 引擎过载/排队满 | 退避重试 |

错误响应体统一：
```json
{
  "error": { "message": "..." },
  "trace_id": "..."
}
```

### A.8 计费/商业授权（FAQ 页面权威）

| 项 | 说明 |
|----|------|
| **计费模式** | 一次性充值（Top-up），非订阅制；余额有效期 12 个月，每次充值续期 |
| **并发限制** | 充值档位决定并发任务数（5/10/更高） |
| **下载费用** | 免费；多轨分离需单独付费 |
| **商业授权** | **付费调用生成的内容拥有完整商业使用权** |
| **退款** | 不支持退款 |
| **账号体系** | API 平台与网页版会员/积分**不互通** |
| **技术支持** | `api-support@mureka.ai`，24h 响应 |

---

## B. 现有两个文件对照官方契约

### B.1 `backend/app/services/mureka_service.py`

| 代码位置/逻辑 | 与官方契约一致性 | 标记 | 备注 |
|----------------|------------------|------|------|
| `BASE_URL = "https://api.mureka.ai/v1"` | ❌ | URL 错误：官方 base 是 `https://api.mureka.ai`，`/v1` 是路径前缀，不在 host |
| `POST /song/generate` | ❌ | 路径错：官方是 `/v1/song/generate` |
| 请求字段 | ⚠️ | ⚠️ | - lyrics：必填 ✅ <br> - model：可选，默认 auto ✅ <br> - prompt：可选 ✅ <br> - style：不是官方 /v1/song/generate 字段 ❌ <br> - duration：不是当前官方 /v1/song/generate 字段 ❌ |
| 响应解析 `data.audio_url` 等 | ❌ | 官方返回 `{id, status, model, trace_id}`，**无 `audio_url`** |
| 同步假设：直接拿 URL 返回 | ❌ | 官方**异步任务**，需轮询 `/v1/song/query/{task_id}` |
| 模型名写死/臆造 `v9` | ❌ | 官方模型：`auto`/`mureka-6`/`mureka-7.6`/`mureka-o1`/`mureka-o2`/`mureka-9.5` 等 |
| 引入 `prompt_enhancer` / `audio_enhancement` / `nv_music_service` 兜底 | ⚠️ | 业务层增强/兜底，属**应用层逻辑**，不属于 Mureka API 契约 |
| `QuotaExceededError` 抛出触发 NVAPI 降级 | ⚠️ | 错误码 429 包含「quota」与「rate limit」两种，需区分处理 |
| `audio_post_processor` 本地后处理 | ❌ | 产物若需 R2 归档，应由上层 `cdn_uploader` 统一处理 |

**结论**：**整体不可用，需废弃/重写**。只能保留「业务层增强/兜底」思路供新 Provider 参考。

---

### B.2 `backend/app/services/inference/mureka.py`

| 代码位置/逻辑 | 与官方契约一致性 | 标记 | 备注 |
|----------------|------------------|------|------|
| `SUPPORTED_ENDPOINTS` 10 个端点 | ❌ | 全部臆造（`/music/generate`、`/bgm/generate`、`/tts/generate`、`/vocal-clone` 等），官方路径均为 `/v1/song/*`、`/v1/instrumental/*`、`/v1/tts/*` |
| `_MUREKA_MODEL = os.getenv("MUREKA_MODEL", "v9")` | ❌ | 官方默认 `auto`，无 `v9` |
| `predict()` 同步期待 `audio_url` | ❌ | 官方异步，需轮询 |
| payload 塞入 `num_songs`、`generate_lyrics` | ❌ | 官方字段：`n`（数量）、`gender`、`reference_id`、`vocal_id`、`melody_id`、`stream` |
| 继承 `BaseInferenceService` 但未接入生产 | ❌ | 生产走 `provider_registry` → RunPod/Fal，此文件属**死代码** |

**结论**：**不可用，不可作为 Mureka 集成入口**。生产集成应实现 `provider_registry.BaseProvider`。

---

## C. 文件处理建议

| 文件 | 建议 | 理由 |
|------|------|------|
| `mureka_service.py` | **LEGACY / NOT USED BY NEW PROVIDER**（暂不删除） | 契约全错；待 MurekaProvider 通过测试后，再全仓库确认引用后决定删除/归档 |
| `inference/mureka.py` | **LEGACY / NOT USED BY NEW PROVIDER**（暂不删除） | 死代码，端点/字段全错，未接入 registry；同上处理 |
| `prompt_enhancer.py` / `audio_enhancement.py` / `audio_post_processor.py` | **保留** | 业务层增强能力，新 Provider 可选择性复用 |
| `nv_music_service.py` / `fal_client.py` / `runpod_client.py` | **保留** | 现有 fallback provider 继续保留 |
| `provider_registry.py` | **扩展** | 新增 `MurekaProvider` 注册进 registry，设为生产主力 |
| `ai_limits.py` / `cdn_uploader.py` / `task_store.py` | **复用** | 额度、R2 上传、任务状态机均现成 |

---

## D. MurekaProvider 设计（仅设计，不写代码）

### D.1 架构位置

```text
用户请求
    ↓
POST /api/v1/ai/generate (ai_music.py)
    ↓
reserve_generation() 额度预留
    ↓
ProviderRegistry.select() → 返回 MurekaProvider (PRIMARY)
    ↓
MurekaProvider.generate(request: dict) -> dict
    ↓
Mureka 官方 API (api.mureka.ai)
    ├─ POST /v1/song/generate  → {id, status, ...}
    ├─ 轮询 GET /v1/song/query/{task_id} 直到终态
    └─ 取 wav_url / audio_url → 下载临时文件
    ↓
返回 volume_files 映射给上层
    ├─ full_wav (本地临时路径)
    ├─ full_mp3 (本地临时路径)
    └─ 可选 stems (若 Mureka 返回)
    ↓
ai_music.py → cdn_uploader.upload_music_package() → R2 私有
    ↓
任务 completed，写入 manifest + 预签名 URL
```

### D.2 实现 `BaseProvider` 契约

```python
class MurekaProvider(BaseProvider):
    name = "mureka"
    provider_type = "mureka_official"
    capabilities = ["text_to_music", "lyrics_to_music", "instrumental", "vocal_clone", "stream"]
    # 官方 /v1/song/generate 无 duration 参数，不声明 max_duration；产品端 300s 目标由上层控制
    gpu = "mureka-cloud"       # 标识用，不计费
    production = True          # 设为生产主力

    async def generate(self, request: dict) -> dict:
        # request 含：lyrics, prompt?, model?, n?, gender?, reference_id?, vocal_id?, melody_id?, stream?
        # 返回：{"success": bool, "volume_files": {"full_wav": local_path, "full_mp3": local_path, ...}, "error": str|None, "provider": "mureka"}
```

### D.3 内部流程细节

1. **提交**：
   - 构建请求体：仅传官方支持字段（`lyrics`/`prompt`/`model`/`n`/`gender`/`reference_id`/`vocal_id`/`melody_id`/`stream`）
   - 调用 `POST https://api.mureka.ai/v1/song/generate`（按需也可用 `instrumental/generate`；Prompt-to-song 的 endpoint 本阶段不视为已确认契约）
   - 拿到 `task_id = response["id"]`，记录 `trace_id`

2. **轮询**：
   - `GET /v1/song/query/{task_id}`，间隔 3-5s，指数退避，总超时 ≤ `MAX_TASK_RUNTIME_SECONDS` (900s)
   - 解析 `status`（仅使用官方确认值）：
     - 官方已确认的进行态：`preparing` / `queued` / `running` / `streaming` → 继续轮询
     - 官方已确认的成功终态：`succeeded` → 取 `wav_url` 优先，回退 `audio_url`
     - 官方已确认的失败/取消终态：`failed` / `timeouted` / `cancelled` → 抛异常上层触发退款
     - 未知 status：记录 task_id、trace_id、status，停止轮询，返回 provider_failed，不得把未知状态自动视为进行态
   - 防御性取音频字段：`wav_url` → `audio_url` → `choices[0].wav_url` 等；具体最终字段结构留待实际 API 响应进一步确认

3. **下载**：
   - 用 `httpx` 下载音频到本地临时文件（`tempfile.mkdtemp()`），文件名保留扩展名
   - 校验文件大小 > 1KB，避免空文件

4. **返回**：
   - `volume_files = {"full_wav": wav_path, "full_mp3": mp3_path_or_wav_path}`
   - 若 Mureka 返回 stems（需实测），追加 `vocals`/`drums`/`bass`/`other`

5. **错误映射**：
   - 400 → 请求参数错误，`validation_failed`（无退款）
   - 401/403 → 配置/地域错误，`provider_failed`（退款）
   - 429 (rate limit) → 退避重试（内部最多 2 次），仍失败 `request_not_sent`
   - 429 (quota) → `provider_failed`（退款），不自动降级，由上层 registry 选 fallback
   - 500/503 → 重试 1 次，仍失败 `provider_failed`（退款）

6. **流式模式**（可选 Phase 2+）：
   - `stream: true` 时解析 SSE，拿 `stream_url` 直接播放/下载，不走 R2 上传

### D.4 与现有 fallback 对接

`provider_registry.py` 现有 `select()` 逻辑：
- `ENVIRONMENT=production` → 默认 `runpod`
- 允许显式选择 `runpod`，禁止显式选择 `fal`/`modal_ace_step`

**改造**：
1. `ProviderRegistry.__init__` 里先注册 `MurekaProvider()`，**注册顺序第一** → `self._default = "mureka"`
2. `select()` 的 production 逻辑保持：**显式指定优先**，无显式时默认 `runpod`（现状）。
   - 要让 Mureka 成为生产默认，需在 `select()` 里对 `production` 环境显式返回 `mureka`，**或**通过环境变量 `AI_GENERATION_PROVIDER=mureka`（现有机制已支持）。
   - 建议：代码默认保持 `runpod`，**通过环境变量 `AI_GENERATION_PROVIDER=mureka` 切主力**（零代码改动、可随时回滚）。
3. fallback 链：`MurekaProvider.generate()` 抛异常 → `ai_music.py` 捕获 → 调用 `refund_generation()` → 上层已有的重试逻辑（`MAX_AUTO_RETRIES`）会自动再次 `provider_registry.select()` → 得到 `runpod` → 再试 → 失败再 `fal`。
   - 现有 `provider_registry` 的 `FalStableAudioProvider`/`RunPodProvider` 内部已实现相互 fallback，**无需改动**。

### D.5 配置项

| 环境变量 | 用途 | 默认值 |
|----------|------|--------|
| `MUREKA_API_KEY` | 必填，Bearer token | — |
| `MUREKA_BASE_URL` | 可选，覆盖官方 base | `https://api.mureka.ai` |
| `MUREKA_MODEL` | 可选，默认模型 | `auto` |
| `MUREKA_TIMEOUT` | 可选，请求超时秒 | `300` |
| `MUREKA_POLL_INTERVAL` | 可选，轮询间隔秒 | `3` |
| `AI_GENERATION_PROVIDER=mureka` | 设为生产主力 | — |

---

## E. Phase API-2 实施计划（下一轮执行范围）

### E.1 新增/修改文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/services/mureka_provider.py` | **新增** | 实现 `MurekaProvider(BaseProvider)`，含异步提交+轮询+下载 |
| `backend/app/services/provider_registry.py` | **修改** | `get_provider_registry()` 里注册 `MurekaProvider()`；保持现有 fallback 逻辑不变 |
| `backend/app/services/__init__.py` | **修改** | 导出 `mureka_provider`（可选） |
| `backend/.env.example` | **修改** | 新增 `MUREKA_API_KEY`/`MUREKA_BASE_URL`/`MUREKA_MODEL`/`MUREKA_TIMEOUT`/`MUREKA_POLL_INTERVAL` 说明 |
| `backend/.env` | **不改** | 由用户自行配置真实 Key |
| `docs/MUREKA_API_CONTRACT_AUDIT.md` | **追加** | 本文件内容合并入（已存在） |

### E.2 接口/注册位置

1. `provider_registry.py`：
   ```python
   from app.services.mureka_provider import MurekaProvider
   # 在 get_provider_registry() 内：
   _registry.register(MurekaProvider())  # 第一顺位注册
   ```
2. 无需修改 `ai_music.py`：它调用 `get_provider_registry().select()`，会自动拿到新 Provider。

### E.3 配置部署

- Render Environment Variables 新增 `MUREKA_API_KEY`（必填）、`MUREKA_MODEL=auto`、`AI_GENERATION_PROVIDER=mureka`（切主力）。
- 现有 `FAL_BUDGET_DAILY`/`RUNPOD_API_KEY` 保留不变。

### E.4 测试项目

需要在查看现有 `ai_music.py`、`provider_registry.py`、`reserve_generation`/`refund_generation` 实现后确定。

### E.5 风险与兜底

| 风险 | 兜底 |
|------|------|
| Mureka 异步轮询超时/状态未知 | `refund_generation(reason="timeout_unknown")`，不扣用户额度，global_usage 不退（成本保护） |
| 官方返回字段名与预期不符 | 防御性多键解析 + Phase API-3 实测确认后回写 |
| Mureka 地域/Key 问题 (403/401) | 启动时 `health_check()` 失败 → registry 标记 unhealthy → 自动跳过到 RunPod |
| 并发/额度耗尽 | 复用现有 `ai_limits` 全链路保护，无需新代码 |

---

## 本轮交付确认

✅ A. 官方 API 契约结论（含所有你列出的字段逐一标记来源/不确认）  
✅ B. 两个现有文件逐字段对照（✅/⚠️/❌/❓）  
✅ C. 文件处理建议（废弃/保留/扩展/复用）  
✅ D. MurekaProvider 设计（架构位置、契约、内部流程、fallback 对接、配置项）  
✅ E. Phase API-2 实施计划（文件清单、注册位置、配置、测试、风险兜底）

---

**下一轮（Phase API-2）开始条件**：你确认本方案无异议 → 我按 E.1/E.2/E.3 编写代码，**不改其他任何文件/配置/环境变量/Git**。