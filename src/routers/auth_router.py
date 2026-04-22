from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database.models import get_db
from src.services.auth_service import authenticate_user, get_current_user, record_audit_event, serialize_user_profile

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    token, user = authenticate_user(db, req.username, req.password)
    return {"token": token, "user": user}


@router.post("/logout")
def logout(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    record_audit_event(
        db,
        actor=current_user.username,
        event_type="auth.logout",
        object_type="user",
        object_id=str(current_user.id),
    )
    return {"success": True}


@router.get("/me")
def me(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return {"user": serialize_user_profile(db, current_user)}
