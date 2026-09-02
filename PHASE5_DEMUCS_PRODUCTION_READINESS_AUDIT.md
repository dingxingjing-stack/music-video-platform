# Phase 5 — Demucs Production Integration Readiness Audit

- 日期：2026-08-17
- 类型：READ-ONLY / DESIGN-ONLY（未修改任何生产代码）
- 前置验证：Phase 1-4 全部 PASS（Modal T4 / CUDA / PyTorch / Demucs 4.1.0 真实 4-stem 分离 / 稳定性 / 性能）

---

## 1. Separation 架构（现状审计）

文件：`backend/app/services/separation/`（Stage 2 隔离包，未接入任何生产路由）

| 文件 | 职责 |
|---|---|
| `base.py` | `SeparatorBackend` 抽象基类（`separate(input, model)` / `get_available_models()`，线程安全 RLock，懒加载）；`SeparationResult` dataclass：契约字段 `success/stems/duration/message` + 审计字段 `backend/model/fallback_used/fallback_reason/real_stems/derived_stems/missing_stems`；`STEM_NAMES=[vocals,drums,bass,other]` |
| `mdx_separator.py` | `MdxSeparator`：python-audio-separator + UVR_MDXNET_9482（2-stem），`real_stems=[vocals,instrumental]`，`derived=[other]`，`missing=[drums,bass]`（绝不虚假填充） |
| `spleeter_separator.py` | `SpleeterSeparator`：包装现有 `audio_separation_service.demucs_service`（生产在用 Modal Spleeter 四轨）作 fallback |
| `audio_separator_service.py` | `AudioSeparatorService` 统一门面：MDX 主 + Spleeter fallback；`separate()` / `separate_4stem()`；全局单例 |
| `models_license_audit.json` | 10 个模型条目，schema 1.0，2026-08-15 核验 |

关键事实：
- **服务路由**：生产 `/api/v1/ai/task/{id}/retry-stems` 走内部 `demucs_service`（实为 Modal Spleeter，见 `audio_separation_service.py` / `spleeter_modal.py`）；`/separate` HTTP 端点模型列表已禁用。
- **模型选择**：MDX 默认 UVR_MDXNET_9482；Spleeter 固定 `spleeter:4stems`。
- **fallback 行为**：MDX 失败 → Spleeter（`fallback_used=True` + 原因日志）。
- **错误处理**：所有 backend 返回 `SeparationResult.failure` 而非抛异常；超时用线程 join 实现。

## 2. Demucs 集成位置（设计结论）

- 新增 `backend/app/services/separation/demucs_separator.py`，实现 `SeparatorBackend`：
  - `backend_name = "demucs"`
  - 懒加载 `demucs.api.Separator(model="htdemucs", device="cuda:0")` + `model.to("cuda:0")`
  - `separate()` 返回 `SeparationResult`，`real_stems=[vocals,drums,bass,other]`（4 轨全真实，无 derived/missing）
  - 线程安全 RLock；超时线程 join（复用 `MdxSeparator._run_with_timeout` 模式）
- `AudioSeparatorService` 增加 `demucs_backend` 注入与 `backend="demucs"` 路由，`separate_4stem()` 优先走 Demucs，失败 fallback Spleeter。
- **不**删除/替换 MDX、Spleeter；Spleeter 永久保留为 fallback（与 Stage 2 约定一致）。
- ⚠️ 注意：`main.py:1639` 的 `_FORBIDDEN_TOP_LEVEL` 包含 `separation`——该包不进入 Modal web bundle，作为 web 容器/独立服务侧调用，此设计保持一致。

## 3. Modal 集成（现状 + 设计）

现状模式（已存在 4 个独立 App）：`spleeter_modal.py` / `musicgen_modal.py` / `gpt_sovits_modal.py` / `ace_step_modal.py`
- web 容器不装 GPU 依赖，经 `modal.Function.from_name("<app>", "<func>").remote(...)` 调用
- 共享数据卷 `avireon-music-platform-data-v1` + 模型卷 `avireon-music-platform-models-v1`
- 函数级 `timeout` + `max_containers=1` + `@modal.concurrent(max_inputs=1)`

设计（Demucs）：
- 新增 `demucs_modal.py`：`_APP = modal.App("avireon-music-platform-demucs")`，GPU=T4，镜像含 demucs==4.1.0 + torch + soundfile；函数签名 `separate_audio(filename_in_volume: str) -> dict`（返回 `{stem: filename}`），与 `spleeter_modal.separate_audio` 完全同构 → web 侧客户端可复用同一读取/上传模式。
- 输入传递：`vol.add_local_file(input, "/generated/<uuid>.wav")` + `commit()`。
- 输出获取：`vol.read_file("/generated/<stem>.wav")`。
- 超时：函数 timeout 900–1500s；web 侧 `asyncio.wait_for`（复用 `MAX_TASK_RUNTIME_SECONDS=600`）。
- 失败：捕获异常 → 返回空 dict（业务层标记 failed/fallback），参考 `ace_step_client` 的 QueueFullError 处理。
- 避免同步阻塞：`asyncio.to_thread(fn.remote, ...)`。
- **需要 async job**：是。分离在 T4 上需秒~分钟级，必须沿用 `task_store` + `asyncio.create_task` 后台任务架构（POST 立即返回 task_id）。

## 4. 文件流 / R2（可完全复用）

现有 R2 能力完整可复用（`cdn_uploader.py`）：
- `upload_music_package(task_id, files)` → 私有 R2 `music/{task_id}/{logical}.wav`（返回 key 清单）
- `get_presigned_download_url(key, expires_in=600)` → 授权下载短时 URL
- `ace_step_client.download_file()` → 三层取数（本地挂载 / Volume read_file）

目标流（与 `_upload_and_finalize` / `_run_retry_stems` 现有模式一致）：
```
本地输入 → vol.add_local_file → Modal Demucs separate_audio
→ vol.read_file(4 stems) → 本地临时目录 → cdn_uploader.upload_music_package
→ task_store.download manifest → API 返回 task 状态 + 预签名下载
```
无新增 R2 基建需求。

## 5. Quota / Budget（现状 + 建议，不改动）

现状（`ai_limits.py`）：
- `reserve_generation()`：每用户每日 1 / 每月 15 / 全平台每日 30 / `MODAL_BUDGET_DAILY` 硬停线，原子自增
- `budget_hard_stop_reached()`：非「生成」GPU 入口专用（`retry-stems` 已用它，达到预算不启动 GPU）
- `refund_generation()`：失败回退用户额度，但不回退 global_usage（成本硬线只增不减）

建议（设计结论，未改动）：
- Demucs 分离**不消耗 generation quota**（它不是"生成新歌"）
- **消耗 global GPU budget**：启动前调用 `budget_hard_stop_reached()`（与 retry-stems 一致），拒绝 429
- 最小集成不新增独立 separation quota 表；如产品需每用户分离上限，再独立计量
- 成本观测：复用 `task_store.log_generation_cost()`；注意 `GPU_RATE_USD_PER_SEC` 目前只有 L40S，需新增 T4 单价或记录 0.0，**绝不虚构成本**

## 6. Failure / Fallback（结合现有代码）

- 主路径：Demucs 4-stem → 失败自动 fallback 到 Spleeter（现有生产 Modal Spleeter，MIT 已确认商用）
- 语义：fallback 必须置 `fallback_used=True` + `fallback_reason`（现有门面已实现此协议）
- 双失败 → job 标记 `completed_with_stems_failed`（现有 `_run_retry_stems` 已实现，可复用 retry-stems 重试）
- 结论：Demucs failure → fallback Spleeter，而不是直接 job failed（瞬态错误可兜底）；两者都失败才 job failed

## 7. 并发分析

- **单 worker 复用模型**：可以。Phase 4 验证：同一 worker 内 3 次分离参数始终 `cuda:0`、GPU allocated 恒定 178.2MB、无状态污染。
- **并发安全**：`@modal.concurrent(max_inputs=1)` + `max_containers=1` 串行化，模型懒加载仅一次。
- **输出隔离**：**必须 job 隔离**——每次调用用唯一工作目录（`/tmp/demucs_{uuid}/`）或 volume 内唯一文件名，避免固定文件名覆盖（spleeter 的固定名 + max_inputs=1 可用，但 Demucs 建议唯一目录更稳）。
- **锁**：web 侧进程内 `threading.RLock`（现有 backend 均如此）；Modal 侧由 concurrent 串行。
- **CUDA OOM**：htdemucs 在 T4 仅 ~178MB allocated / ~786MB reserved（Phase 4），15.6GB 显存下风险极低；segment 默认分块保证长音频内存有界。仍建议函数 timeout + 错误捕获兜底。

## 8. License / Rights（核心结论）

来源：`models_license_audit.json`（2026-08-15 核验）+ 容器内实测（demucs 4.1.0）

| 项 | 状态 |
|---|---|
| Demucs 代码 | MIT（fork）✅ |
| **htdemucs 权重** | **作者 Issue #327 声明：不受 MIT 覆盖，仅限科研用途；无商用确认；禁止再分发** ❌ |
| 训练数据 | MUSDB18（研究用途）为主；htdemucs_6s 为 Meta 自有数据 ❌ |
| 项目自身审计 | risk=high，decision=**C（不引入生产）** |
| **CI 强制断言** | `test_separation_service.py:398-401`：`demucs["decision"].startswith("C")` + `musdb["decision"].startswith("C")`，否则测试失败 |

**Rights Gate 判定：BLOCKED**（不能仅因软件包可安装即判定权利链通过）

SOP v0.1 Rights Gate 文档在仓库中未找到（全库搜索无结果）；当前可执行的权利门 = `models_license_audit.json` 决策 + CI 测试断言。

解除 blocker 途径（二选一）：
1. 获得 htdemucs 权重作者的**书面商用许可**（须更新审计 JSON + 测试断言）
2. 改用商用已确认的 4-stem 模型（Spleeter 4stems 已 MIT 确认，可作生产 4-stem 主路径；Demucs 保持研究/POC 用途）

## 9. 生产集成前必须增加的测试

- **Unit**：DemucsSeparator 契约测试（Mock Separator）、输入校验（空/损坏/缺失）、模型加载失败、超时、轨道语义（4 stem 全 real）、进程内并发
- **Modal 集成测试**：真实 T4 跑短音频，断言 4 stem 存在/非空/可读（Phase 3/4 脚本固化为测试）
- **4-stem 输出测试**：文件存在、size>0、soundfile 可读、sr==44100、channels∈(1,2)、duration≈输入
- **Failure 测试**：Mock Modal 失败 → fallback Spleeter，`fallback_used=True`
- **Timeout 测试**：函数 timeout + web 侧 `asyncio.wait_for`
- **Quota 测试**：`budget_hard_stop_reached` 门控、global_usage 只增不减语义（扩展 `test_ai_limits.py`）
- **R2 测试**：`upload_music_package` manifest + 预签名（Mock boto3）
- **Concurrency 测试**：并行请求串行化、无 OOM、无文件冲突

## 10. 最终建议

### **BLOCKED**

（针对 Demucs/htdemucs 作为生产 4-stem 主路径）

技术准备度完全达标（Modal T4 / CUDA / 性能 RTF≈0.045 / 稳定性 / R2 / quota 模式全部可复用），但存在硬性 blocker：

1. **htdemucs 权重仅限科研用途**，无商用书面许可（blocker #1，决定性）
2. MUSDB18 训练数据为研究用途
3. 项目自身 `models_license_audit.json`（Demucs 条目 L67-79，decision="C - 不引入生产，本阶段禁止"）+ CI 测试 `test_separation_service.py:398-401` 强制断言，生产引入 Demucs 会破坏测试

解除 blocker 前**不得**接入生产音乐链、不得修改 production routing / quota / API。

技术集成本身结论为 READY WITH CONDITIONS：一旦权利链解决，按 §2/§3/§6 设计可实现最小集成（demucs_modal.py + demucs_separator.py + facade 路由 + R2 manifest + budget 门控），无其他架构障碍。
