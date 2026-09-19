"""Exports for FastAPI routers used in main.py.

Provides lazy `mv_app / workflow_app / batch_app / dmca_router / user_app` so that:

    from app.services import mv_app, workflow_app, batch_app, dmca_router, user_app

still works exactly as before for `backend/main.py` (production API unchanged),
while importing a *submodule* (e.g. `from app.services.heartmula_service import ...`
on the RunPod GPU worker) does NOT eagerly import the FastAPI routers / full
FastAPI dependency chain.

This keeps the worker image light and avoids pulling FastAPI into the GPU worker.
"""

__all__ = ["mv_app", "workflow_app", "batch_app", "dmca_router", "user_app"]


def __getattr__(name: str):
    if name == "mv_app":
        from .mv_router import router as mv_app
        return mv_app
    if name == "workflow_app":
        from .workflow_router import router as workflow_app
        return workflow_app
    if name == "batch_app":
        from .batch_router import router as batch_app
        return batch_app
    if name == "dmca_router":
        from .dmca_router import router as dmca_router
        return dmca_router
    if name == "user_app":
        from .user_router import router as user_app
        return user_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")