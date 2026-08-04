# AGENTS.md — 音乐视频平台 (Music Video Platform)

## 📋 项目概述

全球开放的 AI 音乐/视频创作平台。定位在 Suno（太简单）和 Cubase（太贵/太复杂）之间，免费 80% 功能。AI 音乐生成 + MV 一体化 + 实时协作 + 版权检测。

## 🏗 技术栈

| 层 | 技术 |
|---|---|
| 前端 | React 18 + TypeScript + Vite + Tailwind CSS |
| 后端 | Python FastAPI + uvicorn |
| 部署（前端） | Cloudflare Pages |
| 部署（后端） | Render.com（免费实例，冷启动约 2 分钟）|
| 存储 | Cloudflare R2（音频/视频文件）|
| 监控 | Sentry |

## 🧩 项目结构

```
music-video-platform/
├── frontend/          # React + Vite 前端
│   ├── src/
│   │   ├── components/   # 组件
│   │   ├── pages/        # 页面
│   │   ├── utils/        # 工具函数
│   │   ├── types/        # TypeScript 类型
│   │   ├── hooks/        # 自定义 hooks
│   │   ├── config/       # 配置
│   │   └── i18n/         # 国际化
│   ├── package.json
│   └── tsconfig.json
├── backend/           # FastAPI 后端
│   ├── app/
│   │   ├── routers/      # 路由模块
│   │   ├── services/     # 业务逻辑
│   │   ├── models/       # 数据模型
│   │   └── schemas/      # Pydantic schemas
│   ├── main.py
│   ├── Dockerfile
│   └── requirements.txt
└── docs/              # 文档
```

## 🔑 关键环境变量

```
AGNES_API_KEY=sk-xxx       # 主力文本模型（永久免费）
GEMINI_API_KEY=xxx         # 备用文本接口
HF_TOKEN=hf_xxx            # HuggingFace（音频生成）
MUREKA_API_KEY=op_xxx      # AI 音乐生成
R2_BUCKET_NAME=music-audio-storage
SENTRY_DSN=https://xxx@ingest.us.sentry.io/xxx
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=xxx
SUPABASE_SERVICE_ROLE_KEY=xxx
```

## 🚀 部署命令

### 后端（Render）
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 前端（本地开发）
```bash
cd frontend
npm install
npx vite --host 0.0.0.0 --port 3000
```

### 构建
```bash
cd frontend
npm run build  # 注：已改为 vite build（无 tsc 检查）
```

## 🌐 在线地址

- 后端 API: https://ai-music-backend-8e85.onrender.com
- 前端: https://music-video-platform.pages.dev

## 📐 编码规范

1. **中文注释**：所有注释用中文
2. **组件命名**：PascalCase（如 `GrayFeatureLock`）
3. **文件命名**：驼峰 + 点分（如 `useUserGrayStatus.ts`）
4. **路由前缀**：`/api/v1/` 统一前缀
5. **用户识别**：`X-User-ID` 请求头（免鉴权方案）
6. **API 失败降级**：默认 Mock 模式，后端不通时自动降级
7. **Git 提交**：中文前缀（`feat:` / `fix:` / `docs:`）

## ⚠️ 已知限制

- Render 免费实例冷启动约 2 分钟
- SQLite 部署重启后数据重置（灰度阶段可接受）
- 旧文件存在 TS 错误（已禁用 tsc 检查，Vite esbuild 直接编译）
- antd 已安装但部分组件未使用，按需清理

## 🧪 公测灰度系统

- 19 项功能分三级：8 开放 / 5 灰度锁定 / 6 完全关闭
- 自动灰度升级：`activity_score >= 100` 且 `total_generations >= 50`
- 用户额度：每日 20 次，消耗后弹窗
- 路由守卫：`ConsentGuard`（协议拦截）+ `GrayRoute`（灰度拦截）


## 2026-07-18 迭代记录

### 完成
1. 侧边栏「AI员工团队」整组删除
2. 新增「我的作品」页面（/my-works）
3. 新增全局进度弹窗 ProgressModal
4. 路径D音频生成模块（Mock生成+预览+导出+发布社区）
5. 路径C空状态引导 + card-solid统一 + input-glow替换
6. Feed + Profile 锌类替换为统一卡片样式
7. 路由淡入过渡动画（PageTransition）
8. 输入框聚焦发光效果 + 全局CSS规范
9. Cloudflare Pages构建修复（Root Directory=frontend + JSX语法修复 + CSS @import顺序）
10. Hermes节流配置（max_tokens=4096, max_turns=30）

### 待办
- VST JUCE 编译环境搭建（开发音频插件时）
- UGC推广方案落地（6K预算）

## 🔑 核心依赖

前端：react, antd, tailwindcss, zustand, @ant-design/icons
后端：fastapi, uvicorn, sqlite3, httpx, sentry-sdk
---

## 会话记录 (2026-08-04)

### 背景
- 部署平台: Modal,线上 URL: `https://dingxingjing-stack--music-platform.modal.run`
- 后端:`backend/main.py::_MODAL_APP`(web) + `backend/musicgen_modal.py::_APP`(GPU)
- 部署命令: `python -m modal deploy main.py::_MODAL_APP` / `python -m modal deploy musicgen_modal.py::_APP`(Windows 需 chcp 65001 + PYTHONIOENCODING=utf-8)

### 一、Modal 零成本音乐+MV 全链路打通
- MusicGen(开源,Modal T4 GPU 本地生成)→共享卷 `/root/data/generated/`→web 容器经 `/generated/{file}` 下载,零外部付费 API
- 音频生成 `/api/v1/ai/generate` 全链路: Agnes/Gemini 优化歌词 → MusicGen → HF 兜底 → 明确报错(无 mock),产出真实 wav
- MV `/api/v1/mv/render`: MusicGen 音频 → FFmpeg Pillow 渐变图拼接 → h264+aac mp4,FFprobe 验证双流

### 二、跨容器共享卷关键修复(重要经验)
- 问题: MusicGen 写入共享卷后 web 容器 404
- 三个根因逐层修复:
  1. Volume 写后必须显式 `_DATA_VOLUME.commit()` 才对他容器可见
  2. warm 容器卷快照是启动时的旧图 → 新文件不可见 → `download_audio` 改三层取数(本地路径→Modal Volume API→公网 HTTP)
  3. `vol.read_file` 返回的是 python `generator`(虽签名标 AsyncGenerator)→ 用 `b"".join(vol.read_file(path))`
- `download_audio` 公网兜底 URL 由 env `PUBLIC_BASE_URL` 提供(Modal ASGI 容器内无 127.0.0.1:8000)

### 三、异步任务架构
- 原同步长耗时接口改为: 提交即返回 task_id → 前端轮询状态
- 新增 `app/services/task_store.py`: 进程内任务存储
- 音乐 `POST /api/v1/ai/generate` → `{task_id,status_url}`;状态 `GET /api/v1/ai/task/{id}` → `{state,progress,audio_url}`
- MV `POST /api/v1/mv/render` → `{task_id,status_url}`;状态 `GET /api/v1/mv/status/{id}` → `{state,progress,video_url,audio_url}`
- 后台用 `asyncio.create_task` 执行,`app.mount("/generated", StaticFiles(...))` 挂载下载

### 四、适配 Modal 免费 GPU 503"queue is full"(4 点改造)
1. **并发=1**: `musicgen_modal.py` `max_containers=1` + `@modal.concurrent(max_inputs=1)`,单实例只处理 1 个 GPU 任务
2. **用户任务锁**: `task_store.is_user_busy/acquire_lock/release_lock`,同一用户(user_id 或客户端 IP)禁止同时提交;音乐接口返回 `success=false`+中文提示,MV 接口返回 HTTP 429
3. **任务超时**: `TASK_TIMEOUT` 默认 180s(可环境变量覆盖),`asyncio.wait_for` 包裹后台任务,超时自动标记 `failed` 并释放锁;`task_store.get()` 惰性超时兜底
4. **队列满友好提示**: `musicgen_client.QueueFullError` 捕获 Modal 503"queue is full",转中文业务错误文本;音乐/MV 后台捕获并写入任务 error

### 五、前端 Vue3(MusicGenDemo)
- `backend/frontend-web/` 极简 Vue3 + Vite 工程,`src/App.vue` 为 Tailwind 版卡片 UI
- 构建产物输出到 `backend/static_dist/`(index.html + assets/*.js)
- 4 点逻辑改造,与后端任务锁/429/失败状态严格对应:
  1. genMusic `if(!r.success) throw new Error(r.error)` 不启动轮询直接展示后端 error
  2. post 封装解析 `data.detail/error/message`,非 2xx 抛带 status 的 Error;两处 catch `e.status===429` → "服务器当前忙碌,请稍后再提交任务"
  3. 音乐/MV 按钮 `:disabled="busy"`,任务 `busy=true`,`finally{busy=false}` 三场景均能复位
  4. poll `state==='failed'` → `throw new Error(t.error)` 抛后端原始错误文本

### 关键经验教训
- Modal Volume 写入是最终一致,跨容器必须先 `commit()`
- 运行中容器文件系统是启动时快照,新 commit 文件未必立即可见 → 首选 Volume API 读取
- `modal.Volume.read_file` 实际返回同步 generator(文档标 AsyncGenerator)
- 免费 Modal GPU 队列有限,并发/锁/超时必须同时到位
- `unzip` Modal ASGI 容器内没有 127.0.0.1 监听,自引用用线上 PUBLIC_BASE_URL

### 阻塞项(需用户后续)
- SiliconFlow key 平台侧 403(需用户在 siliconflow.cn 核实/充值),MV 生图现走 Slideshow 兜底
- Runway/Agnes/本地音乐优化 key 未配,MV 无动态镜头
- 若需真 AI 歌词/音乐,Modal 侧 secrets 需配 OPENROUTER/相关 key
