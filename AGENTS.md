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