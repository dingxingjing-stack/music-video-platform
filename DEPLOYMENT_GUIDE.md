# Music Video Platform v2.0 - 部署指南

## 📦 系统要求

- **Node.js**: ≥18.x
- **Python**: ≥3.11
- **uv**: 已安装（用于 Python 包管理）
- **FFmpeg**: 用于音频导出（可选）

## 🚀 快速启动

### 1. 前端开发服务器

```bash
cd /c/Users/dingx/music-video-platform/frontend
npm install  # 首次运行
npm run dev  # 启动开发服务器
```

**访问**: http://localhost:3000

### 2. 后端 API 服务器

```bash
cd /c/Users/dingx/music-video-platform/backend
uv pip install -r requirements.txt  # 首次运行
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**API 文档**: http://localhost:8000/docs

## 🎵 AI 音乐生成配置

### Mureka API

1. **获取 API Key**: https://platform.mureka.ai/
2. **设置环境变量**:
   ```bash
   # Windows PowerShell
   $env:MUREKA_API_KEY="your_api_key_here"
   
   # Linux/Mac
   export MUREKA_API_KEY="your_api_key_here"
   ```
3. **或编辑文件**: `backend/app/services/mureka_service.py`
   - 替换 `API_KEY` 默认值

### API 端点

- `GET /api/v1/ai/styles` - 获取支持的音乐风格
- `POST /api/v1/ai/generate` - 生成音乐
  ```json
  {
    "prompt": "夏日午后轻松愉悦的流行音乐",
    "style": "pop",
    "duration": 180,
    "type": "song"
  }
  ```

## 🔧 核心功能

| 功能 | 路径 | 说明 |
|------|------|------|
| 多轨编辑器 | `/` → "多轨编辑" | Cubase 风格多轨时间轴 |
| MIDI 编辑器 | `/path-d` | 钢琴卷帘 + GM 乐器 |
| 效果器 | 多轨编辑器 → "🎛️ 效果器" | EQ/压缩/混响/延迟/增益 |
| 自动化曲线 | 多轨编辑器 → "📈 自动化" | 7 种轨道参数 |
| 项目管理 | 多轨编辑器 → "📁 项目" | 保存/加载/导入/导出 |
| 音频导出 | 多轨编辑器 → "📤 导出音频" | WAV/MP3/FLAC + 分轨 |
| AI 生成 | 多轨编辑器 → "✨ AI 生成" | Mureka API 集成 |
| 社区/发现 | `/community` | Suno 风格 feed |

## 📁 项目结构

```
music-video-platform/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── MultiTrackEditor/   # 多轨编辑器组件
│   │   │   ├── TrackStudio/        # 效果器/自动化/项目/AI 导出
│   │   │   └── MidiEditor/         # MIDI 钢琴卷帘
│   │   ├── pages/
│   │   │   ├── TrackStudio.tsx     # 主工作室页面
│   │   │   └── CommunityFeed.tsx   # 社区发现页
│   │   ├── types/                  # TypeScript 类型定义
│   │   └── utils/                  # 工具函数
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── routers/
│   │   │   └── ai_music.py         # AI 音乐生成路由
│   │   └── services/
│   │       ├── mureka_service.py   # Mureka API 封装
│   │       ├── audio_export.py     # 音频导出服务
│   │       └── audio_router.py     # 音频处理路由
│   └── requirements.txt
└── README.md
```

## 🐛 故障排查

### 前端无法访问

1. 检查端口：`netstat -ano | findstr :3000`
2. 重启开发服务器：`npm run dev`
3. 清除缓存：`rm -rf node_modules/.vite && npm run dev`

### 后端 API 错误

1. 查看日志：后端控制台输出
2. 测试健康检查：`curl http://localhost:8000/api/v1/ai/styles`
3. 检查 Python 依赖：`uv pip install -r requirements.txt`

### AI 生成失败

1. **配额限制**: API 返回 429 → 等待或充值
2. **网络错误**: 检查网络连接
3. **降级处理**: 自动回退到 Mock 音频（示例音频）

## 🔐 生产环境部署

### 方式一：Docker 部署（推荐）

```bash
# 1. 复制环境变量
cp .env.example .env

# 2. 编辑 .env 文件
#    MUREKA_API_KEY=sk-your-api-key-here

# 3. 构建并启动
docker-compose up -d

# 4. 查看日志
docker-compose logs -f app

# 5. 健康检查
curl http://localhost:8000/api/v1/ai/styles

# 停止服务
docker-compose down
```

### 方式二：手动部署

```bash
cd frontend
npm run build
# 输出到 dist/ 目录
# 部署到 Nginx/Vercel/Netlify
```

### 后端部署

```bash
cd backend
# 使用 Gunicorn + Uvicorn workers
uvicorn main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --no-access-log
```

### 环境变量（生产）

```bash
# 必需
MUREKA_API_KEY=sk-xxxxxxxx

# 可选
FRONTEND_URL=https://your-domain.com
ALLOWED_ORIGINS=https://your-domain.com
```

## 📝 更新日志

### v2.0 (2026-07-10)
- ✅ 多轨时间轴编辑器（Cubase 风格）
- ✅ 音频剪辑/拖拽/淡入淡出
- ✅ MIDI 钢琴卷帘编辑器（128 键 + GM 乐器）
- ✅ 效果器链（EQ/压缩/混响/延迟/增益）
- ✅ 自动化曲线（7 种轨道）
- ✅ 项目/工程文件管理
- ✅ 音频导出（WAV/MP3/FLAC，分轨 + 混音）
- ✅ 社区/发现页面（Suno 风格 feed）
- ✅ AI 音频生成（Mureka API 集成）
- ✅ 后端 API（/api/v1/ai/generate + /styles）

---

**🎵 Music Video Platform v2.0 — 专业 DAW + AI 混合工作台**