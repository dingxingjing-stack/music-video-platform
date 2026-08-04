"""
协作编辑路由 (Collaboration Router)

功能:
- 创建/加入协作会话
- 实时同步项目状态 (WebSocket)
- 多人光标/选择显示
- 冲突解决 (OT 算法简化版)
- 权限管理 (查看者/编辑者/管理员)

API 端点:
- POST /api/v1/collab/session - 创建协作会话
- GET /api/v1/collab/session/{id} - 获取会话信息
- POST /api/v1/collab/session/{id}/join - 加入会话
- POST /api/v1/collab/session/{id}/leave - 离开会话
- GET /api/v1/collab/sessions - 获取我的协作会话
- WebSocket /ws/collab/{session_id} - 实时同步
"""

from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect, Query, Body
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
import uuid
import json

router = APIRouter(prefix="/api/v1/collab", tags=["协作编辑"])


# ============ Data Models ============

class SessionMember(BaseModel):
    user_id: str
    username: str
    role: str  # "viewer", "editor", "admin"
    joined_at: datetime
    cursor_position: Optional[int] = None  # 当前编辑位置
    color: str  # 用户专属颜色，用于光标显示


class SessionOperation(BaseModel):
    """操作类型：添加/删除/修改"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    operation: str  # "add", "remove", "update", "cursor"
    target: str  # "track", "clip", "effect", "automation", "cursor"
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)
    version: int  # 用于冲突解决


class CollaborationSession(BaseModel):
    id: str
    project_id: str
    created_by: str
    created_at: datetime
    members: List[SessionMember]
    version: int = 0  # 当前版本号
    state: Dict[str, Any] = {}  # 项目状态快照
    is_active: bool = True


# ============ Mock Storage ============

sessions: Dict[str, CollaborationSession] = {}
user_colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD", "#98D8C8", "#F7DC6F"]


# ============ Helper Functions ============

def assign_color(user_id: str) -> str:
    """为用户分配专属颜色"""
    idx = hash(user_id) % len(user_colors)
    return user_colors[idx]


def apply_operation(session: CollaborationSession, op: SessionOperation) -> bool:
    """
    应用操作到会话状态
    简化版 OT 算法：版本号检查 + 最后写入获胜
    """
    if op.version != session.version + 1:
        # 版本不匹配，可能需要转换操作
        # 简化处理：直接拒绝，让客户端重新同步
        return False
    
    # 应用操作
    if op.operation == "cursor":
        # 更新 cursor 位置 (不进行版本检查)
        for member in session.members:
            if member.user_id == op.user_id:
                member.cursor_position = op.data.get("position")
                break
        return True
    
    # 其他操作：更新 state
    target = op.target
    if op.operation == "add":
        if target not in session.state:
            session.state[target] = []
        session.state[target].append(op.data)
    elif op.operation == "remove":
        if target in session.state:
            item_id = op.data.get("id")
            session.state[target] = [
                item for item in session.state[target] 
                if item.get("id") != item_id
            ]
    elif op.operation == "update":
        if target in session.state:
            item_id = op.data.get("id")
            for i, item in enumerate(session.state[target]):
                if item.get("id") == item_id:
                    session.state[target][i].update(op.data)
                    break
    
    session.version += 1
    return True


# ============ Endpoints ============

@router.post("/session", response_model=CollaborationSession)
async def create_session(
    project_id: str = Body(...),
    created_by: str = Body(...),
    username: str = Body(...)
):
    """创建协作会话"""
    session_id = str(uuid.uuid4())
    
    # 创建者自动成为 admin
    admin_member = SessionMember(
        user_id=created_by,
        username=username,
        role="admin",
        joined_at=datetime.now(),
        color=assign_color(created_by)
    )
    
    session = CollaborationSession(
        id=session_id,
        project_id=project_id,
        created_by=created_by,
        created_at=datetime.now(),
        members=[admin_member],
        version=0,
        state={
            "tracks": [],
            "clips": [],
            "effects": [],
            "automation": [],
            "settings": {}
        }
    )
    
    sessions[session_id] = session
    
    return session


@router.get("/session/{session_id}", response_model=CollaborationSession)
async def get_session(session_id: str):
    """获取会话信息"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    return sessions[session_id]


@router.post("/session/{session_id}/join")
async def join_session(
    session_id: str,
    user_id: str = Body(...),
    username: str = Body(...),
    role: str = Body(default="viewer")
):
    """加入协作会话"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    session = sessions[session_id]
    
    # 检查是否已在会话中
    for member in session.members:
        if member.user_id == user_id:
            return {
                "success": True,
                "message": "已在会话中",
                "session": session,
                "existing": True
            }
    
    # 添加新成员
    new_member = SessionMember(
        user_id=user_id,
        username=username,
        role=role,
        joined_at=datetime.now(),
        color=assign_color(user_id)
    )
    session.members.append(new_member)
    
    return {
        "success": True,
        "message": "加入成功",
        "session": session,
        "member": new_member.dict(),
        "state": session.state,
        "version": session.version
    }


@router.post("/session/{session_id}/leave")
async def leave_session(session_id: str, user_id: str = Body(...)):
    """离开协作会话"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    session = sessions[session_id]
    
    # 移除成员
    session.members = [
        m for m in session.members if m.user_id != user_id
    ]
    
    # 如果所有成员都离开，标记为不活跃
    if len(session.members) == 0:
        session.is_active = False
    
    return {
        "success": True,
        "message": "已离开会话",
        "remaining_members": len(session.members)
    }


@router.get("/sessions")
async def get_my_sessions(user_id: str = Query(...)):
    """获取我的协作会话"""
    my_sessions = []
    for session_id, session in sessions.items():
        if any(m.user_id == user_id for m in session.members):
            my_sessions.append({
                "id": session.id,
                "project_id": session.project_id,
                "created_at": session.created_at.isoformat(),
                "member_count": len(session.members),
                "role": next(
                    m.role for m in session.members if m.user_id == user_id
                ),
                "is_active": session.is_active
            })
    
    return {
        "total": len(my_sessions),
        "sessions": my_sessions
    }


@router.post("/session/{session_id}/operation")
async def apply_operation_endpoint(
    session_id: str,
    operation: SessionOperation
):
    """应用操作到协作会话"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    session = sessions[session_id]
    
    # 检查用户是否在会话中
    if not any(m.user_id == operation.user_id for m in session.members):
        raise HTTPException(status_code=403, detail="未加入会话")
    
    # 检查权限
    user_member = next(m for m in session.members if m.user_id == operation.user_id)
    if user_member.role == "viewer" and operation.operation != "cursor":
        raise HTTPException(status_code=403, detail="查看者不能编辑")
    
    # 应用操作
    success = apply_operation(session, operation)
    
    if not success:
        return {
            "success": False,
            "message": "版本冲突，请重新同步",
            "current_version": session.version,
            "need_sync": True
        }
    
    return {
        "success": True,
        "message": "操作成功",
        "version": session.version,
        "broadcast": True  # 需要广播给其他成员
    }


@router.post("/session/{session_id}/sync")
async def sync_state(session_id: str, user_id: str = Body(...)):
    """同步最新状态"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    session = sessions[session_id]
    
    return {
        "success": True,
        "state": session.state,
        "version": session.version,
        "members": [m.dict() for m in session.members],
        "members_count": len(session.members)
    }


@router.delete("/session/{session_id}")
async def delete_session(session_id: str, created_by: str = Body(...)):
    """删除协作会话"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    session = sessions[session_id]
    if session.created_by != created_by:
        raise HTTPException(status_code=403, detail="只有创建者能删除会话")
    
    del sessions[session_id]
    
    return {
        "success": True,
        "message": "会话已删除"
    }


# ============ WebSocket Handler ============

@router.websocket("/ws/{session_id}")
async def websocket_collab(websocket: WebSocket, session_id: str):
    """
    WebSocket 实时同步端点
    消息格式:
    {
      "type": "join|operation|cursor|leave",
      "data": { ... }
    }
    """
    await websocket.accept()
    
    if session_id not in sessions:
        await websocket.send_json({"error": "会话不存在"})
        await websocket.close()
        return
    
    session = sessions[session_id]
    user_id = None
    username = None
    
    try:
        while True:
            # 接收消息
            raw_message = await websocket.receive_text()
            message = json.loads(raw_message)
            
            msg_type = message.get("type")
            data = message.get("data", {})
            
            if msg_type == "join":
                user_id = data.get("user_id")
                username = data.get("username")
                
                # 检查是否已在会话中
                existing = any(m.user_id == user_id for m in session.members)
                if not existing:
                    # 自动加入为 viewer
                    new_member = SessionMember(
                        user_id=user_id,
                        username=username,
                        role="viewer",
                        joined_at=datetime.now(),
                        color=assign_color(user_id)
                    )
                    session.members.append(new_member)
                
                # 发送当前状态
                await websocket.send_json({
                    "type": "joined",
                    "data": {
                        "user_id": user_id,
                        "session_id": session_id,
                        "state": session.state,
                        "version": session.version,
                        "members": [m.dict() for m in session.members],
                        "your_color": assign_color(user_id)
                    }
                })
                
                # 广播给其他成员：有人加入
                broadcast_data = {
                    "type": "user_joined",
                    "data": {
                        "user_id": user_id,
                        "username": username,
                        "color": assign_color(user_id)
                    }
                }
                await broadcast_to_others(session_id, user_id, broadcast_data)
            
            elif msg_type == "operation":
                if not user_id:
                    continue
                
                op = SessionOperation(
                    user_id=user_id,
                    operation=data.get("operation"),
                    target=data.get("target"),
                    data=data.get("data", {}),
                    version=data.get("version", session.version + 1)
                )
                
                # 检查权限
                member = next((m for m in session.members if m.user_id == user_id), None)
                if member and member.role == "viewer" and op.operation != "cursor":
                    await websocket.send_json({
                        "type": "error",
                        "data": {"message": "查看者不能编辑"}
                    })
                    continue
                
                # 应用操作
                success = apply_operation(session, op)
                
                if success:
                    # 广播给其他成员
                    broadcast_data = {
                        "type": "operation",
                        "data": {
                            "user_id": user_id,
                            "username": username,
                            "operation": op.operation,
                            "target": op.target,
                            "data": op.data,
                            "version": session.version
                        }
                    }
                    await broadcast_to_others(session_id, user_id, broadcast_data)
                    
                    # 确认给发送者
                    await websocket.send_json({
                        "type": "operation_ack",
                        "data": {"version": session.version}
                    })
                else:
                    await websocket.send_json({
                        "type": "sync_required",
                        "data": {
                            "current_version": session.version,
                            "state": session.state
                        }
                    })
            
            elif msg_type == "cursor":
                if not user_id:
                    continue
                
                position = data.get("position")
                
                # 更新 cursor
                for member in session.members:
                    if member.user_id == user_id:
                        member.cursor_position = position
                        break
                
                # 广播 cursor 移动
                broadcast_data = {
                    "type": "cursor_move",
                    "data": {
                        "user_id": user_id,
                        "username": username,
                        "color": assign_color(user_id),
                        "position": position
                    }
                }
                await broadcast_to_others(session_id, user_id, broadcast_data)
            
            elif msg_type == "leave":
                break
            
    except WebSocketDisconnect:
        pass
    finally:
        # 清理
        if user_id and session_id in sessions:
            session = sessions[session_id]
            session.members = [m for m in session.members if m.user_id != user_id]
            
            # 广播有人离开
            broadcast_data = {
                "type": "user_left",
                "data": {
                    "user_id": user_id,
                    "username": username
                }
            }
            await broadcast_to_others(session_id, user_id, broadcast_data)


async def broadcast_to_others(session_id: str, exclude_user_id: str, message: dict):
    """广播消息给会话中的其他成员"""
    # 实际实现需要维护 WebSocket 连接池
    # 这里简化处理，实际项目中需要使用 ConnectionManager
    pass


# ============ Connection Manager ============

class ConnectionManager:
    """管理 WebSocket 连接"""
    
    def __init__(self):
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}
        # session_id -> {user_id -> websocket}
    
    async def connect(self, websocket: WebSocket, session_id: str, user_id: str):
        await websocket.accept()
        
        if session_id not in self.active_connections:
            self.active_connections[session_id] = {}
        
        self.active_connections[session_id][user_id] = websocket
    
    def disconnect(self, session_id: str, user_id: str):
        if session_id in self.active_connections:
            self.active_connections[session_id].pop(user_id, None)
            
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
    
    async def broadcast(self, session_id: str, exclude_user_id: str, message: dict):
        """广播给会话中的其他用户"""
        if session_id not in self.active_connections:
            return
        
        for user_id, websocket in self.active_connections[session_id].items():
            if user_id != exclude_user_id:
                try:
                    await websocket.send_json(message)
                except:
                    # 连接已断开
                    pass


# 全局连接管理器
manager = ConnectionManager()