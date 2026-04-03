"""
HydroAgent FastAPI API layer.
"""
from __future__ import annotations

import datetime
import json
import logging
import uuid
from urllib.parse import urlsplit
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel as PydanticModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from src.database.models import (
    IrrigationLog,
    SessionLocal,
    User,
)
from src.llm.persistence import get_hydro_persistence
from src.services import (
    approve_plan,
    create_plan,
    execute_plan,
    get_plan_by_id,
    get_zone_status,
    list_plans,
    list_zones,
    manual_override_control,
    record_audit_event,
    reject_plan,
    require_permission,
    summarize_system_irrigation,
)

logger = logging.getLogger("hydroagent.api")
router = APIRouter()


def _redact_sensitive_settings(updates: dict) -> dict:
    redacted = dict(updates)
    for key in ("openai_api_key", "embedding_api_key"):
        if key in redacted:
            redacted[key] = "***"
    return redacted


def _should_reload_agent(updates: dict) -> bool:
    reload_keys = {
        "model_name",
        "openai_base_url",
        "openai_api_key",
        "embedding_model_name",
        "embedding_api_key",
        "knowledge_top_k",
    }
    return any(key in updates for key in reload_keys)


def _resolve_models_url(base_url: str | None, model_id: str | None = None) -> str:
    normalized = (base_url or "https://api.openai.com/v1").rstrip("/")
    if normalized.endswith("/models"):
        base_models_url = normalized
    else:
        base_models_url = f"{normalized}/models"
    return f"{base_models_url}/{model_id}" if model_id else base_models_url


class ChatRequest(PydanticModel):
    conversation_id: str
    message: str


class CreateConversationRequest(PydanticModel):
    title: Optional[str] = "新对话"


class IrrigationControlRequest(PydanticModel):
    action: str
    duration_minutes: Optional[int] = 30


class SettingsUpdateRequest(PydanticModel):
    soil_moisture_threshold: Optional[float] = None
    default_duration_minutes: Optional[int] = None
    alarm_threshold: Optional[float] = None
    alarm_enabled: Optional[bool] = None
    collection_interval_minutes: Optional[int] = None
    sensor_ids: Optional[list[str]] = None
    model_name: Optional[str] = None
    embedding_model_name: Optional[str] = None
    openai_base_url: Optional[str] = None
    openai_api_key: Optional[str] = None
    embedding_api_key: Optional[str] = None
    knowledge_top_k: Optional[int] = None
    knowledge_chunk_size: Optional[int] = None
    knowledge_chunk_overlap: Optional[int] = None


class PlanGenerateRequest(PydanticModel):
    zone_id: str
    conversation_id: Optional[str] = None
    trigger: str = "manual"


class PlanDecisionRequest(PydanticModel):
    actor: str = "user"
    comment: Optional[str] = None


class PlanExecuteRequest(PydanticModel):
    actor: str = "user"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/conversations")
async def list_conversations(_: User = Depends(require_permission("chat:view"))):
    persistence = get_hydro_persistence()
    return {"conversations": await persistence.list_conversations(limit=50)}


@router.post("/conversations")
async def create_conversation(req: CreateConversationRequest, _: User = Depends(require_permission("chat:view"))):
    persistence = get_hydro_persistence()
    session_id = str(uuid.uuid4())
    conversation = await persistence.ensure_thread(session_id, title=req.title or "新对话")
    return {"conversation": conversation}


@router.get("/conversations/{session_id}")
async def get_conversation(session_id: str, _: User = Depends(require_permission("chat:view"))):
    persistence = get_hydro_persistence()
    payload = await persistence.get_conversation(session_id)
    if not payload:
        raise HTTPException(status_code=404, detail="会话不存在")
    return payload


@router.delete("/conversations/{session_id}")
async def delete_conversation(session_id: str, _: User = Depends(require_permission("chat:view"))):
    persistence = get_hydro_persistence()
    if not await persistence.thread_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    await persistence.delete_thread(session_id)
    return {"success": True, "message": "会话已删除"}


@router.get("/tool-traces")
async def tool_traces(limit: int = 20, conversation_id: Optional[str] = None, _: User = Depends(require_permission("history:view"))):
    persistence = get_hydro_persistence()
    return {"tool_traces": await persistence.list_tool_traces(limit=limit, conversation_id=conversation_id)}


@router.post("/chat")
async def chat(req: ChatRequest, _: User = Depends(require_permission("chat:view"))):
    persistence = get_hydro_persistence()
    if not await persistence.thread_exists(req.conversation_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    async def generate():
        from src.llm.langchain_agent import get_hydro_agent

        agent = get_hydro_agent()
        if not agent._initialized:
            yield f"data: {json.dumps({'type': 'text', 'content': '正在初始化 AI 引擎...'})}\n\n"
            await agent.initialize()

        assistant_preview_parts: list[str] = []
        trace_id = f"trace_{uuid.uuid4().hex[:12]}"
        step_index = 0

        try:
            async for event in agent.chat_stream(
                [{"role": "user", "content": req.message}],
                conversation_id=req.conversation_id,
            ):
                event_type = event.get("type")
                if event_type == "text":
                    assistant_preview_parts.append(event.get("content", ""))
                trace_payload = _build_trace_event_payload(
                    conversation_id=req.conversation_id,
                    trace_id=trace_id,
                    step_index=step_index,
                    event=event,
                )
                if trace_payload:
                    step_index += 1
                    await persistence.record_trace_event(req.conversation_id, trace_payload)
                decision_payload = _build_decision_event_payload(req.conversation_id, event)
                if decision_payload:
                    await persistence.record_decision_async(decision_payload, thread_id=req.conversation_id)
                plan_event_payload = _build_plan_event_payload(req.conversation_id, event, trace_id=trace_id)
                if plan_event_payload:
                    await persistence.record_plan_event(req.conversation_id, plan_event_payload)
                outbound_event = dict(event)
                if event_type != "done":
                    outbound_event["trace_id"] = trace_id
                yield f"data: {json.dumps(outbound_event, ensure_ascii=False)}\n\n"
                if event_type == "done":
                    break
        except Exception as exc:
            logger.error("[chat SSE] 错误: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': f'出错：{exc}'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        finally:
            await persistence.record_chat_turn(
                req.conversation_id,
                trace_id=trace_id if step_index > 0 else None,
                user_content=req.message,
                assistant_content="".join(part for part in assistant_preview_parts if part).strip(),
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

def _build_trace_event_payload(
    *,
    conversation_id: str,
    trace_id: str,
    step_index: int,
    event: dict,
) -> dict | None:
    event_type = event.get("type")
    if event_type not in {"tool_call", "tool_result", "subagent_handoff", "subagent_result"}:
        return None

    next_index = step_index + 1
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if event_type == "tool_call":
        tool_name = str(event.get("tool") or "未知工具")
        source = _format_agent_source(event)
        return {
            "event_id": f"traceevt_{uuid.uuid4().hex[:12]}",
            "trace_id": trace_id,
            "conversation_id": conversation_id,
            "step_index": next_index,
            "event_type": "tool_call",
            "status": "running",
            "tool_name": tool_name,
            "subagent_name": None,
            "zone_id": event.get("zone_id"),
            "plan_id": event.get("plan_id"),
            "input_preview": _preview_text(event.get("normalized_args") or event.get("args"), limit=180),
            "output_preview": None,
            "duration_ms": None,
            "agent_name": event.get("agent_name"),
            "node_name": event.get("node_name"),
            "layer": "tool",
            "title": "工具调用",
            "detail": f"{source}{tool_name}",
            "created_at": created_at,
        }

    if event_type == "tool_result":
        tool_name = str(event.get("tool") or "未知工具")
        source = _format_agent_source(event)
        return {
            "event_id": f"traceevt_{uuid.uuid4().hex[:12]}",
            "trace_id": trace_id,
            "conversation_id": conversation_id,
            "step_index": next_index,
            "event_type": "tool_result",
            "status": "success",
            "tool_name": tool_name,
            "subagent_name": None,
            "zone_id": event.get("zone_id"),
            "plan_id": event.get("plan_id"),
            "input_preview": _preview_text(event.get("normalized_args") or event.get("args"), limit=180),
            "output_preview": str(event.get("output_preview") or _preview_text(event.get("result"), limit=280) or ""),
            "duration_ms": _coerce_int(event.get("duration_ms")),
            "agent_name": event.get("agent_name"),
            "node_name": event.get("node_name"),
            "layer": "tool",
            "title": "工具返回",
            "detail": f"{source}{event.get('output_preview') or f'{tool_name} 已返回结构化结果'}",
            "created_at": created_at,
        }

    if event_type == "subagent_handoff":
        subagent = str(event.get("subagent") or "subagent")
        return {
            "event_id": f"traceevt_{uuid.uuid4().hex[:12]}",
            "trace_id": trace_id,
            "conversation_id": conversation_id,
            "step_index": next_index,
            "event_type": "subagent_handoff",
            "status": "running",
            "tool_name": None,
            "subagent_name": subagent,
            "zone_id": event.get("zone_id"),
            "plan_id": event.get("plan_id"),
            "input_preview": None,
            "output_preview": str(event.get("task_description") or ""),
            "duration_ms": None,
            "agent_name": event.get("agent_name"),
            "node_name": event.get("node_name"),
            "layer": "subagent",
            "title": f"委派 {subagent}",
            "detail": f"{event.get('zone_id') or '待识别分区'} · {event.get('task_description') or '正在准备任务说明'}",
            "created_at": created_at,
        }

    subagent = str(event.get("subagent") or "subagent")
    return {
        "event_id": f"traceevt_{uuid.uuid4().hex[:12]}",
        "trace_id": trace_id,
        "conversation_id": conversation_id,
        "step_index": next_index,
        "event_type": "subagent_result",
        "status": "success",
        "tool_name": None,
        "subagent_name": subagent,
        "zone_id": event.get("zone_id"),
        "plan_id": event.get("plan_id"),
        "input_preview": None,
        "output_preview": str(event.get("result_preview") or "子代理已完成处理"),
        "duration_ms": None,
        "agent_name": event.get("agent_name"),
        "node_name": event.get("node_name"),
        "layer": "subagent",
        "title": f"{subagent} 已返回",
        "detail": str(event.get("result_preview") or "子代理已完成处理"),
        "created_at": created_at,
    }


def _build_decision_event_payload(conversation_id: str, event: dict) -> dict | None:
    event_type = event.get("type")
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if event_type in {"subagent_handoff", "subagent_result"}:
        subagent = str(event.get("subagent") or "unknown")
        status = "started" if event_type == "subagent_handoff" else "completed"
        reasoning = f"Supervisor {'delegated work to' if status == 'started' else 'received completion from'} {subagent}."
        return {
            "decision_id": f"decision_{uuid.uuid4().hex[:12]}",
            "trigger": "chat",
            "zone_id": event.get("zone_id"),
            "plan_id": event.get("plan_id"),
            "input_context": {
                "conversation_id": conversation_id,
                "event": event_type,
                "task_description": event.get("task_description"),
            },
            "reasoning_chain": reasoning,
            "tools_used": ["task"],
            "decision_result": {
                "subagent": subagent,
                "status": status,
                "result_preview": event.get("result_preview"),
            },
            "reflection_notes": "Captured from official LangGraph streaming updates.",
            "effectiveness_score": None,
            "created_at": created_at,
        }

    if event_type == "approval_requested":
        details = event.get("details") if isinstance(event.get("details"), dict) else {}
        return {
            "decision_id": f"decision_{uuid.uuid4().hex[:12]}",
            "trigger": "chat",
            "zone_id": details.get("zone_id"),
            "plan_id": details.get("plan_id"),
            "input_context": {"conversation_id": conversation_id, "event": event_type},
            "reasoning_chain": "Agent blocked a start-like action because approval is required before execution.",
            "tools_used": [str(event.get("tool") or "control_irrigation")],
            "decision_result": {
                "status": "approval_requested",
                "details": details,
            },
            "reflection_notes": "Approval boundary enforced before irrigation execution.",
            "effectiveness_score": None,
            "created_at": created_at,
        }

    if event_type in {"plan_proposed", "approval_result", "execution_result"}:
        plan = event.get("plan") if isinstance(event.get("plan"), dict) else {}
        event_status = (
            "proposed"
            if event_type == "plan_proposed"
            else str(event.get("decision") or plan.get("execution_status") or event_type)
        )
        return {
            "decision_id": f"decision_{uuid.uuid4().hex[:12]}",
            "trigger": "chat",
            "zone_id": plan.get("zone_id"),
            "plan_id": plan.get("plan_id"),
            "input_context": {"conversation_id": conversation_id, "event": event_type},
            "reasoning_chain": {
                "plan_proposed": "Agent generated a structured irrigation plan after collecting evidence.",
                "approval_result": "Agent recorded an approval decision on an irrigation plan.",
                "execution_result": "Agent recorded an irrigation execution result.",
            }[event_type],
            "tools_used": [
                {
                    "plan_proposed": "create_irrigation_plan",
                    "approval_result": "approve_or_reject_plan",
                    "execution_result": "execute_approved_plan",
                }[event_type]
            ],
            "decision_result": {
                "status": event_status,
                "risk_level": plan.get("risk_level"),
                "proposed_action": plan.get("proposed_action"),
            },
            "reflection_notes": str(plan.get("reasoning_summary") or "Captured from official LangGraph streaming updates."),
            "effectiveness_score": None,
            "created_at": created_at,
        }

    return None


def _build_plan_event_payload(conversation_id: str, event: dict, *, trace_id: str | None = None) -> dict | None:
    event_type = event.get("type")
    if event_type not in {"plan_proposed", "plan_updated", "approval_result", "execution_result"}:
        return None

    plan = event.get("plan") if isinstance(event.get("plan"), dict) else None
    if not plan:
        return None

    plan_id = str(plan.get("plan_id") or "").strip()
    if not plan_id:
        return None

    return {
        "event_id": f"planevt_{uuid.uuid4().hex[:12]}",
        "conversation_id": conversation_id,
        "event_type": event_type,
        "plan_id": plan_id,
        "plan": plan,
        "trace_id": trace_id,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def _preview_text(value, limit: int = 280):
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":")) if isinstance(value, (dict, list)) else str(value)
    except Exception:
        text = str(value)
    if not text:
        return None
    return text if len(text) <= limit else f"{text[:limit]}..."


def _coerce_int(value):
    try:
        return int(value) if value is not None else None
    except Exception:
        return None


def _format_agent_source(event: dict) -> str:
    agent_name = event.get("agent_name")
    if isinstance(agent_name, str) and agent_name and agent_name != "hydro-supervisor":
        return f"{agent_name} · "
    return ""


@router.get("/zones")
async def zones(db: Session = Depends(get_db), _: User = Depends(require_permission("assets:view"))):
    return {"zones": [zone.to_dict() for zone in list_zones(db)]}


@router.get("/zones/{zone_id}/status")
async def zone_status(zone_id: str, db: Session = Depends(get_db), _: User = Depends(require_permission("assets:view"))):
    try:
        return get_zone_status(db, zone_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/plans")
async def plans(limit: int = 20, db: Session = Depends(get_db), _: User = Depends(require_permission("operations:view"))):
    return {"plans": [plan.to_dict() for plan in list_plans(db, limit=limit)]}


@router.post("/plans/generate")
async def generate_plan(
    req: PlanGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("plans:create")),
):
    try:
        plan = create_plan(
            db,
            req.zone_id,
            conversation_id=req.conversation_id,
            trigger=req.trigger,
            requested_by="api",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    record_audit_event(
        db,
        actor=current_user.username,
        event_type="plan.generate",
        object_type="plan",
        object_id=plan.plan_id,
        details={"zone_id": req.zone_id, "trigger": req.trigger},
    )
    await _record_plan_event_if_needed("plan_proposed", plan.to_dict())
    return {"plan": plan.to_dict()}


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: str, db: Session = Depends(get_db), _: User = Depends(require_permission("operations:view"))):
    plan = get_plan_by_id(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    return {"plan": plan.to_dict()}


@router.post("/plans/{plan_id}/approve")
async def approve_plan_endpoint(
    plan_id: str,
    req: PlanDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("plans:approve")),
):
    try:
        plan = approve_plan(db, plan_id, actor=req.actor, comment=req.comment)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_audit_event(
        db,
        actor=current_user.username,
        event_type="plan.approve",
        object_type="plan",
        object_id=plan.plan_id,
        comment=req.comment,
    )
    await _record_plan_event_if_needed("approval_result", plan.to_dict())
    return {"plan": plan.to_dict()}


@router.post("/plans/{plan_id}/reject")
async def reject_plan_endpoint(
    plan_id: str,
    req: PlanDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("plans:approve")),
):
    try:
        plan = reject_plan(db, plan_id, actor=req.actor, comment=req.comment)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_audit_event(
        db,
        actor=current_user.username,
        event_type="plan.reject",
        object_type="plan",
        object_id=plan.plan_id,
        comment=req.comment,
    )
    await _record_plan_event_if_needed("approval_result", plan.to_dict())
    return {"plan": plan.to_dict()}


@router.post("/plans/{plan_id}/execute")
async def execute_plan_endpoint(
    plan_id: str,
    req: PlanExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("plans:execute")),
):
    try:
        plan = execute_plan(db, plan_id, actor=req.actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_audit_event(
        db,
        actor=current_user.username,
        event_type="plan.execute",
        object_type="plan",
        object_id=plan.plan_id,
    )
    await _record_plan_event_if_needed("execution_result", plan.to_dict())
    return {"plan": plan.to_dict()}


async def _record_plan_event_if_needed(event_type: str, plan: dict | None):
    if not isinstance(plan, dict):
        return

    conversation_id = str(plan.get("conversation_id") or "").strip()
    if not conversation_id:
        return

    payload = _build_plan_event_payload(conversation_id, {"type": event_type, "plan": plan})
    if not payload:
        return

    await get_hydro_persistence().record_plan_event(conversation_id, payload)


@router.get("/sensors/current")
async def get_current_sensors(db: Session = Depends(get_db), _: User = Depends(require_permission("dashboard:view"))):
    zones_payload = []
    averages = {"soil_moisture": 0.0, "temperature": 0.0, "light_intensity": 0.0, "rainfall": 0.0}
    zones = list_zones(db)
    for zone in zones:
        status = get_zone_status(db, zone.zone_id)
        average = status["sensor_summary"].get("average", {})
        zones_payload.append({"zone_id": zone.zone_id, "zone_name": zone.name, **average})
        for key in averages:
            averages[key] += float(average.get(key, 0.0) or 0.0)

    divisor = max(len(zones_payload), 1)
    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "sensors": zones_payload,
        "average": {key: round(value / divisor, 2) for key, value in averages.items()},
    }


@router.get("/weather")
async def get_weather(db: Session = Depends(get_db), _: User = Depends(require_permission("dashboard:view"))):
    zones = list_zones(db)
    zone = zones[0]
    status = get_zone_status(db, zone.zone_id)
    weather_summary = status["weather_summary"]
    return {
        "city": weather_summary.get("city", zone.location),
        "live": {
            "weather": weather_summary.get("forecast_days", [{}])[0].get("day_weather", "--"),
            "temperature": weather_summary.get("forecast_days", [{}])[0].get("day_temp", "--"),
            "wind_direction": "--",
            "wind_power": "--",
        },
        "forecast": weather_summary.get("forecast_days", []),
        "note": weather_summary.get("source", "mock"),
    }


@router.get("/irrigation/status")
async def get_irrigation_status(db: Session = Depends(get_db), _: User = Depends(require_permission("dashboard:view"))):
    return summarize_system_irrigation(db)


@router.post("/irrigation/control")
async def control_irrigation(
    req: IrrigationControlRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("plans:execute")),
):
    try:
        result = manual_override_control(db, req.action, duration_minutes=req.duration_minutes or 30)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result["state"] = summarize_system_irrigation(db)
    record_audit_event(
        db,
        actor=current_user.username,
        event_type="irrigation.manual_override",
        object_type="system",
        object_id=req.action,
        details={"duration_minutes": req.duration_minutes},
    )
    return result


@router.get("/irrigation/logs")
async def get_irrigation_logs(limit: int = 20, db: Session = Depends(get_db), _: User = Depends(require_permission("history:view"))):
    logs = db.query(IrrigationLog).order_by(desc(IrrigationLog.created_at)).limit(limit).all()
    return {
        "logs": [
            {
                "id": log.id,
                "event": log.event,
                "zone_id": log.zone_id,
                "actuator_id": log.actuator_id,
                "plan_id": log.plan_id,
                "status": log.status,
                "start_time": log.start_time.isoformat() if log.start_time else None,
                "end_time": log.end_time.isoformat() if log.end_time else None,
                "duration_planned": log.duration_planned_seconds,
                "message": log.message,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
    }


@router.get("/decisions")
async def get_decisions(limit: int = 20, _: User = Depends(require_permission("history:view"))):
    persistence = get_hydro_persistence()
    return {"decisions": await persistence.list_decisions(limit=limit)}


@router.get("/settings")
async def get_settings(_: User = Depends(require_permission("settings:view"))):
    from src.config import config

    return config.get_runtime_settings()


@router.put("/settings")
async def update_settings(
    req: SettingsUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("settings:manage")),
):
    from src.config import config

    updates = req.model_dump(exclude_none=True) if hasattr(req, "model_dump") else req.dict(exclude_none=True)
    settings = config.update_runtime_settings(updates)
    reload_error = None
    reloaded = False
    if _should_reload_agent(updates):
        from src.llm.langchain_agent import get_hydro_agent

        try:
            await get_hydro_agent().reload()
            reloaded = True
        except Exception as exc:
            reload_error = str(exc)
            logger.warning("设置更新后 Agent 热重载失败: %s", exc, exc_info=True)
    audit_details = _redact_sensitive_settings(updates)
    record_audit_event(
        db,
        actor=current_user.username,
        event_type="settings.update",
        object_type="config",
        object_id="runtime",
        details=audit_details,
    )
    return {
        "success": True,
        "settings": settings,
        "agent_reloaded": reloaded,
        "agent_reload_error": reload_error,
    }


@router.get("/settings/openai-models")
async def list_openai_models(
    model_id: Optional[str] = None,
    _: User = Depends(require_permission("settings:view")),
):
    from src.config import config
    import requests

    api_key = config.OPENAI_API_KEY
    if not api_key:
        raise HTTPException(status_code=400, detail="尚未配置 OpenAI API Key。请先在系统设置中保存 key。")

    request_url = _resolve_models_url(config.OPENAI_BASE_URL, model_id=model_id)
    try:
        response = requests.get(
            request_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"请求模型列表失败: {exc}") from exc

    content_type = response.headers.get("content-type", "")
    try:
        payload = response.json() if "application/json" in content_type else {"raw": response.text}
    except ValueError:
        payload = {"raw": response.text}

    if not response.ok:
        raise HTTPException(status_code=response.status_code, detail=payload)

    if model_id:
        item = payload.get("data") if isinstance(payload, dict) else payload
        return {
            "source": request_url,
            "host": urlsplit(request_url).netloc,
            "model": item,
        }

    if isinstance(payload, dict):
        raw_items = payload.get("data") or payload.get("models") or []
    else:
        raw_items = payload if isinstance(payload, list) else []

    models = [
        {
            "id": item.get("id"),
            "owned_by": item.get("owned_by"),
            "created": item.get("created"),
        }
        for item in raw_items
        if isinstance(item, dict) and item.get("id")
    ]
    models.sort(key=lambda item: str(item.get("id")).lower())
    return {
        "source": request_url,
        "host": urlsplit(request_url).netloc,
        "models": models,
    }


@router.get("/status")
async def get_system_status(db: Session = Depends(get_db), _: User = Depends(require_permission("dashboard:view"))):
    from src.llm.langchain_agent import get_hydro_agent

    agent = get_hydro_agent()
    irrigation_status = summarize_system_irrigation(db)
    return {
        "status": "online",
        "timestamp": datetime.datetime.now().isoformat(),
        "agent_initialized": agent._initialized,
        "irrigation_status": irrigation_status["status"],
        "version": "5.0.0",
        "features": [
            "DeepAgents",
            "Zone Plans",
            "Approval Workflow",
            "Streaming SSE",
            "Decision Audit",
            "Knowledge Base",
        ],
    }


@router.get("/health")
async def get_health():
    return {
        "status": "ok",
        "timestamp": datetime.datetime.now().isoformat(),
        "service": "hydroagent-api",
    }
