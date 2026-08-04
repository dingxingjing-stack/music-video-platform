"""Exports for FastAPI routers used in main.py.

Provides shortcut imports so `backend/main.py` can do:
    from app.services import mv_app, workflow_app, batch_app, dmca_router, user_app
"""

from .mv_router import router as mv_app
from .workflow_router import router as workflow_app
from .batch_router import router as batch_app
from .dmca_router import router as dmca_router
from .user_router import router as user_app
