# 个人编码习惯.md

## 🌐 语言偏好

- **对话语言**：中文（除非特别要求英文）
- **注释语言**：中文
- **变量/函数命名**：英文
- **Git 提交消息**：中文前缀 + 英文描述

## 🎨 UI 设计偏好

- **色系**：深色背景（`#121212`），橙色渐变强调
- **风格**：赛博音乐风格，Suno.com 风格
- **Tailwind CSS**：原生 Tailwind，不依赖重型 UI 框架（antd 已安装但尽量少用）

## 🏗 架构风格

- **模块化路由**：每个功能模块独立 router + 独立 service
- **Mock 优先**：API 不通时自动降级 Mock，不做阻塞
- **快速验证**：每做完一小步立即 curl/浏览器验证
- **资源节约**：优先免费方案，不推荐付费套餐
- **分步执行**：从简单到难，每阶段验证后再继续

## 💻 开发习惯

1. **构建前先验证**：`npx tsc --noEmit` 检查类型
2. **API 测试**：`curl` 验证而不是只看代码
3. **Git 流程**：小步 commit，清晰消息
4. **拒绝冗余**：KISS/DRY，删除无效 import 和未使用变量
5. **端口管理**：后端 8000/8001，前端 3000
6. **Windows 注意**：路径用 `~/` 或 `C:\Users\xxx\`，bash 用 git-bash

## 🔥 踩坑记录（高频）

- **Render 部署**：两个项目关联同个仓库可能导致互相干扰，需关闭自动部署
- **端口释放**：Windows 上 `pkill -f uvicorn` 不够，需 `netstat -ano | findstr :8000` + `taskkill /PID`
- **路由前缀**：`include_router` 时注意不要重复添加 `/api/v1/` 前缀
- **SQLite**：部署后会重置，不适合生产数据
- **CF Pages**：修改 `tsconfig.json` 的 `noUnusedLocals` 和 `noUnusedParameters` 可减少很多 TS 错误

## 📦 技术选型原则

1. 能用免费/低成本的绝不付费
2. 能用 Mock 的绝不依赖真实 API
3. 能本地 SQLite 的绝不依赖云数据库
4. 能用 Cloudflare 免费套餐的绝不考虑 AWS
5. SSR 谨慎使用，优先静态部署（CF Pages）

## 🧪 测试原则

- 无单元测试，全部手动 curl + 浏览器验证
- 验收清单驱动：每功能做完列清单逐项打勾
- 优先检查 HTTP 200/404/500 边界情况