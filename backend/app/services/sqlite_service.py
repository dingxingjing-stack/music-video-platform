"""
SQLite 数据库服务
替代 Supabase，使用本地 SQLite 数据库
"""

import os
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

# 数据库文件路径
DB_PATH = Path(__file__).parent.parent / "music_platform.db"


def get_connection() -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表结构"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 用户表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        supabase_user_id TEXT UNIQUE,
        email TEXT UNIQUE NOT NULL,
        username TEXT,
        avatar_url TEXT,
        credits INTEGER DEFAULT 100,
        subscription_tier TEXT DEFAULT 'free',
        age INTEGER,
        is_verified BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 歌曲表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS songs (
        id TEXT PRIMARY KEY,
        user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        lyrics TEXT,
        style TEXT,
        duration_seconds INTEGER,
        audio_url TEXT,
        cover_image_url TEXT,
        mv_url TEXT,
        status TEXT DEFAULT 'pending',
        is_public BOOLEAN DEFAULT FALSE,
        play_count INTEGER DEFAULT 0,
        like_count INTEGER DEFAULT 0,
        metadata TEXT DEFAULT '{}',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 任务表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
        task_type TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        progress INTEGER DEFAULT 0,
        result TEXT,
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP
    )
    """)
    
    # 版权检测表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS copyright_scans (
        id TEXT PRIMARY KEY,
        song_id TEXT REFERENCES songs(id) ON DELETE CASCADE,
        user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
        scan_status TEXT DEFAULT 'pending',
        risk_level TEXT,
        similarity_score REAL,
        matched_works TEXT,
        report_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP
    )
    """)
    
    # 活动日志表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS activity_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
        action TEXT NOT NULL,
        resource_type TEXT,
        resource_id TEXT,
        ip_address TEXT,
        user_agent TEXT,
        metadata TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 收藏表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS favorites (
        id TEXT PRIMARY KEY,
        user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
        song_id TEXT REFERENCES songs(id) ON DELETE CASCADE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, song_id)
    )
    """)
    
    # 评论表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS comments (
        id TEXT PRIMARY KEY,
        user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
        song_id TEXT REFERENCES songs(id) ON DELETE CASCADE,
        content TEXT NOT NULL,
        parent_id TEXT REFERENCES comments(id) ON DELETE CASCADE,
        like_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 订阅表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS subscriptions (
        id TEXT PRIMARY KEY,
        user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
        plan_type TEXT NOT NULL,
        status TEXT DEFAULT 'active',
        start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        end_date TIMESTAMP,
        auto_renew BOOLEAN DEFAULT TRUE,
        payment_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 创建索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_songs_user_id ON songs(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_songs_status ON songs(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_user_id ON activity_logs(user_id)")
    
    conn.commit()
    conn.close()
    print(f"✅ 数据库初始化完成：{DB_PATH}")


# ========== 用户管理 ==========

def get_user(supabase_user_id: str) -> Optional[Dict]:
    """获取用户信息"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE supabase_user_id = ?", (supabase_user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None


def create_user(email: str, supabase_user_id: str, username: Optional[str] = None, age: Optional[int] = None) -> Dict:
    """创建用户"""
    import uuid
    user_id = str(uuid.uuid4())
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (id, supabase_user_id, email, username, age)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, supabase_user_id, email, username, age))
    conn.commit()
    conn.close()
    
    return get_user(supabase_user_id)


def increment_user_credits(user_id: str, amount: int) -> int:
    """增加用户额度"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users SET credits = credits + ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (amount, user_id))
    conn.commit()
    
    cursor.execute("SELECT credits FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    return row[0] if row else 0


def decrement_user_credits(user_id: str, amount: int) -> bool:
    """扣除用户额度"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT credits FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    
    if row and row[0] >= amount:
        cursor.execute("""
            UPDATE users SET credits = credits - ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (amount, user_id))
        conn.commit()
        conn.close()
        return True
    
    conn.close()
    return False


# ========== 歌曲管理 ==========

def create_song(user_id: str, title: str, lyrics: Optional[str] = None, 
                style: Optional[str] = None, **kwargs) -> Dict:
    """创建歌曲"""
    import uuid
    import json
    
    song_id = str(uuid.uuid4())
    metadata = json.dumps(kwargs.get('metadata', {}))
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO songs (id, user_id, title, lyrics, style, metadata)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (song_id, user_id, title, lyrics, style, metadata))
    conn.commit()
    conn.close()
    
    return get_song(song_id)


def get_song(song_id: str) -> Optional[Dict]:
    """获取歌曲详情"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM songs WHERE id = ?", (song_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        result = dict(row)
        if result.get('metadata'):
            import json
            result['metadata'] = json.loads(result['metadata'])
        return result
    return None


def get_user_songs(user_id: str, limit: int = 20) -> List[Dict]:
    """获取用户歌曲列表"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM songs WHERE user_id = ? 
        ORDER BY created_at DESC LIMIT ?
    """, (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        result = dict(row)
        if result.get('metadata'):
            import json
            result['metadata'] = json.loads(result['metadata'])
        results.append(result)
    
    return results


# ========== 任务管理 ==========

def create_task(user_id: str, task_type: str, **kwargs) -> int:
    """创建任务"""
    import json
    
    conn = get_connection()
    cursor = conn.cursor()
    
    result = kwargs.get('result')
    if result and isinstance(result, dict):
        result = json.dumps(result)
    
    cursor.execute("""
        INSERT INTO tasks (user_id, task_type, result)
        VALUES (?, ?, ?)
    """, (user_id, task_type, result))
    conn.commit()
    
    task_id = cursor.lastrowid
    conn.close()
    
    return task_id


def update_task_status(task_id: int, status: str, progress: Optional[int] = None, 
                       error_message: Optional[str] = None) -> Dict:
    """更新任务状态"""
    conn = get_connection()
    cursor = conn.cursor()
    
    updates = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
    params = [status]
    
    if progress is not None:
        updates.append("progress = ?")
        params.append(progress)
    
    if error_message:
        updates.append("error_message = ?")
        params.append(error_message)
    
    if status in ('completed', 'failed'):
        updates.append("completed_at = CURRENT_TIMESTAMP")
    
    params.append(task_id)
    
    cursor.execute(f"""
        UPDATE tasks SET {', '.join(updates)} WHERE id = ?
    """, params)
    conn.commit()
    
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        result = dict(row)
        if result.get('result'):
            import json
            result['result'] = json.loads(result['result'])
        return result
    return {}


# ========== 活动日志 ==========

def log_activity(user_id: str, action: str, resource_type: Optional[str] = None,
                 resource_id: Optional[str] = None, metadata: Optional[Dict] = None):
    """记录活动日志"""
    import json
    
    conn = get_connection()
    cursor = conn.cursor()
    
    metadata_str = json.dumps(metadata) if metadata else None
    
    cursor.execute("""
        INSERT INTO activity_logs (user_id, action, resource_type, resource_id, metadata)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, action, resource_type, resource_id, metadata_str))
    conn.commit()
    conn.close()


# ========== 初始化 ==========

# 自动初始化数据库
init_db()