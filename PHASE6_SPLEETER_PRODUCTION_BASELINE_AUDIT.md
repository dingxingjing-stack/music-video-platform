# Phase 6 — Spleeter Production Baseline Verification

- 日期：2026-08-17
- 类型：READ-ONLY / VERIFICATION ONLY（未修改任何生产代码）
- 前置：Phase 1-5 完成；Phase 5 结论 = BLOCKED（Demucs 权重许可）；Phase 6.1 已确认 `/api/v1/audio/separate` = C. INTERNAL / UNUSED

---

## 1. Executive Summary

生产主链（ACE-Step Modal → 独立 Spleeter Modal 4-stem 分离 → R2 私有对象 + 预签名）经逐文件核对与测试运行验证，**技术层面真实、无 mock 污染主链、额度/预算/锁/R2/task_store 均符合审计契约**。

最终结论：**PASS WITH CONDITIONS**

- PASS：10
- WARNING/GAP：3（`/api/v1/audio/separate` 无预算门；`models_license_audit.json` 为无效 JSON 致 1 测试失败；Mock 存在但仅在非生产/测试路径）
- BLOCKER：0（Demucs 生产接入仍为许可 BLOCKED，但属于 Research/POC 限定，不影响当前 Spleeter 生产基线）
- E2E：NOT EXECUTED / BLOCKED BY ENVIRONMENT

---

## 2. 实际生产链（已核实）

```
POST /api/v1/ai/generate
→ reserve_generation()                         ai_music.py:417 / ai_limits.py:180
→ task_store.acquire_lock()                    ai_music.py:428 / task_store.py:217
→ asyncio.create_task(_run_with_timeout)       ai_music.py:436
→ agnes_service (仅优化提示词/歌词)             ai_music.py:230
→ provider_registry.select() → modal_ace_step   ai_music.py:241
→ ace_step_client.generate_full_song()         ace_step_client.py:47
→ ACE-Step Modal (generate_full_song)          ace_step_modal.py:163
→ _separate_via_spleeter()                     ace_step_modal.py:216
→ avireon-music-platform-spleeter/separate_audio  spleeter_modal.py:87
→ vocals / drums / bass / other                spleeter_modal.py:_STEM_NAMES
→ download_file()                              ace_step_client.py:80
→ upload_music_package() → Private R2          ai_music.py:338 / cdn_uploader.py:224
→ 预签名 URL                                   cdn_uploader.py:201
→ task_store 终态                              ai_music.py:341-349
→ GET /task/{id}                                ai_music.py:444
```

主链分离**真实走 Spleeter**，非 Mock / SoundHelix / Demucs / test-only。

## 3. reserve_generation（PASS）

- `ai_limits.py:180-260`：原子预留，`cap = min(GLOBAL_DAILY, MODAL_BUDGET_DAILY)`（:196-197）
- 原子性：`_DB_LOCK` + `BEGIN IMMEDIATE` + 单条条件自增 SQL（:219-222），并发/重复无法越过硬线
- 预算 429：`/generate` 中 `"预算" in error` → HTTP 429（ai_music.py:420-424）
- GPU 启动路径：provider.generate 仅在后台 `_run_with_timeout` 中被调用；reserve 在 POST 同步阶段完成 → **不存在 reserve 前启动 GPU 的路径**
- 测试：test_ai_budget.py 5/6/7（并发/重复/重启持久化）+ test_ai_limits.py budget_hard_stop

## 4. task lock（PASS）

- `acquire_lock`（task_store.py:217-242）：`INSERT ... SELECT WHERE NOT EXISTS` 原子锁，仅无进行中任务时成功
- duplicate/concurrent：`is_user_busy`（:199）先拒 + 原子锁二次保证（测试 test_busy_lock_blocks_duplicate）
- lock failure：`new_task` 后 `acquire_lock` 失败 → `delete` + `refund`（ai_music.py:428-434）
- timeout：`_run_with_timeout`（ai_music.py:382-392）+ `get()` 惰性超时标记 failed 并释放锁（task_store.py:168-177）
- exception/cleanup：`finally: release_lock_for_task`（ai_music.py:305/618）
- 结论：不会 GPU 重复执行 / 配额重复消耗 / 永久 running（超时双保险）

## 5. ACE-Step → Spleeter（PASS）

- `ace_step_client.py:26/31`：`Function.from_name("avireon-music-platform-acestep","generate_full_song")` 与 `("avireon-music-platform-spleeter","separate_audio")`
- `ace_step_modal.py:163` `generate_full_song` → `:216 _separate_via_spleeter` → `:246` 转发独立 Spleeter App
- `spleeter_modal.py:87` `separate_audio`：真实 Spleeter 4stems，输出 `vocals/drums/bass/other`（`_STEM_NAMES`，:39）
- 生产主链无 Mock/SoundHelix/Demucs；ACE-Step 容器不安装 demucs/spleeter/tensorflow（ace_step_modal.py:55,237-238）
- 4 stem 真实：spleeter_modal.py:106-118 逐轨写入共享卷并 commit 后返回
- 独立 `/separate` 端点走 `audio_separation_service.demucs_service`（实为 Modal Spleeter），主链不走它（已核实）

## 6. Mock contamination（PASS，主链无污染）

- 主链 `_run_generation`：`agnes_result` 仅使用 `optimized_prompt`/`generated_lyrics`（ai_music.py:232-236），`agnes_result.audio_url`（SoundHelix mock）**从未被使用**（grep 无引用）
- HF 兜底 `_try_hf_ace_step_fallback`：显式拒绝 soundhelix（ai_music.py:155）
- 生产 `/generate` 主链不调用 `audio_separation_service`；其 `_mock_separate`（同文件 4 次引用）仅在 modal SDK 不可用的独立 `/separate` 端点触发 → **不进生产主链**
- 测试中的 Mock（fake_modal 等）是测试替身，不进生产
- **WARNING**：`audio_separation_service._mock_separate` 在 modal SDK 不可用时返回输入文件 4 次引用（含独立 `/separate` 端点）；生产 render.yaml 曾配置 `*_FORCE_MOCK=true`（inference/base.py:931 读取），但仅影响 inference 服务健康状态，不影响 Spleeter 分离主链

## 7. R2（PASS）

- `ace_step_client.download_file`（:80-107）：三层取数，失败返回 None → `_upload_and_finalize` 抛 RuntimeError（ai_music.py:319-321）→ 任务 failed + refund
- `cdn_uploader.upload_music_package`（:224-241）→ `upload_private`（:171-199）**私有对象**，返回 R2 key（非公开 URL）
- `get_presigned_download_url`（:201-222）短期 600s 签名
- 上传失败不会假成功：`upload_private` 抛异常 → 中断 → failed
- 下载失败不会假成功：`download_file` None → RuntimeError → failed
- 本地路径不会直接当结果：manifest 存 R2 key，audio_url 经 `_sign_for_playback`（:352）签名
- 测试：test_ai_music_flow full flow + 下载预签名断言

## 8. task_store 状态机（PASS）

- 内部状态：pending → processing → generating → (separating) → uploading → completed / completed_with_stems_failed / failed
- ACE-Step 失败 → HF 兜底 → 双失败 → failed + refund（ai_music.py:283-291）
- Spleeter 失败 → stems 缺失 → completed_with_stems_failed（:340-348，主歌曲仍可用）
- download/R2 失败 → RuntimeError → failed（:319-321）
- 超时 → `_run_with_timeout` + `get()` 惰性双保险
- **completed 不会在文件/R2 完成前设置**：`_upload_and_finalize` 全部下载→上传后才 update completed（:338-349）
- 锁释放：所有出口 finally release（:305/:392/:618）+ 惰性超时删锁
- GET /task/{id} 返回真实状态（:444-481，completed_with_stems_failed 对外映射 completed + stems_state）

## 9. failure handling（PASS，含 GAP 标记）

| 失败路径 | 处理 | 测试覆盖 |
|---|---|---|
| budget exhausted | reserve 返回失败 → 429（生成）/ retry-stems 429 | ✅ test_ai_budget |
| duplicate lock | is_user_busy + 原子锁 | ✅ test_busy_lock_blocks_duplicate |
| Modal timeout | `_run_with_timeout` + `get()` 惰性超时 | ⚠️ 仅 task_store.get 惰性，无独立 wait_for 注入测试（GAP-轻） |
| Spleeter failure | stems 缺失 → completed_with_stems_failed + retry-stems | ✅ test_retry_stems_limit |
| R2 failure | RuntimeError → failed + refund | ⚠️ test_audio_separation 覆盖 /separate 端点 R2 失败；主链 upload 失败走异常→failed（无专项断言，GAP-轻） |
| invalid input | prompt <5 字 → 400 | ⚠️ 端点级无专项测试（GAP-轻） |
| task exception | except → failed + refund | ✅ test_failed_flow_refunds |

未修改生产代码来制造测试；GAP 均以测试补充为后续项。

## 10. Quota Bypass 总结（WARNING）

| GPU 入口 | 调用来源 | 预算门 | 可绕过 | 状态 |
|---|---|---|---|---|
| `/generate` | ai_music.py:395 | reserve_generation（cap=min(global,budget)） | 否 | PASS |
| `retry-stems` | ai_music.py:540 | budget_hard_stop_reached | 否 | PASS |
| `/api/v1/audio/separate` | audio_processing.py:102 | **无** | **是（潜在）** | **WARNING/GAP** |
| ACE-Step Modal | provider modal_ace_step | 经 /generate reserve | 否 | PASS |
| Spleeter Modal | ace_step_modal 内嵌 + separate_only + audio_separation_service | 主链经 reserve/budget；/separate 无门 | 部分 | 主链 PASS |
| Demucs Modal | 无（Research only） | - | - | N/A |
| musicgen_modal | mv_router（main.py:306 禁用） | - | 路由未注册 | PASS（隔离） |
| gpt_sovits / tts_client | voice_clone（未批准新服务，不入 bundle） | - | 不入生产 bundle | PASS（隔离） |
| poc 脚本 | scripts/（不入 bundle） | - | 隔离 | PASS |

**WARNING/GAP（关键）**：`/api/v1/audio/separate` 无 reserve/budget 门。Phase 6.1 已确认当前 INTERNAL / UNUSED（前端未挂载路由 + onrender 404），不作为当前 blocker；但**若未来重新部署/启用该 endpoint，必须先增加 authentication + rate limiting + Modal budget gate，否则存在 GPU cost/quota bypass 风险**。

## 11. License / Rights（Spleeter PASS / Demucs BLOCKED）

- **Spleeter**：models_license_audit.json L52-65：代码 MIT、权重 MIT（JOSS 论文明确）、训练数据 Deezer、商用确认 是（Issue #259）、decision="A - 永久保留为 fallback" → **PASS**
- **Demucs**：L67-79：权重仅科研（Issue #327）、无商用确认、decision="C" → **Research/POC only，BLOCKED for production**（本阶段不接入）
- CI Rights Gate：test_separation_service.py:398-401 断言 Demucs/MUSDB 系 decision 以 "C" 开头
- **WARNING/GAP**：`models_license_audit.json` 本身是**无效 JSON**（L124 缺 `"decision"` 键值），导致 `test_separation_service.py::test_license_audit_record_exists_and_complete` 失败（本地实测 1 failed / 36 passed）。这是预先存在的缺陷，与 Phase 6 修改无关

## 12. E2E

**E2E = NOT EXECUTED / BLOCKED BY ENVIRONMENT**

- 本地无 `modal` SDK（import modal → ModuleNotFoundError）→ 无法调用真实 Modal
- 生产 onrender 域名当前不可达（`/health` 404）→ 无法对生产执行真实 `/generate`
- 无 R2 生产凭证在本机 → 无法真实上传/预签名
- 已执行：本地测试 `test_ai_music_flow.py`（12 passed）、`test_ai_limits.py`、`test_ai_budget.py`、`test_separation_service.py`（36 passed / 1 failed 为 JSON 缺陷）、`test_audio_separation.py`（3 passed）
- 未伪造 PASS。

## 13. 文件修改情况

- 修改生产代码：**无**
- 创建文件（审计产物，非生产）：
  - `PHASE6_1_AUDIO_SEPARATE_EXPOSURE_AUDIT.md`
  - `PHASE6_SPLEETER_PRODUCTION_BASELINE_AUDIT.md`（本文件）

## 14. 风险

1. `/api/v1/audio/separate` 无预算门 + 无认证 + 无限流（当前 INTERNAL/UNUSED，重新启用即暴露）— **HIGH if enabled**
2. `models_license_audit.json` 无效 JSON → CI Rights Gate 测试失败（1 项）— **MEDIUM（审计完整性）**
3. HF 兜底依赖 HF_TOKEN + 外部 Space；失败路径清晰但网络不可控 — LOW
4. 变量名不匹配：`.env.production` 用 `VITE_API_BASE_URL`，代码读 `VITE_API_BASE` → 生产构建回退硬编码 onrender 域名 — **MEDIUM（前端配置）**

## 15. 最终结论

### PASS WITH CONDITIONS

- 生产主链（ACE-Step → Spleeter 4-stem → R2 私有 + 预签名）**真实、无 mock、门控完整**
- Condition（不阻塞当前基线，但必须列入待办）：
  1. `/api/v1/audio/separate` 重新启用前必须加 authentication + rate limiting + Modal budget gate
  2. 修复 `models_license_audit.json` 的 JSON 语法（恢复 CI 测试）
  3. 统一前端 `.env.production` 变量名
  4. Demucs 维持 Research/POC，许可确认前不得接入生产
  5. 补充失败路径专项测试（timeout 注入、主链 R2 失败、invalid input）

---

## 验收清单汇总

- 最终判定：**PASS WITH CONDITIONS**
- PASS 数量：**10**
- WARNING/GAP 数量：**3**（/audio/separate 无预算门、license JSON 无效、前端变量名不匹配；另含 3 项轻量测试 GAP）
- BLOCKER 数量：**0**（Demucs 许可 BLOCKED 属 Research/POC 限定，非当前生产基线 blocker）
- E2E：**NOT EXECUTED / BLOCKED BY ENVIRONMENT**
- License：Spleeter PASS；Demucs BLOCKED（Research only）
- `/audio/separate`：C. INTERNAL / UNUSED → WARNING/GAP，非 blocker
- 修改 production code：**否**