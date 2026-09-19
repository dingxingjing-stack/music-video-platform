"""Projects 最小 CRUD 路由 —— Phase 3-3。

身份：唯一来源 = Authorization Bearer JWT → get_verified_user_id。
禁止信任客户端传入 user_id / body.user_id；所有权一律以 JWT user_id 为准。

数据访问：现有 SQLAlchemy（app.db.database.SessionLocal + Project 模型），
不引入新的连接体系，不新增 FK，不实现 Update / cascade。
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db.database import SessionLocal, Project
from app.services.auth_identity import get_verified_user_id
from app.services.supabase_service import get_song_by_id, update_song, get_songs_by_project, detach_songs_from_project
from app.routers.songs import SongResponse

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class ProjectUpdate(BaseModel):
    """PATCH 只允许更新 name；user_id/extra 字段被忽略（不改所有者）。"""
    name: str = Field(..., min_length=1, max_length=255)


class ProjectResponse(BaseModel):
    id: str
    user_id: str
    name: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


def _to_response(p: Project) -> ProjectResponse:
    def iso(v):
        return v.isoformat() if v is not None else None

    return ProjectResponse(
        id=p.id,
        user_id=p.user_id,
        name=p.name,
        created_at=iso(p.created_at),
        updated_at=iso(p.updated_at),
    )


@router.post("/", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: ProjectCreate,
    user_id: str = Depends(get_verified_user_id),
):
    """创建 project（name 唯一输入；user_id 取自 JWT，忽略任何客户端 user_id）。"""
    db = SessionLocal()
    try:
        project = Project(
            id=str(uuid.uuid4()),
            user_id=user_id,
            name=body.name,
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        return _to_response(project)
    finally:
        db.close()


@router.get("/", response_model=List[ProjectResponse])
async def list_projects(user_id: str = Depends(get_verified_user_id)):
    """只返回当前 JWT 用户自己的 projects，按 created_at DESC。"""
    db = SessionLocal()
    try:
        rows = (
            db.query(Project)
            .filter(Project.user_id == user_id)
            .order_by(Project.created_at.desc())
            .all()
        )
        return [_to_response(p) for p in rows]
    finally:
        db.close()


@router.get("/{project_id}/songs", response_model=List[SongResponse])
async def list_project_songs(project_id: str, user_id: str = Depends(get_verified_user_id)):
    """查看自己 Project 下的 Songs（只读）。

    权限：project 必须属于当前 JWT 用户；查询同时过滤 project_id + user_id，
    避免返回其他用户的 Song。不属于当前用户 → 404。
    """
    # 1) project ownership 校验（SQLAlchemy）
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if p is None or p.user_id != user_id:
            raise HTTPException(status_code=404, detail="Project not found")
    finally:
        db.close()

    # 2) songs 双归属过滤（Supabase service：project_id + user_id，created_at DESC）
    songs = get_songs_by_project(project_id, user_id)
    return [SongResponse(**s) for s in songs]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, user_id: str = Depends(get_verified_user_id)):
    """只能读取自己的 project；不属于当前用户 → 404（不泄露存在性）。"""
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if p is None or p.user_id != user_id:
            raise HTTPException(status_code=404, detail="Project not found")
        return _to_response(p)
    finally:
        db.close()


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, user_id: str = Depends(get_verified_user_id)):
    """删除自己的 project，同时把关联（当前用户、project_id=该 project）的 Songs.project_id 置 NULL。

    - 保留 Song 及其音频/R2，不 cascade 删除；
    - 只 detach 当前用户的 Songs（双重过滤，不触碰他人）；
    - 无 Songs 的 project 也正常删除。
    """
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if p is None or p.user_id != user_id:
            raise HTTPException(status_code=404, detail="Project not found")
        # 先 detach 关联 Songs（保留 Song）—— 失败则中止，避免留下悬挂引用
        if not detach_songs_from_project(project_id, user_id):
            raise HTTPException(status_code=500, detail="Failed to detach songs")
        db.delete(p)
        db.commit()
    finally:
        db.close()


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    user_id: str = Depends(get_verified_user_id),
):
    """只更新自己的 project 的 name（user_id 一律来自 JWT，忽略 body 中的 user_id）。"""
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if p is None or p.user_id != user_id:
            raise HTTPException(status_code=404, detail="Project not found")
        # 仅更新 name；updated_at 由模型 onupdate 自动刷新
        p.name = body.name
        db.commit()
        db.refresh(p)
        return _to_response(p)
    finally:
        db.close()


class SongBindResponse(BaseModel):
    """绑定成功返回的 Song（含更新后的 project_id）。"""
    id: str
    user_id: str
    title: Optional[str] = None
    project_id: Optional[str] = None
    status: Optional[str] = None
    updated_at: Optional[str] = None


@router.post("/{project_id}/songs/{song_id}", response_model=SongBindResponse)
async def bind_song_to_project(
    project_id: str,
    song_id: str,
    user_id: str = Depends(get_verified_user_id),
):
    """把「自己的 Song」绑定到「自己的 Project」（songs.project_id = project_id）。

    权限：project 与 song 都必须属于当前 JWT user_id；任一不属于 → 404（不泄露存在性）。
    幂等：已属于该 project 时不再重复写（单标量列，无关联表，无重复数据）。
    """
    # 1) project 必须属于当前用户
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project is None or project.user_id != user_id:
            raise HTTPException(status_code=404, detail="Project not found")
    finally:
        db.close()

    # 2) song 必须属于当前用户
    song = get_song_by_id(song_id)
    if song is None or song.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Song not found")

    # 3) 幂等：已绑定到目标 project 时不重复写
    if song.get("project_id") != project_id:
        updated = update_song(song_id, {"project_id": project_id})
        if not updated:
            raise HTTPException(status_code=500, detail="Failed to bind song")
        song = updated

    return SongBindResponse(
        id=song.get("id"),
        user_id=song.get("user_id"),
        title=song.get("title"),
        project_id=song.get("project_id"),
        status=song.get("status"),
        updated_at=song.get("updated_at"),
    )