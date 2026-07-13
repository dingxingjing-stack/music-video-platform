"""
私信系统路由 (Messaging Router)

功能:
- 发送/接收私信
- 对话列表
- WebSocket 实时聊天
- 未读消息计数

API 端点:
- GET /api/v1/messages/conversations - 对话列表
- GET /api/v1/messages/conversations/{with_user_id} - 与某人的聊天记录
- POST /api/v1/messages - 发送消息
- PUT /api/v1/messages/{id}/read - 标记已读
- WebSocket /ws/messages/{user_id} - 实时聊天
"""

from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime
import asyncio

router = APIRouter(prefix="/api/v1/messages", tags=["Messages"])

# 内存存储
messages_db: Dict[str, List[dict]] = {}  # conversation_id -> messages
conversations_db: Dict[str, set] = {}  # user_id -> set of conversation partners
websocket_messages: Dict[str, List[WebSocket]] = {}


def get_conversation_id(user1: str, user2: str) -> str:
    """生成对话 ID (按字母顺序确保唯一)"""
    return f"conv_{'_'.join(sorted([user1, user2]))}"


class MessageCreate(BaseModel):
    sender_id: str = Field(..., description="发送者 ID")
    receiver_id: str = Field(..., description="接收者 ID")
    content: str = Field(..., max_length=2000, description="消息内容")
    type: str = Field(default="text", description="消息类型：text/image/file")
    media_url: Optional[str] = Field(None, description="媒体 URL (如果是图片/文件)")


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    sender_id: str
    receiver_id: str
    content: str
    type: str
    media_url: Optional[str]
    is_read: bool
    created_at: datetime


class ConversationSummary(BaseModel):
    conversation_id: str
    partner_id: str
    partner_name: Optional[str]
    last_message: str
    last_message_time: datetime
    unread_count: int


def generate_message_id() -> str:
    return f"msg_{datetime.now().timestamp()}_{id(messages_db)}"


@router.post("", response_model=MessageResponse, status_code=201)
async def send_message(msg: MessageCreate):
    """发送私信"""
    conv_id = get_conversation_id(msg.sender_id, msg.receiver_id)
    
    message = {
        "id": generate_message_id(),
        "conversation_id": conv_id,
        "sender_id": msg.sender_id,
        "receiver_id": msg.receiver_id,
        "content": msg.content,
        "type": msg.type,
        "media_url": msg.media_url,
        "is_read": False,
        "created_at": datetime.now()
    }
    
    # 存储消息
    if conv_id not in messages_db:
        messages_db[conv_id] = []
    messages_db[conv_id].append(message)
    
    # 更新对话关系
    if msg.sender_id not in conversations_db:
        conversations_db[msg.sender_id] = set()
    if msg.receiver_id not in conversations_db:
        conversations_db[msg.receiver_id] = set()
    conversations_db[msg.sender_id].add(msg.receiver_id)
    conversations_db[msg.receiver_id].add(msg.sender_id)
    
    # WebSocket 推送给接收者
    if msg.receiver_id in websocket_messages:
        for ws in websocket_messages[msg.receiver_id]:
            try:
                await ws.send_json({
                    "type": "new_message",
                    "message": message
                })
            except:
                pass
    
    return message


@router.get("/conversations")
async def get_conversations(user_id: str = Query(..., description="用户 ID")):
    """获取用户的对话列表"""
    if user_id not in conversations_db:
        return []
    
    conversations = []
    for partner_id in conversations_db[user_id]:
        conv_id = get_conversation_id(user_id, partner_id)
        conv_messages = messages_db.get(conv_id, [])
        
        if not conv_messages:
            continue
        
        # 最后一条消息
        last_msg = conv_messages[-1]
        # 未读计数
        unread = sum(1 for m in conv_messages if m["receiver_id"] == user_id and not m["is_read"])
        
        conversations.append({
            "conversation_id": conv_id,
            "partner_id": partner_id,
            "partner_name": None,  # 可从用户服务获取
            "last_message": last_msg["content"],
            "last_message_time": last_msg["created_at"],
            "unread_count": unread
        })
    
    # 按最后消息时间排序
    conversations.sort(key=lambda x: x["last_message_time"], reverse=True)
    return conversations


@router.get("/conversations/{with_user_id}")
async def get_conversation_messages(
    with_user_id: str,
    user_id: str = Query(..., description="当前用户 ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    """获取与某人的聊天记录"""
    conv_id = get_conversation_id(user_id, with_user_id)
    conv_messages = messages_db.get(conv_id, [])
    
    # 分页 (倒序，最新消息在前)
    paginated = list(reversed(conv_messages))[offset:offset + limit]
    return paginated


@router.put("/{message_id}/read")
async def mark_message_as_read(message_id: str):
    """标记消息为已读"""
    for conv_id, messages in messages_db.items():
        for msg in messages:
            if msg["id"] == message_id:
                msg["is_read"] = True
                return {"message": "标记为已读", "message_id": message_id}
    
    raise HTTPException(status_code=404, detail="消息未找到")


@router.websocket("/ws/messages/{user_id}")
async def messages_websocket(websocket: WebSocket, user_id: str):
    """WebSocket 实时私信"""
    await websocket.accept()
    
    # 注册连接
    if user_id not in websocket_messages:
        websocket_messages[user_id] = []
    websocket_messages[user_id].append(websocket)
    
    try:
        while True:
            data = await websocket.receive_json()
            # 可以处理客户端消息
    except WebSocketDisconnect:
        # 移除连接
        if user_id in websocket_messages:
            websocket_messages[user_id].remove(websocket)
            if not websocket_messages[user_id]:
                del websocket_messages[user_id]