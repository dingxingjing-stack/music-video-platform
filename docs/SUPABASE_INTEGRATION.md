# 🗄️ Supabase 数据库集成文档

## ✅ 已完成配置

### 1. Supabase 项目信息

| 项目 | 值 |
|------|-----|
| **项目名** | ai-music-studio-v1 |
| **区域** | 美国东部（北弗吉尼亚） |
| **API URL** | https://gdowyyvzvseheccisdfhl.supabase.co/rest/v1/ |
| **Anon Key** | sb_publishable_HgKv9LIR0-_CPK1sASyzWw_W_vvaOda |
| **Service Role Key** | sb_secret_rETZ_hbLnEdJvr_-IEZPyA_nZv6HMzd |

### 2. 环境变量配置

**后端 `.env` 文件**:
```env
SUPABASE_URL=https://gdowyyvzvseheccisdfhl.supabase.co
SUPABASE_ANON_KEY=sb_publishable_HgKv9LIR0-_CPK1sASyzWw_W_vvaOda
SUPABASE_SERVICE_ROLE_KEY=sb_secret_rETZ_hbLnEdJvr_-IEZPyA_nZv6HMzd
```

**前端 `.env.production`**:
```env
VITE_SUPABASE_URL=https://gdowyyvzvseheccisdfhl.supabase.co
VITE_SUPABASE_ANON_KEY=sb_publishable_HgKv9LIR0-_CPK1sASyzWw_W_vvaOda
```

---

## 📋 数据库表结构

### 已创建的表（8 个）

1. **users** - 用户信息
   - 字段：id, email, username, credits, subscription_tier, age, etc.
   - 索引：email, supabase_user_id

2. **songs** - 歌曲记录
   - 字段：title, lyrics, style, audio_url, mv_url, status, is_public, etc.
   - 索引：user_id, status, is_public

3. **tasks** - 任务队列
   - 字段：task_type, status, progress, result, error_message
   - 索引：user_id, status, task_type

4. **copyright_scans** - 版权检测
   - 字段：song_id, scan_status, risk_level, similarity_score
   - 索引：song_id, user_id, status

5. **activity_logs** - 活动日志
   - 字段：action, resource_type, resource_id, ip_address
   - 索引：user_id, action, created_at

6. **favorites** - 收藏
   - 字段：user_id, song_id
   - 索引：user_id, song_id

7. **comments** - 评论
   - 字段：content, song_id, parent_id, like_count
   - 索引：song_id, user_id, parent_id

8. **subscriptions** - 订阅
   - 字段：plan_type, status, start_date, end_date
   - 索引：user_id, status

---

## 🔧 已实现的功能

### 1. Supabase 服务层 (`app/services/supabase_service.py`)

**用户管理**:
- `get_user(user_id)` - 获取用户信息
- `create_user(email, supabase_user_id)` - 创建用户
- `increment_user_credits(user_id, amount)` - 增加额度
- `decrement_user_credits(user_id, amount)` - 扣除额度

**歌曲管理**:
- `create_song(**data)` - 创建歌曲
- `get_user_songs(user_id, limit)` - 获取用户歌曲列表

**任务管理**:
- `create_task(**data)` - 创建任务
- `update_task(task_id, status)` - 更新任务状态

**版权检测**:
- `create_copyright_scan(**data)` - 创建版权扫描记录

**活动日志**:
- `log_activity(user_id, action, **data)` - 记录活动日志

### 2. API 路由器

#### 认证路由 (`/api/v1/auth`)
- `POST /register` - 用户注册
- `GET /me` - 获取当前用户
- `GET /{user_id}` - 获取用户信息
- `POST /credits/add` - 增加额度
- `POST /credits/consume` - 消耗额度
- `GET /{user_id}/stats` - 用户统计

#### 歌曲管理路由 (`/api/v1/songs`)
- `POST /` - 创建歌曲
- `GET /` - 获取用户歌曲列表
- `GET /{song_id}` - 获取歌曲详情
- `PUT /{song_id}` - 更新歌曲
- `DELETE /{song_id}` - 删除歌曲
- `POST /{song_id}/publish` - 发布歌曲
- `GET /{song_id}/stats` - 歌曲统计

---

## 🔒 安全配置

### RLS (行级安全) 策略

所有表都已启用 RLS，确保数据安全：

**users 表**:
- ✅ 用户只能查看/修改自己的数据
- ✅ 需要 Supabase Auth JWT 验证

**songs 表**:
- ✅ 公开歌曲所有人可见
- ✅ 私有歌曲仅所有者可见
- ✅ 仅所有者可增删改

**tasks 表**:
- ✅ 用户只能查看自己的任务

**copyright_scans 表**:
- ✅ 用户只能查看自己的扫描记录

**activity_logs 表**:
- ✅ 用户只能查看自己的日志
- ✅ Service Role 可写入所有日志

---

## 🚀 部署步骤

### 1. 初始化数据库

在 **Supabase Dashboard** → **SQL Editor** 中运行：

```sql
-- 运行初始化脚本
-- 文件位置：backend/database/init_supabase.sql
```

或者使用 Supabase CLI:

```bash
# 安装 Supabase CLI
npm install -g supabase

# 登录
supabase login

# 链接项目
supabase link --project-ref gdowyyvzvseheccisdfhl

# 推送数据库迁移
supabase db push
```

### 2. 启动后端测试

```bash
cd backend
python test_supabase.py  # 测试连接
uvicorn main:app --reload --host 0.0.0.0 --port 8002
```

### 3. 测试 API

```bash
# 健康检查
curl http://localhost:8002/health

# 用户注册（需要 Supabase Auth Token）
curl -X POST http://localhost:8002/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_SUPABASE_TOKEN" \
  -d '{"email": "test@example.com", "username": "TestUser"}'

# 获取用户信息
curl http://localhost:8002/api/v1/auth/me \
  -H "Authorization: Bearer YOUR_SUPABASE_TOKEN"

# 创建歌曲
curl -X POST http://localhost:8002/api/v1/songs \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_SUPABASE_TOKEN" \
  -d '{"title": "My Song", "style": "Pop"}'
```

---

## 📊 数据库使用量监控

### 免费套餐限额

| 资源 | 免费额度 | 监控建议 |
|------|---------|---------|
| **数据库** | 500MB | 足够 10 万 + 用户 |
| **带宽** | 2GB/月 | 监控 API 调用量 |
| **存储** | 1GB | 仅存元数据，文件存 R2 |
| **Auth 用户** | 无限 | 无限制 |

### 建议使用 Cloudflare R2 存储大文件

- ✅ 音频文件 → R2 Buckets
- ✅ 封面图片 → R2 Buckets
- ✅ MV 视频 → R2 Buckets
- ✅ 数据库仅存 URL

---

## 🆘 故障排查

### 连接失败
```bash
# 检查 .env 文件
cat backend/.env | grep SUPABASE

# 测试连接
python backend/test_supabase.py
```

### RLS 权限错误
- 确认已运行 `init_supabase.sql` 启用 RLS
- 检查 JWT Token 是否正确
- 验证用户是否有对应策略权限

### 额度扣除失败
- 检查 `increment_user_credits` 函数是否创建
- 确认用户表有 `credits` 字段

---

## 📝 后续优化

1. **数据库备份**
   - 启用 Supabase 自动备份（Pro 功能）
   - 或定期导出 SQL 备份

2. **性能优化**
   - 添加更多索引（根据查询模式）
   - 使用 Supabase 缓存层

3. **监控告警**
   - 集成 Supabase Webhooks
   - 配置使用量告警

4. **数据迁移**
   - 从旧数据库迁移用户数据
   - 导入初始歌曲库

---

## 🎉 完成状态

- ✅ Supabase 客户端集成
- ✅ 数据库服务层实现
- ✅ 用户认证 API
- ✅ 歌曲管理 API
- ✅ RLS 安全策略
- ✅ 数据库初始化脚本
- ✅ 测试脚本
- ✅ 完整文档

**下一步**: 在 Supabase Dashboard 运行 SQL 脚本，然后启动后端测试！🚀