# 🎵 Music Video Platform v2.0

**专业级 DAW + AI 混合工作台**  
*Professional Audio Workstation with AI-Integrated Workflow*

[![Status](https://img.shields.io/badge/status-complete-success)](PROJECT_SUMMARY.md)
[![Version](https://img.shields.io/badge/version-2.0-blue)](PROJECT_SUMMARY.md)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## 🚀 快速开始

### 开发环境（推荐新手）

**Windows:**
```bash
deploy.bat
```

**Linux/Mac:**
```bash
chmod +x deploy.sh
./deploy.sh dev
```

访问：
- **前端**: http://localhost:3000
- **后端 API**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs

### 生产环境

**Docker 部署:**
```bash
cp .env.example .env
# 编辑 .env 设置 MUREKA_API_KEY

docker-compose up -d
```

**手动部署:**
```bash
./deploy.sh prod
```

---

## ✨ 核心功能

### 🎹 DAW 功能（9 项）

| 功能 | 描述 | 入口 |
|------|------|------|
| **多轨编辑器** | Cubase 风格多轨时间轴 | 主页 → "多轨编辑" |
| **音频剪辑** | 拖拽/调整大小/淡入淡出 | 多轨编辑器 |
| **MIDI 编辑器** | 128 键钢琴卷帘 + GM 乐器 | Path D |
| **效果器链** | EQ/压缩/混响/延迟/增益 | 多轨编辑器 → 🎛️ |
| **自动化曲线** | 7 种轨道参数自动化 | 多轨编辑器 → 📈 |
| **项目管理** | 保存/加载/导入/导出 | 多轨编辑器 → 📁 |
| **音频导出** | WAV/MP3/FLAC + 分轨导出 | 多轨编辑器 → 📤 |
| **AI 生成** | Mureka AI 音乐生成 | 多轨编辑器 → ✨ |
| **社区发现** | Suno 风格作品 feed | /community |

### 🤖 AI 功能

- **歌曲生成**: 提示词 → 完整歌曲（带人声）
- **纯音乐**: 提示词 → 器乐曲
- **背景音乐**: 自定义时长 BGM
- **10 种风格**: 流行/摇滚/电子/嘻哈/R&B/爵士/古典/氛围/电影配乐/Lo-Fi

---

## 📚 文档

| 文档 | 说明 |
|------|------|
| [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | 详细部署指南 |
| [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) | 项目总结与技术细节 |
| [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) | 部署检查清单 |
| [API Docs](http://localhost:8000/docs) | FastAPI 自动生成 |

---

## 🛠️ 技术栈

### 前端
- **框架**: React 18 + TypeScript + Vite
- **样式**: Tailwind CSS
- **音频**: Tone.js, @tonejs/midi, wavesurfer.js
- **路由**: React Router v6

### 后端
- **框架**: FastAPI + Uvicorn
- **语言**: Python 3.11+
- **AI 集成**: Mureka API, HTTPX
- **验证**: Pydantic v2

### 部署
- **容器**: Docker + Docker Compose
- **代理**: Nginx（可选）
- **CI/CD**: GitHub Actions（待配置）

---

## 🎯 项目亮点

1. **AI + DAW 混合工作流**
   - 从提示词直接生成音频到轨道
   - 支持 10 种音乐风格
   - 自动回退机制（API 失败时用 Mock）

2. **专业级多轨编辑**
   - Cubase 风格时间轴
   - 无损音频处理
   - 实时播放控制

3. **完整效果器链**
   - 5 种专业效果器
   - 独立开关 + 参数调节
   - 可视化参数面板

4. **自动化曲线**
   - 7 种可自动化参数
   - 贝塞尔曲线绘制
   - 控制点拖拽编辑

5. **社区发现系统**
   - Suno 风格 feed 流
   - 标签过滤
   - 社交互动功能

---

## 📦 项目结构

```
music-video-platform/
├── frontend/                 # 前端代码
│   ├── src/
│   │   ├── components/       # React 组件
│   │   ├── pages/            # 页面
│   │   ├── types/            # TypeScript 类型
│   │   └── utils/            # 工具函数
│   └── package.json
├── backend/                  # 后端代码
│   ├── app/
│   │   ├── routers/          # API 路由
│   │   └── services/         # 业务逻辑
│   └── requirements.txt
├── DEPLOYMENT_GUIDE.md       # 部署指南
├── PROJECT_SUMMARY.md        # 项目总结
├── DEPLOYMENT_CHECKLIST.md   # 检查清单
├── docker-compose.yml        # Docker 配置
├── Dockerfile                # 容器镜像
├── deploy.sh / deploy.bat    # 部署脚本
└── README.md                 # 本文件
```

---

## 🧪 测试

### 功能测试
```bash
# 前端构建测试
cd frontend
npm run build

# 后端 API 测试
curl http://localhost:8000/api/v1/ai/styles
curl -X POST http://localhost:8000/api/v1/ai/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"test","style":"pop"}'
```

### 浏览器测试
访问 http://localhost:3000 并测试：
- ✅ 多轨编辑器加载
- ✅ 添加轨道/片段
- ✅ MIDI 编辑器
- ✅ 效果器面板
- ✅ 自动化曲线
- ✅ AI 生成

---

## 🔧 故障排查

### 常见问题

**Q: 前端无法访问？**
```bash
# 检查端口
netstat -ano | findstr :3000

# 重启开发服务器
cd frontend && npm run dev
```

**Q: 后端 API 错误？**
```bash
# 查看日志
docker-compose logs -f app

# 测试健康检查
curl http://localhost:8000/api/v1/ai/styles
```

**Q: AI 生成失败？**
- 检查 MUREKA_API_KEY 是否正确
- API 配额耗尽会自动回退到 Mock 音频
- 查看后端日志获取详细错误

详见 [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) 故障排查章节。

---

## 📝 更新日志

### v2.0 (2026-07-10)
**🎉 首次完整发布**
- ✅ 多轨时间轴编辑器
- ✅ 音频剪辑/淡入淡出
- ✅ MIDI 钢琴卷帘
- ✅ 效果器链（5 种）
- ✅ 自动化曲线（7 轨道）
- ✅ 项目管理
- ✅ 音频导出
- ✅ 社区/发现页面
- ✅ AI 音频生成（Mureka API）
- ✅ 后端 API 服务
- ✅ Docker 部署支持

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

---

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

---

## 📞 联系方式

- **项目主页**: https://github.com/yourusername/music-video-platform
- **问题反馈**: https://github.com/yourusername/music-video-platform/issues
- **API 文档**: http://localhost:8000/docs

---

**🎵 Music Video Platform v2.0**  
*专业 DAW + AI 混合工作台 — 开发完成*  
2026-07-10