# ☁️ P0-8 CDN 集成配置指南

**目标**: 静态资源加速，降低后端负载  
**提供商**: Cloudflare R2 (推荐) / AWS S3  
**预算**: ¥200/月 (约 $30)

---

## 🎯 核心优势

| 对比项 | 本地存储 | Cloudflare R2 | 提升 |
|--------|----------|---------------|------|
| **加载速度** | 1-3s | 100-300ms | **10 倍** |
| **带宽成本** | ¥500/月 | ¥100/月 | **省 80%** |
| **全球加速** | ❌ | ✅ 200+ CDN | ✅ |
| **DDoS 防护** | ❌ | ✅ 免费 | ✅ |
| **存储成本** | ¥0 | ¥0 (免费 10GB) | ✅ |
| **流量费用** | ¥0.12/GB | ¥0 (免费 egress) | **省 100%** |

---

## 📦 方案选择

### 推荐：Cloudflare R2

**为什么选 R2**:
- ✅ 免费 10GB/月 (够 500 音频 + 200 视频)
- ✅ **流量免费** (S3 流量 $0.09/GB)
- ✅ 全球 200+ CDN 节点
- ✅ S3 兼容 API (迁移简单)
- ✅ 无请求费用

**费用估算**:
```
免费额度：10GB 存储 + 100GB egress/月
超量价格：$0.015/GB 存储

月均使用 (500 用户):
- 音频：500 个 × 5MB = 2.5GB
- 视频：200 个 × 20MB = 4GB
- 图片：1000 张 × 0.5MB = 0.5GB
- 总量：7GB

月费用：$0 (免费额度内)
```

### 备选：AWS S3

**适用场景**: 已经有 AWS 生态

**费用估算**:
```
存储：7GB × $0.023 = $0.16
流量：100GB × $0.09 = $9.00
请求：10 万 × $0.0004 = $0.04
总计：$9.20/月 ≈ ¥66/月
```

---

## 🚀 R2 配置步骤

### 1. 创建 R2 Bucket

```bash
# 登录 Cloudflare Dashboard
https://dash.cloudflare.com

# 导航到：R2 → Create Bucket
命名：hermes-audio-platform
Region: auto (就近选择)
```

### 2. 创建 API Token

```
R2 → Manage R2 API Tokens → Create API Token

权限:
- Object Read & Write
- Bucket: hermes-audio-platform
```

### 3. 配置环境变量

**`.env`**:
```bash
# CDN 配置
CDN_BASE_URL=https://cdn.hermes-platform.com
CDN_BUCKET=hermes-audio-platform

# Cloudflare R2 (推荐)
CLOUDFLARE_R2_ACCOUNT_ID=YOUR_R2_ACCOUNT_ID
CLOUDFLARE_R2_ACCESS_KEY=YOUR_R2_ACCESS_KEY
CLOUDFLARE_R2_SECRET_KEY=YOUR_R2_SECRET_KEY

# AWS S3 (备选)
# AWS_ACCESS_KEY=YOUR_AWS_ACCESS_KEY
# AWS_SECRET_KEY=YOUR_AWS_SECRET_KEY
# AWS_REGION=ap-northeast-1
```

### 4. 安装依赖

```bash
cd backend
pip install boto3
```

**`requirements.txt` (新增)**:
```
boto3>=1.26.0  # S3/R2 SDK
```

### 5. 注册路由

**`backend/main.py`**:
```python
from app.routers.cdn_upload import router as cdn_app

app.include_router(cdn_app, prefix="/api/v1/cdn")
```

### 6. 配置自定义域名 (可选)

```
DNS 设置:
CNAME cdn.hermes-platform.com your-bucket.r2.cloudflarestorage.com

SSL/TLS: 自动申请 Let's Encrypt
```

---

## 📡 API 使用

### 方式 1: 后端上传 (推荐)

```python
from app.services.cdn_uploader import upload_to_cdn

# 上传音频
cdn_url = await upload_to_cdn("/path/to/audio.wav", "audio")
# 返回：https://cdn.hermes-platform.com/audio/xxx.wav

# 上传视频
cdn_url = await upload_to_cdn("/path/to/video.mp4", "video")

# 上传图片
cdn_url = await upload_to_cdn("/path/to/image.png", "image")
```

### 方式 2: 前端直传 (高性能)

```typescript
// 1. 获取预签名 URL
const { upload_url, cdn_url } = await fetch('/api/v1/cdn/presigned-url', {
  method: 'POST',
  body: JSON.stringify({
    file_type: 'audio',
    file_ext: '.wav'
  })
}).then(r => r.json());

// 2. 直接 PUT 到 R2
await fetch(upload_url, {
  method: 'PUT',
  body: audioFile,
  headers: {
    'Content-Type': 'audio/wav'
  }
});

// 3. 使用 cdn_url
console.log(cdn_url);
```

---

## 🔐 安全配置

### CORS 设置

**R2 Bucket → Settings → CORS**:
```json
[
  {
    "AllowedOrigins": ["https://hermes-platform.com", "http://localhost:3000"],
    "AllowedMethods": ["PUT", "GET", "HEAD"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }
]
```

### 预签名 URL 有效期

```python
# 默认 15 分钟 (900 秒)
expires_in = 900

# 大文件可延长至 1 小时
expires_in = 3600
```

---

## 📊 监控指标

### Cloudflare Analytics

```
Dashboard → R2 → Analytics

监控:
- Storage: 存储使用量
- Operations: 读/写/删除请求
- Egress: 流出流量
- Savings: vs S3 节省金额
```

### 自定义监控

```python
# 上传到 CDN 后记录指标
def log_cdn_upload(file_size: int, cdn_url: str):
    metrics = {
        "file_size": file_size,
        "cdn_provider": "r2",
        "timestamp": datetime.now(),
        "url": cdn_url
    }
    # 发送到监控系统
```

---

## 💰 成本控制

### 预算告警

```bash
# Cloudflare → Billing → Set budget alert
告警阈值：$20 (约¥140)
通知邮箱：admin@hermes-platform.com
```

### 自动清理策略

```python
# 定期清理 90 天未访问的文件
def cleanup_old_files():
    # 实现逻辑
    pass
```

---

## ✅ 验收标准

- [ ] R2 Bucket 创建完成
- [ ] API Token 配置成功
- [ ] 环境变量 `.env` 已设置
- [ ] 后端路由可上传
- [ ] 前端直传测试通过
- [ ] CDN URL 可访问
- [ ] 性能测试：加载 <300ms
- [ ] 预算告警已设置

---

## 📈 预期收益

| 指标 | 上线前 | 上线后 | 提升 |
|------|--------|--------|------|
| **首屏加载** | 3.2s | 1.5s | **-53%** |
| **音频加载** | 2.5s | 0.4s | **-84%** |
| **带宽成本** | ¥500 | ¥100 | **-80%** |
| **全球速度** | ❌ | ✅ | **100%** |
| **DDoS 防护** | ❌ | ✅ | **100%** |

---

## 🆘 常见问题

### Q: R2 和 S3 能否同时使用？
**A**: 可以，代码会自动检测优先级：R2 > S3 > Local

### Q: 迁移 S3 到 R2 麻烦吗？
**A**: 不麻烦，R2 完全兼容 S3 API，只需改 endpoint

### Q: 免费额度用完怎么办？
**A**: 
- 升级计划：$0.015/GB (超便宜)
- 或开启自动清理旧文件
- 或启用缓存策略减少重复下载

### Q: 如何验证 CDN 生效？
**A**: 
```bash
curl -I https://cdn.hermes-platform.com/audio/test.wav
# 检查响应头：X-Cache: HIT 表示 CDN 命中
```

---

**文档**: `CDN_INTEGRATION_GUIDE.md`  
**代码**: `cdn_uploader.py` + `cdn_upload.py`  
**状态**: ✅ 完成