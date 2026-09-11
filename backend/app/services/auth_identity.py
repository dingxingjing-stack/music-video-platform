"""认证身份解析（auth identity）——统一处理 Authorization: Bearer 头。

目标（Supabase PostgreSQL 修复）：
  1. Bearer <JWT> 必须经 Supabase Auth 验证，取 JWT 的 auth user id（UUID），
     绝不把整段 JWT 当作用户 ID 传入数据库查询/写入。
  2. 无法验证（缺配置/无效 token）时明确返回 None，由路由层 fail-closed 401。
  3. 开发/测试环境（未配置 SUPABASE_URL/KEY，走 SQLite 后端）保留旧语义：
     Bearer 后的值直接当作用户标识，避免破坏本地与测试流程。

不引入新依赖、不新建表、不改 schema。
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)

# RFC 4122 UUID（大小写不敏感）
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def is_uuid(value: str) -> bool:
    """判断字符串是否为合法 UUID 形态。"""
    return bool(value) and bool(_UUID_RE.match(value))


def resolve_x_user_id(x_user_id: Optional[str]) -> Optional[str]:
    """从 X-User-ID 头解析权威用户标识（唯一可信身份来源）。

    - 仅接受 X-User-ID（去空白后非空），缺失/空白返回 None。
    - 绝不接受 body.user_id / client.host 作为替代身份（防伪造）。
    调用方应把 None 视为 401（缺少用户标识）。
    """
    if not x_user_id:
        return None
    v = x_user_id.strip()
    return v or None


def extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    """从 Authorization 头提取 Bearer token；非 Bearer 头返回 None。"""
    if not authorization:
        return None
    parts = authorization.strip().split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        token = parts[1].strip()
        return token or None
    # 兼容历史上直接传 token（无 Bearer 前缀）的客户端
    return authorization.strip() or None


def supabase_configured() -> bool:
    return bool(
        os.getenv("SUPABASE_URL")
        and (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY"))
    )


def verify_bearer_jwt(token: str) -> Optional[str]:
    """用 Supabase Auth 验证 JWT，返回 auth user id（UUID）；失败返回 None。

    JWT 无效/过期/签名校验失败时返回 None，绝不返回 token 本身。
    """
    if not supabase_configured():
        return None
    try:
        # 惰性 import + 惰性 client：未配置时 supabase_service.supabase 是可导入的占位
        from app.services.supabase_service import supabase
        resp = supabase.auth.get_user(token)
        user = getattr(resp, "user", None)
        uid = getattr(user, "id", None)
        if uid and is_uuid(str(uid)):
            uid_str = str(uid)
            # Phase 3-2A：JWT 兜底补建 public.users（trigger 为主，此处最佳努力、不阻断认证）。
            email = getattr(user, "email", None)
            if email:
                try:
                    from app.services.supabase_service import ensure_user
                    ensure_user(uid_str, email)
                except Exception:  # noqa: BLE001 —— 补建失败不影响身份验证
                    pass
            return uid_str
        logger.warning("Supabase Auth 验证未返回有效 user id")
        return None
    except Exception as exc:  # noqa: BLE001 —— 任何验证失败都按未认证处理
        logger.warning("Supabase Auth JWT 验证失败: %s", type(exc).__name__)
        return None


def resolve_auth_user_id(authorization: Optional[str]) -> Optional[str]:
    """把 Authorization 头解析为可信用户标识。

    - 生产（已配置 Supabase）：Bearer JWT 必须能被 Supabase Auth 验证，
      返回 auth.users.id（UUID）；验证失败返回 None → 路由层应 401。
    - 开发/测试（未配置 Supabase）：退化为「Bearer 后的值即用户标识」，
      与既有 SQLite 本地流程兼容。
    """
    token = extract_bearer_token(authorization)
    if not token:
        return None
    if supabase_configured():
        return verify_bearer_jwt(token)
    return token


async def get_verified_user_id(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> str:
    """FastAPI 身份依赖：唯一可信用户标识 = verified `auth.users.id`（UUID 字符串）。

    - 唯一来源：`Authorization: Bearer <Supabase access_token>` → `resolve_auth_user_id()`。
    - 解析失败 / 缺失 / 无效 token → HTTPException 401（fail-closed）。
    - 绝不回退 X-User-ID / body.user_id / query / form / client.host / anonymous / 自造 id。
    """
    user_id = resolve_auth_user_id(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or missing Authorization token")
    return user_id


async def get_verified_user_id_optional(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Optional[str]:
    """FastAPI 可选身份依赖：有有效 Bearer JWT → verified `auth.users.id`；无 Authorization → None。

    - 有 Authorization 但 token 无效 → 按既有语义返回 None（invalid == 未认证），
      不把无效 token 当合法身份、也不抛出（供“登录可选”的读端点使用）。
    - 仍复用 resolve_auth_user_id()（Supabase Auth 验签），不复制验证逻辑。
    """
    if not authorization:
        return None
    return resolve_auth_user_id(authorization)
