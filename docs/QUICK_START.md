# 🚀 Music Video Platform v2.0 — 快速上手指南

**3 分钟学会使用所有功能**

---

## ⚡ 30 秒启动

```bash
# 终端 1 — 后端
cd backend && uvicorn main:app --port 8000

# 终端 2 — 前端
cd frontend && npx vite --port 3001
```

打开浏览器 → `http://localhost:3001`

---

## 🎵 1 分钟生成你的第一首歌

1. 点击 **"路径 A — Suno 风格"**
2. 输入提示词：`一首温暖的流行歌曲`
3. 点击 **"✨ 🎵 生成"**
4. 完成！

---

## 🎚️ 30 秒打开混音台

1. 点击 **"多轨编辑"**
2. 点击 **"🎚️ 混音台"**
3. 拖动推子调整音量
4. 点击 **Mute** / **Solo** 控制轨道

---

## 🏆 30 秒浏览社区

1. 左侧导航 → **"🏆 社区排行榜"**
2. 点击 **🔥热门 / 🆕新歌 / 📈趋势**
3. 搜索或按风格筛选

---

## 🎛️ 高级功能速查

| 功能 | 入口 | 一句话说明 |
|------|------|-----------|
| AI 生成 | 路径 A | 提示词 → 完整歌曲 |
| 混音台 | 多轨编辑 → 🎚️ | 音量/声像/效果器 |
| 分轨导出 | 📤 导出 | 分离人声/鼓/贝斯 |
| 音阶辅助 | MIDI 编辑器 | 8 种音阶 + 防错音 |
| 音高修正 | MIDI 编辑器 | 自动修正到音阶 |
| 和弦轨道 | MIDI 编辑器 | 26 和弦 + 自动进行 |
| Comping | 多轨编辑 | 多次录制取最佳 |
| 时间伸缩 | 多轨编辑 | 变速不变调 |
| Remix | 多轨编辑 | 10 种风格转换 |
| 声音克隆 | 多轨编辑 | 上传样本 → AI 模仿 |

---

## 🔌 API 快速调用

```bash
# 社区排行榜
curl http://localhost:8000/api/v1/community/hot

# Remix 风格列表
curl http://localhost:8000/api/v1/remix/styles

# 和弦库
curl http://localhost:8000/api/v1/chords/library

# 音阶列表
curl http://localhost:8000/api/v1/pitch/scales

# Swagger 文档
# 浏览器打开 http://localhost:8000/docs
```

---

## ❓ 遇到问题？

| 问题 | 解决方案 |
|------|---------|
| 页面空白 | `Ctrl+F5` 硬刷新 |
| API 404 | 检查后端是否运行 |
| 端口被占 | `taskkill /PID <PID> /F` |
| 编译错误 | `cd frontend && npm run build` |

---

*更多详情请查看 `docs/USER_GUIDE.md`* 📖