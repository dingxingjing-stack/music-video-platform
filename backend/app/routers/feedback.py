from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel
from app.services.feedback_service import create_feedback, get_feedback
from app.services.auth_identity import resolve_auth_user_id
from app.services.supabase_service import get_user

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])

class FeedbackCreate(BaseModel):
    name: str | None = None
    text: str

class FeedbackResponse(BaseModel):
    id: str
    name: str
    text: str
    created_at: str

@router.post("/", status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    feedback: FeedbackCreate,
    authorization: Optional[str] = Header(None),
):
    """提交反馈。

    真实 feedback 表要求 user_id(uuid, FK users.id) + content + text 均 NOT NULL，
    因此必须能解析出认证用户：Bearer JWT 经 Supabase Auth 验证 → auth user id
    → users.supabase_user_id 映射到 users.id。无法识别用户则 fail-closed 401，
    不写入会违反约束或破坏外键的记录。
    """
    name = feedback.name.strip() if feedback.name and feedback.name.strip() else "匿名用户"
    text = feedback.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Feedback text cannot be empty")

    auth_user_id = resolve_auth_user_id(authorization)
    if not auth_user_id:
        raise HTTPException(status_code=401, detail="请先登录后再提交反馈")
    user = get_user(auth_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        result = create_feedback(name, text, user["id"])
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=list[FeedbackResponse])
async def list_feedback(
    # user: dict | None = Depends(get_current_user_optional)  # Optional auth
):
    try:
        # For now, we allow anyone to list feedback (public feedback)
        results = get_feedback(limit=50, offset=0)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
