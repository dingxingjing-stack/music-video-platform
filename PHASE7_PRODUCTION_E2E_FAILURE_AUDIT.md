# Phase 7 — Production E2E & Failure-Path Hardening Audit

- 日期：2026-08-17
- 类型：VERIFICATION ONLY（未修改任何 production code）
- 前置：Phase 6.5 = PASS；Demucs 保持 Research-only；/audio/separate 保持 INTERNAL/UNUSED

---

## 1. Executive Summary

Phase 7 针对真实生产主链（POST /api/v1/ai/generate → reserve_generation → acquire_lock → async task → ACE-Step Modal → Spleeter Modal → 4 stems → download → R2 → presigned → completed → GET /task/{id}）执行 VERIFICATION ONLY。

**线上环境当前不可达**（Cloudflare error 1003 "Direct IP access not allowed" / 403；onrender 后端全路径 404），因此 **真实 E2E 无法执行**。

**结论：PASS WITH CONDITIONS**

- 真实 E2E：**NOT EXECUTED / BLOCKED BY ENVIRONMENT**（不得因代码审计通过而判 E2E PASS）
- 代码级验证 + 现有测试：**PASS**（49 项 Phase 7 相关测试全通过，覆盖全部失败路径）

| 维度 | 状态 |
|---|---|
| Production endpoint | GAP（线上不可达） |
| /generate E2E | NOT EXECUTED / BLOCKED BY ENVIRONMENT |
| task state / quota / R2 / failure paths | PASS（代码 + 测试） |
| 4-stem | PASS（管线设计 + 测试替身验证；真实输出未执行） |
| Mock contamination | PASS |
| 修改 production code | 否 |

## 2. Production Endpoint（GAP — 线上不可达）

### 实测结果（2026-08-17）

| 目标 | 方法 | 结果 |
|---|---|---|
| `https://music-api-gateway.dingxingjing.workers.dev` | GET /、/health、/api/v1/ai/limits、/api/v1/ai/generate | **403 Forbidden** |
| 同上 | POST /api/v1/ai/generate（空体探测） | **Cloudflare error 1003 "Direct IP access not allowed"（HTML 页面，非 worker JSON）** |
| 同上 | OPTIONS /api/v1/ai/generate、/api/v1/ai/task/x | 200（CORS 预检，含 Access-Control-Allow-Methods） |
| `https://ai-music-backend-8e85.onrender.com` | GET /health、/api/v1/ai/limits | **404** |

### 分析
- `workers/gateway.js` 无任何返回 403 的分支（仅 429 限流 / 502 后端错误 / 404 R2 未找到）；403 与 1003 来自 **Cloudflare 层**（域名/Worker 未正确绑定或访问受限）。
- OPTIONS 200 仅证明预检被放行，不代表 Worker 代码在线上运行。
- `wrangler.toml` 将 `API_BASE_URL` 指向 onrender.com（当前 404）→ 即使网关可达，后端也不在线。
- 前端构建产物（dist/assets/js/useAiMusicTask-*.js）确认使用 `https://music-api-gateway.dingxingjing.workers.dev/api/v1/ai`（Phase 6.5 修复生效，**不再回退 onrender.com**）。

**结论**：生产后端当前**不可达**。无法对线上执行最小真实生成。

## 3. /generate 真实 E2E — NOT EXECUTED / BLOCKED BY ENVIRONMENT

按规则，未伪造成功。未执行 1 次最小生成的原因：
1. 线上 API 不可达（见上节）
2. 本地无 `modal` SDK（`import modal` → ModuleNotFoundError），无法驱动真实 Modal GPU
3. 本机无 R2 生产凭证

不执行真实生成也避免了对生产 quota/budget 的无谓消耗。**不绕过 reserve_generation、不修改 quota/budget。**

## 4. Task State（PASS — 代码 + 测试）

状态机核实（ai_music.py + task_store.py）：
- 内部：`pending → processing → generating → uploading → completed / completed_with_stems_failed / failed`
- `_upload_and_finalize`（ai_music.py:308-349）：manifest **仅在上传成功后写入**（`upload_music_package` 抛异常则中断）；`stems_ok`（4 轨齐全）才置 `completed`，否则 `completed_with_stems_failed`（:340-341）
- 对外 GET /task/{id}（:449-481）：终态正确映射，返回短期预签名 URL
- 测试：`test_full_flow_completed`（独立 DB + 注入 Modal 边界 + 驱动真实生产管线函数）PASS

## 5. Quota / reserve（PASS）

- `/generate` POST 同步阶段先 `reserve_generation`（ai_music.py:417，ai_limits.py cap=min(GLOBAL_DAILY, MODAL_BUDGET_DAILY)），**在 asyncio.create_task 启动后台 GPU 之前**（:436）→ 预算硬线先于 GPU 生效
- 预算耗尽 → 429（:420-424），**GPU 不启动**（test_blocked_does_not_start_gpu PASS）
- 测试覆盖：`test_ai_budget.py` 8 项（under/at budget、并发/重复不能绕过、retry-stems 门控、重启持久化）+ `test_ai_limits.py` budget_hard_stop/global_daily_cost_guard → **全部 PASS**
- 未人为耗尽生产 quota

## 6. ACE-Step（PASS — 管线核实）

- `_run_generation`（:245-268）：经 `get_provider_registry().select()` → Modal ACE-Step，`MAX_AUTO_RETRIES` 自动重试，失败记录成本观测后走 HF 兜底
- `test_auto_retry_on_generate_failure`、`test_failed_flow_refunds_and_marks_failed` PASS

## 7. Spleeter（PASS — 管线核实）

- `_upload_and_finalize` 对 `vocals/drums/bass/other` 逐轨下载；`_sign_for_playback`/`_stems_signed` 签发预签名
- `test_separation_service.py` 19 项（含 fallback_to_spleeter、force_spleeter_backend、stem_semantics_honest、license audit）**全部 PASS**
- `test_ai_music_flow.py::test_retry_stems_success`、`test_retry_stems_limit` PASS

## 8. 4-stem（PASS WITH CONDITION — 管线验证，真实输出未执行）

测试替身（fake_modal）在**注入点之外调用真实生产管线**，验证 4 轨逻辑语义（vocals/drums/bass/other 齐全 → completed；缺轨 → completed_with_stems_failed）。真实 GPU 输出（存在/非空/WAV 可读/采样率/时长/URL 可访问/非本地路径/presigned private）**因环境不可达未在真实链上验证**（NOT EXECUTED）。

条件：环境恢复后需补真实 4-stem 验证。

## 9. R2（PASS — 代码核实）

- 生产路径 `upload_music_package` → **`upload_private`**（cdn_uploader.py:171-199）：无公开 ACL，返回 R2 key（:239-240）
- `public-read` ACL（:162、:262、:334、:365）仅存在于公开用途方法（`upload_public`/`_upload_s3` 等），**不在生产音乐包路径**
- 预签名：`get_presigned_download_url`（:201-222）短期 600s，仅后端授权后签发
- 失败不假成功：`upload_private` 抛异常 → `_upload_and_finalize` 中断 → 任务 failed；`download_file` 返回 None → RuntimeError → failed（ai_music.py:319-321）

## 10. Presigned URL（PASS — 代码核实）

- `_sign_for_playback`（:352-364）/`_stems_signed`（:367-379）：优先 full_mp3，缺则 full_wav；失败返回 None
- 测试断言下载返回 600s 短期预签名（test_ai_limits.py::test_download_full_wav_and_stems 等 PASS）

## 11. Failure Path（PASS — 测试全部通过）

| 场景 | 代码/测试证据 | 状态 |
|---|---|---|
| A. reserve failure | test_ai_budget（at_budget/blocks GPU）+ /generate 429 | PASS |
| B. duplicate task lock | `is_user_busy` + `acquire_lock` 原子（task_store.py:217-242）；test_busy_lock_blocks_duplicate / test_repeat_requests / test_concurrency | PASS |
| C. ACE-Step failure | MAX_AUTO_RETRIES → HF 兜底 → 双失败 → failed + refund（ai_music.py:283-287）；test_auto_retry / test_failed_flow_refunds | PASS |
| D. Spleeter failure | 缺轨 → completed_with_stems_failed（:340-348），完整歌仍可下载；retry-stems 受 budget + MAX 限制；test_retry_stems_limit / test_retry_stems_success | PASS |
| E. download failure | `download_file` None → RuntimeError → failed + refund（:319-321）；test_separation_service::test_timeout | PASS |
| F. R2 upload failure | upload 异常 → failed（不置 completed）；test_audio_separation::test_separate_audio_upload_failure | PASS |
| G. timeout | `_run_with_timeout`（:382-392）+ task_store.get() 惰性超时同事务标记 failed+删锁（task_store.py:150-178） | PASS |
| H. task exception | except 兜底 → failed + refund（:298-303），finally release_lock（:305） | PASS |

每个场景均确认：终态正确、锁释放、quota refund、不错误 completed、不永久 running、不返回不存在的 R2 URL。

## 12. Mock contamination（PASS）

- `agnes_music_service.generate_song` 返回 SoundHelix `MOCK_AUDIO_URLS`（agnes_music_service.py:48-95），但 `_run_generation` **仅使用 `agnes_result.optimized_prompt` / `generated_lyrics`**（ai_music.py:232-236），**从不读取 `agnes_result.audio_url`**（grep 确认无引用）
- HF 兜底显式拒绝 soundhelix URL（ai_music.py:155）
- 测试替身 `fake_modal` 仅注入 Modal 边界（ace_step_generate/download/separate + upload/presign），生产管线函数本身真实执行
- 结论：**SoundHelix / Agnes mock audio 绝不进入最终 production audio result**

## 13. Historical Test Failures（记录，不处理）

| 失败 | 根因 | 与 Phase 7 相关性 |
|---|---|---|
| `test_inference.py::test_create_all` | 缺环境变量 `MUREKA_SPACE_URL` | 无关（未改 inference） |
| 4 × `test_voice_clone_task_local.py` | `VoiceCloneService` 缺 `find_voice`（功能未批准/未实现） | 无关（未改 voice_clone） |
| `test_mix_engine.py`（collection error） | 测试导入 `_resolve_audio_source`，mix_engine.py 无此符号 | 无关（git diff 确认未改动） |

确认：与 Phase 7 修改无关、不阻塞当前 Spleeter production baseline。**未修改它们。**

## 14. Environment Limitations（记录，不伪造）

- 线上 API 不可达：gateway 403 / Cloudflare error 1003 / onrender 404
- 本地无 modal SDK → 无法驱动真实 Modal GPU
- 本地无 R2 生产凭证 → 无法真实上传/预签名
- 受约束不修改 quota/budget/production code

## 15. Modified Files

- 修改 production code：**否**
- 创建文件：`PHASE7_PRODUCTION_E2E_FAILURE_AUDIT.md`（本文件）

## 16. Final Conclusion

### PASS WITH CONDITIONS

- **Code-level production chain**：ACE-Step → Spleeter 4-stem → R2 private → presigned → task_store 终态，逻辑完整、门控正确、失败路径均有测试覆盖（49 项 PASS）
- **Mock contamination**：无污染
- **真实 E2E**：**NOT EXECUTED / BLOCKED BY ENVIRONMENT**（线上不可达）
- **4-stem 真实输出**：NOT EXECUTED（环境受限）
- **条件**：
  1. 恢复线上可达（修复 gateway Worker 绑定 / onrender 部署 / DNS）后执行真实最小生成 + 4-stem 验证
  2. 补真实 R2 上传/预签名验证（需生产凭证或受控测试环境）

## 验收清单

- 最终判定：**PASS WITH CONDITIONS**
- E2E 状态：NOT EXECUTED / BLOCKED BY ENVIRONMENT
- 4-stem 状态：管线 PASS / 真实输出 NOT EXECUTED
- R2 状态：私有上传 + 预签名逻辑 PASS（真实上传 NOT EXECUTED）
- Failure-path 状态：PASS（49 项测试）
- Quota 状态：PASS（reserve 先于 GPU；预算 429；refund 正确）
- PASS：49（测试）+ 代码级多项
- FAIL：0
- GAP：2（线上不可达、真实 4-stem/R2 未执行）
- 修改 production code：否
- 报告路径：`C:\Users\dingx\music-video-platform\PHASE7_PRODUCTION_E2E_FAILURE_AUDIT.md`
- 下一步建议：
  1. 修复并恢复生产部署（Cloudflare Worker 绑定 + onrender/R2 凭证）后重跑真实 E2E
  2. 之后可进入真实 4-stem / R2 / presigned 端到端验证
  3. 独立处理历史测试失败（MUREKA_SPACE_URL、voice_clone、mix_engine）
  4. Demucs 持续保持 Research-only