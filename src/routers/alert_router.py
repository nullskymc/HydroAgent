from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database.models import User, get_db
from src.services.alert_service import acknowledge_alert, list_alert_events, resolve_alert
from src.services.auth_service import record_audit_event, require_permission

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertActionRequest(BaseModel):
    comment: str | None = None


@router.get("")
def get_alerts(
    status: str | None = None,
    _: User = Depends(require_permission("alerts:view")),
    db: Session = Depends(get_db),
):
    return {"alerts": [alert.to_dict() for alert in list_alert_events(db, status=status)]}


@router.post("/{alert_id}/acknowledge")
def acknowledge(
    alert_id: str,
    req: AlertActionRequest,
    current_user: User = Depends(require_permission("alerts:manage")),
    db: Session = Depends(get_db),
):
    alert = acknowledge_alert(db, alert_id, current_user.username)
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")
    record_audit_event(
        db,
        actor=current_user.username,
        event_type="alert.acknowledge",
        object_type="alert",
        object_id=alert.alert_id,
        comment=req.comment,
    )
    return {"alert": alert.to_dict()}


@router.post("/{alert_id}/resolve")
def resolve(
    alert_id: str,
    req: AlertActionRequest,
    current_user: User = Depends(require_permission("alerts:manage")),
    db: Session = Depends(get_db),
):
    alert = resolve_alert(db, alert_id, current_user.username)
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")
    record_audit_event(
        db,
        actor=current_user.username,
        event_type="alert.resolve",
        object_type="alert",
        object_id=alert.alert_id,
        comment=req.comment,
    )
    return {"alert": alert.to_dict()}
