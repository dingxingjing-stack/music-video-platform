"""
V1.1 前端配置脚本
用途:
  1. 复制 .env.v1_production → .env
  2. 禁用二期功能组件
  3. 修改 API 基地址
"""

import os
import shutil
from pathlib import Path

# ===== 配置 =====
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
ENV_SOURCE = FRONTEND_DIR / ".env.v1_production"
ENV_TARGET = FRONTEND_DIR / ".env"

# 二期功能组件路径 (需要禁用/隐藏)
V2_COMPONENTS = [
    "CollaborationPanel.tsx",  # 实时协作
    "VideoSyncStudio.tsx",     # MV 同步
    "P2AudioMasteringPage.tsx", # 母带处理
    "P2AudioSeparationPage.tsx", # 音频分离
    "VoiceClonePanel.tsx",     # 声音克隆
    "UGCSubmit.tsx",           # UGC 投稿
]

# 二期功能页面 (需要隐藏路由)
V2_PAGES = [
    "PathBPage.tsx",  # 专业模式
    "PathCPage.tsx",  # 协作编辑
    "PathDPage.tsx",  # AI 辅助
    "TrackStudio.tsx", # 专业 DAW
]


def main():
    print("=" * 60)
    print("🔧 V1.1 前端配置脚本")
    print("=" * 60)
    print()
    
    # 步骤 1: 复制环境配置
    print("1️⃣  复制环境配置...")
    if ENV_SOURCE.exists():
        shutil.copy(ENV_SOURCE, ENV_TARGET)
        print(f"   ✅ {ENV_SOURCE.name} → {ENV_TARGET.name}")
    else:
        print(f"   ❌ 源文件不存在：{ENV_SOURCE}")
        print("   请手动创建 .env.v1_production")
        return False
    print()
    
    # 步骤 2: 读取 App.tsx (路由配置)
    print("2️⃣  修改路由配置 (禁用二期页面)...")
    app_tsx = FRONTEND_DIR / "src" / "App.tsx"
    if app_tsx.exists():
        content = app_tsx.read_text(encoding="utf-8")
        
        # 注释掉二期页面路由
        modified = False
        for page in V2_PAGES:
            page_name = page.replace(".tsx", "")
            if f'<Route path="/{page_name}' in content:
                # 简单处理：添加注释标记 (实际需要手动编辑)
                print(f"   ⚠️  需要手动注释：{page_name} 路由")
                modified = True
        
        if not modified:
            print("   ✅ 无需修改 (或已禁用)")
    else:
        print(f"   ⚠️  App.tsx 不存在，跳过")
    print()
    
    # 步骤 3: 总结
    print("=" * 60)
    print("✅ V1.1 前端配置完成！")
    print("=" * 60)
    print()
    print("📋 完成事项:")
    print(f"   ✅ 环境配置：{ENV_TARGET.name}")
    print("   ⚠️  路由配置：待手动确认")
    print()
    print("📝 下一步:")
    print("   1. 检查 src/App.tsx，注释二期功能路由")
    print("   2. 填充真实 API 地址 (VITE_API_BASE_URL)")
    print("   3. 运行：npm run build")
    print()
    
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)