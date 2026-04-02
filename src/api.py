"""
HydroAgent FastAPI API layer.
"""
from __future__ import annotations

import datetime
import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel as PydanticModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from src.database.models import (
    AgentDecisionLog,
    ChatMessage,
    ConversationSession,
    IrrigationLog,
    SessionLocal,
)
from src.services import (
    approve_plan,
    create_plan,
    execute_plan,
    get_plan_by_id,
    get_zone_status,
    list_plans,
    list_zones,
    manual_override_control,
    reject_plan,
    summarize_system_irrigation,
)
from src.services.tool_trace_service import (
    attach_tool_traces_to_messages,
    create_trace_id,
    list_tool_trace_payloads,
    persist_tool_execution_event,
    save_assistant_message,
)

logger = logging.getLogger("hydroagent.api")
router = APIRouter()


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
async def list_conversations(db: Session = Depends(get_db)):
    sessions = db.query(ConversationSession).order_by(ConversationSession.updated_at.desc()).limit(50).all()
    return {"conversations": [session.to_dict() for session in sessions]}


@router.post("/conversations")
async def create_conversation(req: CreateConversationRequest, db: Session = Depends(get_db)):
    session = ConversationSession(session_id=str(uuid.uuid4()), title=req.title or "新对话")
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"conversation": session.to_dict()}


@router.get("/conversations/{session_id}")
async def get_conversation(session_id: str, db: Session = Depends(get_db)):
    session = db.query(ConversationSession).filter(ConversationSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = db.query(ChatMessage).filter(ChatMessage.conversation_id == session_id).order_by(ChatMessage.created_at).all()
    return {"conversation": session.to_dict(), "messages": attach_tool_traces_to_messages(db, messages)}


@router.delete("/conversations/{session_id}")
async def delete_conversation(session_id: str, db: Session = Depends(get_db)):
    session = db.query(ConversationSession).filter(ConversationSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.delete(session)
    db.commit()
    return {"success": True, "message": "会话已删除"}


@router.get("/tool-traces")
async def tool_traces(limit: int = 20, conversation_id: Optional[str] = None, db: Session = Depends(get_db)):
    return {"tool_traces": list_tool_trace_payloads(db, limit=limit, conversation_id=conversation_id)}


@router.post("/chat")
async def chat(req: ChatRequest, db: Session = Depends(get_db)):
    session = db.query(ConversationSession).filter(ConversationSession.session_id == req.conversation_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    history = db.query(ChatMessage).filter(ChatMessage.conversation_id == req.conversation_id).order_by(ChatMessage.created_at).all()
    messages = [{"role": message.role, "content": message.content or ""} for message in history if message.role in ("user", "assistant")]
    messages.append({"role": "user", "content": req.message})

    db.add(ChatMessage(conversation_id=req.conversation_id, role="user", content=req.message))
    if session.message_count == 0:
        session.title = req.message[:40] + ("..." if len(req.message) > 40 else "")
    session.message_count = (session.message_count or 0) + 1
    session.updated_at = datetime.datetime.utcnow()
    db.commit()

    async def generate():
        from src.llm.langchain_agent import get_hydro_agent

        agent = get_hydro_agent()
        if not agent._initialized:
            yield f"data: {json.dumps({'type': 'text', 'content': '正在初始化 AI 引擎...'})}\n\n"
            await agent.initialize()

        full_response_parts: list[str] = []
        tool_calls_used: list[str] = []
        trace_id = create_trace_id()
        step_index = 0

        try:
            async for event in agent.chat_stream(messages, conversation_id=req.conversation_id):
                event_type = event.get("type")
                if event_type == "text":
                    full_response_parts.append(event.get("content", ""))
                elif event_type == "tool_call":
                    tool_calls_used.append(event.get("tool", ""))
                elif event_type in {
                    "plan_proposed",
                    "plan_updated",
                    "approval_requested",
                    "approval_result",
                    "execution_result",
                    "subagent_handoff",
                    "subagent_result",
                }:
                    full_response_parts.append(_event_to_summary_text(event))
                step_index = _persist_tool_trace_event(
                    db,
                    conversation_id=req.conversation_id,
                    trace_id=trace_id,
                    step_index=step_index,
                    event=event,
                )
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
            full_response = "\n".join(part for part in full_response_parts if part).strip()
            if full_response:
                save_assistant_message(
                    db,
                    conversation_id=req.conversation_id,
                    content=full_response,
                    tools_used=tool_calls_used,
                    trace_id=trace_id,
                )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

def _event_to_summary_text(event: dict) -> str:
    event_type = event.get("type")
    if event_type in {"plan_proposed", "plan_updated", "approval_result", "execution_result"}:
        plan = event.get("plan", {})
        if not isinstance(plan, dict):
            return ""
        if event_type == "plan_proposed":
            return (
                f"已生成计划 {plan.get('plan_id')}，分区 {plan.get('zone_name') or plan.get('zone_id')}，"
                f"动作 {plan.get('proposed_action')}，风险 {plan.get('risk_level')}。"
            )
        if event_type == "plan_updated":
            return f"计划 {plan.get('plan_id')} 已更新，当前状态 {plan.get('status')}。"
        if event_type == "approval_result":
            return f"计划 {plan.get('plan_id')} 审批结果：{event.get('decision')}。"
        if event_type == "execution_result":
            return f"计划 {plan.get('plan_id')} 已执行，执行状态 {plan.get('execution_status')}。"
    if event_type == "approval_requested":
        details = event.get("details", {})
        if isinstance(details, dict):
            return f"执行前需要审批：分区 {details.get('zone_id')}，原因：{'、'.join(details.get('reasons', [])) or 'start 操作需要审批'}。"
    if event_type == "subagent_handoff":
        return f"已委派给子代理 {event.get('subagent')}，目标分区 {event.get('zone_id') or '待识别'}。"
    if event_type == "subagent_result":
        return f"子代理 {event.get('subagent')} 已完成，结果摘要：{event.get('result_preview') or '无'}。"
    return ""


def _persist_tool_trace_event(
    db: Session,
    *,
    conversation_id: str,
    trace_id: str,
    step_index: int,
    event: dict,
) -> int:
    event_type = event.get("type")
    if event_type not in {"tool_call", "tool_result", "subagent_handoff", "subagent_result"}:
        return step_index

    next_index = step_index + 1
    if event_type == "tool_call":
        persist_tool_execution_event(
            db,
            trace_id=trace_id,
            conversation_id=conversation_id,
            step_index=next_index,
            event_type="tool_start",
            status="running",
            run_id=event.get("run_id"),
            tool_name=event.get("tool"),
            zone_id=event.get("zone_id"),
            plan_id=event.get("plan_id"),
            input_args=_coerce_event_object(event.get("args")),
            normalized_args=_coerce_normalized_args(event),
        )
        return next_index

    if event_type == "tool_result":
        result = event.get("result")
        output_payload, payload_truncated = _coerce_output_payload(result)
        persist_tool_execution_event(
            db,
            trace_id=trace_id,
            conversation_id=conversation_id,
            step_index=next_index,
            event_type="tool_end",
            status="success",
            run_id=event.get("run_id"),
            tool_name=event.get("tool"),
            zone_id=event.get("zone_id"),
            plan_id=event.get("plan_id"),
            input_args=_coerce_event_object(event.get("args")),
            normalized_args=_coerce_normalized_args(event),
            output_payload=output_payload,
            output_preview=str(event.get("output_preview") or _preview_text(result, limit=280) or event.get("tool") or ""),
            duration_ms=_coerce_int(event.get("duration_ms")),
            payload_truncated=payload_truncated,
        )
        return next_index

    if event_type == "subagent_handoff":
        persist_tool_execution_event(
            db,
            trace_id=trace_id,
            conversation_id=conversation_id,
            step_index=next_index,
            event_type="subagent_handoff",
            status="running",
            run_id=event.get("run_id"),
            subagent_name=event.get("subagent"),
            zone_id=event.get("zone_id"),
            plan_id=event.get("plan_id"),
            output_preview=f"{event.get('zone_id') or '待识别分区'} · {event.get('task_description') or '正在准备任务说明'}",
        )
        return next_index

    persist_tool_execution_event(
        db,
        trace_id=trace_id,
        conversation_id=conversation_id,
        step_index=next_index,
        event_type="subagent_result",
        status="success",
        run_id=event.get("run_id"),
        subagent_name=event.get("subagent"),
        zone_id=event.get("zone_id"),
        plan_id=event.get("plan_id"),
        output_preview=str(event.get("result_preview") or "子代理已完成处理"),
    )
    return next_index


def _coerce_event_object(value):
    return value if isinstance(value, dict) else None


def _coerce_normalized_args(event: dict):
    normalized = event.get("normalized_args")
    if not isinstance(normalized, dict):
        return None
    if normalized == event.get("args"):
        return None
    return normalized


def _coerce_output_payload(result):
    if isinstance(result, (dict, list)):
        return result, False
    text = str(result or "")
    return None, len(text) > 800


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


@router.get("/zones")
async def zones(db: Session = Depends(get_db)):
    return {"zones": [zone.to_dict() for zone in list_zones(db)]}


@router.get("/zones/{zone_id}/status")
async def zone_status(zone_id: str, db: Session = Depends(get_db)):
    try:
        return get_zone_status(db, zone_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/plans")
async def plans(limit: int = 20, db: Session = Depends(get_db)):
    return {"plans": [plan.to_dict() for plan in list_plans(db, limit=limit)]}


@router.post("/plans/generate")
async def generate_plan(req: PlanGenerateRequest, db: Session = Depends(get_db)):
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
    return {"plan": plan.to_dict()}


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: str, db: Session = Depends(get_db)):
    plan = get_plan_by_id(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    return {"plan": plan.to_dict()}


@router.post("/plans/{plan_id}/approve")
async def approve_plan_endpoint(plan_id: str, req: PlanDecisionRequest, db: Session = Depends(get_db)):
    try:
        plan = approve_plan(db, plan_id, actor=req.actor, comment=req.comment)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"plan": plan.to_dict()}


@router.post("/plans/{plan_id}/reject")
async def reject_plan_endpoint(plan_id: str, req: PlanDecisionRequest, db: Session = Depends(get_db)):
    try:
        plan = reject_plan(db, plan_id, actor=req.actor, comment=req.comment)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"plan": plan.to_dict()}


@router.post("/plans/{plan_id}/execute")
async def execute_plan_endpoint(plan_id: str, req: PlanExecuteRequest, db: Session = Depends(get_db)):
    try:
        plan = execute_plan(db, plan_id, actor=req.actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"plan": plan.to_dict()}


@router.get("/sensors/current")
async def get_current_sensors(db: Session = Depends(get_db)):
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
async def get_weather(db: Session = Depends(get_db)):
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
async def get_irrigation_status(db: Session = Depends(get_db)):
    return summarize_system_irrigation(db)


@router.post("/irrigation/control")
async def control_irrigation(req: IrrigationControlRequest, db: Session = Depends(get_db)):
    try:
        result = manual_override_control(db, req.action, duration_minutes=req.duration_minutes or 30)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result["state"] = summarize_system_irrigation(db)
    return result


@router.get("/irrigation/logs")
async def get_irrigation_logs(limit: int = 20, db: Session = Depends(get_db)):
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
async def get_decisions(limit: int = 20, db: Session = Depends(get_db)):
    logs = db.query(AgentDecisionLog).order_by(AgentDecisionLog.created_at.desc()).limit(limit).all()
    return {"decisions": [log.to_dict() for log in logs]}


@router.get("/settings")
async def get_settings():
    from src.config import config

    return config.get_runtime_settings()


@router.put("/settings")
async def update_settings(req: SettingsUpdateRequest):
    from src.config import config

    updates = req.dict(exclude_none=True)
    settings = config.update_runtime_settings(updates)
    return {"success": True, "settings": settings}


@router.get("/status")
async def get_system_status(db: Session = Depends(get_db)):
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
        ],
    }


@router.get("/health")
async def get_health():
    return {
        "status": "ok",
        "timestamp": datetime.datetime.now().isoformat(),
        "service": "hydroagent-api",
    }
