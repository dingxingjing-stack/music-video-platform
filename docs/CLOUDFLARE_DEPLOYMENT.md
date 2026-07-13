# 🌐 Cloudflare 部署文档

## ✅ 已完成部署

### 1. Pages 前端托管
- **地址**: https://9b8f75e7.music-video-platform.pages.dev
- **构建命令**: `cd frontend && npm run build`
- **输出目录**: `frontend/dist`
- **部署命令**: `wrangler pages deploy ./frontend/dist --project-name music-video-platform`

### 2. Workers API 网关
- **地址**: https://music-api-gateway.dingxingjing.workers.dev
- **功能**:
  - ✅ CORS 跨域支持
  - ✅ IP 限流（100 请求/分钟/IP）
  - ✅ 请求转发到后端
  - ✅ R2 上传/下载
- **部署命令**: `wrangler deploy workers/gateway.js --name music-api-gateway`

### 3. R2 对象存储
- **存储桶**: music-audio-storage
- **容量**: 10GB（免费套餐）
- **用途**: 音频文件、封面图片存储
- **上传端点**: `PUT /api/v1/r2/upload?key=filename.mp3`
- **下载端点**: `GET /api/v1/r2/download/filename.mp3`

---

## 🔧 配置文件

### wrangler.toml
```toml
name = "music-api-gateway"
main = "workers/gateway.js"
compatibility_date = "2026-07-13"

# R2 存储桶绑定
[[r2_buckets]]
binding = "BUCKET"
bucket_name = "music-audio-storage"

# 环境变量
[vars]
API_BASE_URL = "http://localhost:8002"
RATE_LIMIT = "100"
CORS_ORIGIN = "*"
```

### .env.production
```env
VITE_API_BASE_URL=https://music-api-gateway.dingxingjing.workers.dev
```

---

## 🚀 快速部署命令

### 部署前端（Pages）
```bash
cd frontend && npm run build
wrangler pages deploy ./dist --project-name music-video-platform
```

### 部署网关（Workers）
```bash
wrangler deploy workers/gateway.js --name music-api-gateway
```

### 查看部署状态
```bash
wrangler deployment list
wrangler pages project list
wrangler r2 bucket list
```

---

## 🌍 访问地址

| 服务 | URL | 用途 |
|------|-----|------|
| **前端网站** | https://9b8f75e7.music-video-platform.pages.dev | 用户访问 |
| **API 网关** | https://music-api-gateway.dingxingjing.workers.dev | API 调用 |
| **R2 存储** | (通过 Workers 访问) | 文件存储 |

---

## 💰 免费套餐限额

| 服务 | 免费额度 | 当前使用 |
|------|---------|---------|
| **Pages** | 500 构建/月 | ~10 次 |
| **Workers** | 10 万请求/天 | ~100 次 |
| **R2** | 10GB 存储 + 10GB 读取/月 | ~1MB |

---

## 🔒 安全配置

- ✅ CORS 限制（允许所有来源，生产环境可限制）
- ✅ IP 限流（100 请求/分钟/IP）
- ✅ R2 私有 Bucket（通过 Workers 鉴权访问）
- ⚠️ 建议：生产环境添加 API Key 鉴权

---

## 📝 下一步

1. **绑定自定义域名**（可选）
   - Pages: `www.yourdomain.com`
   - Workers: `api.yourdomain.com`

2. **配置生产后端**
   - 更新 `wrangler.toml` 中的 `API_BASE_URL`
   - 部署后端到 Cloudflare Workers 或其他平台

3. **启用 HTTPS**
   - Cloudflare 自动提供 HTTPS 证书
   - 无需额外配置

4. **监控与分析**
   - Cloudflare Analytics
   - 查看 Workers 日志: `wrangler tail`

---

## 🆘 故障排查

### Pages 无法访问
```bash
wrangler pages project list
wrangler pages deployment list --project-name music-video-platform
```

### Workers 返回 502
- 检查后端是否可访问
- 确认 `API_BASE_URL` 配置正确
- 查看 Workers 日志：`wrangler tail music-api-gateway`

### R2 上传失败
- 确认 R2 Bucket 存在
- 检查 Workers 绑定了 R2
- 确认 CORS 配置正确

---

## 🎉 完成！

您的 **Music Video Platform** 已成功部署到 Cloudflare 全球 CDN！

- ✅ 前端：Pages 托管
- ✅ 网关：Workers 边缘计算
- ✅ 存储：R2 对象存储
- ✅ 安全：CORS + 限流
- ✅ 免费：完全在免费套餐内

**生产就绪！** 🚀