"""
Alert domain service for HydroAgent.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from src.database.models import AlertEvent, AlertRule, IrrigationPlan
from src.services.irrigation_service import collect_zone_evidence, list_zones
from src.services.system_settings_service import get_default_soil_moisture_threshold

DEFAULT_ALERT_RULES = [
    ("low_moisture", "低湿度告警", "土壤湿度进入紧急带，需要人工关注。", "high"),
    ("sensor_offline", "传感器异常", "传感器缺失或返回无效数据。", "high"),
    ("actuator_fault", "执行器风险", "执行器状态异常、已禁用或存在冲突。", "medium"),
    ("weather_risk", "天气风险", "未来 48 小时有降雨风险，存在启动计划。", "medium"),
]


def ensure_alert_rules(db: Session):
    for rule_key, name, description, severity in DEFAULT_ALERT_RULES:
        rule = db.query(AlertRule).filter(AlertRule.rule_key == rule_key).first()
        if not rule:
            db.add(
                AlertRule(
                    rule_key=rule_key,
                    name=name,
                    description=description,
                    severity=severity,
                    is_enabled=True,
                )
            )
    db.commit()


def _upsert_open_alert(
    db: Session,
    *,
    rule_key: str,
    severity: str,
    title: str,
    message: str,
    object_type: str,
    object_id: str,
    zone_id: str | None = None,
    sensor_device_id: str | None = None,
    actuator_id: str | None = None,
    plan_id: str | None = None,
    context: dict | None = None,
):
    existing = (
        db.query(AlertEvent)
        .filter(
            AlertEvent.rule_key == rule_key,
            AlertEvent.object_type == object_type,
            AlertEvent.object_id == object_id,
            AlertEvent.status.in_(["open", "acknowledged"]),
        )
        .order_by(AlertEvent.created_at.desc())
        .first()
    )
    if existing:
        return existing

    alert = AlertEvent(
        rule_key=rule_key,
        severity=severity,
        status="open",
        title=title,
        message=message,
        object_type=object_type,
        object_id=object_id,
        zone_id=zone_id,
        sensor_device_id=sensor_device_id,
        actuator_id=actuator_id,
        plan_id=plan_id,
        context=context or {},
    )
    db.add(alert)
    return alert


def evaluate_alerts(db: Session):
    ensure_alert_rules(db)
    zones = list_zones(db)
    for zone in zones:
        evidence = collect_zone_evidence(db, zone)
        sensor_average = evidence.sensor_summary.get("average", {})
        moisture = float(sensor_average.get("soil_moisture", 0.0) or 0.0)
        threshold = float(zone.soil_moisture_threshold or get_default_soil_moisture_threshold(db) or 40.0)
        emergency_band = max(0.0, threshold - 15.0)
        actuator = evidence.actuator
        latest_plan = (
            db.query(IrrigationPlan)
            .filter(IrrigationPlan.zone_id == zone.zone_id)
            .order_by(IrrigationPlan.created_at.desc())
            .first()
        )

        if evidence.sensor_summary.get("status") != "ok":
            _upsert_open_alert(
                db,
                rule_key="sensor_offline",
                severity="high",
                title=f"{zone.name} 传感器异常",
                message="当前分区缺少可用传感器数据，自动灌溉将保持 hold/defer。",
                object_type="zone",
                object_id=zone.zone_id,
                zone_id=zone.zone_id,
                context={"sensor_summary": evidence.sensor_summary},
            )

        if moisture < emergency_band:
            _upsert_open_alert(
                db,
                rule_key="low_moisture",
                severity="high",
                title=f"{zone.name} 湿度进入紧急带",
                message=f"当前湿度 {moisture:.2f}% 已低于紧急带 {emergency_band:.2f}%。",
                object_type="zone",
                object_id=zone.zone_id,
                zone_id=zone.zone_id,
                plan_id=latest_plan.plan_id if latest_plan else None,
                context={"soil_moisture": moisture, "threshold": threshold, "emergency_band": emergency_band},
            )

        if actuator and (not actuator.is_enabled or actuator.status in {"unknown", "running"} or actuator.health_status not in {"healthy", "warning"}):
            _upsert_open_alert(
                db,
                rule_key="actuator_fault",
                severity="medium" if actuator.is_enabled else "high",
                title=f"{zone.name} 执行器状态异常",
                message=f"执行器状态为 {actuator.status}，健康状态为 {actuator.health_status}。",
                object_type="actuator",
                object_id=actuator.actuator_id,
                zone_id=zone.zone_id,
                actuator_id=actuator.actuator_id,
                context=actuator.to_dict(),
            )

        if evidence.weather_summary.get("rain_expected") and latest_plan and latest_plan.proposed_action == "start":
            _upsert_open_alert(
                db,
                rule_key="weather_risk",
                severity="medium",
                title=f"{zone.name} 存在天气风险",
                message="未来 48 小时存在降雨信号，但当前仍有启动型灌溉计划。",
                object_type="plan",
                object_id=latest_plan.plan_id,
                zone_id=zone.zone_id,
                plan_id=latest_plan.plan_id,
                context={"weather_summary": evidence.weather_summary, "plan": latest_plan.to_dict()},
            )

    db.commit()


def list_alert_events(db: Session, status: str | None = None, limit: int = 100):
    evaluate_alerts(db)
    query = db.query(AlertEvent).order_by(AlertEvent.created_at.desc())
    if status:
        query = query.filter(AlertEvent.status == status)
    return query.limit(limit).all()


def acknowledge_alert(db: Session, alert_id: str, assignee: str) -> AlertEvent | None:
    alert = db.query(AlertEvent).filter(AlertEvent.alert_id == alert_id).first()
    if not alert:
        return None
    alert.status = "acknowledged"
    alert.assignee = assignee
    alert.acknowledged_at = dt.datetime.utcnow()
    db.commit()
    db.refresh(alert)
    return alert


def resolve_alert(db: Session, alert_id: str, assignee: str) -> AlertEvent | None:
    alert = db.query(AlertEvent).filter(AlertEvent.alert_id == alert_id).first()
    if not alert:
        return None
    alert.status = "resolved"
    alert.assignee = assignee
    if not alert.acknowledged_at:
        alert.acknowledged_at = dt.datetime.utcnow()
    alert.resolved_at = dt.datetime.utcnow()
    db.commit()
    db.refresh(alert)
    return alert
