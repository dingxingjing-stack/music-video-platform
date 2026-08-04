"""
社交数据存储 (Social Storage)

提供点赞/收藏/关注/播放统计/Feed 推荐的持久化实现。
以 SQLite 为存储后端，API 全部为同步方法（供 FastAPI 同步调用）。
"""

import os
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set, Tuple

# 数据库文件默认放在 backend/data 目录下
_DEFAULT_DB_DIR = Path(os.getenv("SOCIAL_DB_DIR", Path(__file__).resolve().parents[2] / "data"))
_DEFAULT_DB_PATH = _DEFAULT_DB_DIR / "social.db"


@dataclass
class WorkStats:
    """作品统计信息"""
    work_id: str
    likes: int = 0
    favorites: int = 0
    plays: int = 0


class SocialStorage:
    """
    社交数据存储

    表结构:
    - likes     (user_id, work_id)  点赞
    - favorites (user_id, work_id)  收藏
    - follows   (user_id, target_user_id)  关注
    - plays     (work_id, count)    播放计数
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = str(db_path or _DEFAULT_DB_PATH)
        self._lock = threading.RLock()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ─── 内部工具 ───────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS likes (
                        user_id TEXT NOT NULL,
                        work_id TEXT NOT NULL,
                        created_at TEXT DEFAULT (datetime('now')),
                        PRIMARY KEY (user_id, work_id)
                    );
                    CREATE TABLE IF NOT EXISTS favorites (
                        user_id TEXT NOT NULL,
                        work_id TEXT NOT NULL,
                        created_at TEXT DEFAULT (datetime('now')),
                        PRIMARY KEY (user_id, work_id)
                    );
                    CREATE TABLE IF NOT EXISTS follows (
                        user_id TEXT NOT NULL,
                        target_user_id TEXT NOT NULL,
                        created_at TEXT DEFAULT (datetime('now')),
                        PRIMARY KEY (user_id, target_user_id)
                    );
                    CREATE TABLE IF NOT EXISTS plays (
                        work_id TEXT PRIMARY KEY,
                        count INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE INDEX IF NOT EXISTS idx_likes_work ON likes(work_id);
                    CREATE INDEX IF NOT EXISTS idx_favs_work ON favorites(work_id);
                    CREATE INDEX IF NOT EXISTS idx_follows_target ON follows(target_user_id);
                    """
                )
                conn.commit()
            finally:
                conn.close()

    # ─── 点赞 ───────────────────────────────────────

    def add_like(self, user_id: str, work_id: str) -> bool:
        """点赞作品，成功返回 True，重复点赞返回 False"""
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO likes (user_id, work_id) VALUES (?, ?)",
                    (user_id, work_id),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def remove_like(self, user_id: str, work_id: str) -> bool:
        """取消点赞，删除成功返回 True"""
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM likes WHERE user_id = ? AND work_id = ?",
                    (user_id, work_id),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def get_like_count(self, work_id: str) -> int:
        """获取作品点赞数"""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM likes WHERE work_id = ?", (work_id,)
                ).fetchone()
                return row["c"] if row else 0
            finally:
                conn.close()

    def is_liked(self, user_id: str, work_id: str) -> bool:
        """判断用户是否已点赞"""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT 1 FROM likes WHERE user_id = ? AND work_id = ?",
                    (user_id, work_id),
                ).fetchone()
                return row is not None
            finally:
                conn.close()

    # ─── 收藏 ───────────────────────────────────────

    def add_favorite(self, user_id: str, work_id: str) -> bool:
        """收藏作品，成功返回 True，重复收藏返回 False"""
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO favorites (user_id, work_id) VALUES (?, ?)",
                    (user_id, work_id),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def remove_favorite(self, user_id: str, work_id: str) -> bool:
        """取消收藏，删除成功返回 True"""
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM favorites WHERE user_id = ? AND work_id = ?",
                    (user_id, work_id),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def get_favorite_count(self, work_id: str) -> int:
        """获取作品收藏数"""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM favorites WHERE work_id = ?", (work_id,)
                ).fetchone()
                return row["c"] if row else 0
            finally:
                conn.close()

    def is_favorited(self, user_id: str, work_id: str) -> bool:
        """判断用户是否已收藏"""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT 1 FROM favorites WHERE user_id = ? AND work_id = ?",
                    (user_id, work_id),
                ).fetchone()
                return row is not None
            finally:
                conn.close()

    # ─── 关注 ───────────────────────────────────────

    def add_follow(self, user_id: str, target_user_id: str) -> bool:
        """关注用户，成功返回 True，重复关注返回 False"""
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO follows (user_id, target_user_id) VALUES (?, ?)",
                    (user_id, target_user_id),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def remove_follow(self, user_id: str, target_user_id: str) -> bool:
        """取消关注，删除成功返回 True"""
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM follows WHERE user_id = ? AND target_user_id = ?",
                    (user_id, target_user_id),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def get_follower_count(self, user_id: str) -> int:
        """获取用户粉丝数"""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM follows WHERE target_user_id = ?",
                    (user_id,),
                ).fetchone()
                return row["c"] if row else 0
            finally:
                conn.close()

    def get_following_count(self, user_id: str) -> int:
        """获取用户关注数"""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM follows WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
                return row["c"] if row else 0
            finally:
                conn.close()

    def get_following(self, user_id: str) -> List[str]:
        """获取用户关注的用户列表"""
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT target_user_id FROM follows WHERE user_id = ?", (user_id,)
                ).fetchall()
                return [r["target_user_id"] for r in rows]
            finally:
                conn.close()

    def get_followers(self, user_id: str) -> List[str]:
        """获取用户的粉丝列表"""
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT user_id FROM follows WHERE target_user_id = ?", (user_id,)
                ).fetchall()
                return [r["user_id"] for r in rows]
            finally:
                conn.close()

    # ─── 播放统计 ───────────────────────────────────

    def increment_play(self, work_id: str) -> int:
        """播放计数 +1，返回新的计数"""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO plays (work_id, count) VALUES (?, 1) "
                    "ON CONFLICT(work_id) DO UPDATE SET count = count + 1",
                    (work_id,),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT count FROM plays WHERE work_id = ?", (work_id,)
                ).fetchone()
                return row["count"] if row else 1
            finally:
                conn.close()

    # ─── 统计聚合 ───────────────────────────────────

    def get_work_stats(self, work_id: str) -> WorkStats:
        """获取作品统计（点赞/收藏/播放）"""
        with self._lock:
            conn = self._connect()
            try:
                like_row = conn.execute(
                    "SELECT COUNT(*) AS c FROM likes WHERE work_id = ?", (work_id,)
                ).fetchone()
                fav_row = conn.execute(
                    "SELECT COUNT(*) AS c FROM favorites WHERE work_id = ?", (work_id,)
                ).fetchone()
                play_row = conn.execute(
                    "SELECT count FROM plays WHERE work_id = ?", (work_id,)
                ).fetchone()
                return WorkStats(
                    work_id=work_id,
                    likes=like_row["c"] if like_row else 0,
                    favorites=fav_row["c"] if fav_row else 0,
                    plays=play_row["count"] if play_row else 0,
                )
            finally:
                conn.close()

    # ─── Feed 推荐 ──────────────────────────────────

    def get_user_feed(self, user_id: str, limit: int = 20) -> List[str]:
        """
        获取个性化推荐 feed。

        规则：先取用户关注对象点赞/收藏过的作品，再补充全站高赞作品。
        """
        with self._lock:
            conn = self._connect()
            try:
                following = [r["target_user_id"] for r in conn.execute(
                    "SELECT target_user_id FROM follows WHERE user_id = ?", (user_id,)
                ).fetchall()]
                result: List[str] = []
                seen: Set[str] = set()

                if following:
                    placeholders = ",".join("?" for _ in following)
                    rows = conn.execute(
                        f"""
                        SELECT work_id, MAX(cnt) AS popularity FROM (
                            SELECT work_id, 1 AS cnt FROM likes WHERE user_id IN ({placeholders})
                            UNION ALL
                            SELECT work_id, 1 FROM favorites WHERE user_id IN ({placeholders})
                        ) GROUP BY work_id ORDER BY popularity DESC
                        """,
                        following * 2,
                    ).fetchall()
                    for r in rows:
                        wid = r["work_id"]
                        if wid not in seen:
                            seen.add(wid)
                            result.append(wid)
                        if len(result) >= limit:
                            return result

                # 补充全站热榜
                rows = conn.execute(
                    """
                    SELECT work_id, SUM(c) AS hot FROM (
                        SELECT work_id, COUNT(*) AS c FROM likes GROUP BY work_id
                        UNION ALL
                        SELECT work_id, COUNT(*) AS c FROM favorites GROUP BY work_id
                        UNION ALL
                        SELECT work_id, count AS c FROM plays
                    )
                    GROUP BY work_id ORDER BY hot DESC
                    """
                ).fetchall()
                for r in rows:
                    wid = r["work_id"]
                    if wid not in seen:
                        seen.add(wid)
                        result.append(wid)
                    if len(result) >= limit:
                        break
                return result[:limit]
            finally:
                conn.close()


# 全局单例
social_storage = SocialStorage()
