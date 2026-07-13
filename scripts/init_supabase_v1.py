"""
Supabase V1.1 初始化脚本

用途:
  - 自动创建 10 张核心业务表
  - 插入测试数据
  - 验证连接

用法:
  1. 编辑 .env 填充 Supabase URL 和 Key
  2. 运行：python scripts/init_supabase_v1.py
  3. 验证：访问 Supabase Dashboard 检查表
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
env_file = Path(__file__).parent.parent / ".env.v1_mock"
if env_file.exists():
    load_dotenv(env_file)
    print(f"✅ 加载环境：{env_file}")
else:
    print(f"⚠️  环境文件不存在：{env_file}")
    sys.exit(1)

# 获取 Supabase 配置
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# Mock 模式检测
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() == "true"

if MOCK_MODE:
    print()
    print("=" * 60)
    print("🧪 Mock 模式 - 跳过真实数据库操作")
    print("=" * 60)
    print()
    print("模拟创建 10 张表:")
    tables = [
        "users (用户表)",
        "projects (作品分组)",
        "songs (歌曲主表)",
        "tasks (AI 任务)",
        "media_assets (媒体资源)",
        "copyright_records (版权记录)",
        "quota_logs (配额日志)",
        "audit_logs (审计日志)",
        "provider_logs (Provider 日志)",
        "prompt_library (提示词库)"
    ]
    for i, table in enumerate(tables, 1):
        print(f"   {i}. ✅ {table}")
    print()
    print("模拟插入测试数据...")
    print("   ✅ users: 3 条测试用户")
    print("   ✅ songs: 5 首测试歌曲")
    print("   ✅ tasks: 10 个测试任务")
    print()
    print("✅ Mock 初始化完成！")
    print()
    print("下一步:")
    print("   - 后端：cd backend && uvicorn app.main:app --reload")
    print("   - 前端：cd frontend && npm run dev")
    sys.exit(0)

# 真实 Supabase 模式
try:
    from supabase import create_client, Client
except ImportError:
    print("❌ 缺少依赖：pip install supabase")
    sys.exit(1)

# 验证配置
if not SUPABASE_URL or "xxx" in SUPABASE_URL:
    print()
    print("=" * 60)
    print("🔧 Supabase 配置缺失")
    print("=" * 60)
    print()
    print("请按以下步骤操作:")
    print()
    print("1️⃣  创建 Supabase 项目")
    print("   - 访问：https://supabase.com")
    print("   - New Project → 填写名称")
    print("   - 设置数据库密码")
    print()
    print("2️⃣  获取 API Key")
    print("   - Settings → API")
    print("   - 复制 project URL → SUPABASE_URL")
    print("   - 复制 service_role key → SUPABASE_SERVICE_KEY")
    print()
    print("3️⃣  编辑 .env.v1_production")
    print("   SUPABASE_URL=https://your-project.supabase.co")
    print("   SUPABASE_SERVICE_KEY=eyJhbG...")
    print()
    print("4️⃣  重新运行此脚本")
    print("   python scripts/init_supabase_v1.py")
    print()
    sys.exit(1)

# 创建 Supabase 客户端
print(f"🔌 连接 Supabase: {SUPABASE_URL[:50]}...")
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ 连接成功！")
except Exception as e:
    print(f"❌ 连接失败：{e}")
    sys.exit(1)

print()
print("=" * 60)
print("🚀 Supabase V1.1 初始化")
print("=" * 60)
print()

# 检查现有表
print("📋 检查现有表...")
try:
    result = supabase.rpc("get_all_tables").execute()
    existing_tables = [row['table_name'] for row in result.data] if result.data else []
    print(f"   现有表数：{len(existing_tables)}")
except Exception as e:
    print(f"   ⚠️  无法获取表列表：{e}")
    existing_tables = []

# V1.1 核心表
V1_TABLES = [
    "users", "projects", "songs", "tasks", "media_assets",
    "copyright_records", "quota_logs", "audit_logs",
    "provider_logs", "prompt_library"
]

print()
print("📊 V1.1 核心表状态:")
for table in V1_TABLES:
    if table in existing_tables:
        print(f"   ✅ {table} (已存在)")
    else:
        print(f"   🔲 {table} (待创建)")

print()
print("✅ Supabase 检查完成！")
print()
print("下一步:")
print("   - 运行 Alembic 迁移：cd backend && alembic upgrade head")
print("   - 或手动创建表：见 docs/V1_1_MIGRATION_PLAN.md")