# RunwayML API 配置说明

## 获取 API Key

1. 访问：https://runwayml.com
2. 注册/登录账号
3. 进入 Settings → API
4. 生成 API Key

## 配置方法

### 方法 A: 环境变量 (推荐)
在 `.env` 文件中添加:
```
RUNWAYML_API_KEY=your_api_key_here
```

### 方法 B: 配置文件
复制 `backend/.env.example` 为 `backend/.env`，填入:
```
RUNWAYML_API_KEY=your_api_key_here
```

## 价格说明

- **Gen-2 (图生视频)**: $0.35/秒
  - 4 秒视频 = $1.4
  - 8 秒视频 = $2.8
  
- **Inpainting (AI 扩图)**: $0.05/张

- **Segmentation (背景移除)**: $0.02/张

- **免费额度**: 125 credits/月 (约$12.5)

## 测试命令

配置 API Key 后，运行:
```bash
# 测试图生视频
curl -X POST http://localhost:8001/api/v1/ai-effects/video \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://example.com/image.jpg",
    "prompt": "camera zoom in",
    "motion_score": 5,
    "duration": 4
  }'

# 查询状态
curl http://localhost:8001/api/v1/ai-effects/status/{task_id}
```

## 注意事项

1. **首次使用**: 建议先用免费额度测试
2. **生产环境**: 设置使用上限，防止超额
3. **错误处理**: API 已内置重试和错误提示
4. **配额监控**: 定期检查剩余 credits

## 备用方案

如果 RunwayML API 不可用，系统会自动降级:
- 背景移除 → 使用本地 rembg 库 (免费)
- 图生视频 → 返回提示 "API 配额耗尽"