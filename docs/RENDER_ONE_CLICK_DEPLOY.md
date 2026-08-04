# 🎉 一键部署到 Render

## 🚀 最简单方式：点击 Deploy 按钮

Render 提供**一键部署**功能！点击下方按钮，自动完成所有配置：

### 🔗 一键部署链接

```
https://render.com/deploy?repo=https://github.com/YOUR_USERNAME/music-video-platform
```

**替换 `YOUR_USERNAME` 为您的 GitHub 用户名**，然后点击链接！

---

## 📋 半自动方式（推荐）

如果还没有 GitHub 仓库，请按以下步骤操作（仅需 3 分钟）：

### 步骤 1: 在 GitHub 创建仓库（30 秒）

1. 访问：**https://github.com/new**
2. Repository name: `music-video-platform`
3. 选择 **Public** 或 **Private**（Render 都支持）
4. **不要**初始化 README/.gitignore（保持空仓库）
5. 点击 **Create repository**

### 步骤 2: 推送代码（1 分钟）

在本地项目根目录运行：

```bash
cd C:\Users\dingx\music-video-platform

# 初始化 Git（如果还没有）
git init

# 添加远程仓库（替换 YOUR_USERNAME）
git remote add origin https://github.com/YOUR_USERNAME/music-video-platform.git

# 推送代码
git add .
git commit -m "Initial commit - Ready for Render deployment"
git branch -M main
git push -u origin main
```

### 步骤 3: 一键部署（1 分钟）

1. 访问：**https://render.com/deploy?repo=https://github.com/YOUR_USERNAME/music-video-platform**
2. 登录 GitHub（授权 Render 访问）
3. 选择仓库：`music-video-platform`
4. 自动填充配置：
   - **Name**: `ai-music-backend`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. 添加环境变量（5 个）：
   ```
   SUPABASE_URL = https://gdowyyvzvseheccisdfhl.supabase.co
   SUPABASE_ANON_KEY = sb_publishable_HgKv9LIR0-_CPK1sASyzWw_W_vvaOda
   SUPABASE_SERVICE_ROLE_KEY = sb_secret_rETZ_hbLnEdJvr_-IEZPyA_nZv6HMzd
   R2_BUCKET_NAME = music-audio-storage
   MUREKA_API_KEY = <在 Render Dashboard 注入；本机用 backend/secrets.local.json>
   ```
6. 点击 **Create Web Service**

---

## ✅ 部署完成后

Render 会自动：
1. ✅ 拉取 GitHub 代码
2. ✅ 安装 Python 依赖
3. ✅ 启动 FastAPI 服务
4. ✅ 生成专属域名

**告诉我您的 Render 域名**（格式：`https://xxx.onrender.com`），我会立即：
- ✅ 测试 API 健康检查
- ✅ 验证数据库连接
- ✅ 测试完整流程

---

## 💡 需要帮助？

如果您遇到任何问题，请截图或复制错误信息，我会立即帮您解决！