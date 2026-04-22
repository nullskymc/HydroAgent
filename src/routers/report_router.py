from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from src.database.models import User, get_db
from src.services.auth_service import require_permission
from src.services.report_service import export_audit_report, export_operations_report, export_zone_report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/operations/export")
def operations_export(
    _: User = Depends(require_permission("reports:export")),
    db: Session = Depends(get_db),
):
    return PlainTextResponse(
        export_operations_report(db),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="operations-report.csv"'},
    )


@router.get("/audit/export")
def audit_export(
    _: User = Depends(require_permission("reports:export")),
    db: Session = Depends(get_db),
):
    return PlainTextResponse(
        export_audit_report(db),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit-report.csv"'},
    )


@router.get("/zones/{zone_id}/export")
def zone_export(
    zone_id: str,
    _: User = Depends(require_permission("reports:export")),
    db: Session = Depends(get_db),
):
    return PlainTextResponse(
        export_zone_report(db, zone_id),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{zone_id}-report.csv"'},
    )
