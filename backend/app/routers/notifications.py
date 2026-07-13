"""
通知系统路由 (Notification Router)

功能:
- 创建/获取/标记通知
- WebSocket 实时推送
- 通知类型：点赞/收藏/关注/评论/系统
- 未读计数

API 端点:
- GET /api/v1/notifications - 获取用户通知列表
- POST /api/v1/notifications - 创建通知
- PUT /api/v1/notifications/{id}/read - 标记已读
- PUT /api/v1/notifications/read-all - 全部已读
- DELETE /api/v1/notifications/{id} - 删除通知
- GET /api/v1/notifications/unread/count - 未读计数
- WebSocket /ws/notifications/{user_id} - 实时推送
"""

from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime
import asyncio

router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])

# 内存存储 (生产环境需换数据库)
notifications_db: Dict[str, List[dict]] = {}
websocket_connections: Dict[str, List[WebSocket]] = {}


class NotificationType:
    LIKE = "like"
    FAVORITE = "favorite"
    FOLLOW = "follow"
    COMMENT = "comment"
    SYSTEM = "system"
    COLLAB_INVITE = "collab_invite"
    COPYRIGHT_ALERT = "copyright_alert"


class NotificationCreate(BaseModel):
    user_id: str = Field(..., description="接收通知的用户 ID")
    type: str = Field(..., description="通知类型")
    title: str = Field(..., max_length=100)
    content: str = Field(..., max_length=500)
    related_id: Optional[str] = Field(None, description="关联对象 ID (作品 ID/评论 ID 等)")
    sender_id: Optional[str] = Field(None, description="发送者 ID")
    sender_name: Optional[str] = Field(None, description="发送者名称")


class NotificationResponse(BaseModel):
    id: str
    user_id: str
    type: str
    title: str
    content: str
    related_id: Optional[str]
    sender_id: Optional[str]
    sender_name: Optional[str]
    is_read: bool
    created_at: datetime


def generate_notification_id() -> str:
    return f"notif_{datetime.now().timestamp()}_{id(notifications_db)}"


@router.post("", response_model=NotificationResponse, status_code=201)
async def create_notification(notif: NotificationCreate):
    """创建通知并推送给接收者"""
    notification = {
        "id": generate_notification_id(),
        "user_id": notif.user_id,
        "type": notif.type,
        "title": notif.title,
        "content": notif.content,
        "related_id": notif.related_id,
        "sender_id": notif.sender_id,
        "sender_name": notif.sender_name,
        "is_read": False,
        "created_at": datetime.now()
    }
    
    # 存入数据库
    if notif.user_id not in notifications_db:
        notifications_db[notif.user_id] = []
    notifications_db[notif.user_id].insert(0, notification)
    
    # WebSocket 实时推送
    if notif.user_id in websocket_connections:
        for ws in websocket_connections[notif.user_id]:
            try:
                await ws.send_json(notification)
            except:
                pass  # 连接已断开
    
    return notification


@router.get("", response_model=List[NotificationResponse])
async def get_notifications(
    user_id: str = Query(..., description="用户 ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    type_filter: Optional[str] = Query(None, description="按类型筛选"),
    unread_only: bool = Query(False, description="只看未读")
):
    """获取用户通知列表"""
    user_notifs = notifications_db.get(user_id, [])
    
    # 筛选
    if type_filter:
        user_notifs = [n for n in user_notifs if n["type"] == type_filter]
    if unread_only:
        user_notifs = [n for n in user_notifs if not n["is_read"]]
    
    # 分页
    paginated = user_notifs[offset:offset + limit]
    
    return paginated


@router.get("/unread/count")
async def get_unread_count(user_id: str = Query(..., description="用户 ID")):
    """获取未读通知数量"""
    user_notifs = notifications_db.get(user_id, [])
    unread_count = sum(1 for n in user_notifs if not n["is_read"])
    return {"user_id": user_id, "unread_count": unread_count}


@router.put("/{notification_id}/read")
async def mark_as_read(notification_id: str):
    """标记通知为已读"""
    # 查找通知
    for user_id, notifs in notifications_db.items():
        for notif in notifs:
            if notif["id"] == notification_id:
                notif["is_read"] = True
                return {"message": "标记为已读", "notification_id": notification_id}
    
    raise HTTPException(status_code=404, detail="通知未找到")


@router.put("/read-all")
async def mark_all_as_read(user_id: str = Query(..., description="用户 ID")):
    """标记所有通知为已读"""
    user_notifs = notifications_db.get(user_id, [])
    for notif in user_notifs:
        notif["is_read"] = True
    
    return {"message": "全部标记为已读", "user_id": user_id, "marked_count": len(user_notifs)}


@router.delete("/{notification_id}")
async def delete_notification(notification_id: str):
    """删除通知"""
    for user_id, notifs in notifications_db.items():
        for i, notif in enumerate(notifs):
            if notif["id"] == notification_id:
                notifs.pop(i)
                return {"message": "删除成功", "notification_id": notification_id}
    
    raise HTTPException(status_code=404, detail="通知未找到")


@router.websocket("/ws/notifications/{user_id}")
async def notifications_websocket(websocket: WebSocket, user_id: str):
    """WebSocket 实时推送通知"""
    await websocket.accept()
    
    # 注册连接
    if user_id not in websocket_connections:
        websocket_connections[user_id] = []
    websocket_connections[user_id].append(websocket)
    
    try:
        # 发送当前未读计数
        user_notifs = notifications_db.get(user_id, [])
        unread_count = sum(1 for n in user_notifs if not n["is_read"])
        await websocket.send_json({
            "type": "init",
            "unread_count": unread_count
        })
        
        # 保持连接并处理消息
        while True:
            data = await websocket.receive_text()
            # 可以处理客户端消息 (如标记已读确认)
    except WebSocketDisconnect:
        # 移除断开连接
        if user_id in websocket_connections:
            websocket_connections[user_id].remove(websocket)
            if not websocket_connections[user_id]:
                del websocket_connections[user_id]