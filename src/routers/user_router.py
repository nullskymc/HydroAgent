from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.config import config
from src.database.models import AuditEvent, User, get_db
from src.security import hash_password
from src.services.auth_service import get_current_user, record_audit_event, require_permission, serialize_user_profile
from src.services.rbac_service import list_permissions, list_roles, set_user_roles

router = APIRouter(tags=["users"])


class CreateUserRequest(BaseModel):
    username: str
    password: str = Field(min_length=6)
    email: str | None = None
    display_name: str | None = None
    phone: str | None = None
    is_active: bool = True
    role_keys: list[str] = Field(default_factory=list)


class UpdateUserRequest(BaseModel):
    email: str | None = None
    display_name: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    role_keys: list[str] | None = None
    password: str | None = None


@router.get("/users")
def get_users(
    _: User = Depends(require_permission("users:view")),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.created_at.asc()).all()
    return {"users": [serialize_user_profile(db, user) for user in users]}


@router.post("/users")
def create_user(
    req: CreateUserRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if "users:manage" not in serialize_user_profile(db, current_user)["permissions"]:
        raise HTTPException(status_code=403, detail="缺少权限: users:manage")
    if config.DEMO_MODE:
        raise HTTPException(status_code=403, detail="演示模式禁止创建新用户")
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        email=req.email,
        display_name=req.display_name,
        phone=req.phone,
        is_active=req.is_active,
        created_by=current_user.username,
        password_changed_at=dt.datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    set_user_roles(db, user, req.role_keys or ["viewer"], assigned_by=current_user.username)
    record_audit_event(
        db,
        actor=current_user.username,
        event_type="user.create",
        object_type="user",
        object_id=str(user.id),
        details={"username": user.username, "roles": req.role_keys},
    )
    return {"user": serialize_user_profile(db, user)}


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    req: UpdateUserRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if "users:manage" not in serialize_user_profile(db, current_user)["permissions"]:
        raise HTTPException(status_code=403, detail="缺少权限: users:manage")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    updates = req.dict(exclude_unset=True)
    role_keys = updates.pop("role_keys", None)
    password = updates.pop("password", None)
    for key, value in updates.items():
        setattr(user, key, value)
    if password:
        user.password_hash = hash_password(password)
        user.password_changed_at = dt.datetime.utcnow()
    db.commit()
    db.refresh(user)
    if role_keys is not None:
        set_user_roles(db, user, role_keys, assigned_by=current_user.username)
    record_audit_event(
        db,
        actor=current_user.username,
        event_type="user.update",
        object_type="user",
        object_id=str(user.id),
        details={"updates": list(updates.keys()), "roles": role_keys},
    )
    return {"user": serialize_user_profile(db, user)}


@router.get("/roles")
def get_roles(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    permissions = serialize_user_profile(db, current_user)["permissions"]
    if "users:view" not in permissions and "users:manage" not in permissions:
        raise HTTPException(status_code=403, detail="缺少权限: users:view")
    return {"roles": [role.to_dict() for role in list_roles(db)]}


@router.get("/permissions")
def get_permissions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    permissions = serialize_user_profile(db, current_user)["permissions"]
    if "users:view" not in permissions and "users:manage" not in permissions:
        raise HTTPException(status_code=403, detail="缺少权限: users:view")
    return {"permissions": [permission.to_dict() for permission in list_permissions(db)]}


@router.get("/audits")
def get_audits(
    _: User = Depends(require_permission("history:view")),
    db: Session = Depends(get_db),
):
    audits = db.query(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(100).all()
    return {"audits": [audit.to_dict() for audit in audits]}
