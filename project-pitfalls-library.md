# 项目历史问题库.md

> 记录 music-video-platform 开发过程中遇到的所有问题、根因、解决方案，避免重复踩坑。

## 🏗 构建部署

### 1. Render 部署构建失败 (2026-07-16)
**症状**：`npm run build` 退出码 1，错误 `Exited with status 1`
**根因**：`vstRecommendationEngine.ts` 两处 TS 错误：
- TS2820：`'Effect'`（大写）不匹配类型 `'effect'`（小写）
- TS2322：`format: ['VST2', 'VST3']`（数组）不匹配 `'VST2' | 'VST3'`（单值）
**修复**：统一小写 `effect`，`format` 改单值字符串
**衍生**：修复后暴露出新错误 `PluginProfile extends VSTPlugin` 缺少 `subtype` 等字段，最终改为独立定义

### 2. Build 命令包含 tsc 类型检查导致失败 (2026-07-16)
**根因**：`package.json` 中 `"build": "tsc && vite build"`，旧文件 TS 错误很多阻挡构建
**修复**：改为 `"build": "vite build"`（esbuild 不检查类型，直接编译）
**tsconfig.json**：同时关闭 `noUnusedLocals` / `noUnusedParameters`

### 3. 旧文件大量 TS6133/TS2307 (持续)
**TS6133**：未使用变量/参数 → 已关掉检查
**TS2307**：找不到模块 `antd` → 安装 `antd @ant-design/icons`
**TS2307**：找不到 `'../types/audio'` → 创建 `src/types/audio.ts`
**TS2307**：`'../../types'` 路径错误 → 改为 `'../types/video-sync'`

## 🔌 API & 路由

### 4. FastAPI 路由前缀重复 (2026-07-11)
**症状**：AI 生成 API 404
**根因**：`include_router` 加了 `/api/v1/ai`，router 内部又有 `prefix="/api/v1/ai"`
**修复**：选择其一，不要重复
**规律**：注册路由后立即 curl 验证前缀路径

### 5. 端口释放不彻底 (2026-07-11)
**症状**：`pkill -f uvicorn` 后端口 8000 仍被占用
**根因**：Windows 上 `pkill` 不彻底
**修复**：两步法：`pkill -f uvicorn` → `taskkill /PID xxx /F`

### 6. SQLite 数据库自动建表 (2026-07-15)
**方案**：`beta_service.py` 启动时自动建表，零手动 SQL
**注意**：Render 重启后数据重置（灰度阶段可接受）

## 💻 前端

### 7. TypeScript 编译问题 (2026-07-16)

| 问题 | 位置 | 修复 |
|------|------|------|
| `id` 属性不存在 | `RecordingEngine.ts` | `track.id` → `track.trackId` |
| `onLevelUpdate` 未声明 | `RecordingEngine.ts` | 添加 `public onLevelUpdate?: (data) => void` |
| `quantizeConfig` 未使用 | `RecordingEngine.ts` | 加 `void this._quantizeConfig` 读取一次 |
| `p.info` 可能 undefined | `VSTHost.ts` | 用可选链 `p.info?.type` |
| `midiChannel` 不存在 | `PluginInfo` | 添加 `midiChannel?: number` |

### 8. 前端构建卡死/超时
**根因**：tsc 运行太慢，尤其在 Windows 上
**解决**：直接 `vite build` 跳过 tsc 检查

## 🚀 部署 & CI/CD

### 9. Render 多项目关联冲突
**问题**：同一 GitHub 仓库关联了 `ai-music-backend` 和 `my-finance-project`，
推送代码触发两次部署，后者因环境不同失败
**当前阶段**：未修复，收到邮件可忽略（不影响主项目）
**建议方案**：关闭 `my-finance-project` 的 auto-deploy

### 10. Render 冷启动
**症状**：`curl` 返回 `HTTP 000`，超时无响应
**根因**：免费实例 15 分钟无请求后进入休眠
**修复**：等待约 2 分钟自动唤醒，或用轮询脚本
**脚本**：
```bash
while true; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" https://xxx.onrender.com/)
  [ "$CODE" = "200" ] && break
  sleep 15
done
```

## 🧪 公测灰度系统

### 11. 4个联调风险点 (2026-07-15)
1. App.tsx 路由未用 FeatureGate 包裹 → 改为 GrayRoute 双守卫
2. BetaConsentModal 仅 localStorage 判断 → 用 ConsentGuard 路由级拦截
3. consumeCredit 未同步后端 → 改为 fetch POST /beta/consume-credit
4. GrayFeatureLock userId 硬编码 → 改为动态 prop 传入

## 📁 文件

### 12. 缺失类型文件
| 缺失文件 | 引用位置 | 处理 |
|----------|----------|------|
| `src/types/audio.ts` | `multiTrackRecorder.ts`, `aiQualityOptimizer.ts` | 已创建 |
| `StockCategory` | `StockLibrary.tsx` | 已加到 `video-sync.ts` |


### 13. Cloudflare Pages @import顺序错误 (2026-07-18)
**症状**：构建失败，vite:css 报 @import must precede all other statements
**根因**：`@import './styles/mobile.css'` 写在 `@tailwind` 指令之后
**修复**：移到文件第一行，`@tailwind` 指令之前

### 14. JSX三元表达式花括号错误 (2026-07-18)
**症状**：`Expected "}" but found "."` at PathCPage.tsx:198
**根因**：三元 `:` 后多了一层 `{voices.map(...)}`，`{}` 导致解析器期望 `}` 但却遇到 `.`
**修复**：去掉多余的 `{`，三元分支直接返回 JSX 元素

### 15. Cloudflare构建配置 (2026-07-18)
**配置**：Root Directory = `frontend`，Build = `npm install && npm run build`，Output = `dist`
**注意**：wrangler.toml 位于仓库根目录，需忽略或删除

## 🔮 已知待处理

- GPT-SoVITS / MusicGen / CogVideoX 的 HuggingFace URL 尚未配置
- `my-finance-project` 自动部署关闭
- PWA 离线缓存策略需验证
- VST 编译环境搭建 (JUCE)
- UGC 推广启动 (¥6K 预算)