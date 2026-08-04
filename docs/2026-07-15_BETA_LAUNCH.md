# 2026-07-15 公测装修 + 灰度权限系统

## 已完成

### 前端（Cloudflare Pages）
| 文件 | 说明 |
|------|------|
| `src/pages/Landing.tsx` | 公测落地首页：标语动效+5大功能卡片+福利对比+案例+反馈+bug弹窗+页脚 |
| `src/AppLayout.tsx` | 导航栏改造：公测badge+灰度专区+隐藏付费入口+灰度状态指示器 |
| `src/App.tsx` | 路由更新：/landing 落地页（独立）+ 主应用路由 |
| `src/config/features.ts` | 三级权限配置表（8开放/5灰度/6关闭=19项） |
| `src/hooks/useUserGrayStatus.ts` | 灰度状态 Hook（localStorage+API双源） |
| `src/components/BetaConsentModal.tsx` | 登录自动弹窗（5条公测规则，localStorage记忆） |
| `src/components/GrayFeatureLock.tsx` | 灰度锁定覆盖层 + FeatureGate路由组件 + 申请弹窗 |

### 后端（Render → 186 API）
| 文件 | 说明 |
|------|------|
| `backend/app/services/beta_service.py` | 公测灰度服务（SQLite，自动建表零操作） |
| `backend/app/routers/beta.py` | 5个端点：status / apply-gray / consume-credit / feature-access / daily-reset |
| `backend/main.py` | 注册 beta 路由 |

### 环境变量已配置
AGNES_API_KEY / GEMINI_API_KEY / HF_TOKEN / MUREKA_API_KEY / SENTRY_DSN / R2_BUCKET_NAME / SUPABASE_URL / SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY

### 验证结果（7/7通过）
- 根路径 HTTP 200 ✅
- beta/status ✅
- consume-credit ✅
- apply-gray ✅
- feature-access (19项) ✅
- 前端 /landing HTTP 200 ✅
- 前端 / HTTP 200 ✅

## 待办
1. 前端 Cloudflare Pages 自动部署更新后，访问 `/landing` 验证落地页
2. 在 Cloudflare 绑定自定义域名（如需要）