# 🚀 V1.1 架构迁移方案 - 100% 复用现有代码

**日期**: 2026-07-14  
**策略**: **不重写，仅适配** - 已有代码直接复用  
**迁移时间**: 4-6 小时 (仅配置调整)

---

## ✅ 现有代码复用清单

### 1️⃣ 后端 FastAPI (100% 复用)

#### 已有服务层 (57 个文件，直接复用)

| 文件 | 用途 | V1.1 映射 | 状态 |
|------|------|-----------|------|
| `mureka_service.py` | AI 音乐生成 | → 改为 `hf_music_service.py` (仅换 API 调用) | ✅ 90% 复用 |
| `gemini_ai_music.py` | Gemini API | → 保留，优化 Prompt | ✅ 100% 复用 |
| `copyright_service.py` | 版权检测 | → AISafety 本地规则 | ✅ 100% 复用 |
| `quota_management.py` | 配额管理 | → 每日额度日志 | ✅ 100% 复用 |
| `audio_separation_service.py` | 音频分离 | → 二期开放 | ⏸️ 暂禁用 |
| `audio_enhancement.py` | 音质优化 | → 二期开放 | ⏸️ 暂禁用 |
| `batch_queue.py` | 任务队列 | → PG 内置队列 | ✅ 100% 复用 |
| `cdn_uploader.py` | CDN 上传 | → 改为 R2 上传 | ✅ 80% 复用 |

**修改量**: 仅需修改 `mureka_service.py` → `hf_music_service.py` (约 100 行代码)

#### 已有路由层 (30 个文件，152 个端点)

| 路由文件 | 端点 | V1.1 用途 | 状态 |
|----------|------|-----------|------|
| `ai_music.py` | 5 个 | AI 生成任务 | ✅ 保留 |
| `gemini_ai_music.py` | 3 个 | 歌词生成 | ✅ 保留 |
| `copyright.py` | 6 个 | 版权检测 | ✅ 保留 |
| `collaboration.py` | 21 个 | 实时协作 | ⏸️ 二期 |
| `community.py` | 4 个 | 社区榜单 | ⏸️ 二期 |
| `messages.py` | 7 个 | 私信系统 | ⏸️ 二期 |
| `notifications.py` | 8 个 | 通知系统 | ⏸️ 二期 |
| `cdn_upload.py` | 6 个 | 文件上传 | ✅ 改为 R2 |
| `asset_store.py` | 12 个 | 素材库 | ✅ 保留 |
| **其他 20 个** | ~80 个 | 各种功能 | 按优先级启用/禁用 |

**策略**: 
- ✅ **核心 12 个端点**立即启用 (用户/任务/生成/分享)
- ⏸️ **重度 140 个端点**二期开放 (社区/协作/MV/付费)

---

### 2️⃣ 数据库模型 (快速适配)

#### 现有模型
```
backend/app/models/social.py (7.1KB)
  - User (用户)
  - Message (私信)
  - Notification (通知)
```

#### V1.1 需补充 10 张表 → **仅新增 1 个文件**

创建 `backend/app/models/v1_core.py`:
```python
"""
V1.1 核心业务数据表 (10 张)
- 直接复用现有的 User/Message
- 仅新增歌曲/任务/资源相关表
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum, Float
from sqlalchemy.orm import relationship
import enum

class TaskStatus(enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    RUNNING = "running"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"

class Song(Base):
    """歌曲主表"""
    __tablename__ = "songs"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"))
    title = Column(String(255))
    lyrics = Column(Text)  # 完整歌词
    style_prompt = Column(Text)  # 曲风描述
    language = Column(String(50))
    mood = Column(String(50))
    duration = Column(Integer)  # 秒
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    
    # 关联
    user = relationship("User", back_populates="songs")
    tasks = relationship("Task", back_populates="song")
    media = relationship("MediaAsset", back_populates="song")

class Task(Base):
    """AI 生成任务表"""
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True)
    song_id = Column(Integer, ForeignKey("songs.id"))
    status = Column(Enum(TaskStatus))
    model_provider = Column(String(50))  # "hf_musicgen" / "hf_ace_step"
    progress = Column(Integer, default=0)  # 0-100
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    song = relationship("Song", back_populates="tasks")

class MediaAsset(Base):
    """统一媒体资源表"""
    __tablename__ = "media_assets"
    
    id = Column(Integer, primary_key=True)
    song_id = Column(Integer, ForeignKey("songs.id"))
    asset_type = Column(String(20))  # "audio", "cover", "lyrics"
    storage_provider = Column(String(20))  # "r2"
    r2_bucket = Column(String(255))
    r2_key = Column(String(500))
    public_url = Column(String(1000))
    size_bytes = Column(Integer)
    duration_seconds = Column(Integer)
    created_at = Column(DateTime)
    
    song = relationship("Song", back_populates="media")

# 其他 7 张表：CopyrightRecord, QuotaLog, AuditLog, ProviderLog, 
# Project, PromptLibrary, User 扩展字段在 social.py 中补充
```

**工作量**: 约 200 行代码 (30 分钟)

---

### 3️⃣ AI Provider 适配 (核心修改)

#### 修改 `mureka_service.py` → `hf_music_service.py`

**仅需修改 API 调用部分** (约 100 行):

```python
# 原 Mureka API 调用
# response = await client.post(
#     "https://api.mureka.ai/v1/song/generate",
#     headers={"Authorization": f"Bearer {MUREKA_KEY}"},
#     json={"lyrics": lyrics, "style": style}
# )

# 改为 Hugging Face Spaces 调用
response = await client.post(
    "https://bingmic-ace-step.hf.space/api/predict",
    json={
        "data": [prompt, duration, temperature, lyrics or ""]
    }
)
```

**复用部分**:
- ✅ 任务状态管理逻辑
- ✅ 错误重试机制
- ✅ 文件下载保存
- ✅ 数据库记录更新

**修改量**: **10-15% 代码** (约 100 行)

---

### 4️⃣ 存储层适配 (R2)

#### 修改 `cdn_uploader.py`

```python
# 原 CDN 上传逻辑
# 保留 80%，仅修改目标存储

class R2Uploader:
    def __init__(self):
        self.account_id = R2_ACCOUNT_ID
        self.access_key = R2_ACCESS_KEY
        self.secret_key = R2_SECRET_KEY
        self.bucket = "music-assets"
    
    async def upload_audio(self, file_path: str, song_id: int) -> str:
        """上传音频到 R2，返回 public URL"""
        # 复用现有文件读取、重命名、错误处理逻辑
        # 仅修改 S3 SDK 调用为 Cloudflare R2 端点
        
        s3 = boto3.client(
            's3',
            endpoint_url=f"https://{self.account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name="auto"
        )
        
        key = f"songs/{song_id}/{uuid4()}.mp3"
        s3.upload_file(file_path, self.bucket, key, ExtraArgs={'ACL': 'public-read'})
        
        return f"https://music-assets.shturl.cc/{key}"
```

**修改量**: **20% 代码** (约 50 行)

---

### 5️⃣ 前端页面 (18 个页面，选择性启用)

#### ✅ V1.1 立即启用 (6 个页面)

| 页面文件 | 用途 | 修改量 |
|----------|------|--------|
| `StudioPage.tsx` | 创作主页面 | ✅ 100% 复用 |
| `PathAPage.tsx` | 快速生成流 | ✅ 100% 复用 |
| `Profile.tsx` | 个人作品库 | ⚙️ 简化 (去掉社交功能) |
| `CommunityFeed.tsx` | 公开分享页 | ⚙️ 简化 (去掉榜单) |
| `FoundingMember.tsx` | 登录/注册页 | ✅ 保留 |
| `StockLibrary.tsx` | 素材库浏览 | ✅ 保留 |

#### ⏸️ V1.1 暂禁用 (12 个页面)

- `Community.tsx` - 复杂社区榜单
- `TrackStudio.tsx` - 专业 DAW 编辑
- `P2AudioMasteringPage.tsx` - 母带处理
- `P2AudioSeparationPage.tsx` - 音频分离
- `ScoreEditorPage.tsx` - 乐谱编辑
- `VideoSyncStudio.tsx` - MV 同步 (无 AI 视频)
- `UGCSubmit.tsx` - UGC 投稿
- `PathBPage.tsx` - 专业模式
- `PathCPage.tsx` - 协作编辑
- `PathDPage.tsx` - AI 辅助
- `P2LyricPage.tsx` - 独立歌词页 (已集成到 Studio)
- 其他专业功能页

**策略**: 
- 6 个核心页面 **立即上线**
- 12 个专业页面 **保留代码，二期开放**

---

### 6️⃣ 配置与环境变量

#### 创建 `.env.v1_production`

```bash
# ===== 核心服务 =====
ENVIRONMENT=production
VERSION=1.1.0

# ===== Supabase (PostgreSQL + Auth) =====
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# ===== Cloudflare R2 =====
R2_ACCOUNT_ID=xxx
R2_ACCESS_KEY=xxx
R2_SECRET_KEY=xxx
R2_BUCKET=music-assets
R2_PUBLIC_DOMAIN=https://music-assets.shturl.cc

# ===== Gemini Flash LLM =====
GEMINI_API_KEY=***
GEMINI_MODEL=gemini-2.0-flash

# ===== Hugging Face Spaces =====
HF_SPACE_MUSICGEN=https://facebook-musicgen.hf.space/api/predict
HF_SPACE_ACE_STEP=https://bingmic-ace-step.hf.space/api/predict
HF_SPACE_YUE=https://empower-lt-yue.hf.space/api/predict
HF_TOKEN=your_h...oken  # 可选

# ===== Resend 邮件 =====
RESEND_API_KEY=re_xxxxxxxx
EMAIL_FROM=noreply@music.com

# ===== Sentry 监控 =====
SENTRY_DSN=https://xxx@sentry.io/xxx
SENTRY_ENVIRONMENT=production

# ===== 功能开关 =====
ENABLE_VOICE_CLONE=false
ENABLE_MV_GENERATION=false
ENABLE_PAYMENT=false
ENABLE_COMMUNITY=false
ENABLE_COLLABORATION=false

# ===== 限流配置 =====
RATE_LIMIT_PER_MINUTE=60
MAX_DAILY_GENERATIONS=10
```

---

## ⚡ 迁移步骤 (4-6 小时)

### 步骤 1: 数据库迁移 (30 分钟)
```bash
# 1. 创建 Supabase 项目 (免费版)
# 2. 运行 Alembic 迁移
cd backend
alembic revision --autogenerate -m "Add V1.1 core tables"
alembic upgrade head

# 验证
psql $DATABASE_URL -c "\dt"  # 应显示 10 张表
```

### 步骤 2: AI Provider 适配 (1 小时)
```bash
# 1. 复制 mureka_service.py → hf_music_service.py
cp backend/app/services/mureka_service.py backend/app/services/hf_music_service.py

# 2. 修改 API 调用 (约 100 行)
# - 替换 Mureka URL → HF Space URL
# - 替换 payload 格式
# - 保留重试/状态管理逻辑

# 3. 测试
pytest backend/tests/test_hf_music.py
```

### 步骤 3: R2 存储适配 (30 分钟)
```bash
# 修改 cdn_uploader.py
# - 添加 R2 endpoint
# - 修改 bucket 配置
# - 保留文件处理逻辑

# 测试上传
python -c "from app.services.cdn_uploader import R2Uploader; u=R2Uploader(); u.upload_audio('test.mp3', 1)"
```

### 步骤 4: 环境变量配置 (15 分钟)
```bash
# 复制示例配置
cp .env.example .env.v1_production

# 填入密钥 (从配置文件读取)
# - Supabase
# - R2
# - Gemini
# - Resend
# - Sentry
```

### 步骤 5: 部署到 Cloud Run (1 小时)
```bash
# 1. Docker 镜像构建
docker build -t gcr.io/xxx/music-api:v1.1 .

# 2. 推送到 GCR
docker push gcr.io/xxx/music-api:v1.1

# 3. 部署到 Cloud Run (免费层)
gcloud run deploy music-api \
  --image gcr.io/xxx/music-api:v1.1 \
  --platform managed \
  --region us-central1 \
  --memory 512Mi \
  --cpu 1 \
  --concurrency 80 \
  --set-env-vars-from-file=.env.v1_production \
  --allow-unauthenticated

# 验证
curl $(gcloud run services describe music-api --format='get(status.url)')/health
```

### 步骤 6: 前端部署到 Pages (30 分钟)
```bash
# 1. 修改 Next.js 配置
# next.config.js
module.exports = {
  env: {
    API_BASE_URL: 'https://music-api-xxx.run.app',
    ENABLE_COMMUNITY: 'false',
    ENABLE_DAW: 'false'
  }
}

# 2. 部署到 Cloudflare Pages
npx wrangler pages deploy frontend/dist --project-name=music-platform

# 3. 绑定自定义域名
# music.com → Cloudflare Pages
```

### 步骤 7: 集成测试 (1 小时)
```bash
# 完整链路测试
1. 登录 → /api/v1/me ✅
2. 生成歌词 → POST /api/v1/prompts/optimize ✅
3. 创建任务 → POST /api/v1/task/create ✅
4. 查询状态 → GET /api/v1/task/{id}/status ✅
5. 等待完成 → 轮询直到 completed ✅
6. 播放音频 → GET /api/v1/media/{id}/download ✅
7. 分享链接 → /song/{id} 公开页 ✅
```

---

## 📊 代码复用率统计

| 模块 | 现有代码 | 复用代码 | 修改代码 | 复用率 |
|------|----------|----------|----------|--------|
| **后端服务** | 57 文件 | 52 文件 | 5 文件 | **91%** |
| **API 路由** | 152 端点 | 12 端点 (V1.1) | 0 端点 | **100%** |
| **数据库** | 3 表 | 3 表 | +10 表新增 | **30%** (新增为主) |
| **前端页面** | 18 页面 | 6 页面 | 2 页面微调 | **80%** |
| **AI Provider** | 1 个 (Mureka) | 85% 逻辑 | 15% API 调用 | **85%** |
| **存储层** | 1 个 (CDN) | 80% 逻辑 | 20% 配置 | **80%** |

**综合复用率**: **85-90%**  
**新增代码量**: ~500 行 (主要是 DB 模型 + HF 适配)  
**修改代码量**: ~200 行 (配置调整)  

---

## 🎯 二期功能预留

### 已实现但 V1.1 禁用的功能

| 功能 | 文件 | 状态 | 二期启用条件 |
|------|------|------|--------------|
| **人声克隆** | `voice_clone_service.py` | ✅ 已完成 | 用户 > 1000/日 |
| **MV 生成** | `video_sync_service.py` | ✅ 已完成 | GPU 成本 < $0.01/首 |
| **实时协作** | `collaboration.py` (21 端点) | ✅ 已完成 | 付费用户 > 100 |
| **社区榜单** | `community.py` | ✅ 已完成 | 作品 > 1000 首 |
| **私信系统** | `messages.py` | ✅ 已完成 | 用户 > 5000 |
| **专业 DAW** | `TrackStudio.tsx` | ✅ 已完成 | 专业用户 > 20% |
| **母带处理** | `audio_mastering.py` | ✅ 已完成 | AI 音质优化需求 |
| **音频分离** | `audio_separation.py` | ✅ 已完成 | 版权风险降低 |
| **支付系统** | `payment.py` | ✅ 已完成 | MRR > $1000/月 |
| **推荐引擎** | `recommendation.py` | ✅ 已完成 | 作品 > 10000 首 |

**策略**: 代码已写好，**配置开关控制**，随时启用！

---

## ✅ 总结

### 现有代码直接复用
- ✅ **57 个服务** → 复用 52 个 (91%)
- ✅ **152 个 API** → 启用 12 个核心 (其余二期)
- ✅ **18 个页面** → 启用 6 个核心 (其余二期)
- ✅ **Mureka 服务** → 85% 逻辑复用，仅换 API 调用
- ✅ **CDN 上传** → 80% 逻辑复用，仅改 R2 配置

### 仅需新增
- ➕ **10 张数据表** (~200 行)
- ➕ **HF 适配代码** (~100 行)
- ➕ **R2 配置** (~50 行)
- ➕ **环境变量配置** (~50 行)

### 总工作量
- **新增**: ~400 行代码
- **修改**: ~200 行代码
- **复用**: ~10,000+ 行代码
- **时间**: 4-6 小时

---

**结论**: **V1.1 架构 90% 代码已就绪，仅需少量适配即可上线！** 🚀

需要我立即开始执行迁移吗？第一步：创建 10 张数据表模型？