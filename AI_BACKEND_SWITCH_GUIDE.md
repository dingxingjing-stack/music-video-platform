# AI 服务切换指南

## 开发阶段（Gemini 免费额度）

当前配置使用 **Gemini AI** 作为临时方案，享受免费额度适合开发和测试。

### 配置文件 `.env`

```bash
# 开发阶段：使用 Gemini（免费）
GEMINI_API_KEY=your-gemini-api-key-here

# 生产阶段：注释掉上面这行，取消下面这行注释
# MUREKA_API_KEY=sk-your-api-key-here
```

### 获取 Gemini API Key

1. 访问：https://aistudio.google.com/apikey
2. 登录 Google 账号
3. 创建 API Key（免费）
4. 复制到 `.env` 文件

### Gemini 服务特性

| 功能 | 状态 | 说明 |
|------|------|------|
| **提示词优化** | ✅ | Gemini 自动优化音乐提示词 |
| **风格建议** | ✅ | 返回相关风格标签 |
| **音频生成** | ⚠️  | Mock 音频（开发阶段） |
| **免费额度** | ✅ | 每月 60 次请求（Gemini 2.0 Flash） |

---

## 生产阶段（Mureka API）

正式上线时切换回 **Mureka API**（真实音频生成）。

### 切换步骤

1. **编辑 `.env`**:
   ```bash
   # 注释掉 Gemini
   # GEMINI_API_KEY=...
   
   # 启用 Mureka
   MUREKA_API_KEY=sk-your-api-key-here
   ```

2. **修改 `backend/main.py`**:
   ```python
   # 当前（Gemini）:
   from app.routers import gemini_ai_music as ai_music
   
   # 改为（Mureka）:
   from app.routers import ai_music
   ```

3. **重启后端**:
   ```bash
   # 停止旧进程
   # 启动新进程
   cd backend
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

4. **验证**:
   ```bash
   curl -X POST http://localhost:8000/api/v1/ai/generate \
     -H "Content-Type: application/json" \
     -d '{"prompt":"test","style":"pop"}'
   ```

### Mureka 服务特性

| 功能 | 状态 | 说明 |
|------|------|------|
| **真实音频生成** | ✅ | AI 生成完整音乐（带人声/器乐） |
| **10 种风格** | ✅ | pop/rock/electronic/hip-hop/r&b/jazz/classical/ambient/cinematic/lo-fi |
| **多种类型** | ✅ | song（带歌词）/music（纯音乐）/bgm（背景音乐） |
| **付费模式** | 💰 | 按生成次数计费 |

---

## 代码文件对比

| 文件 | Gemini 版本 | Mureka 版本 |
|------|-------------|-------------|
| **服务** | `gemini_music_service.py` | `mureka_service.py` |
| **路由** | `gemini_ai_music.py` | `ai_music.py` |
| **导入** | `from app.routers import gemini_ai_music as ai_music` | `from app.routers import ai_music` |

---

## 快速切换脚本

创建 `switch_ai-backend.sh` 脚本：

```bash
#!/bin/bash
# 切换 AI 后端（Gemini ↔ Mureka）

MODE=${1:-gemini}

if [ "$MODE" = "gemini" ]; then
    echo "Switching to Gemini AI (free tier)..."
    # 更新 .env
    sed -i 's/^GEMINI_API_KEY=/#GEMINI_API_KEY=/' .env
    sed -i 's/^#MUREKA_API_KEY=/MUREKA_API_KEY=/' .env
    sed -i 's/from app.routers import ai_music/from app.routers import gemini_ai_music as ai_music/' backend/main.py
else
    echo "Switching to Mureka AI (production)..."
    # 更新 .env
    sed -i 's/^#GEMINI_API_KEY=/GEMINI_API_KEY=/' .env
    sed -i 's/^MUREKA_API_KEY=/#MUREKA_API_KEY=/' .env
    sed -i 's/from app.routers import gemini_ai_music as ai_music/from app.routers import ai_music/' backend/main.py
fi

echo "Restart backend..."
# 重启后端逻辑
```

---

## API 端点

两个服务使用相同的端点，切换无需修改前端代码：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/ai/styles` | GET | 获取音乐风格列表 |
| `/api/v1/ai/generate` | POST | 生成音乐 |

**请求格式**:
```json
{
  "prompt": "夏日午后轻松愉悦的流行音乐",
  "style": "pop",
  "duration": 180,
  "type": "song"
}
```

**响应格式**:
```json
{
  "success": true,
  "audio_url": "https://...",
  "optimized_prompt": "...",
  "style_suggestions": ["upbeat", "summer", "guitar"],
  "error": null,
  "task_id": "gemini-xxxxx"
}
```

---

**🎵 Music Video Platform v2.0**  
*开发阶段：Gemini（免费） · 生产阶段：Mureka（真实音频）*  
2026-07-10