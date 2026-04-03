from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.database.models import User, get_db
from src.services.analytics_service import get_alert_trend, get_analytics_overview, get_plan_funnel, get_zone_trend
from src.services.auth_service import require_permission

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview")
def overview(
    range: str = "7d",
    _: User = Depends(require_permission("dashboard:view")),
    db: Session = Depends(get_db),
):
    return get_analytics_overview(db, range)


@router.get("/zones/{zone_id}/trend")
def zone_trend(
    zone_id: str,
    range: str = "7d",
    _: User = Depends(require_permission("assets:view")),
    db: Session = Depends(get_db),
):
    return get_zone_trend(db, zone_id, range)


@router.get("/plans/funnel")
def plan_funnel(
    range: str = "7d",
    _: User = Depends(require_permission("operations:view")),
    db: Session = Depends(get_db),
):
    return get_plan_funnel(db, range)


@router.get("/alerts/trend")
def alert_trend(
    range: str = "7d",
    _: User = Depends(require_permission("alerts:view")),
    db: Session = Depends(get_db),
):
    return get_alert_trend(db, range)
