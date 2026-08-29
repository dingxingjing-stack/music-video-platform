# Phase 6.1 — Audio Separation Endpoint Exposure Verification

- 日期：2026-08-17
- 类型：READ-ONLY / EXPOSURE AUDIT
- 结论：**C. INTERNAL / UNUSED（当前），代码层面无保护，部署即 PUBLIC+ACTIVE**

---

## 结论摘要

| 判定项 | 结果 |
|---|---|
| 最终结论 | **C. INTERNAL / UNUSED** |
| 后端代码注册 | ✅ 已注册 `/api/v1/audio/separate`（main.py:322） |
| 认证/授权 | ❌ 无（无 X-User-ID / 无 auth dependency / 无 rate limit） |
| 预算门控 | ❌ 无（无 reserve_generation / 无 budget_hard_stop_reached） |
| 前端 UI 入口 | ❌ 无（P2AudioSeparationPage 未挂载路由） |
| 当前线上可达性 | onrender 全路径 404；workers 网关 GET 403 |
| 是否生产 active GPU endpoint | **未证实**（当前线上不可达 + 前端无入口） |
| Phase 6 是否 BLOCKED | **否** → 记录为 WARNING/GAP |

---

## 一、main.py 是否注册 /api/v1/audio/separate

**是。**

- `backend/main.py:322`：`app.include_router(audio_processing.router, prefix="/api/v1/audio")`
- `backend/app/routers/audio_processing.py:102`：`@router.post("/separate")` → 完整路径 `POST /api/v1/audio/separate`
- 同文件 :55 注册 `GET /separate/models`（已返回空列表 + 禁用提示）

## 二、生产部署是否包含 audio_processing router

**是（代码层面）。**

- `render.yaml`（仓库根）：`rootDir: backend`、`dockerfilePath: ./Dockerfile`、web 服务 `ai-music-backend`
- `backend/Dockerfile`：`COPY . .` + `uvicorn main:app` → 打包全部 backend 代码，含 audio_processing.py
- `backend/requirements.txt`：含 `modal==1.5.3`、`boto3==1.35.0` → 生产容器有 modal SDK + R2 客户端

## 三、当前 Render/onrender 生产部署是否实际暴露该端点

**无法证实（当前不可达）。**

实测（2026-08-17）`https://ai-music-backend-8e85.onrender.com`：
- `GET /` → 404
- `GET /health` → 404（render.yaml healthCheckPath 指向 /health）
- `GET /api/v1/ai/limits` → 404
- `GET /api/v1/audio/separate/models` → 404
- `POST /api/v1/audio/separate/models` → 404
- `OPTIONS /api/v1/audio/separate` → 404
- `HEAD /api/v1/audio/separate` → 404
- 响应头 `Server: cloudflare`；与不存在的 `nonexistent-xyz-abc.onrender.com` 行为一致（同 404）→ 该服务当前**未运行 / 已暂停 / 已删除**，无法证明线上正在提供该端点。

## 四、前端 AudioSeparationPanel.tsx 是否仍调用 /api/v1/audio/separate

**组件存在且硬编码调用，但未被路由挂载。**

- `frontend/src/components/AudioSeparationPanel.tsx:45`：
  `fetch('https://ai-music-backend-8e85.onrender.com/api/v1/audio/separate', ...)`（硬编码，POST multipart）
- `frontend/src/pages/P2AudioSeparationPage.tsx:5,7,10` 引用并渲染该组件
- **关键**：`frontend/src/App.tsx`（路由表）中**没有** `P2AudioSeparationPage` 的 lazy import 或 `<Route>` → **前端 UI 无入口**，用户无法通过正常页面触发该组件。

## 五、全仓库引用清单

| 文件 | 引用 |
|---|---|
| backend/app/routers/audio_processing.py:55,102 | `/separate/models`、`/separate` 定义 |
| backend/tests/test_audio_separation.py:43,81,112 | 测试调用（mock） |
| frontend/src/components/AudioSeparationPanel.tsx:45 | 硬编码调用（未挂载） |
| frontend/src/pages/P2AudioSeparationPage.tsx:5 | import 组件（未被 App.tsx 引用） |

无其他生产引用。

## 六、调用地址

| 地址 | 状态 |
|---|---|
| `https://ai-music-backend-8e85.onrender.com`（硬编码默认 + wrangler API_BASE_URL） | 当前 404，服务不可达 |
| `https://music-api-gateway.dingxingjing.workers.dev`（.env.production VITE_API_BASE_URL） | GET 403、OPTIONS 200（worker 存在但 GET 被 Cloudflare 层拦截） |
| `localhost:8002` / `localhost:8001`（vite dev proxy 目标） | 开发环境 |
| test only | test_audio_separation.py（mock） |

**注意变量名不匹配**：`.env.production` 设 `VITE_API_BASE_URL`，但代码读取 `VITE_API_BASE`（api.ts:3、useAiMusicTask.ts:19）→ 生产构建回退到硬编码 `https://ai-music-backend-8e85.onrender.com`。

## 七、是否需要认证

**否。** `audio_processing.py::separate_audio` 无任何鉴权：无 `X-User-ID` 校验、无 `Authorization`、无 auth dependency、无用户归属检查。PrivacyMiddleware 仅设置 cookie，不鉴权。

## 八、rate limit / 认证 / 授权 / feature flag / disabled route

| 机制 | 是否存在 |
|---|---|
| rate limit | ❌ 无（未调用 check_and_log_download） |
| authentication | ❌ 无 |
| authorization | ❌ 无 |
| feature flag | ❌ 无 |
| disabled route | ❌ `POST /separate` 无禁用逻辑（仅 `GET /separate/models` 返回空列表） |

## 九、/separate/models 禁用是否意味着 /separate 禁用

**否（不自行推断，依据代码）。**
- `GET /separate/models`（audio_processing.py:55-62）：返回空 models + 禁用提示 message —— **仅模型列表被禁用**。
- `POST /separate`（audio_processing.py:102-178）：完整可执行逻辑（保存上传 → demucs_service.separate → CDN 上传），**无禁用标记、无 feature flag、无条件返回**。
- 两者独立；`/separate/models` 禁用**不等于** `/separate` 禁用。

## 十、只读验证执行情况

- 已对 onrender / workers 网关执行 GET/HEAD/OPTIONS（未做真实 GPU 分离调用，无文件上传）
- 已执行本地测试 `test_audio_separation.py`（3 项通过，纯 mock）
- 未修改任何代码

---

## 风险评估

若后端未来重新部署到可访问域名（onrender 恢复 / 网关转发正常），`POST /api/v1/audio/separate` 将**立即成为无认证、无预算门控、无限流的公开 GPU 端点**：
- 任意匿名用户可上传音频 → 触发 Spleeter Modal GPU（L40S）→ 消耗 Modal 预算 → **绕过 MODAL_BUDGET_DAILY 硬停线**
- 前端组件虽未挂载，但该端点对任何能访问域名的 HTTP 客户端开放
- 与主链 `/generate`（reserve_generation）和 `retry-stems`（budget_hard_stop_reached）形成门控不对称

## 建议（Phase 6 范围外，仅记录）

1. 移除或禁用 `POST /api/v1/audio/separate`（或为它增加 `budget_hard_stop_reached()` 门控 + 认证）
2. 修复前端 `.env.production` 变量名（`VITE_API_BASE_URL` → `VITE_API_BASE`）或统一
3. 清理 `AudioSeparationPanel.tsx` / `P2AudioSeparationPage.tsx` 或补路由挂载并加门控
4. 部署前 `predeploy_check.py` 可扩展：校验 audio_processing 分离端点无预算门 → 阻断

---

## Phase 6 判定影响

- `/api/v1/audio/separate` 当前为 **INTERNAL / UNUSED**（前端无入口 + 线上不可达）
- 因此 **不判定为 production active GPU endpoint**，Phase 6 不因此 BLOCKED
- 记录为 **WARNING/GAP**（代码层面无保护端点，潜在 GPU budget bypass，重新部署即触发）