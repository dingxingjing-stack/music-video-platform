#!/usr/bin/env python3
"""
每日额度重置脚本
用法: python scripts/daily_credit_reset.py
或配合 cron: 0 0 * * * cd /app && python scripts/daily_credit_reset.py
"""

import asyncio
import sys
import os

# 添加项目根目录到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.beta_service import daily_reset


async def main():
    result = await daily_reset()
    print(f"[{result.get('success', False)}] {result.get('message', '')}")


if __name__ == "__main__":
    asyncio.run(main())
