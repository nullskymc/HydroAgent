"""
Authentication and audit service for HydroAgent admin console.
"""
from __future__ import annotations

import datetime as dt
import logging
import secrets
import string
from typing import Any

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from src.database.models import AuditEvent, User, get_db
from src.security import check_password, create_access_token, decode_access_token, hash_password
from src.services.rbac_service import ensure_rbac_seed, get_user_permission_keys, get_user_roles, set_user_roles, user_has_permission

logger = logging.getLogger(__name__)

DEFAULT_USERS = [
    ("admin", "admin123", ["admin"], "系统管理员"),
    ("manager", "manager123", ["manager"], "运营经理"),
    ("operator", "operator123", ["operator"], "值班操作员"),
    ("viewer", "viewer123", ["viewer"], "只读观察员"),
    ("auditor", "auditor123", ["auditor"], "审计员"),
]


def _generate_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def record_audit_event(
    db: Session,
    *,
    actor: str,
    event_type: str,
    object_type: str,
    object_id: str | None = None,
    result: str = "success",
    comment: str | None = None,
    details: dict[str, Any] | None = None,
):
    event = AuditEvent(
        actor=actor,
        event_type=event_type,
        object_type=object_type,
        object_id=object_id,
        result=result,
        comment=comment,
        details=details or {},
        occurred_at=dt.datetime.utcnow(),
    )
    db.add(event)
    db.commit()
    return event


def ensure_auth_seed(db: Session):
    ensure_rbac_seed(db)
    if db.query(User).count() > 0:
        return

    from src.config import config

    if config.DEMO_MODE:
        password = _generate_password()
        user = User(
            username="admin",
            password_hash=hash_password(password),
            email="admin@hydro.local",
            display_name="系统管理员",
            is_active=True,
            created_by="system",
            password_changed_at=dt.datetime.utcnow(),
        )
        db.add(user)
        db.flush()
        set_user_roles(db, user, ["admin"], assigned_by="system")
        db.commit()

        logger.info("=" * 60)
        logger.info("🔐 演示模式已启动 —— 唯一管理员账号：")
        logger.info(f"       用户名: admin")
        logger.info(f"       密码:   {password}")
        logger.info("       请立即保存此密码，容器重启后不会再次输出。")
        logger.info("=" * 60)
        return

    for username, password, role_keys, display_name in DEFAULT_USERS:
        user = User(
            username=username,
            password_hash=hash_password(password),
            email=f"{username}@hydro.local",
            display_name=display_name,
            is_active=True,
            created_by="system",
            password_changed_at=dt.datetime.utcnow(),
        )
        db.add(user)
        db.flush()
        set_user_roles(db, user, role_keys, assigned_by="system")
    db.commit()


def get_user_by_username(db: Session, username: str) -> User | None:
    ensure_auth_seed(db)
    return db.query(User).filter(User.username == username).first()


def serialize_user_profile(db: Session, user: User) -> dict[str, Any]:
    profile = user.to_dict()
    profile["roles"] = [role.role_key for role in get_user_roles(db, user)]
    profile["permissions"] = get_user_permission_keys(db, user)
    return profile


def authenticate_user(db: Session, username: str, password: str) -> tuple[str, dict[str, Any]]:
    ensure_auth_seed(db)
    user = get_user_by_username(db, username)
    if not user or not user.is_active or not check_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    user.last_login = dt.datetime.utcnow()
    db.commit()
    token = create_access_token(
        user.username,
        {
            "roles": [role.role_key for role in get_user_roles(db, user)],
            "permissions": get_user_permission_keys(db, user),
        },
    )
    record_audit_event(
        db,
        actor=user.username,
        event_type="auth.login",
        object_type="user",
        object_id=str(user.id),
        details={"username": user.username},
    )
    return token, serialize_user_profile(db, user)


def get_authenticated_user(db: Session, token: str | None) -> User:
    ensure_auth_seed(db)
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="登录状态无效")
    user = get_user_by_username(db, str(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已停用")
    return user


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    token = _extract_bearer_token(authorization)
    return get_authenticated_user(db, token)


def require_permission(permission_key: str):
    def dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if not user_has_permission(db, current_user, permission_key):
            raise HTTPException(status_code=403, detail=f"缺少权限: {permission_key}")
        return current_user

    return dependency
