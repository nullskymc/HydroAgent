"""Persistence and aggregation helpers for tool-chain replay."""
from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from src.database.models import ChatMessage, ConversationSession, ToolExecutionEvent

_OUTPUT_PREVIEW_LIMIT = 280
_INPUT_PREVIEW_LIMIT = 180


def create_trace_id() -> str:
    return f"trace_{uuid.uuid4().hex[:12]}"


def persist_tool_execution_event(
    db: Session,
    *,
    trace_id: str,
    conversation_id: str,
    step_index: int,
    event_type: str,
    status: str,
    run_id: str | None = None,
    tool_name: str | None = None,
    subagent_name: str | None = None,
    zone_id: str | None = None,
    plan_id: str | None = None,
    input_args: dict[str, Any] | None = None,
    normalized_args: dict[str, Any] | None = None,
    output_payload: Any = None,
    output_preview: str | None = None,
    error_message: str | None = None,
    duration_ms: int | None = None,
    payload_truncated: bool = False,
) -> ToolExecutionEvent:
    event = ToolExecutionEvent(
        trace_id=trace_id,
        conversation_id=conversation_id,
        run_id=run_id,
        step_index=step_index,
        event_type=event_type,
        status=status,
        tool_name=tool_name,
        subagent_name=subagent_name,
        zone_id=zone_id,
        plan_id=plan_id,
        input_args=input_args,
        normalized_args=normalized_args,
        output_payload=output_payload,
        output_preview=output_preview,
        error_message=error_message,
        duration_ms=duration_ms,
        payload_truncated=payload_truncated,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def save_assistant_message(
    db: Session,
    *,
    conversation_id: str,
    content: str,
    tools_used: list[str],
    trace_id: str | None,
) -> ChatMessage:
    message = ChatMessage(
        conversation_id=conversation_id,
        role="assistant",
        content=content,
        trace_id=trace_id,
        tool_calls=tools_used if tools_used else None,
    )
    db.add(message)
    conversation = db.query(ConversationSession).filter(ConversationSession.session_id == conversation_id).first()
    if conversation:
        conversation.message_count = (conversation.message_count or 0) + 1
        conversation.updated_at = dt.datetime.utcnow()
    db.commit()
    db.refresh(message)
    return message


def build_trace_step_payload(event: ToolExecutionEvent) -> dict[str, Any]:
    input_source = event.normalized_args or event.input_args
    return {
        "step_index": event.step_index,
        "event_type": event.event_type,
        "status": event.status,
        "tool_name": event.tool_name,
        "subagent_name": event.subagent_name,
        "title": _build_step_title(event),
        "detail": _build_step_detail(event),
        "input_preview": _preview_json(input_source, _INPUT_PREVIEW_LIMIT),
        "output_preview": event.output_preview,
        "zone_id": event.zone_id,
        "plan_id": event.plan_id,
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "duration_ms": event.duration_ms,
    }


def build_tool_trace_payload(events: list[ToolExecutionEvent], *, conversation_title: str | None = None) -> dict[str, Any]:
    steps = [build_trace_step_payload(event) for event in events]
    latest_event = events[-1] if events else None
    statuses = {event.status for event in events}
    status = "error" if "error" in statuses else latest_event.status if latest_event and latest_event.status == "running" else "completed"
    started_at = events[0].created_at.isoformat() if events and events[0].created_at else None
    ended_at = events[-1].created_at.isoformat() if events and events[-1].created_at and status != "running" else None
    total_duration = sum(event.duration_ms or 0 for event in events if event.duration_ms)
    latest = steps[-1] if steps else None

    return {
        "trace_id": events[0].trace_id if events else None,
        "conversation_id": events[0].conversation_id if events else None,
        "conversation_title": conversation_title,
        "status": status,
        "steps": steps,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": total_duration or None,
        "tool_count": sum(1 for event in events if event.event_type in {"tool_start", "tool_end"}),
        "latest_step": latest,
        "zone_id": _last_non_empty([event.zone_id for event in events]),
        "plan_id": _last_non_empty([event.plan_id for event in events]),
    }


def attach_tool_traces_to_messages(db: Session, messages: list[ChatMessage]) -> list[dict[str, Any]]:
    trace_ids = [message.trace_id for message in messages if message.trace_id]
    trace_map = get_tool_trace_map(db, trace_ids)
    payload: list[dict[str, Any]] = []
    for message in messages:
        item = message.to_dict()
        if message.trace_id:
            item["tool_trace"] = trace_map.get(message.trace_id)
        payload.append(item)
    return payload


def get_tool_trace_map(db: Session, trace_ids: list[str | None]) -> dict[str, dict[str, Any]]:
    valid_trace_ids = [trace_id for trace_id in trace_ids if trace_id]
    if not valid_trace_ids:
        return {}

    events = (
        db.query(ToolExecutionEvent)
        .filter(ToolExecutionEvent.trace_id.in_(valid_trace_ids))
        .order_by(ToolExecutionEvent.trace_id.asc(), ToolExecutionEvent.step_index.asc(), ToolExecutionEvent.created_at.asc())
        .all()
    )
    conversations = (
        db.query(ConversationSession)
        .filter(ConversationSession.session_id.in_({event.conversation_id for event in events if event.conversation_id}))
        .all()
    )
    conversation_map = {conversation.session_id: conversation.title for conversation in conversations}

    grouped: dict[str, list[ToolExecutionEvent]] = {}
    for event in events:
        grouped.setdefault(event.trace_id, []).append(event)

    return {
        trace_id: build_tool_trace_payload(items, conversation_title=conversation_map.get(items[0].conversation_id))
        for trace_id, items in grouped.items()
    }


def list_tool_trace_payloads(db: Session, *, limit: int = 20, conversation_id: str | None = None) -> list[dict[str, Any]]:
    query = db.query(ToolExecutionEvent)
    if conversation_id:
        query = query.filter(ToolExecutionEvent.conversation_id == conversation_id)
    events = query.order_by(ToolExecutionEvent.created_at.desc()).all()

    grouped: dict[str, list[ToolExecutionEvent]] = {}
    ordered_trace_ids: list[str] = []
    for event in events:
        if event.trace_id not in grouped:
            if len(ordered_trace_ids) >= limit:
                continue
            ordered_trace_ids.append(event.trace_id)
            grouped[event.trace_id] = []
        grouped[event.trace_id].append(event)

    if not grouped:
        return []

    conversation_ids = {items[0].conversation_id for items in grouped.values() if items and items[0].conversation_id}
    conversations = (
        db.query(ConversationSession)
        .filter(ConversationSession.session_id.in_(conversation_ids))
        .all()
    )
    conversation_map = {conversation.session_id: conversation.title for conversation in conversations}

    payloads: list[dict[str, Any]] = []
    for trace_id in ordered_trace_ids:
        items = sorted(grouped[trace_id], key=lambda item: (item.step_index, item.created_at or item.updated_at))
        payloads.append(build_tool_trace_payload(items, conversation_title=conversation_map.get(items[0].conversation_id)))
    return payloads


def _build_step_title(event: ToolExecutionEvent) -> str:
    if event.event_type == "subagent_handoff":
        return f"委派 {event.subagent_name or 'subagent'}"
    if event.event_type == "subagent_result":
        return f"{event.subagent_name or 'subagent'} 已返回"
    if event.event_type == "tool_start":
        return "工具调用"
    if event.event_type == "tool_end":
        return "工具返回"
    return event.event_type


def _build_step_detail(event: ToolExecutionEvent) -> str:
    if event.event_type == "subagent_handoff":
        return event.output_preview or event.tool_name or "子代理任务已下发"
    if event.event_type == "subagent_result":
        return event.output_preview or "子代理已完成处理"
    if event.event_type == "tool_start":
        return event.tool_name or "未知工具"
    if event.error_message:
        return event.error_message
    return event.output_preview or event.tool_name or "工具步骤已记录"


def _preview_json(value: Any, limit: int) -> str | None:
    if value in (None, "", {}, []):
        return None
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        text = str(value)
    return text if len(text) <= limit else f"{text[:limit]}..."


def _last_non_empty(values: list[str | None]) -> str | None:
    for value in reversed(values):
        if value:
            return value
    return None
