# 部署检查清单 (Deployment Checklist)

## 📋 部署前准备

### 环境检查
- [ ] Node.js ≥18.x 已安装
- [ ] Python ≥3.11 已安装
- [ ] FFmpeg 已安装（音频导出）
- [ ] Docker & Docker Compose 已安装（可选）

### 配置文件
- [ ] `.env` 文件已创建（从 `.env.example` 复制）
- [ ] `MUREKA_API_KEY` 已设置
- [ ] `FRONTEND_URL` 已配置
- [ ] `ALLOWED_ORIGINS` 已设置

### 依赖安装
- [ ] `frontend/package.json` 依赖已安装 (`npm install`)
- [ ] `backend/requirements.txt` 依赖已安装 (`pip install -r requirements.txt`)

## 🚀 开发环境部署

### 快速启动（Windows）
```bash
deploy.bat
```

### 快速启动（Linux/Mac）
```bash
chmod +x deploy.sh
./deploy.sh dev
```

### 手动启动
```bash
# Terminal 1 - Backend
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 - Frontend
cd frontend
npm run dev
```

### 验证
- [ ] 前端可访问：http://localhost:3000
- [ ] 后端可访问：http://localhost:8000
- [ ] API 文档：http://localhost:8000/docs
- [ ] AI 风格端点：`GET /api/v1/ai/styles`

## 🌐 生产环境部署

### Docker 部署
1. [ ] `.env` 文件已正确配置
2. [ ] `docker-compose.yml` 已检查
3. [ ] 构建镜像：`docker-compose build`
4. [ ] 启动服务：`docker-compose up -d`
5. [ ] 健康检查通过
6. [ ] 日志正常：`docker-compose logs -f`

### 手动部署
1. [ ] 前端构建：`npm run build`
2. [ ] 构建输出到 `dist/`
3. [ ] 配置 Nginx 反向代理
4. [ ] 配置 SSL 证书（HTTPS）
5. [ ] 启动后端：`uvicorn main:app --workers 4`
6. [ ] 配置进程守护（systemd/supervisor）

### 安全配置
- [ ] HTTPS 已启用
- [ ] CORS 已正确配置
- [ ] API 限流已启用
- [ ] 敏感信息未泄露（.env 未提交到 Git）
- [ ] 数据库备份已配置

## 🧪 功能测试

### 核心功能
- [ ] 多轨编辑器加载正常
- [ ] 添加轨道/片段功能正常
- [ ] 音频播放/暂停功能正常
- [ ] MIDI 编辑器（Path D）正常
- [ ] 效果器面板（5 种效果器）正常
- [ ] 自动化曲线（7 轨道）正常
- [ ] 项目管理（保存/加载）正常
- [ ] 音频导出功能正常

### AI 功能
- [ ] AI 生成功能面板打开
- [ ] 提示词输入正常
- [ ] 风格选择正常
- [ ] API 调用成功（或 Mock 回退）
- [ ] 生成音频添加到轨道

### 社区功能
- [ ] 社区页面加载正常
- [ ] 帖子列表显示正常
- [ ] 标签过滤功能正常
- [ ] 点赞/播放功能正常

## 📊 性能优化

### 前端
- [ ] 构建体积检查：`npm run build`
- [ ] 代码分割已配置
- [ ] 静态资源 CDN 已配置（可选）
- [ ] 图片已优化

### 后端
- [ ] 数据库连接池已配置
- [ ] 缓存已启用（Redis，可选）
- [ ] 日志轮转已配置
- [ ] 监控已配置（Prometheus/Grafana，可选）

## 🔍 监控与日志

### 日志
- [ ] 应用日志正常输出
- [ ] 错误日志已记录
- [ ] 访问日志已记录
- [ ] 日志级别已正确设置

### 监控
- [ ] 健康检查端点可用
- [ ] 性能监控已配置
- [ ] 错误告警已配置
- [ ] 资源使用监控已配置

## 📱 备份与恢复

### 数据备份
- [ ] 数据库备份脚本已编写
- [ ] 定时备份已配置（cron）
- [ ] 备份文件存储到安全位置
- [ ] 恢复流程已测试

### 灾难恢复
- [ ] 恢复文档已编写
- [ ] 恢复流程已测试
- [ ] 紧急联系人已确定

## ✅ 最终检查

- [ ] 所有测试通过
- [ ] 文档已更新
- [ ] 团队成员已通知
- [ ] 回滚方案已准备
- [ ] 用户通知已准备

---

**签署确认：**

部署人：_____________  
日期：_____________  
版本：v2.0  
环境：[ ] 开发  [ ] 测试  [ ] 生产