# Phase 6.5 — Production Baseline Cleanup Report

- 日期：2026-08-17
- 目标：只修复 Phase 6 已确认的两个当前问题（P0 license JSON、P1 前端 env 变量名），不开发功能、不接入 Demucs
- 结论：**PASS**

---

## 1. 修复前问题

| ID | 问题 | 证据（Phase 6） |
|---|---|---|
| P0 | `backend/app/services/separation/models_license_audit.json` 不是有效 JSON | `test_license_audit_record_exists_and_complete` 失败（JSONDecodeError），本地实测 1 failed / 36 passed |
| P1 | `.env.production` 使用 `VITE_API_BASE_URL`，但代码读取 `VITE_API_BASE` → 生产构建回退硬编码 onrender.com 域名 | api.ts:3、useAiMusicTask.ts:19 与 .env.production:2 变量名不匹配；构建产物确认回退 `https://ai-music-backend-8e85.onrender.com` |

## 2. 实际修改文件（本次仅 4 个）

| 文件 | 修改类型 |
|---|---|
| `backend/app/services/separation/models_license_audit.json` | P0 修复 |
| `frontend/src/config/api.ts` | P1 修复 |
| `frontend/src/hooks/useAiMusicTask.ts` | P1 修复 |
| `backend/frontend-web/src/App.vue` | P1 修复（同变量名，统一规范） |

## 3. 每个修改的最小 diff 摘要

### P0 — models_license_audit.json

**问题**：`Bandit v2` 条目缺少 `"decision"` 键值对，其 `risk` 行后直接出现 `{`（新对象起始），导致 JSON 解析中断。

**修复**：为 Bandit v2 条目补齐 `"decision"` 并闭合该对象，然后正常开始 `MVSep Mega 53-Stems` 条目。

```
- "risk": "low (但为 3-stem 影视向，不匹配音乐 4-stem 管线)",
- {
+ "risk": "low (但为 3-stem 影视向，不匹配音乐 4-stem 管线)",
+ "decision": "B - 候选但受限：3-stem 影视向，不匹配音乐 4-stem 管线，本阶段不采用"
+ },
+ {
```

语义保持不变：`Spleeter = A`（MIT / 生产允许）、`Demucs = C`（Research-only / 生产禁止）、MUSDB18HQ = C、UVR/MDX = A。未删除任何审计证据，未降低 Rights Gate 标准。

### P1 — 前端环境变量命名统一

仓库搜索确认：配置侧 `.env.production`、`.env.v1_production`、docs（CLOUDFLARE_DEPLOYMENT.md、RENDER_DEPLOYMENT.md、V1_1_FINAL_REPORT.md）、scripts/configure_frontend_v1.py 全部使用 `VITE_API_BASE_URL`。唯一规范变量 = **`VITE_API_BASE_URL`**。最小改动 = 修正代码读取侧 3 处：

```
# api.ts
- import.meta.env.VITE_API_BASE ||
+ import.meta.env.VITE_API_BASE_URL ||

# useAiMusicTask.ts
- (import.meta as any).env?.VITE_API_BASE ||
+ (import.meta as any).env?.VITE_API_BASE_URL ||

# App.vue
- import.meta.env.VITE_API_BASE ||
+ import.meta.env.VITE_API_BASE_URL ||
```

未改后端 API 路径、/generate 主链、audio separation、R2、Modal、quota。`VITE_WS_BASE`（api.ts:7）不在本次问题范围，保持不动。

## 4. JSON validation — PASS

```
python -c "import json; d=json.load(open('.../models_license_audit.json', encoding='utf-8')); ..."
→ VALID JSON; models: 10
```

10 个模型条目 decision 全部就位：Spleeter=A、Demucs=C、MUSDB18HQ=C、Bandit=B、MVSep Mega=B、MVSEP-MDX23=C、BS-RoFormer=B/C、UVR/MDX23C/Audio-separator=A。

## 5. License tests — PASS

```
pytest tests/test_separation_service.py -v
→ 19 passed (原失败项 test_license_audit_record_exists_and_complete 现为 PASS)
```

## 6. Frontend build — PASS

```
npm run build（frontend/）
→ ✓ built in 7.67s; PWA generateSW 完成
```

构建产物验证：`dist/assets/js/useAiMusicTask-DX8FDbgP.js` 解析到 `const c="https://music-api-gateway.dingxingjing.workers.dev/api/v1/ai"`（正确读取 `.env.production` 的 `VITE_API_BASE_URL`），**不再回退 onrender.com**。

引用搜索确认：`frontend/src` 下已无 `VITE_API_BASE`（旧名）残留；全仓库代码侧仅 App.vue/api.ts/useAiMusicTask.ts 3 处均已统一为 `VITE_API_BASE_URL`。

## 7. 全量测试结果

### 全量（含全部 tests/）— 294 passed / 5 failed / 1 collection error（跳过 mix_engine）

| 测试 | 结果 | 归因 |
|---|---|---|
| test_separation_service.py | 19 passed | Phase 6.5 验证对象 |
| test_ai_limits.py + test_ai_budget.py | passed | 主链门控 |
| test_ai_music_flow.py | passed | 生产主链 |
| test_audio_separation.py | passed | /separate 端点 |
| test_inference.py::test_create_all | **FAILED** | 预存在：缺环境变量 `MUREKA_SPACE_URL`，与本次无关 |
| test_voice_clone_task_local.py | **4 FAILED** | 预存在：`VoiceCloneService` 缺 `find_voice` 方法（功能未批准/未实现），与本次无关 |
| test_mix_engine.py | **collection error** | 预存在：测试导入 `_resolve_audio_source` 但 mix_engine.py 无此符号，git diff 确认该文件未改动 |

5 个失败 + 1 个 collection error 全部为**预存在问题**，涉及文件（inference/voice_clone/mix_engine）均未被本次修改。绝对未将未执行/失败的测试记为 PASS。

## 8. /audio/separate 保持不变的原因

Phase 6.1 已判定 `POST /api/v1/audio/separate` = **C. INTERNAL / UNUSED**（前端无路由入口 + 生产域名不可达）。按指令**本次不修改**。风险继续记录：

> 若未来重新启用该 endpoint，必须先增加 authentication + rate limiting + Modal budget gate，否则存在 GPU cost/quota bypass 风险。

## 9. Demucs 保持 Research-only 的原因

models_license_audit.json 中 Demucs 权重许可为科研用途（Issue #327 作者声明），无商用确认，decision=C。本次未修改该 decision，未接入生产，Spleeter 生产 fallback 保持不变。

## 10. 最终状态

| 项 | 状态 |
|---|---|
| P0 models_license_audit.json | ✅ valid JSON，原 failed CI test PASS |
| P1 前端环境变量统一 | ✅ `VITE_API_BASE_URL` 唯一规范，build 成功，无残留旧引用 |
| License 语义（Spleeter=A / Demucs=C） | ✅ 保持 |
| 全量测试 | 294 passed / 5 failed（预存在）/ 1 collection error（预存在） |
| /audio/separate | 未修改（INTERNAL/UNUSED，风险已记录） |
| Demucs | 未修改（Research-only，decision=C） |
| 修改文件 | 4 个（2 P0 修复 + 2 统一） |
| 修改 production code | **否**（仅 1 个审计 JSON 数据文件 + 3 处前端变量名，未动 ai_music/auth/ai_limits/ace_step/spleeter/task_store/R2/quota） |

## 结论

### PASS

- 两个当前问题（P0 JSON、P1 env 变量名）均已修复并验证通过
- 无新增失败；5 个失败与 1 个 collection error 全部为预存在且与本次无关
- 无 blocker 阻挡进入 Phase 7