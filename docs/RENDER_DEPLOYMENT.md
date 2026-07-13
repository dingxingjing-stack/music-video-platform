# 🚀 Render 部署完整指南

**Render**: https://dashboard.render.com  
**用途**: 7×24 小时托管 FastAPI 后端网关

---

## 📋 Render 的作用（适配 AI 音乐项目）

### 核心功能

| 功能 | 说明 |
|------|------|
| **24 小时在线** | 前端可随时调用 API，本地关机器也正常运行 |
| **免费额度** | 单实例永久免费，满足公测需求 |
| **自动部署** | 代码 push 到 GitHub 后自动更新 |
| **安全密钥** | 环境变量存储，不暴露在代码中 |

### 服务分工

- **Cloudflare R2** → 存歌曲 MP3、封面图片（文件存储）
- **Supabase** → 存用户信息、歌曲记录（数据库）
- **Render FastAPI** → 中间枢纽，连接前端、数据库、R2、AI 模型

---

## 🎯 完整部署步骤

### 步骤 1: 注册并登录 Render

1. 访问：**https://dashboard.render.com**
2. 点击 **Sign up with GitHub**
3. 用您的 GitHub 账号授权登录

---

### 步骤 2: 创建 Web Service

#### 2.1 Connect GitHub

1. 登录后首页 → 点击 **New**
2. 选择 **Web Service**
3. 点击 **Connect a repository**
4. 授权 Render 访问您的 GitHub
5. 选择仓库：`music-video-platform`
6. 点击 **Connect**

#### 2.2 配置部署参数

| 字段 | 值 |
|------|-----|
| **Name** | `ai-music-backend` |
| **Region** | `North Virginia (us-east)` ⚠️ 和 Supabase 同区域 |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn main:app --host 0.0.0.0 --port $PORT` |

> ⚠️ **重要**: Render 自动设置 `$PORT` 环境变量（默认 10000），必须使用 `$PORT` 而不是硬编码端口！

---

### 步骤 3: 配置环境变量（关键！）

点击 **Advanced** → **Environment Variables** → **Add Variable**

#### 3.1 Supabase 数据库

| Key | Value |
|-----|-------|
| `SUPABASE_URL` | `https://gdowyyvzvseheccisdfhl.supabase.co` |
| `SUPABASE_ANON_KEY` | `sb_publishable_HgKv9LIR0-_CPK1sASyzWw_W_vvaOda` |
| `SUPABASE_SERVICE_ROLE_KEY` | `sb_secret_rETZ_hbLnEdJvr_-IEZPyA_nZv6HMzd` |

#### 3.2 Cloudflare R2 存储

| Key | Value |
|-----|-------|
| `R2_ACCOUNT_ID` | （从 Cloudflare Dashboard 复制） |
| `R2_ACCESS_KEY_ID` | （从 Cloudflare R2 → API Tokens 复制） |
| `R2_SECRET_ACCESS_KEY` | （从 Cloudflare R2 → API Tokens 复制） |
| `R2_BUCKET_NAME` | `music-audio-storage` |

#### 3.3 AI 音乐 API（可选）

| Key | Value |
|-----|-------|
| `MUREKA_API_KEY` | `op_pw90y7tcbmf2at4afa9crzd1ltzvzghzb` |
| `GEMINI_API_KEY` | （如有） |

---

### 步骤 4: 部署并获取 API 地址

1. 点击 **Create Web Service** 底部
2. Render 自动执行：
   - ✅ Git 拉取代码
   - ✅ 安装 Python 依赖
   - ✅ 启动 FastAPI
3. 部署成功后，顶部显示专属域名：
   ```
   https://ai-music-backend-xxxx.onrender.com
   ```
4. 这就是您的 **生产环境 API 地址**！

---

### 步骤 5: 验证部署

```bash
# 健康检查
curl https://ai-music-backend-xxxx.onrender.com/health

# 测试用户注册
curl -X POST https://ai-music-backend-xxxx.onrender.com/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-token" \
  -d '{"email": "test@example.com", "username": "TestUser"}'

# 测试歌曲创建
curl -X POST https://ai-music-backend-xxxx.onrender.com/api/v1/songs \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-token" \
  -d '{"title": "My Song", "style": "Pop"}'
```

---

## 🆘 常见问题

### Q1: 部署失败 - Build Error

**原因**: `requirements.txt` 缺失或格式错误

**解决**:
```bash
# 确保 requirements.txt 存在
cat backend/requirements.txt

# 重新部署：Render Dashboard → Manual Deploy → Deploy Manually
```

### Q2: 启动失败 - Port Error

**原因**: 端口未使用 `$PORT` 变量

**解决**: 确保启动命令是：
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

### Q3: 连接 Supabase 失败

**原因**: 环境变量未设置或 DNS 问题（国内网络）

**解决**:
1. 检查环境变量是否正确复制
2. 如果 Render 在美国，Supabase 也在美国，应该无 DNS 问题
3. 查看 Render Logs → 查看具体错误信息

### Q4: 首次访问超时 30 秒

**原因**: Render 免费实例休眠机制

**解决**: 正常现象！首次访问会唤醒实例（30-50 秒），后续访问秒响应。如需秒开，可升级到付费实例（$7/月）。

---

## 📊 自动更新流程

### 代码更新后自动部署

1. 本地修改代码
2. `git add . && git commit -m "fix: xxx"`
3. `git push origin main`
4. Render 自动检测 → 重新构建 → 重启服务
5. 新代码生效！

### 查看部署日志

Render Dashboard → 您的服务 → **Logs** 标签页

---

## 💰 免费额度详情

| 资源 | 免费额度 | 说明 |
|------|---------|------|
| **实例运行** | 750 小时/月 | 单实例常驻（约 25 天/月） |
| **带宽** | 100GB/月 | 足够 1 万+ 请求 |
| **存储** | 1GB 持久化 | 用于临时缓存 |
| **构建时间** | 500 分钟/月 | 自动部署使用 |

> ✅ 公测阶段完全够用！

---

## 🔐 安全最佳实践

### ✅ 推荐

- 所有密钥存在 Render 环境变量
- 不在代码中硬编码密钥
- 定期轮换密钥
- 使用 `.gitignore` 排除 `.env` 文件

### ❌ 避免

- ❌ 将密钥写入代码文件
- ❌ 将 `.env` 提交到 Git
- ❌ 在 GitHub 泄露密钥

---

## 📝 下一步

### 部署完成后

1. ✅ 复制 Render 分配的域名
2. ✅ 更新前端配置：`.env.production` 中的 `VITE_API_BASE_URL`
3. ✅ 测试完整流程：注册 → 登录 → 生成歌曲
4. ✅ 监控 Logs 查看使用量

### 前端配置示例

```env
# frontend/.env.production
VITE_API_BASE_URL=https://ai-music-backend-xxxx.onrender.com
VITE_SUPABASE_URL=https://gdowyyvzvseheccisdfhl.supabase.co
VITE_SUPABASE_ANON_KEY=sb_publishable_HgKv9LIR0-_CPK1sASyzWw_W_vvaOda
```

---

## 🎉 完成状态

准备工作：
- ✅ `requirements.txt` 已创建
- ✅ `render.yaml` 已创建
- ✅ 环境变量清单已整理

**下一步**: 访问 https://dashboard.render.com 开始部署！

告诉我 **"开始部署"** 或遇到任何问题时截图日志，我会帮您排查！🚀