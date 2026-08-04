"""
UGC 投稿系统 API

端点:
- POST /api/v1/ugc/submit - 投稿
- GET /api/v1/ugc/submissions - 我的投稿列表
- POST /api/v1/ugc/review - 审核 (管理员)
- GET /api/v1/ugc/earnings - 收益查询
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

router = APIRouter(prefix="/api/v1/ugc", tags=["UGC"])


# ========== 数据模型 ==========

class UGCSubmission(BaseModel):
    """投稿作品"""
    id: str
    user_id: str
    type: str  # template, material, effect
    title: str
    description: str
    category: str
    tags: List[str]
    price: float
    status: str  # pending, approved, rejected
    created_at: datetime
    downloads: int = 0
    earnings: float = 0.0


class SubmitRequest(BaseModel):
    """投稿请求"""
    type: str
    title: str
    description: str
    category: str
    tags: List[str]
    price: float


class ReviewRequest(BaseModel):
    """审核请求"""
    submission_id: str
    status: str  # approved, rejected
    reason: Optional[str] = None
    suggested_price: Optional[float] = None


# ========== Mock 数据 ==========

mock_submissions: List[UGCSubmission] = []


# ========== 路由 ==========

@router.post("/submit")
async def submit_work(
    type: str = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    tags: str = Form(...),  # JSON string
    price: float = Form(...),
    file: UploadFile = File(...)
):
    """
    投稿作品
    
    用户上传模板/素材/效果，投稿到平台
    """
    import json
    import uuid
    
    # 解析标签
    tags_list = json.loads(tags)
    
    # 创建投稿记录
    submission = UGCSubmission(
        id=str(uuid.uuid4()),
        user_id="user_123",  # TODO: 从 auth 获取
        type=type,
        title=title,
        description=description,
        category=category,
        tags=tags_list,
        price=price,
        status="pending",
        created_at=datetime.now(),
    )
    
    # TODO: 保存文件到存储
    # file_path = save_file(file, submission.id)
    
    mock_submissions.append(submission)
    
    return {
        "success": True,
        "submission_id": submission.id,
        "message": "投稿成功，等待审核 (1-2 个工作日)"
    }


@router.get("/submissions")
async def get_my_submissions(user_id: str = "user_123"):
    """获取我的投稿列表"""
    user_subs = [s for s in mock_submissions if s.user_id == user_id]
    
    return {
        "success": True,
        "submissions": user_subs,
        "total": len(user_subs)
    }


@router.post("/review")
async def review_submission(request: ReviewRequest):
    """
    审核投稿 (管理员)
    
    管理员审核投稿作品，决定是否上架
    """
    # 查找投稿
    submission = None
    for s in mock_submissions:
        if s.id == request.submission_id:
            submission = s
            break
    
    if not submission:
        raise HTTPException(status_code=404, detail="投稿不存在")
    
    # 更新状态
    submission.status = request.status
    if request.suggested_price:
        submission.price = request.suggested_price
    
    # TODO: 发送通知邮件
    
    return {
        "success": True,
        "message": f"投稿已{ '通过' if request.status == 'approved' else '拒绝' }"
    }


@router.get("/earnings")
async def get_earnings(user_id: str = "user_123"):
    """
    查询收益
    
    查看投稿作品的下载量和分成收入
    """
    user_subs = [s for s in mock_submissions if s.user_id == user_id]
    
    total_earnings = sum(s.earnings for s in user_subs)
    total_downloads = sum(s.downloads for s in user_subs)
    
    # 收益明细
    details = [
        {
            "id": s.id,
            "title": s.title,
            "downloads": s.downloads,
            "price": s.price,
            "earnings": s.earnings,
            "rate": "50%" if s.type == "template" else "40%"
        }
        for s in user_subs
    ]
    
    return {
        "success": True,
        "total_earnings": total_earnings,
        "total_downloads": total_downloads,
        "details": details
    }


@router.get("/marketplace")
async def get_marketplace(
    type: Optional[str] = None,
    category: Optional[str] = None,
    sort: str = "popular"  # popular, newest, top_earning
):
    """
    素材市场 - 浏览可购买的模板/素材
    
    只返回已审核通过的作品
    """
    approved = [s for s in mock_submissions if s.status == "approved"]
    
    # 过滤
    if type:
        approved = [s for s in approved if s.type == type]
    if category:
        approved = [s for s in approved if s.category == category]
    
    # 排序
    if sort == "popular":
        approved.sort(key=lambda x: x.downloads, reverse=True)
    elif sort == "newest":
        approved.sort(key=lambda x: x.created_at, reverse=True)
    elif sort == "top_earning":
        approved.sort(key=lambda x: x.earnings, reverse=True)
    
    return {
        "success": True,
        "items": approved,
        "total": len(approved)
    }