# 一键发布功能 (One-Click Publish)

将音乐视频一键发布到多个平台：YouTube、TikTok、哔哩哔哩

## 功能特性

### 支持的平台

- **YouTube** (Data API v3)
  - 标题/描述/标签管理
  - 隐私设置 (公开/不公开/私密)
  - 分类选择
  - 缩略图上传
  - 儿童内容声明

- **TikTok** (Upload API)
  - 标题/描述/标签
  - 隐私设置
  - 背景音乐集成
  - 直接上传

- **哔哩哔哩** (开放平台 API)
  - 分区选择
  - 标签/话题
  - 版权声明
  - 原创声明

### OAuth 2.0 集成

- 安全的授权流程
- access_token/refresh_token 自动管理
- Token 自动刷新
- 多账号支持 (扩展功能)

### Mock 模式

当没有配置 API Key 时，自动切换到 Mock 模式：
- 模拟上传成功
- 显示假进度条动画
- 用于开发和演示

## API 端点

### 获取平台列表
```
GET /api/v1/publish/platforms
```

响应示例:
```json
{
  "platforms": [
    {
      "id": "youtube",
      "name": "YouTube",
      "icon": "📺",
      "supported": true,
      "authorized": false,
      "features": ["标题/描述/标签", "隐私设置", "分类选择"]
    }
  ]
}
```

### 授权平台
```
POST /api/v1/publish/auth/{platform}
```

请求体:
```json
{
  "redirect_uri": "http://localhost:3000/auth/callback"
}
```

### 上传视频
```
POST /api/v1/publish/upload
```

请求体:
```json
{
  "video_url": "/results/video.mp4",
  "platforms": ["youtube", "bilibili"],
  "title": "我的音乐视频",
  "description": "视频描述",
  "tags": ["music", "mv"],
  "privacy": "public",
  "youtube_category_id": "10",
  "bilibili_tid": 112
}
```

### 查询发布状态
```
GET /api/v1/publish/status/{task_id}
```

响应示例:
```json
{
  "task_id": "abc12345",
  "status": "completed",
  "progress": 100,
  "message": "成功 2/2 平台",
  "platform_results": {
    "youtube": {
      "status": "success",
      "video_id": "dQw4w9WgXcQ",
      "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    },
    "bilibili": {
      "status": "success",
      "video_id": "BV1xxx",
      "url": "https://www.bilibili.com/video/BV1xxx"
    }
  }
}
```

## 前端组件

### PlatformSelector
平台选择组件，支持多选和显示授权状态。

```tsx
import { PlatformSelector } from './components/PlatformSelector';

function MyComponent() {
  const [selected, setSelected] = useState([]);
  
  return (
    <PlatformSelector
      selectedPlatforms={selected}
      onPlatformToggle={setSelected}
    />
  );
}
```

### OneClickPublish
完整的一键发布组件，包含表单、进度条和状态通知。

```tsx
import { OneClickPublish } from './components/OneClickPublish';

function VideoPage({ videoUrl }) {
  return (
    <OneClickPublish
      videoUrl={videoUrl}
      onClose={() => console.log('closed')}
    />
  );
}
```

## 配置 API Keys

### YouTube
1. 访问 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建项目并启用 YouTube Data API v3
3. 创建 OAuth 2.0 凭据
4. 在 `.env` 文件中配置:
```
YOUTUBE_API_KEY=your_api_key
YOUTUBE_CLIENT_ID=your_client_id
YOUTUBE_CLIENT_SECRET=your_client_secret
YOUTUBE_ACCESS_TOKEN=optional_access_token
YOUTUBE_REFRESH_TOKEN=optional_refresh_token
```

### TikTok
1. 访问 [TikTok for Developers](https://developers.tiktok.com/)
2. 创建应用并申请上传权限
3. 配置 `.env`:
```
TIKTOK_CLIENT_KEY=your_client_key
TIKTOK_CLIENT_SECRET=your_client_secret
TIKTOK_ACCESS_TOKEN=optional_access_token
TIKTOK_REFRESH_TOKEN=optional_refresh_token
```

### 哔哩哔哩
1. 访问 [Bilibili 开放平台](https://open.bilibili.com/)
2. 创建应用
3. 配置 `.env`:
```
BILIBILI_APP_KEY=your_app_key
BILIBILI_APP_SECRET=your_app_secret
BILIBILI_ACCESS_TOKEN=optional_access_token
BILIBILI_REFRESH_TOKEN=optional_refresh_token
```

## 测试

运行测试脚本:
```bash
cd backend
python scripts/test_one_click_publish.py
```

确保后端服务器正在运行:
```bash
cd backend
uvicorn main:app --reload --port 8000
```

## 文件结构

```
backend/
├── app/
│   ├── routers/
│   │   └── one_click_publish.py    # 主要路由
│   └── services/
│       ├── youtube_service.py      # YouTube 服务
│       ├── tiktok_service.py       # TikTok 服务
│       └── bilibili_service.py     # B 站服务
└── scripts/
    └── test_one_click_publish.py   # 测试脚本

frontend/
└── src/
    ├── components/
    │   ├── OneClickPublish.tsx     # 主组件
    │   └── PlatformSelector.tsx    # 平台选择器
    └── api/
        └── publish.ts              # API 客户端
```

## 使用流程

1. **选择平台**: 在 PlatformSelector 中勾选要发布的平台
2. **填写信息**: 输入标题、描述、标签等
3. **配置选项**: 设置隐私、分类等平台特定选项
4. **点击发布**: 一键发布到所有选中的平台
5. **查看进度**: 实时查看各平台的上传进度
6. **获取结果**: 发布完成后获取各平台的视频链接

## 注意事项

- Mock 模式仅用于开发测试，生产环境需要配置真实的 API Keys
- 视频文件需要预先上传到服务器或可访问的 URL
- 各平台的审核时间不同，视频可能需要几分钟到几小时才能公开
- 请遵守各平台的内容政策和版权规定

## 扩展开发

添加新平台:

1. 创建服务类 `backend/app/services/newplatform_service.py`
2. 实现 `publish_video()` 方法
3. 在 `one_click_publish.py` 中注册新平台
4. 更新前端组件支持新平台选项

## 相关文档

- [YouTube Data API v3](https://developers.google.com/youtube/v3)
- [TikTok Display API](https://developers.tiktok.com/doc/display-api-introduction/)
- [Bilibili 开放平台](https://open.bilibili.com/)