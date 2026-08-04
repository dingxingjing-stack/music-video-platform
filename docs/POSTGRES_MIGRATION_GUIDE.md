# 🗄️ P0-7 PostgreSQL 数据库迁移指南

**目标**: 从 SQLite/JSON 迁移到 PostgreSQL  
**收益**: 查询性能 10x+ / 并发写入 / 完整事务支持  
**时间**: 2-3 小时

---

## 📊 为什么迁移？

| 对比项 | SQLite | PostgreSQL | 提升 |
|--------|--------|------------|------|
| **并发写入** | ❌ 文件锁 | ✅ 行级锁 | **无限** |
| **查询性能** | 1x | 10-100x | **10 倍** |
| **连接池** | ❌ | ✅ 20+ 连接 | ✅ |
| **全文搜索** | ❌ | ✅ 内置 | ✅ |
| **GIS 支持** | ❌ | ✅ PostGIS | ✅ |
| **备份恢复** | 手动 | 自动工具 | ✅ |
| **规模支持** | <10GB | TB 级 | **无限** |

---

## 🚀 迁移步骤

### Step 1: 安装 PostgreSQL

**Windows**:
```bash
# 下载安装包
https://www.postgresql.org/download/windows/

# 或使用 Chocolatey
choco install postgresql

# 安装后设置环境变量
setx PATH "%PATH%;C:\Program Files\PostgreSQL\16\bin"
```

**验证安装**:
```bash
psql --version
# 输出：psql (PostgreSQL) 16.x
```

---

### Step 2: 创建数据库和用户

```bash
# 以 postgres 用户登录
psql -U postgres

# 创建数据库
CREATE DATABASE hermes_platform;

# 创建用户
CREATE USER hermes WITH PASSWORD 'hermes_password';

# 授权
GRANT ALL PRIVILEGES ON DATABASE hermes_platform TO hermes;

# 设置 search_path
ALTER ROLE hermes SET search_path TO hermes_platform,public;

# 退出
\q
```

---

### Step 3: 安装 Python 驱动

```bash
cd backend

# 安装 asyncio 驱动 (高性能)
pip install asyncpg

# 安装 SQLAlchemy ORM
pip install sqlalchemy==2.0.23

# 添加到 requirements.txt
echo "asyncpg>=0.29.0" >> requirements.txt
echo "sqlalchemy==2.0.23" >> requirements.txt
```

---

### Step 4: 配置环境变量

**复制 `.env.example` 到 `.env`**:
```bash
cp .env.example .env
```

**编辑 `.env`**:
```bash
# PostgreSQL 配置
DATABASE_URL=postgresql://hermes:hermes_password@localhost:5432/hermes_platform
POSTGRES_USER=hermes
POSTGRES_PASSWORD=hermes_password
POSTGRES_DB=hermes_platform

# 连接池
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=40
```

---

### Step 5: 初始化数据库

```bash
cd backend

# 运行初始化脚本
python -m app.db.postgres
```

**输出**:
```
============================================================
🗄️  PostgreSQL 数据库初始化
============================================================
[PostgreSQL] 正在创建数据表...
[PostgreSQL] ✅ 数据表创建完成
[优化] 创建索引...
[优化] ✅ 索引创建完成
[优化] 执行 VACUUM ANALYZE...
[优化] ✅ VACUUM ANALYZE 完成

✅ PostgreSQL 数据库就绪！
```

---

### Step 6: 数据迁移 (从 SQLite)

如果有现有 SQLite 数据:

```bash
# 创建迁移脚本
python << 'EOF'
from app.db.postgres import migrate_from_sqlite

def on_progress(table, count):
    print(f"迁移 {table}: {count} 行")

migrate_from_sqlite("data/hermes.db", on_progress)
EOF
```

**迁移报告**:
```
[迁移] 从 SQLite 迁移：data/hermes.db
[迁移] 迁移用户表...
[迁移] 迁移轨道表...
[迁移] ✅ 完成！迁移 100 用户，500 轨道
```

---

### Step 7: 更新后端使用 PostgreSQL

**`backend/app/main.py`** - 替换数据库依赖:

```python
# 原来:
from app.db.sqlite import get_db

# 改为:
from app.db.postgres import get_db
```

**更新所有路由**:
```python
@router.get("/tracks")
def get_tracks(db: Session = Depends(get_db)):
    # 原有逻辑不变
```

---

### Step 8: 性能测试

**基准测试脚本**:
```python
import time
from app.db.postgres import SessionLocal
from app.models import Track

def benchmark():
    db = SessionLocal()
    
    # 查询测试
    start = time.time()
    tracks = db.query(Track).filter(Track.is_public == True).all()
    duration = time.time() - start
    
    print(f"查询 {len(tracks)} 轨道：{duration*1000:.2f}ms")
    
    db.close()
    return duration

# 运行 10 次
for i in range(10):
    benchmark()
```

**预期结果**:
- SQLite: 100-200ms
- PostgreSQL: **10-20ms** (10x 提升)

---

### Step 9: 配置连接池监控

**`backend/app/db/monitor.py`**:
```python
from app.db.postgres import engine

def get_pool_stats():
    """获取连接池统计"""
    return {
        "pool_size": engine.pool.size(),
        "checked_out": engine.pool.checkedout(),
        "overflow": engine.pool.overflow(),
    }

@router.get("/db/stats")
def db_stats():
    return {"success": True, "stats": get_pool_stats()}
```

**API 响应**:
```json
{
  "success": true,
  "stats": {
    "pool_size": 20,
    "checked_out": 5,
    "overflow": 0
  }
}
```

---

## 📈 性能优化建议

### 1. 索引策略

```sql
-- 高频查询字段加索引
CREATE INDEX idx_tracks_user_created ON tracks(user_id, created_at DESC);
CREATE INDEX idx_tracks_style_tempo ON tracks(style, tempo);

-- 全文搜索索引 (PostgreSQL 独家)
CREATE INDEX idx_tracks_lyrics_trgm ON tracks USING gin (lyrics gin_trgm_ops);
```

### 2. 查询优化

```python
# ❌ 避免 N+1 查询
tracks = db.query(Track).all()
for track in tracks:
    user = track.user  # 每次都查数据库

# ✅ 使用 joinedload
from sqlalchemy.orm import joinedload
tracks = db.query(Track).options(joinedload(Track.user)).all()
```

### 3. 异步查询 (高并发)

```python
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.future import select

async def get_tracks_async():
    async with async_session() as session:
        result = await session.execute(select(Track))
        return result.scalars().all()
```

---

## 🔐 安全配置

### 1. 密码加密

```bash
# .env 中使用强密码
POSTGRES_PASSWORD=$(openssl rand -base64 32)
```

### 2. 限制远程访问

**`pg_hba.conf`**:
```
# 只允许本地连接
host    all             all             127.0.0.1/32            scram-sha-256
host    all             all             ::1/128                 scram-sha-256

# 生产环境：限制特定 IP
host    all             all             192.168.1.0/24          scram-sha-256
```

### 3. 定期备份

```bash
# 创建备份脚本 backup.sh
pg_dump -U hermes hermes_platform | gzip > backup_$(date +%Y%m%d).sql.gz

# 添加到 cron (每天 2am)
0 2 * * * /path/to/backup.sh
```

---

## ✅ 验收标准

- [ ] PostgreSQL 16 安装完成
- [ ] 数据库 `hermes_platform` 创建
- [ ] 用户 `hermes` 授权成功
- [ ] 连接池配置正确
- [ ] 所有表创建完成
- [ ] 索引优化完成
- [ ] 数据迁移成功
- [ ] 性能测试通过 (10x)
- [ ] 备份脚本运行正常

---

## 💰 成本对比

| 方案 | 月成本 | 性能 | 管理难度 |
|------|--------|------|----------|
| **自托管 PostgreSQL** | ¥0 (本地) | ⭐⭐⭐⭐⭐ | 中 |
| **Supabase (托管)** | ¥0 (免费 500MB) | ⭐⭐⭐⭐ | 低 |
| **AWS RDS** | ¥100+ | ⭐⭐⭐⭐⭐ | 低 |
| **SQLite (现状)** | ¥0 | ⭐⭐ | 极低 |

**推荐**: 本地开发用自托管，生产用 Supabase (免费额度够用)

---

## 🆘 常见问题

### Q: 迁移会丢数据吗？
**A**: 不会，迁移脚本会保留所有数据。建议先备份 SQLite 数据库。

### Q: 需要停机多久？
**A**: 小数据 (<1GB) 1-2 分钟，大数据可在线迁移。

### Q: 能否回滚？
**A**: 可以，保留 SQLite 数据库 1 周验证。

### Q: 性能提升多少？
**A**: 简单查询 10x，复杂查询 50-100x，并发 100x+。

---

## 📚 参考文档

- PostgreSQL: https://www.postgresql.org/docs/
- SQLAlchemy: https://docs.sqlalchemy.org/
- asyncpg: https://magicstack.github.io/asyncpg/

---

**状态**: ✅ 完成  
**文档**: `POSTGRES_MIGRATION_GUIDE.md`  
**代码**: `backend/app/db/postgres.py`  
**配置**: `backend/.env.example`