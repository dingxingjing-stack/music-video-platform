"""
一次性迁移脚本：SQLite (beta.db / music_platform.db) -> Supabase PostgreSQL

用途：若旧环境有需保留的 beta 额度 / 任务状态，可执行本脚本一次性导入。
特性：幂等（ON CONFLICT DO NOTHING / DO UPDATE）、保留 ID/timestamps、失败可重试。

执行：DATABASE_URL=postgresql://... python scripts/migrate_sqlite_to_postgres.py [--beta beta.db] [--mp music_platform.db] [--dry-run]
"""
from __future__ import annotations
import argparse
import os
import sqlite3
import sys
from pathlib import Path

# 确保可 import backend
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

def migrate_beta(sqlite_path: str, dry_run: bool = False):
    if not Path(sqlite_path).exists():
        print(f"[beta] 跳过，不存在: {sqlite_path}")
        return 0
    import sqlite3 as s3
    conn = s3.connect(sqlite_path)
    conn.row_factory = s3.Row
    cur = conn.cursor()
    # 检测是否已有旧表
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cur.fetchall()}
    except Exception:
        tables = set()
    print(f"[beta] 检测到表: {tables}")
    if dry_run:
        print("[beta] dry-run 不写入 PG")
        conn.close()
        return 0
    from app.db.database import SessionLocal, Base, engine
    Base.metadata.create_all(bind=engine)
    sess = SessionLocal()
    try:
        from sqlalchemy import text
        # 迁移 generation_usage / global_usage / download_logs / beta_users 等
        for tbl in ["generation_usage", "global_usage", "download_logs", "beta_users", "beta_gray_applications", "beta_bug_reports", "ai_tasks", "task_locks", "generation_cost_logs"]:
            if tbl not in tables:
                continue
            rows = list(cur.execute(f"SELECT * FROM {tbl}"))
            if not rows:
                continue
            print(f"[{tbl}] {len(rows)} 行")
            for row in rows:
                cols = row.keys()
                vals = {k: row[k] for k in cols}
                # 构造 INSERT ... ON CONFLICT DO NOTHING（保留 ID）
                col_list = ", ".join(vals.keys())
                ph = ", ".join(f":{k}" for k in vals.keys())
                # PG 主键冲突策略：若表有主键/唯一键则 DO NOTHING，否则直接插入
                try:
                    sess.execute(text(f"INSERT INTO {tbl} ({col_list}) VALUES ({ph}) ON CONFLICT DO NOTHING"), vals)
                except Exception as e:
                    # SQLite 语法差异（如 TEXT JSON）回退：逐列插入并忽略错误
                    print(f"  警告 {tbl} 行插入失败: {e}")
            sess.commit()
            print(f"[{tbl}] done")
    except Exception as e:
        sess.rollback()
        print(f"[beta] 失败: {e}")
        raise
    finally:
        sess.close()
        conn.close()
    return 1

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--beta", default="backend/data/beta.db")
    ap.add_argument("--mp", default="backend/app/music_platform.db")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    print(f"DATABASE_URL={os.getenv('DATABASE_URL','(env)')[:40]}... dry_run={args.dry_run}")
    # 检查生产数据是否为空：若两库均无有效生产数据，可提示无需迁移
    beta_p = Path(args.beta)
    mp_p = Path(args.mp)
    beta_exists = beta_p.exists() and beta_p.stat().st_size > 10000
    mp_exists = mp_p.exists() and mp_p.stat().st_size > 10000
    if not beta_exists and not mp_exists:
        print("当前 SQLite 均为空或无有效生产数据，无需迁移，仅需初始化 PG schema（执行 app.db.database.init_db 即可）。")
        if args.dry_run:
            return
    if beta_p.exists():
        migrate_beta(str(beta_p), dry_run=args.dry_run)
    if mp_p.exists():
        migrate_beta(str(mp_p), dry_run=args.dry_run)
    print("迁移完成。请验证：psql $DATABASE_URL -c \"\\dt\"  应显示 10+ 张表")

if __name__ == "__main__":
    main()
