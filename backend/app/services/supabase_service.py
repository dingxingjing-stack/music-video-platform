"""
Supabase 数据库服务
功能：用户、歌曲、任务、版权、日志数据访问
"""

import os
from supabase import create_client, Client
from typing import Optional, List, Dict, Any
from datetime import datetime

# 初始化 Supabase 客户端
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")  # 后端使用 service_role_key

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase credentials. Check .env file.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


class SupabaseService:
    """Supabase 数据库服务类"""
    
    @staticmethod
    def get_user_by_id(user_id: str) -> Optional[Dict]:
        """根据 ID 获取用户"""
        try:
            response = supabase.table("users").select("*").eq("id", user_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error fetching user: {e}")
            return None
    
    @staticmethod
    def create_user(email: str, supabase_user_id: str, extra_data: Optional[Dict] = None) -> Dict:
        """创建新用户"""
        user_data = {
            "email": email,
            "supabase_user_id": supabase_user_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        
        if extra_data:
            user_data.update(extra_data)
        
        response = supabase.table("users").insert(user_data).execute()
        return response.data[0]
    
    @staticmethod
    def create_song(song_data: Dict) -> Dict:
        """创建歌曲记录"""
        song_data["created_at"] = datetime.utcnow().isoformat()
        song_data["updated_at"] = datetime.utcnow().isoformat()
        
        response = supabase.table("songs").insert(song_data).execute()
        return response.data[0]
    
    @staticmethod
    def get_user_songs(user_id: str, limit: int = 20) -> List[Dict]:
        """获取用户的歌曲列表"""
        response = supabase.table("songs")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()
        return response.data
    
    @staticmethod
    def create_task(task_data: Dict) -> Dict:
        """创建任务记录"""
        task_data["created_at"] = datetime.utcnow().isoformat()
        task_data["updated_at"] = datetime.utcnow().isoformat()
        
        response = supabase.table("tasks").insert(task_data).execute()
        return response.data[0]
    
    @staticmethod
    def update_task_status(task_id: int, status: str, result: Optional[Dict] = None) -> Dict:
        """更新任务状态"""
        update_data = {
            "status": status,
            "updated_at": datetime.utcnow().isoformat(),
        }
        
        if result:
            update_data["result"] = result
        
        response = supabase.table("tasks")\
            .update(update_data)\
            .eq("id", task_id)\
            .execute()
        return response.data[0]
    
    @staticmethod
    def create_copyright_scan(scan_data: Dict) -> Dict:
        """创建版权检测记录"""
        scan_data["created_at"] = datetime.utcnow().isoformat()
        
        response = supabase.table("copyright_scans").insert(scan_data).execute()
        return response.data[0]
    
    @staticmethod
    def create_activity_log(log_data: Dict) -> Dict:
        """创建活动日志"""
        log_data["created_at"] = datetime.utcnow().isoformat()
        
        response = supabase.table("activity_logs").insert(log_data).execute()
        return response.data[0]
    
    @staticmethod
    def increment_user_credits(user_id: str, amount: int) -> Dict:
        """增加用户额度"""
        response = supabase.rpc("increment_user_credits")\
            .params({"p_user_id": user_id, "p_amount": amount})\
            .execute()
        return response.data
    
    @staticmethod
    def decrement_user_credits(user_id: str, amount: int) -> bool:
        """扣除用户额度"""
        try:
            # 先检查余额
            user = SupabaseService.get_user_by_id(user_id)
            if not user or user.get("credits", 0) < amount:
                return False
            
            response = supabase.rpc("decrement_user_credits")\
                .params({"p_user_id": user_id, "p_amount": amount})\
                .execute()
            return True
        except Exception as e:
            print(f"Error decrementing credits: {e}")
            return False


# 快捷函数
def get_user(user_id: str) -> Optional[Dict]:
    return SupabaseService.get_user_by_id(user_id)

def create_user(email: str, supabase_user_id: str, **kwargs) -> Dict:
    return SupabaseService.create_user(email, supabase_user_id, kwargs)

def create_song(**kwargs) -> Dict:
    return SupabaseService.create_song(kwargs)

def get_user_songs(user_id: str, limit: int = 20) -> List[Dict]:
    return SupabaseService.get_user_songs(user_id, limit)

def create_task(**kwargs) -> Dict:
    return SupabaseService.create_task(kwargs)

def update_task(task_id: int, status: str, **kwargs) -> Dict:
    return SupabaseService.update_task_status(task_id, status, kwargs)

def log_activity(user_id: str, action: str, **kwargs) -> Dict:
    return SupabaseService.create_activity_log({
        "user_id": user_id,
        "action": action,
        **kwargs
    })