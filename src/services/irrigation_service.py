"""
Irrigation service layer for zone-aware planning, approval, and execution.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import uuid
from dataclasses import dataclass
from threading import Lock
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.config import config
from src.data.data_collection import DataCollectionModule, sync_mock_moisture
from src.data.data_processing import DataProcessingModule
from src.database.models import (
    Actuator,
    IrrigationLog,
    IrrigationPlan,
    PlanApproval,
    PlanExecutionEvent,
    SensorData,
    SensorDevice,
    Zone,
    ZoneSensorBinding,
)
from src.llm.persistence import get_hydro_persistence
from src.services.decision_learning_service import recommend_plan_decision
from src.services.ml_prediction_service import predict_zone_soil_moisture
from src.services.system_settings_service import (
    get_default_duration_minutes,
    get_default_soil_moisture_threshold,
    get_system_settings_snapshot,
)

logger = logging.getLogger("hydroagent.service")

WORKSPACE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", ".hydro_workspace")
EVIDENCE_CACHE_TTL_SECONDS = 5
OPEN_PLAN_STATUSES = ("pending_approval", "approved", "executing")
RUNNING_PLAN_STATUSES = {"executing"}
FINISHED_EXECUTION_STATUSES = {"running", "stopped", "completed", "executed"}
AUTO_PLAN_DUPLICATE_WINDOW_MINUTES = 60
MIN_MOISTURE_STOP_PROTECTION_SECONDS = 60
_sensor_summary_cache: dict[str, tuple[dt.datetime, dict[str, Any]]] = {}
_weather_summary_cache: dict[str, tuple[dt.datetime, dict[str, Any]]] = {}
_cache_lock = Lock()


@dataclass
class ZoneEvidence:
    zone: Zone
    actuator: Actuator | None
    sensor_summary: dict[str, Any]
    weather_summary: dict[str, Any]
    current_plan: dict[str, Any] | None
    system_settings: dict[str, Any] | None = None
    ml_prediction: dict[str, Any] | None = None
    decision_model: dict[str, Any] | None = None


def _build_suggestion_id(evidence_hash: str | None) -> str:
    suffix = (evidence_hash or uuid.uuid4().hex)[:12]
    return f"suggestion_{suffix}"


def _sync_plan_status_fields(plan: IrrigationPlan) -> None:
    """同步兼容字段，避免旧前端继续依赖 approval/execution 字段时出现脏状态。"""
    status = str(plan.status or "")
    if status == "pending_approval":
        plan.approval_status = "pending"
        plan.execution_status = "not_started"
    elif status == "approved":
        plan.approval_status = "approved"
        plan.execution_status = "not_started"
    elif status == "executing":
        plan.approval_status = "approved"
        plan.execution_status = "running"
    elif status == "completed":
        if plan.approval_status not in {"approved", "rejected"}:
            plan.approval_status = "approved"
        if plan.execution_status not in {"stopped", "completed"}:
            plan.execution_status = "stopped"
    elif status == "rejected":
        plan.approval_status = "rejected"
        if not plan.execution_status:
            plan.execution_status = "not_started"
    elif status in {"cancelled", "superseded"}:
        plan.approval_status = "not_required"
        if not plan.execution_status:
            plan.execution_status = "not_started"


def bootstrap_default_zones(db: Session) -> list[Zone]:
    """Create one default zone per configured sensor when no zones exist."""
    existing = db.query(Zone).order_by(Zone.created_at.asc()).all()
    if existing:
        return existing

    created: list[Zone] = []
    sensor_ids = config.SENSOR_IDS or ["sensor_001"]
    default_threshold = get_default_soil_moisture_threshold(db)
    default_duration = get_default_duration_minutes(db)
    for index, sensor_id in enumerate(sensor_ids, start=1):
        zone = Zone(
            name=f"分区 {index}",
            location="北京",
            crop_type="通用作物",
            soil_moisture_threshold=default_threshold,
            default_duration_minutes=default_duration,
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


def get_open_plan_for_zone(db: Session, zone_id: str) -> IrrigationPlan | None:
    return (
        db.query(IrrigationPlan)
        .filter(IrrigationPlan.zone_id == zone_id, IrrigationPlan.status.in_(OPEN_PLAN_STATUSES))
        .order_by(IrrigationPlan.created_at.desc())
        .first()
    )


def list_plans(db: Session, limit: int = 20) -> list[IrrigationPlan]:
    return db.query(IrrigationPlan).order_by(IrrigationPlan.created_at.desc()).limit(limit).all()


def list_open_plans(db: Session, limit: int = 20) -> list[IrrigationPlan]:
    return (
        db.query(IrrigationPlan)
        .filter(IrrigationPlan.status.in_(OPEN_PLAN_STATUSES))
        .order_by(IrrigationPlan.created_at.desc())
        .limit(limit)
        .all()
    )


def get_zone_status(db: Session, zone_id: str) -> dict[str, Any]:
    zone = get_zone_by_id(db, zone_id)
    if not zone:
        raise ValueError(f"Zone not found: {zone_id}")

    evidence = collect_zone_evidence(db, zone)
    pending_plan = get_open_plan_for_zone(db, zone_id)
    return {
        "zone": zone.to_dict(),
        "sensor_summary": evidence.sensor_summary,
        "weather_summary": evidence.weather_summary,
        "actuator": evidence.actuator.to_dict() if evidence.actuator else None,
        "pending_plan": pending_plan.to_dict() if pending_plan else None,
    }


def list_farm_context(db: Session) -> list[dict[str, Any]]:
    context_items: list[dict[str, Any]] = []
    for zone in list_zones(db):
        if not zone.is_enabled:
            continue
        status = get_zone_status(db, zone.zone_id)
        sensor_average = status["sensor_summary"].get("average", {})
        moisture = float(sensor_average.get("soil_moisture", 0.0) or 0.0)
        threshold = _resolve_zone_threshold(db, zone)
        active_plan = status.get("pending_plan") or {}
        rain_expected = bool(status["weather_summary"].get("rain_expected"))
        actuator_status = (status.get("actuator") or {}).get("status") or "unknown"
        risk_hint = "observe"
        if moisture < max(0.0, threshold - 15):
            risk_hint = "emergency_dry"
        elif rain_expected:
            risk_hint = "rain_risk"
        elif actuator_status == "running":
            risk_hint = "actuator_running"
        elif active_plan:
            risk_hint = str(active_plan.get("status") or "active_plan")
        context_items.append(
            {
                "zone_id": zone.zone_id,
                "zone_name": zone.name,
                "soil_moisture": round(moisture, 2),
                "threshold": round(threshold, 2),
                "rain_expected": rain_expected,
                "actuator_status": actuator_status,
                "active_plan_status": active_plan.get("status"),
                "latest_plan_id": active_plan.get("plan_id"),
                "risk_hint": risk_hint,
            }
        )
    return context_items


def collect_zone_evidence(db: Session, zone: Zone) -> ZoneEvidence:
    sensor_summary = _collect_zone_sensor_summary(db, zone)
    weather_summary = _get_weather_summary(zone.location)
    system_settings = get_system_settings_snapshot(db)
    current_plan = get_open_plan_for_zone(db, zone.zone_id) or (
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
        system_settings=system_settings,
    )


def create_plan(
    db: Session,
    zone_id: str,
    *,
    conversation_id: str | None = None,
    trigger: str = "manual",
    requested_by: str = "user",
) -> IrrigationPlan:
    zone, evidence, plan_payload = _prepare_plan_candidate(db, zone_id)
    if plan_payload["proposed_action"] != "start":
        raise ValueError("Only start proposals can be materialized as formal plans")
    plan = _persist_plan(
        db,
        zone=zone,
        evidence=evidence,
        plan_payload=plan_payload,
        conversation_id=conversation_id,
        trigger=trigger,
        requested_by=requested_by,
    )
    return plan


def generate_plan_result(
    db: Session,
    zone_id: str,
    *,
    conversation_id: str | None = None,
    trigger: str = "manual",
    requested_by: str = "user",
    replace: bool = False,
) -> dict[str, Any]:
    zone, evidence, plan_payload = _prepare_plan_candidate(db, zone_id)
    if plan_payload["proposed_action"] != "start":
        suggestion = _build_suggestion_payload(
            zone=zone,
            evidence=evidence,
            plan_payload=plan_payload,
            conversation_id=conversation_id,
            trigger=trigger,
            requested_by=requested_by,
        )
        _record_suggestion_decision(
            zone=zone,
            conversation_id=conversation_id,
            trigger=trigger,
            requested_by=requested_by,
            suggestion=suggestion,
        )
        return {
            "plan": None,
            "suggestion": suggestion,
            "reused_existing": False,
            "suggestion_only": True,
        }

    open_plan = get_open_plan_for_zone(db, zone_id)
    if open_plan and not replace:
        return {
            "plan": open_plan.to_dict(),
            "suggestion": None,
            "reused_existing": True,
            "suggestion_only": False,
        }
    if open_plan and replace:
        if open_plan.status == "executing":
            raise ValueError("Executing plan cannot be replaced")
        _supersede_plan(open_plan)
        db.commit()

    plan = _persist_plan(
        db,
        zone=zone,
        evidence=evidence,
        plan_payload=plan_payload,
        conversation_id=conversation_id,
        trigger=trigger,
        requested_by=requested_by,
    )
    return {
        "plan": plan.to_dict(),
        "suggestion": None,
        "reused_existing": False,
        "suggestion_only": False,
    }


def _prepare_plan_candidate(db: Session, zone_id: str) -> tuple[Zone, ZoneEvidence, dict[str, Any]]:
    zone = get_zone_by_id(db, zone_id)
    if not zone:
        raise ValueError(f"Zone not found: {zone_id}")

    evidence = collect_zone_evidence(db, zone)
    evidence.ml_prediction = predict_zone_soil_moisture(
        db,
        zone.zone_id,
        current_sensor_summary=evidence.sensor_summary,
        current_weather_summary=evidence.weather_summary,
    )
    evidence.decision_model = recommend_plan_decision(
        db,
        zone_id=zone.zone_id,
        evidence=evidence,
        ml_prediction=evidence.ml_prediction,
    )
    plan_payload = _build_plan_payload(evidence)
    return zone, evidence, plan_payload


def _build_suggestion_payload(
    *,
    zone: Zone,
    evidence: ZoneEvidence,
    plan_payload: dict[str, Any],
    conversation_id: str | None,
    trigger: str,
    requested_by: str,
) -> dict[str, Any]:
    evidence_summary = plan_payload["evidence_summary"]
    evidence_hash = str(evidence_summary.get("evidence_hash") or "")
    return {
        "suggestion_id": _build_suggestion_id(evidence_hash),
        "zone_id": zone.zone_id,
        "zone_name": zone.name,
        "conversation_id": conversation_id,
        "trigger": trigger,
        "requested_by": requested_by,
        "proposed_action": plan_payload["proposed_action"],
        "urgency": plan_payload["urgency"],
        "risk_level": plan_payload["risk_level"],
        "recommended_duration_minutes": plan_payload["recommended_duration_minutes"],
        "reasoning_summary": plan_payload["reasoning_summary"],
        "evidence_summary": evidence_summary,
        "safety_review": plan_payload["safety_review"],
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def _record_suggestion_decision(
    *,
    zone: Zone,
    conversation_id: str | None,
    trigger: str,
    requested_by: str,
    suggestion: dict[str, Any],
) -> None:
    evidence_summary = suggestion.get("evidence_summary") or {}
    current_plan = evidence_summary.get("current_plan") if isinstance(evidence_summary, dict) else None
    get_hydro_persistence().record_decision_sync(
        {
            "decision_id": f"decision_{uuid.uuid4().hex[:12]}",
            "trigger": trigger,
            "zone_id": zone.zone_id,
            "plan_id": None,
            "trace_id": None,
            "source": "service_layer",
            "skill_ids": [],
            "input_context": {
                "conversation_id": conversation_id,
                "requested_by": requested_by,
                "zone_id": zone.zone_id,
            },
            "reasoning_chain": suggestion.get("reasoning_summary"),
            "tools_used": ["query_sensor_data", "query_weather", "predict_soil_moisture", "recommend_plan_decision"],
            "decision_result": {
                "kind": "suggestion",
                "suggestion_id": suggestion.get("suggestion_id"),
                "proposed_action": suggestion.get("proposed_action"),
                "risk_level": suggestion.get("risk_level"),
                "recommended_duration_minutes": suggestion.get("recommended_duration_minutes"),
            },
            "evidence_refs": {
                "zone_id": zone.zone_id,
                "conversation_id": conversation_id,
                "suggestion_id": suggestion.get("suggestion_id"),
                "evidence_hash": evidence_summary.get("evidence_hash") if isinstance(evidence_summary, dict) else None,
                "current_plan_id": current_plan.get("plan_id") if isinstance(current_plan, dict) else None,
            },
            "reflection_notes": "Suggestion recorded without creating a formal irrigation plan.",
            "effectiveness_score": None,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
        thread_id=conversation_id,
    )


def _supersede_plan(plan: IrrigationPlan) -> None:
    plan.status = "superseded"
    plan.approval_status = "not_required"
    if not plan.execution_status:
        plan.execution_status = "not_started"


def _persist_plan(
    db: Session,
    *,
    zone: Zone,
    evidence: ZoneEvidence,
    plan_payload: dict[str, Any],
    conversation_id: str | None,
    trigger: str,
    requested_by: str,
) -> IrrigationPlan:
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
    _sync_plan_status_fields(plan)
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
            "trace_id": None,
            "source": "service_layer",
            "skill_ids": [],
            "input_context": {
                "conversation_id": conversation_id,
                "requested_by": requested_by,
                "zone_id": zone.zone_id,
            },
            "reasoning_chain": plan.reasoning_summary,
            "tools_used": ["query_sensor_data", "query_weather", "predict_soil_moisture", "recommend_plan_decision"],
            "decision_result": {
                "proposed_action": plan.proposed_action,
                "risk_level": plan.risk_level,
                "recommended_duration_minutes": plan.recommended_duration_minutes,
            },
            "evidence_refs": {
                "zone_id": zone.zone_id,
                "conversation_id": conversation_id,
                "evidence_hash": (plan.evidence_summary or {}).get("evidence_hash"),
                "current_plan_id": (evidence.current_plan or {}).get("plan_id"),
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
    if plan.status == "approved":
        return plan
    if plan.status != "pending_approval":
        raise ValueError("Only pending approval plans can be approved")

    approval = PlanApproval(plan_id=plan.plan_id, decision="approved", actor=actor, comment=comment)
    plan.status = "approved"
    _sync_plan_status_fields(plan)
    plan.approved_at = dt.datetime.utcnow()
    db.add(approval)
    db.commit()
    db.refresh(plan)
    return plan


def reject_plan(db: Session, plan_id: str, actor: str = "user", comment: str | None = None) -> IrrigationPlan:
    plan = get_plan_by_id(db, plan_id)
    if not plan:
        raise ValueError(f"Plan not found: {plan_id}")
    if plan.status == "rejected":
        return plan
    if plan.status != "pending_approval":
        raise ValueError("Only pending approval plans can be rejected")

    approval = PlanApproval(plan_id=plan.plan_id, decision="rejected", actor=actor, comment=comment)
    plan.status = "rejected"
    _sync_plan_status_fields(plan)
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
    if plan.status == "executing":
        return plan
    if plan.approval_status != "approved" or plan.status != "approved":
        raise ValueError("Plan must be approved before execution")

    actuator = plan.actuator
    if not actuator or not actuator.is_enabled:
        raise ValueError("Actuator unavailable")

    now = dt.datetime.utcnow()
    actuator.status = "running"
    actuator.last_command_at = now
    plan.status = "executing"
    _sync_plan_status_fields(plan)
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


def _complete_running_log(db: Session, actuator: Actuator, *, now: dt.datetime, actor: str, reason: str) -> str | None:
    running_log = (
        db.query(IrrigationLog)
        .filter(
            IrrigationLog.actuator_id == actuator.actuator_id,
            IrrigationLog.event == "start",
            IrrigationLog.status == "running",
        )
        .order_by(IrrigationLog.start_time.desc())
        .first()
    )
    plan_id = running_log.plan_id if running_log else None
    if running_log:
        running_log.end_time = now
        if running_log.start_time:
            running_log.duration_actual_seconds = max(0, int((now - running_log.start_time).total_seconds()))
        running_log.status = "completed"
        running_log.message = f"{running_log.message or ''} Stopped by {actor}: {reason}".strip()
    return plan_id


def _stop_actuator(db: Session, actuator: Actuator, *, actor: str, reason: str, now: dt.datetime | None = None) -> dict[str, Any]:
    stopped_at = now or dt.datetime.utcnow()
    plan_id = _complete_running_log(db, actuator, now=stopped_at, actor=actor, reason=reason)
    if not plan_id:
        latest_plan = (
            db.query(IrrigationPlan)
            .filter(IrrigationPlan.actuator_id == actuator.actuator_id, IrrigationPlan.execution_status.in_(FINISHED_EXECUTION_STATUSES))
            .order_by(IrrigationPlan.executed_at.desc())
            .first()
        )
        plan_id = latest_plan.plan_id if latest_plan else None

    actuator.status = "idle"
    actuator.last_command_at = stopped_at
    db.add(
        IrrigationLog(
            event="stop",
            zone_id=actuator.zone_id,
            actuator_id=actuator.actuator_id,
            plan_id=plan_id,
            end_time=stopped_at,
            status="completed",
            message=f"Stopped by {actor}: {reason}",
        )
    )
    if plan_id:
        plan = get_plan_by_id(db, plan_id)
        if plan:
            execution_result = dict(plan.execution_result) if isinstance(plan.execution_result, dict) else {}
            execution_result.update(
                {
                    "stopped_at": stopped_at.isoformat(),
                    "stopped_by": actor,
                    "stop_reason": reason,
                }
            )
            plan.status = "completed"
            _sync_plan_status_fields(plan)
            plan.execution_result = execution_result
        db.add(
            PlanExecutionEvent(
                plan_id=plan_id,
                event="stop",
                status="success",
                details={"actor": actor, "actuator_id": actuator.actuator_id, "reason": reason},
            )
        )
    return {
        "zone_id": actuator.zone_id,
        "actuator_id": actuator.actuator_id,
        "reason": reason,
        "stopped_at": stopped_at.isoformat(),
    }


def stop_zone_irrigation(db: Session, zone_id: str, actor: str = "manual-override") -> dict[str, Any]:
    zone = get_zone_by_id(db, zone_id)
    if not zone:
        raise ValueError(f"Zone not found: {zone_id}")
    actuator = next((item for item in zone.actuators if item.status == "running"), None)
    if not actuator:
        return {"success": False, "message": "该分区当前未在灌溉"}

    stopped = _stop_actuator(db, actuator, actor=actor, reason="manual_stop")
    db.commit()
    return {
        "success": True,
        "message": f"{zone.name} 已停止灌溉",
        "zone_id": zone.zone_id,
        "actuator_id": actuator.actuator_id,
        "stopped": stopped,
    }


def stop_running_irrigation(db: Session, actor: str = "manual-override") -> dict[str, Any]:
    running_actuators = db.query(Actuator).filter(Actuator.status == "running").all()
    if not running_actuators:
        return {"success": False, "message": "当前没有运行中的灌溉执行器", "stopped": []}

    stopped = [_stop_actuator(db, actuator, actor=actor, reason="manual_stop") for actuator in running_actuators]
    db.commit()
    return {
        "success": True,
        "message": f"已停止 {len(stopped)} 个运行中的灌溉执行器",
        "stopped": stopped,
    }


def manual_override_control(
    db: Session,
    action: str,
    duration_minutes: int = 30,
    *,
    zone_id: str | None = None,
) -> dict[str, Any]:
    if action not in {"start", "stop"}:
        raise ValueError(f"Unsupported irrigation action: {action}")
    if action == "stop":
        return stop_zone_irrigation(db, zone_id, actor="manual-override") if zone_id else stop_running_irrigation(db, actor="manual-override")

    zone = get_zone_by_id(db, zone_id) if zone_id else next((item for item in list_zones(db) if item.is_enabled), None)
    if not zone:
        raise ValueError("No enabled zone available")
    if not zone.is_enabled:
        raise ValueError(f"Zone disabled: {zone.zone_id}")

    open_plan = get_open_plan_for_zone(db, zone.zone_id)
    if open_plan:
        raise ValueError(f"{zone.name} 当前已有打开计划 {open_plan.plan_id}")

    evidence = collect_zone_evidence(db, zone)
    manual_payload = _build_plan_payload(evidence)
    manual_payload["proposed_action"] = "start"
    manual_payload["status"] = "pending_approval"
    manual_payload["approval_status"] = "pending"
    manual_payload["requires_approval"] = True
    manual_payload["recommended_duration_minutes"] = duration_minutes or manual_payload["recommended_duration_minutes"] or _resolve_zone_duration(db, zone)
    manual_payload["reasoning_summary"] = (
        f"{manual_payload['reasoning_summary']} 手动 override 要求立即创建 start 计划，并在同一事务中批准执行。"
    ).strip()

    plan = _persist_plan(
        db,
        zone=zone,
        evidence=evidence,
        plan_payload=manual_payload,
        conversation_id=None,
        trigger="manual_override",
        requested_by="manual-override",
    )
    approve_plan(db, plan.plan_id, actor="manual-override", comment="Dashboard manual override")
    plan = execute_plan(db, plan.plan_id, actor="manual-override")
    return {
        "success": True,
        "message": f"{zone.name} 已启动灌溉，计划 {plan.recommended_duration_minutes} 分钟",
        "plan": plan.to_dict(),
    }


def reconcile_running_irrigation(db: Session, actor: str = "system-watchdog") -> list[dict[str, Any]]:
    stopped: list[dict[str, Any]] = []
    now = dt.datetime.utcnow()
    running_actuators = db.query(Actuator).filter(Actuator.status == "running").all()
    for actuator in running_actuators:
        reason = _running_stop_reason(db, actuator, now=now)
        if reason:
            stopped.append(_stop_actuator(db, actuator, actor=actor, reason=reason, now=now))

    if stopped:
        db.commit()
    return stopped


def create_auto_plan_if_needed(db: Session, zone_id: str) -> dict[str, Any]:
    zone, evidence, plan_payload = _prepare_plan_candidate(db, zone_id)
    if plan_payload["proposed_action"] != "start":
        suggestion = _build_suggestion_payload(
            zone=zone,
            evidence=evidence,
            plan_payload=plan_payload,
            conversation_id=None,
            trigger="auto",
            requested_by="scheduler",
        )
        _record_suggestion_decision(
            zone=zone,
            conversation_id=None,
            trigger="auto",
            requested_by="scheduler",
            suggestion=suggestion,
        )
        return {
            "status": "suggestion_only",
            "zone_id": zone.zone_id,
            "suggestion_id": suggestion["suggestion_id"],
            "message": f"{zone.name} 当前建议 {suggestion['proposed_action']}，已记录为审计建议",
        }

    skip_reason = _should_skip_auto_plan(db, zone.zone_id, plan_payload)
    if skip_reason:
        return {
            "status": skip_reason["status"],
            "zone_id": zone.zone_id,
            "plan_id": skip_reason.get("plan_id"),
            "evidence_hash": plan_payload["evidence_summary"].get("evidence_hash"),
            "message": skip_reason["message"],
        }

    plan = _persist_plan(
        db,
        zone=zone,
        evidence=evidence,
        plan_payload=plan_payload,
        conversation_id=None,
        trigger="auto",
        requested_by="scheduler",
    )
    return {
        "status": "generated",
        "zone_id": zone.zone_id,
        "plan_id": plan.plan_id,
        "evidence_hash": (plan.evidence_summary or {}).get("evidence_hash"),
        "message": f"{zone.name} 已生成自动计划",
    }


def _should_skip_auto_plan(db: Session, zone_id: str, plan_payload: dict[str, Any]) -> dict[str, Any] | None:
    active_plan = get_open_plan_for_zone(db, zone_id)
    if active_plan:
        return {
            "status": "skipped_active_plan",
            "plan_id": active_plan.plan_id,
            "message": f"分区 {zone_id} 已存在活跃计划 {active_plan.plan_id}",
        }

    latest_plan = (
        db.query(IrrigationPlan)
        .filter(IrrigationPlan.zone_id == zone_id)
        .order_by(IrrigationPlan.created_at.desc())
        .first()
    )
    if not latest_plan:
        return None

    latest_evidence = latest_plan.evidence_summary or {}
    latest_hash = latest_evidence.get("evidence_hash")
    current_hash = plan_payload["evidence_summary"].get("evidence_hash")
    created_at = latest_plan.created_at or dt.datetime.utcnow()
    within_window = (dt.datetime.utcnow() - created_at).total_seconds() <= AUTO_PLAN_DUPLICATE_WINDOW_MINUTES * 60

    if current_hash and latest_hash == current_hash and within_window:
        return {
            "status": "skipped_duplicate_evidence",
            "plan_id": latest_plan.plan_id,
            "message": f"分区 {zone_id} 最近计划证据未变化，跳过重复建计划",
        }

    return None


def _get_running_plan_for_actuator(db: Session, actuator: Actuator) -> IrrigationPlan | None:
    return (
        db.query(IrrigationPlan)
        .filter(
            IrrigationPlan.actuator_id == actuator.actuator_id,
            or_(
                IrrigationPlan.status.in_(RUNNING_PLAN_STATUSES),
                IrrigationPlan.execution_status == "running",
            ),
        )
        .order_by(IrrigationPlan.executed_at.desc())
        .first()
    )


def _get_running_plan_for_zone(db: Session, zone_id: str) -> IrrigationPlan | None:
    return (
        db.query(IrrigationPlan)
        .filter(
            IrrigationPlan.zone_id == zone_id,
            or_(
                IrrigationPlan.status.in_(RUNNING_PLAN_STATUSES),
                IrrigationPlan.execution_status == "running",
            ),
        )
        .order_by(IrrigationPlan.executed_at.desc())
        .first()
    )


def _elapsed_execution_seconds(plan: IrrigationPlan, *, now: dt.datetime) -> float:
    if not plan.executed_at:
        return 0.0
    return max(0.0, (now - plan.executed_at).total_seconds())


def _moisture_stop_protection_seconds(plan: IrrigationPlan) -> float:
    duration_seconds = max(0, int(plan.recommended_duration_minutes or 0)) * 60
    if duration_seconds <= 0:
        return float(MIN_MOISTURE_STOP_PROTECTION_SECONDS)
    return float(min(MIN_MOISTURE_STOP_PROTECTION_SECONDS, duration_seconds))


def _running_stop_reason(db: Session, actuator: Actuator, *, now: dt.datetime) -> str | None:
    latest_plan = _get_running_plan_for_actuator(db, actuator)
    elapsed_seconds = _elapsed_execution_seconds(latest_plan, now=now) if latest_plan else 0.0
    if latest_plan and latest_plan.recommended_duration_minutes:
        if elapsed_seconds >= latest_plan.recommended_duration_minutes * 60:
            return "planned_duration_elapsed"

    zone = actuator.zone
    if not zone:
        return None
    if latest_plan and elapsed_seconds < _moisture_stop_protection_seconds(latest_plan):
        return None

    evidence = collect_zone_evidence(db, zone)
    average = evidence.sensor_summary.get("average", {})
    moisture = float(average.get("soil_moisture", 0.0) or 0.0)
    threshold = _resolve_zone_threshold(db, zone)
    if evidence.sensor_summary.get("status") == "ok" and moisture >= threshold:
        return "soil_moisture_threshold_reached"
    return None


def summarize_system_irrigation(db: Session) -> dict[str, Any]:
    stopped = reconcile_running_irrigation(db)
    running = db.query(Actuator).filter(Actuator.status == "running").all()
    if not running:
        return {"status": "stopped", "start_time": None, "duration_minutes": 0, "auto_stopped": stopped}

    latest_plan = (
        db.query(IrrigationPlan)
        .filter(
            or_(
                IrrigationPlan.status.in_(RUNNING_PLAN_STATUSES),
                IrrigationPlan.execution_status.in_(FINISHED_EXECUTION_STATUSES),
            )
        )
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
        "auto_stopped": stopped,
    }


def _collect_zone_sensor_summary(db: Session, zone: Zone) -> dict[str, Any]:
    cached = _read_cached_payload(_sensor_summary_cache, zone.zone_id)
    if cached:
        return dict(cached)

    sensor_ids = [binding.sensor_id for binding in zone.sensor_bindings if binding.is_enabled]
    if not sensor_ids:
        sensor_ids = [
            device.sensor_id
            for device in db.query(SensorDevice).filter(SensorDevice.is_enabled.is_(True)).order_by(SensorDevice.created_at.asc()).limit(1)
        ]
    if not sensor_ids:
        sensor_ids = config.SENSOR_IDS[:1] or ["sensor_001"]
    readings = []
    raw_readings = []
    for sensor_id in sensor_ids:
        try:
            data = DataCollectionModule([sensor_id]).get_data()
            _stabilize_running_mock_reading(db, zone, sensor_id, data.get("data", {}))
            raw_reading = dict(data)
            raw_reading.setdefault("sensor_id", sensor_id)
            readings.append({"sensor_id": sensor_id, **data["data"]})
            raw_readings.append(raw_reading)
            binding = next((item for item in zone.sensor_bindings if item.sensor_id == sensor_id), None)
            if binding and binding.sensor_device:
                binding.sensor_device.status = "online"
                binding.sensor_device.last_seen_at = dt.datetime.utcnow()
        except Exception as exc:
            logger.warning("Sensor collection failed for %s: %s", sensor_id, exc)

    if not readings:
        payload = {
            "sensor_ids": sensor_ids,
            "readings": [],
            "average": {},
            "status": "missing",
        }
        _write_cached_payload(_sensor_summary_cache, zone.zone_id, payload)
        return payload

    metrics = ["soil_moisture", "temperature", "light_intensity", "rainfall"]
    average = {
        key: round(sum(float(reading.get(key, 0.0)) for reading in readings) / len(readings), 2)
        for key in metrics
    }
    payload = {
        "sensor_ids": sensor_ids,
        "readings": readings,
        "average": average,
        "status": "ok",
        "timestamp": dt.datetime.utcnow().isoformat(),
    }
    _store_sensor_history(db, raw_readings)
    _write_cached_payload(_sensor_summary_cache, zone.zone_id, payload)
    return payload


def _stabilize_running_mock_reading(db: Session, zone: Zone, sensor_id: str, reading: dict[str, Any]) -> None:
    """灌溉期间湿度线性上升，并同步回模拟状态，确保灌溉停止后从当前值继续线性下降"""
    running_plan = _get_running_plan_for_zone(db, zone.zone_id)
    if not running_plan:
        return

    current = float(reading.get("soil_moisture", 0) or 0)
    if current <= 0:
        return

    threshold = _resolve_zone_threshold(db, zone)
    elapsed = _elapsed_execution_seconds(running_plan, now=dt.datetime.utcnow())
    protection = max(1.0, _moisture_stop_protection_seconds(running_plan))
    progress = min(1.0, elapsed / protection)

    target = threshold + 3.0
    new_moisture = current + (target - current) * progress
    new_moisture = min(100.0, new_moisture)

    reading["soil_moisture"] = round(new_moisture, 2)
    sync_mock_moisture(new_moisture)


def _store_sensor_history(db: Session, raw_readings: list[dict[str, Any]]) -> None:
    if not raw_readings:
        return
    try:
        for item in raw_readings:
            data = item.get("data", {})
            timestamp = item.get("timestamp")
            db.add(
                SensorData(
                    sensor_id=item.get("sensor_id"),
                    timestamp=dt.datetime.fromisoformat(timestamp) if timestamp else dt.datetime.utcnow(),
                    soil_moisture=data.get("soil_moisture"),
                    temperature=data.get("temperature"),
                    light_intensity=data.get("light_intensity"),
                    rainfall=data.get("rainfall"),
                    raw_data=item,
                )
            )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Sensor history persistence failed: %s", exc)


def _get_weather_summary(location: str) -> dict[str, Any]:
    cached = _read_cached_payload(_weather_summary_cache, location)
    if cached:
        return dict(cached)

    default_summary = {
        "city": location,
        "forecast_days": [],
        "rain_expected": False,
        "source": "mock",
    }
    try:
        payload = DataProcessingModule().get_weather_by_city_name(location)
        casts = payload.get("forecast", [])
        if casts:
            forecast_days = [
                {
                    "date": item.get("date"),
                    "day_weather": item.get("dayweather"),
                    "day_temp": item.get("daytemp"),
                    "night_temp": item.get("nighttemp"),
                }
                for item in casts[:4]
            ]
            payload = {
                "city": payload.get("city", location),
                "forecast_days": forecast_days,
                "rain_expected": any("雨" in (item.get("day_weather") or "") for item in forecast_days[:2]),
                "source": "open-meteo",
            }
            _write_cached_payload(_weather_summary_cache, location, payload)
            return payload
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
    _write_cached_payload(_weather_summary_cache, location, default_summary)
    return default_summary


def _build_plan_payload(evidence: ZoneEvidence) -> dict[str, Any]:
    zone = evidence.zone
    sensor_average = evidence.sensor_summary.get("average", {})
    moisture = float(sensor_average.get("soil_moisture", 0.0) or 0.0)
    threshold = _resolve_zone_threshold_for_evidence(evidence)
    rainfall_expected = bool(evidence.weather_summary.get("rain_expected"))
    actuator = evidence.actuator
    ml_prediction = evidence.ml_prediction or {}
    decision_model = evidence.decision_model or {}
    predicted_moisture = _coerce_prediction_moisture(ml_prediction)
    prediction_usable = bool(ml_prediction) and not ml_prediction.get("fallback_used") and predicted_moisture is not None
    decision_moisture = min(moisture, predicted_moisture) if prediction_usable else moisture

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
    if ml_prediction.get("fallback_used"):
        risk_factors.append("ML 预测历史样本不足，仅作为低置信度证据")
    elif prediction_usable and predicted_moisture < threshold:
        risk_factors.append(f"ML 预测 24 小时湿度 {predicted_moisture:.2f}% 低于阈值")
    if decision_model.get("fallback_used"):
        risk_factors.append("决策模型历史计划样本不足，仅作为低置信度证据")
    elif decision_model.get("recommended_action") in {"hold", "defer"}:
        risk_factors.append(f"决策模型建议 {decision_model.get('recommended_action')}")

    deficit = max(0.0, threshold - decision_moisture)
    recommended_duration = max(_resolve_zone_duration_for_evidence(evidence), int(deficit * 1.5) + 10) if deficit > 0 else 0
    emergency_band = max(0.0, threshold - 15)

    proposed_action = "hold"
    if decision_moisture < threshold and not blockers and (not rainfall_expected or moisture < emergency_band):
        proposed_action = "start"

    if decision_moisture < emergency_band:
        urgency = "emergency"
    elif decision_moisture < threshold:
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

    model_duration = _coerce_decision_model_duration(decision_model)
    model_confidence = _coerce_decision_model_confidence(decision_model)
    if proposed_action == "start" and model_duration is not None and model_confidence >= 0.6:
        recommended_duration = max(1, model_duration)

    reasoning = [
        f"{zone.name} 当前平均土壤湿度 {moisture:.2f}%，阈值 {threshold:.2f}%。",
        "建议启动灌溉。" if proposed_action == "start" else "当前建议暂缓灌溉。",
    ]
    if prediction_usable:
        reasoning.append(f"ML 预测 24 小时湿度 {predicted_moisture:.2f}%，已纳入推荐时长计算。")
    elif ml_prediction.get("fallback_used"):
        reasoning.append("ML 预测使用低置信度兜底结果，不单独改变启动判断。")
    if decision_model and not decision_model.get("fallback_used"):
        reasoning.append(
            f"决策模型建议 {decision_model.get('recommended_action')}，"
            f"建议时长 {decision_model.get('recommended_duration_minutes')} 分钟，"
            f"置信度 {model_confidence:.2f}。"
        )
    elif decision_model.get("fallback_used"):
        reasoning.append("决策模型使用低置信度兜底结果，不改变安全规则裁决。")
    if rainfall_expected:
        reasoning.append("天气预报提示近期可能降雨。")
    if blockers:
        reasoning.append(f"阻断因素：{'、'.join(blockers)}。")
    elif risk_factors:
        reasoning.append(f"风险因素：{'、'.join(risk_factors)}。")

    evidence_summary = {
        "zone": zone.to_dict(),
        "sensor_summary": evidence.sensor_summary,
        "weather_summary": evidence.weather_summary,
        "system_settings": evidence.system_settings,
        "ml_prediction": ml_prediction,
        "decision_model": decision_model,
        "current_plan": evidence.current_plan,
    }
    evidence_summary["evidence_hash"] = _build_evidence_hash(
        zone=zone,
        evidence_summary=evidence_summary,
        proposed_action=proposed_action,
        recommended_duration_minutes=recommended_duration,
        risk_level=risk_level,
    )

    return {
        "status": status,
        "approval_status": approval_status,
        "proposed_action": proposed_action,
        "urgency": urgency,
        "risk_level": risk_level,
        "requires_approval": requires_approval,
        "recommended_duration_minutes": recommended_duration,
        "reasoning_summary": " ".join(reasoning),
        "evidence_summary": evidence_summary,
        "safety_review": {
            "blockers": blockers,
            "risk_factors": risk_factors,
            "can_execute": proposed_action == "start" and not blockers and (not rainfall_expected or moisture < emergency_band),
            "approval_required": requires_approval,
        },
    }


def _coerce_prediction_moisture(ml_prediction: dict[str, Any]) -> float | None:
    try:
        value = ml_prediction.get("predicted_soil_moisture_24h")
        if value is None:
            return None
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return None


def _coerce_decision_model_duration(decision_model: dict[str, Any]) -> int | None:
    try:
        if decision_model.get("fallback_used"):
            return None
        value = decision_model.get("recommended_duration_minutes")
        if value is None:
            return None
        return max(0, min(120, int(round(float(value)))))
    except (TypeError, ValueError):
        return None


def _coerce_decision_model_confidence(decision_model: dict[str, Any]) -> float:
    try:
        return max(0.0, min(1.0, float(decision_model.get("confidence", 0.0) or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _build_evidence_hash(
    *,
    zone: Zone,
    evidence_summary: dict[str, Any],
    proposed_action: str,
    recommended_duration_minutes: int,
    risk_level: str,
) -> str:
    sensor_average = (evidence_summary.get("sensor_summary") or {}).get("average") or {}
    weather_summary = evidence_summary.get("weather_summary") or {}
    prediction = evidence_summary.get("ml_prediction") or {}
    decision_model = evidence_summary.get("decision_model") or {}
    canonical_payload = {
        "zone_id": zone.zone_id,
        "soil_moisture": round(float(sensor_average.get("soil_moisture", 0.0) or 0.0), 2),
        "threshold": round(_resolve_zone_threshold_for_evidence_obj(zone, evidence_summary), 2),
        "rain_expected": bool(weather_summary.get("rain_expected")),
        "actuator_status": evidence_summary.get("zone", {}).get("actuators", [{}])[0].get("status") if isinstance(evidence_summary.get("zone"), dict) else None,
        "predicted_soil_moisture_24h": prediction.get("predicted_soil_moisture_24h"),
        "prediction_fallback": bool(prediction.get("fallback_used")),
        "decision_action": decision_model.get("recommended_action"),
        "decision_duration": decision_model.get("recommended_duration_minutes"),
        "decision_fallback": bool(decision_model.get("fallback_used")),
        "proposed_action": proposed_action,
        "recommended_duration_minutes": recommended_duration_minutes,
        "risk_level": risk_level,
    }
    digest = hashlib.sha256(json.dumps(canonical_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return digest[:16]


def _resolve_zone_threshold(db: Session, zone: Zone) -> float:
    return float(zone.soil_moisture_threshold or get_default_soil_moisture_threshold(db) or 40.0)


def _resolve_zone_duration(db: Session, zone: Zone) -> int:
    return int(zone.default_duration_minutes or get_default_duration_minutes(db) or 30)


def _resolve_zone_threshold_for_evidence(evidence: ZoneEvidence) -> float:
    snapshot = evidence.system_settings if isinstance(evidence.system_settings, dict) else {}
    fallback = (snapshot.get("default_soil_moisture_threshold") or 40.0)
    return float(evidence.zone.soil_moisture_threshold or fallback)


def _resolve_zone_duration_for_evidence(evidence: ZoneEvidence) -> int:
    snapshot = evidence.system_settings if isinstance(evidence.system_settings, dict) else {}
    fallback = snapshot.get("default_duration_minutes") or 30
    return int(evidence.zone.default_duration_minutes or fallback)


def _resolve_zone_threshold_for_evidence_obj(zone: Zone, evidence_summary: dict[str, Any]) -> float:
    settings = evidence_summary.get("system_settings") if isinstance(evidence_summary, dict) else {}
    fallback = (settings or {}).get("default_soil_moisture_threshold") or 40.0
    return float(zone.soil_moisture_threshold or fallback)


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


def _read_cached_payload(cache: dict[str, tuple[dt.datetime, dict[str, Any]]], key: str) -> dict[str, Any] | None:
    with _cache_lock:
        cached = cache.get(key)
    if not cached:
        return None
    cached_at, payload = cached
    if (dt.datetime.utcnow() - cached_at).total_seconds() > EVIDENCE_CACHE_TTL_SECONDS:
        with _cache_lock:
            cache.pop(key, None)
        return None
    return payload


def _write_cached_payload(cache: dict[str, tuple[dt.datetime, dict[str, Any]]], key: str, payload: dict[str, Any]):
    with _cache_lock:
        cache[key] = (dt.datetime.utcnow(), payload)
