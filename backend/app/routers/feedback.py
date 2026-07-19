from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.services.feedback_service import create_feedback, get_feedback

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
    # user: dict | None = Depends(get_current_user_optional)  # Optional auth
):
    # For guest mode, we allow submission without auth
    # If you want to require auth, uncomment the dependency and use user info
    try:
        # Use provided name or default to anonymous
        name = feedback.name.strip() if feedback.name and feedback.name.strip() else "匿名用户"
        text = feedback.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="Feedback text cannot be empty")
        result = create_feedback(name, text)
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