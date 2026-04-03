"""
Irrigation service layer for zone-aware planning, approval, and execution.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any

import requests
from sqlalchemy.orm import Session

from src.config import config
from src.data.data_collection import DataCollectionModule
from src.database.models import (
    Actuator,
    IrrigationLog,
    IrrigationPlan,
    PlanApproval,
    PlanExecutionEvent,
    SensorDevice,
    Zone,
    ZoneSensorBinding,
)
from src.llm.persistence import get_hydro_persistence

logger = logging.getLogger("hydroagent.service")

WORKSPACE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", ".hydro_workspace")


@dataclass
class ZoneEvidence:
    zone: Zone
    actuator: Actuator | None
    sensor_summary: dict[str, Any]
    weather_summary: dict[str, Any]
    current_plan: dict[str, Any] | None


def bootstrap_default_zones(db: Session) -> list[Zone]:
    """Create one default zone per configured sensor when no zones exist."""
    existing = db.query(Zone).order_by(Zone.created_at.asc()).all()
    if existing:
        return existing

    created: list[Zone] = []
    sensor_ids = config.SENSOR_IDS or ["sensor_001"]
    for index, sensor_id in enumerate(sensor_ids, start=1):
        zone = Zone(
            name=f"分区 {index}",
            location="北京",
            crop_type="通用作物",
            soil_moisture_threshold=config.IRRIGATION_STRATEGY.get("soil_moisture_threshold", 40.0),
            default_duration_minutes=config.IRRIGATION_STRATEGY.get("default_duration_minutes", 30),
            notes=f"默认分区，绑定传感器 {sensor_id}",
        )
        db.add(zone)
        db.flush()

        device = SensorDevice(
            sensor_id=sensor_id,
            name=f"分区 {index} 传感器",
            location=zone.location,
            status="online",
            is_enabled=True,
            last_seen_at=dt.datetime.utcnow(),
        )
        db.add(device)
        db.flush()

        binding = ZoneSensorBinding(zone_id=zone.zone_id, sensor_id=sensor_id, role="primary")
        actuator = Actuator(
            zone_id=zone.zone_id,
            name=f"{zone.name} 阀门",
            actuator_type="valve",
            status="idle",
            capabilities={"supports_start": True, "supports_stop": True, "max_duration_minutes": 90},
            health_status="healthy",
            serial_number=f"SN-{zone.zone_id[-6:]}",
            firmware_version="1.0.0",
            last_seen_at=dt.datetime.utcnow(),
        )
        binding.sensor_device_id = device.sensor_device_id
        db.add(binding)
        db.add(actuator)
        created.append(zone)

    db.commit()
    for zone in created:
        db.refresh(zone)
    return created


def list_zones(db: Session) -> list[Zone]:
    bootstrap_default_zones(db)
    return db.query(Zone).order_by(Zone.created_at.asc()).all()


def get_zone_by_id(db: Session, zone_id: str) -> Zone | None:
    bootstrap_default_zones(db)
    return db.query(Zone).filter(Zone.zone_id == zone_id).first()


def get_plan_by_id(db: Session, plan_id: str) -> IrrigationPlan | None:
    return db.query(IrrigationPlan).filter(IrrigationPlan.plan_id == plan_id).first()


def list_plans(db: Session, limit: int = 20) -> list[IrrigationPlan]:
    return db.query(IrrigationPlan).order_by(IrrigationPlan.created_at.desc()).limit(limit).all()


def get_zone_status(db: Session, zone_id: str) -> dict[str, Any]:
    zone = get_zone_by_id(db, zone_id)
    if not zone:
        raise ValueError(f"Zone not found: {zone_id}")

    evidence = collect_zone_evidence(db, zone)
    pending_plan = (
        db.query(IrrigationPlan)
        .filter(IrrigationPlan.zone_id == zone_id, IrrigationPlan.status.in_(["pending_approval", "approved", "executed"]))
        .order_by(IrrigationPlan.created_at.desc())
        .first()
    )
    return {
        "zone": zone.to_dict(),
        "sensor_summary": evidence.sensor_summary,
        "weather_summary": evidence.weather_summary,
        "actuator": evidence.actuator.to_dict() if evidence.actuator else None,
        "pending_plan": pending_plan.to_dict() if pending_plan else None,
    }


def collect_zone_evidence(db: Session, zone: Zone) -> ZoneEvidence:
    sensor_summary = _collect_zone_sensor_summary(zone)
    weather_summary = _get_weather_summary(zone.location)
    current_plan = (
        db.query(IrrigationPlan)
        .filter(IrrigationPlan.zone_id == zone.zone_id)
        .order_by(IrrigationPlan.created_at.desc())
        .first()
    )
    actuator = next((item for item in zone.actuators if item.is_enabled), None)
    return ZoneEvidence(
        zone=zone,
        actuator=actuator,
        sensor_summary=sensor_summary,
        weather_summary=weather_summary,
        current_plan=current_plan.to_dict() if current_plan else None,
    )


def create_plan(
    db: Session,
    zone_id: str,
    *,
    conversation_id: str | None = None,
    trigger: str = "manual",
    requested_by: str = "user",
) -> IrrigationPlan:
    zone = get_zone_by_id(db, zone_id)
    if not zone:
        raise ValueError(f"Zone not found: {zone_id}")

    evidence = collect_zone_evidence(db, zone)
    plan_payload = _build_plan_payload(evidence)

    plan = IrrigationPlan(
        zone_id=zone.zone_id,
        actuator_id=evidence.actuator.actuator_id if evidence.actuator else None,
        conversation_id=conversation_id,
        trigger=trigger,
        status=plan_payload["status"],
        approval_status=plan_payload["approval_status"],
        execution_status="not_started",
        proposed_action=plan_payload["proposed_action"],
        urgency=plan_payload["urgency"],
        risk_level=plan_payload["risk_level"],
        recommended_duration_minutes=plan_payload["recommended_duration_minutes"],
        requires_approval=plan_payload["requires_approval"],
        reasoning_summary=plan_payload["reasoning_summary"],
        evidence_summary=plan_payload["evidence_summary"],
        safety_review=plan_payload["safety_review"],
        requested_by=requested_by,
    )
    db.add(plan)
    db.flush()

    workspace_path = _write_workspace(
        plan.plan_id,
        evidence=plan_payload["evidence_summary"],
        candidate_plan=plan.to_dict(),
        safety_review=plan_payload["safety_review"],
    )
    plan.workspace_path = workspace_path

    db.commit()
    db.refresh(plan)
    get_hydro_persistence().record_decision_sync(
        {
            "decision_id": f"decision_{uuid.uuid4().hex[:12]}",
            "trigger": trigger,
            "zone_id": zone.zone_id,
            "plan_id": plan.plan_id,
            "input_context": {
                "conversation_id": conversation_id,
                "requested_by": requested_by,
                "zone_id": zone.zone_id,
            },
            "reasoning_chain": plan.reasoning_summary,
            "tools_used": ["query_sensor_data", "query_weather", "recommend_irrigation_plan"],
            "decision_result": {
                "proposed_action": plan.proposed_action,
                "risk_level": plan.risk_level,
                "recommended_duration_minutes": plan.recommended_duration_minutes,
            },
            "reflection_notes": "Plan generated by service layer.",
            "effectiveness_score": None,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
        thread_id=conversation_id,
    )
    return plan


def approve_plan(db: Session, plan_id: str, actor: str = "user", comment: str | None = None) -> IrrigationPlan:
    plan = get_plan_by_id(db, plan_id)
    if not plan:
        raise ValueError(f"Plan not found: {plan_id}")

    approval = PlanApproval(plan_id=plan.plan_id, decision="approved", actor=actor, comment=comment)
    plan.approval_status = "approved"
    plan.status = "approved"
    plan.approved_at = dt.datetime.utcnow()
    db.add(approval)
    db.commit()
    db.refresh(plan)
    return plan


def reject_plan(db: Session, plan_id: str, actor: str = "user", comment: str | None = None) -> IrrigationPlan:
    plan = get_plan_by_id(db, plan_id)
    if not plan:
        raise ValueError(f"Plan not found: {plan_id}")

    approval = PlanApproval(plan_id=plan.plan_id, decision="rejected", actor=actor, comment=comment)
    plan.approval_status = "rejected"
    plan.status = "rejected"
    plan.rejected_at = dt.datetime.utcnow()
    db.add(approval)
    db.commit()
    db.refresh(plan)
    return plan


def execute_plan(db: Session, plan_id: str, actor: str = "system") -> IrrigationPlan:
    plan = get_plan_by_id(db, plan_id)
    if not plan:
        raise ValueError(f"Plan not found: {plan_id}")
    if plan.proposed_action != "start":
        raise ValueError("Only start plans can be executed")
    if plan.approval_status != "approved":
        raise ValueError("Plan must be approved before execution")

    actuator = plan.actuator
    if not actuator or not actuator.is_enabled:
        raise ValueError("Actuator unavailable")

    now = dt.datetime.utcnow()
    actuator.status = "running"
    actuator.last_command_at = now
    plan.status = "executed"
    plan.execution_status = "executed"
    plan.executed_at = now
    plan.execution_result = {
        "executed_by": actor,
        "executed_at": now.isoformat(),
        "message": f"已执行 {plan.zone.name if plan.zone else plan.zone_id} 灌溉计划",
    }

    db.add(
        PlanExecutionEvent(
            plan_id=plan.plan_id,
            event="start",
            status="success",
            details={
                "actor": actor,
                "actuator_id": actuator.actuator_id,
                "duration_minutes": plan.recommended_duration_minutes,
            },
        )
    )
    db.add(
        IrrigationLog(
            event="start",
            zone_id=plan.zone_id,
            actuator_id=plan.actuator_id,
            plan_id=plan.plan_id,
            start_time=now,
            duration_planned_seconds=plan.recommended_duration_minutes * 60,
            status="running",
            message=f"Plan {plan.plan_id} executed by {actor}",
        )
    )
    _write_workspace(plan.plan_id, execution_receipt=plan.execution_result)
    db.commit()
    db.refresh(plan)
    return plan


def stop_zone_irrigation(db: Session, zone_id: str, actor: str = "manual-override") -> dict[str, Any]:
    zone = get_zone_by_id(db, zone_id)
    if not zone:
        raise ValueError(f"Zone not found: {zone_id}")
    actuator = next((item for item in zone.actuators if item.status == "running"), None)
    if not actuator:
        return {"success": False, "message": "该分区当前未在灌溉"}

    now = dt.datetime.utcnow()
    actuator.status = "idle"
    actuator.last_command_at = now
    db.add(
        IrrigationLog(
            event="stop",
            zone_id=zone.zone_id,
            actuator_id=actuator.actuator_id,
            end_time=now,
            status="completed",
            message=f"Stopped by {actor}",
        )
    )
    db.commit()
    return {
        "success": True,
        "message": f"{zone.name} 已停止灌溉",
        "zone_id": zone.zone_id,
        "actuator_id": actuator.actuator_id,
    }


def manual_override_control(db: Session, action: str, duration_minutes: int = 30) -> dict[str, Any]:
    zone = next((item for item in list_zones(db) if item.is_enabled), None)
    if not zone:
        raise ValueError("No enabled zone available")
    if action == "stop":
        return stop_zone_irrigation(db, zone.zone_id, actor="manual-override")

    plan = create_plan(db, zone.zone_id, trigger="manual_override", requested_by="manual-override")
    plan.recommended_duration_minutes = duration_minutes or plan.recommended_duration_minutes
    plan.proposed_action = "start"
    plan.requires_approval = True
    plan.approval_status = "pending"
    plan.status = "pending_approval"
    db.commit()
    approve_plan(db, plan.plan_id, actor="manual-override", comment="Dashboard manual override")
    plan = execute_plan(db, plan.plan_id, actor="manual-override")
    return {
        "success": True,
        "message": f"{zone.name} 已启动灌溉，计划 {plan.recommended_duration_minutes} 分钟",
        "plan": plan.to_dict(),
    }


def summarize_system_irrigation(db: Session) -> dict[str, Any]:
    running = db.query(Actuator).filter(Actuator.status == "running").all()
    if not running:
        return {"status": "stopped", "start_time": None, "duration_minutes": 0}

    latest_plan = (
        db.query(IrrigationPlan)
        .filter(IrrigationPlan.execution_status == "executed")
        .order_by(IrrigationPlan.executed_at.desc())
        .first()
    )
    start_time = latest_plan.executed_at if latest_plan and latest_plan.executed_at else None
    duration = latest_plan.recommended_duration_minutes if latest_plan else 0
    elapsed = 0.0
    remaining = float(duration)
    if start_time:
        elapsed = max(0.0, (dt.datetime.utcnow() - start_time).total_seconds() / 60)
        remaining = max(0.0, duration - elapsed)
    return {
        "status": "running",
        "start_time": start_time.isoformat() if start_time else None,
        "duration_minutes": duration,
        "elapsed_minutes": round(elapsed, 1),
        "remaining_minutes": round(remaining, 1),
        "zones": [item.zone_id for item in running],
    }


def _collect_zone_sensor_summary(zone: Zone) -> dict[str, Any]:
    sensor_ids = [binding.sensor_id for binding in zone.sensor_bindings if binding.is_enabled] or config.SENSOR_IDS[:1]
    readings = []
    for sensor_id in sensor_ids:
        try:
            data = DataCollectionModule([sensor_id]).get_data()
            readings.append({"sensor_id": sensor_id, **data["data"]})
            binding = next((item for item in zone.sensor_bindings if item.sensor_id == sensor_id), None)
            if binding and binding.sensor_device:
                binding.sensor_device.status = "online"
                binding.sensor_device.last_seen_at = dt.datetime.utcnow()
        except Exception as exc:
            logger.warning("Sensor collection failed for %s: %s", sensor_id, exc)

    if not readings:
        return {
            "sensor_ids": sensor_ids,
            "readings": [],
            "average": {},
            "status": "missing",
        }

    metrics = ["soil_moisture", "temperature", "light_intensity", "rainfall"]
    average = {
        key: round(sum(float(reading.get(key, 0.0)) for reading in readings) / len(readings), 2)
        for key in metrics
    }
    return {
        "sensor_ids": sensor_ids,
        "readings": readings,
        "average": average,
        "status": "ok",
        "timestamp": dt.datetime.utcnow().isoformat(),
    }


def _get_weather_summary(location: str) -> dict[str, Any]:
    default_summary = {
        "city": location,
        "forecast_days": [],
        "rain_expected": False,
        "source": "mock",
    }
    try:
        params = {
            "city": location,
            "key": config.WEATHER_API_KEY,
            "extensions": "all",
            "output": "JSON",
        }
        response = requests.get(config.API_SERVICE_URL, params=params, timeout=5)
        payload = response.json()
        forecasts = payload.get("forecasts", [])
        if payload.get("status") == "1" and forecasts:
            casts = forecasts[0].get("casts", [])
            forecast_days = [
                {
                    "date": item.get("date"),
                    "day_weather": item.get("dayweather"),
                    "day_temp": item.get("daytemp"),
                    "night_temp": item.get("nighttemp"),
                }
                for item in casts[:4]
            ]
            return {
                "city": location,
                "forecast_days": forecast_days,
                "rain_expected": any("雨" in (item.get("day_weather") or "") for item in forecast_days[:2]),
                "source": "api",
            }
    except Exception as exc:
        logger.warning("Weather lookup failed for %s: %s", location, exc)

    now = dt.date.today()
    forecast_days = [
        {
            "date": (now + dt.timedelta(days=index)).isoformat(),
            "day_weather": weather,
            "day_temp": str(24 + index),
            "night_temp": str(16 + index),
        }
        for index, weather in enumerate(["多云", "晴", "小雨", "多云"])
    ]
    default_summary["forecast_days"] = forecast_days
    default_summary["rain_expected"] = any("雨" in (item.get("day_weather") or "") for item in forecast_days[:2])
    return default_summary


def _build_plan_payload(evidence: ZoneEvidence) -> dict[str, Any]:
    zone = evidence.zone
    sensor_average = evidence.sensor_summary.get("average", {})
    moisture = float(sensor_average.get("soil_moisture", 0.0) or 0.0)
    threshold = float(zone.soil_moisture_threshold or 40.0)
    rainfall_expected = bool(evidence.weather_summary.get("rain_expected"))
    actuator = evidence.actuator

    blockers: list[str] = []
    risk_factors: list[str] = []
    if evidence.sensor_summary.get("status") != "ok":
        blockers.append("传感器数据缺失")
    if rainfall_expected:
        risk_factors.append("未来 48 小时存在降雨信号")
    if not actuator:
        blockers.append("分区缺少可用执行器")
    elif not actuator.is_enabled:
        blockers.append("执行器已禁用")
    elif actuator.status == "running":
        risk_factors.append("执行器当前已在运行")

    deficit = max(0.0, threshold - moisture)
    recommended_duration = max(zone.default_duration_minutes or 30, int(deficit * 1.5) + 10) if deficit > 0 else 0
    emergency_band = max(0.0, threshold - 15)

    proposed_action = "hold"
    if moisture < threshold and not blockers and (not rainfall_expected or moisture < emergency_band):
        proposed_action = "start"

    if moisture < emergency_band:
        urgency = "emergency"
    elif moisture < threshold:
        urgency = "high"
    else:
        urgency = "normal"

    risk_level = "low"
    if blockers:
        risk_level = "high"
    elif rainfall_expected or (actuator and actuator.status == "running"):
        risk_level = "medium"

    requires_approval = proposed_action == "start"
    if proposed_action == "start":
        status = "pending_approval"
        approval_status = "pending"
    else:
        status = "ready"
        approval_status = "not_required"

    reasoning = [
        f"{zone.name} 当前平均土壤湿度 {moisture:.2f}%，阈值 {threshold:.2f}%。",
        "建议启动灌溉。" if proposed_action == "start" else "当前建议暂缓灌溉。",
    ]
    if rainfall_expected:
        reasoning.append("天气预报提示近期可能降雨。")
    if blockers:
        reasoning.append(f"阻断因素：{'、'.join(blockers)}。")
    elif risk_factors:
        reasoning.append(f"风险因素：{'、'.join(risk_factors)}。")

    return {
        "status": status,
        "approval_status": approval_status,
        "proposed_action": proposed_action,
        "urgency": urgency,
        "risk_level": risk_level,
        "requires_approval": requires_approval,
        "recommended_duration_minutes": recommended_duration,
        "reasoning_summary": " ".join(reasoning),
        "evidence_summary": {
            "zone": zone.to_dict(),
            "sensor_summary": evidence.sensor_summary,
            "weather_summary": evidence.weather_summary,
            "current_plan": evidence.current_plan,
        },
        "safety_review": {
            "blockers": blockers,
            "risk_factors": risk_factors,
            "can_execute": proposed_action == "start" and not blockers and (not rainfall_expected or moisture < emergency_band),
            "approval_required": requires_approval,
        },
    }


def _write_workspace(plan_id: str, **payloads: Any) -> str:
    workspace_dir = os.path.abspath(os.path.join(WORKSPACE_ROOT, plan_id))
    os.makedirs(workspace_dir, exist_ok=True)
    for name, payload in payloads.items():
        if payload is None:
            continue
        file_path = os.path.join(workspace_dir, f"{name}.json")
        with open(file_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
    return workspace_dir
