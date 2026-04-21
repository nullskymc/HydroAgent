"""
HydroAgent FastAPI API layer.
"""
from __future__ import annotations

import datetime
import json
import logging
import uuid
from urllib.parse import urlsplit
from typing import Any, Optional

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
from src.llm.agent_runtime import DEFAULT_AGENT_MODE, normalize_mode
from src.llm.persistence import get_hydro_persistence
from src.llm.skill_runtime import get_skill_runtime
from src.services import (
    approve_plan,
    ensure_system_settings,
    execute_plan,
    generate_plan_result,
    get_plan_by_id,
    get_open_plan_for_zone,
    get_system_settings_snapshot,
    get_zone_status,
    list_farm_context,
    list_plans,
    list_zones,
    manual_override_control,
    record_audit_event,
    reject_plan,
    require_permission,
    summarize_system_irrigation,
    update_system_settings,
)

logger = logging.getLogger("hydroagent.api")
router = APIRouter()

CHAT_REQUEST_MODES = {"advisor", "planner", "operator"}

INQUIRY_KEYWORDS = (
    "是否",
    "能否",
    "可否",
    "可以",
    "能不能",
    "查看",
    "检查",
    "看看",
    "说明",
    "解释",
    "为什么",
    "原因",
    "风险",
    "status",
    "why",
    "explain",
    "review",
)

OPERATOR_KEYWORDS = (
    "批准",
    "通过",
    "同意",
    "拒绝",
    "驳回",
    "执行",
    "启动",
    "开始灌溉",
    "停止",
    "关闭",
    "approve",
    "reject",
    "execute",
    "start irrigation",
    "stop irrigation",
)

AUDIT_KEYWORDS = (
    "审计",
    "复盘",
    "回放",
    "trace",
    "日志",
    "记录",
    "历史",
    "链路",
    "决策来源",
    "为什么",
    "原因",
)

PLANNING_KEYWORDS = (
    "计划",
    "生成",
    "建议",
    "灌溉",
    "浇水",
    "湿度",
    "soil moisture",
    "预测",
    "待审批",
    "待执行",
    "plan",
    "recommend",
    "forecast",
)

PLAN_REFERENCE_KEYWORDS = ("这个计划", "该计划", "它", "this plan", "current plan")
APPROVE_KEYWORDS = ("批准", "通过", "同意", "approve")
REJECT_KEYWORDS = ("拒绝", "驳回", "reject")
EXECUTE_KEYWORDS = ("执行", "启动", "开始灌溉", "execute", "start irrigation")


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
    }
    return any(key in updates for key in reload_keys)


def _build_settings_response(*, yaml_settings: dict, business_settings: dict) -> dict:
    """兼容旧字段，同时暴露新的 source-aware 结构。"""
    return {
        **yaml_settings,
        "soil_moisture_threshold": business_settings.get("default_soil_moisture_threshold"),
        "default_duration_minutes": business_settings.get("default_duration_minutes"),
        "alarm_threshold": business_settings.get("alarm_threshold"),
        "alarm_enabled": business_settings.get("alarm_enabled"),
        "collection_interval_minutes": business_settings.get("collection_interval_minutes"),
        "knowledge_top_k": business_settings.get("knowledge_top_k"),
        "knowledge_chunk_size": business_settings.get("knowledge_chunk_size"),
        "knowledge_chunk_overlap": business_settings.get("knowledge_chunk_overlap"),
        "yaml_settings": yaml_settings,
        "business_settings": business_settings,
    }


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
    mode: Optional[str] = None
    skill_ids: Optional[list[str]] = None


class SkillImportRequest(PydanticModel):
    url: str
    overwrite: bool = False


class CreateConversationRequest(PydanticModel):
    title: Optional[str] = "新对话"


class IrrigationControlRequest(PydanticModel):
    action: str
    duration_minutes: Optional[int] = 30
    zone_id: Optional[str] = None


class SettingsUpdateRequest(PydanticModel):
    soil_moisture_threshold: Optional[float] = None
    default_duration_minutes: Optional[int] = None
    alarm_threshold: Optional[float] = None
    alarm_enabled: Optional[bool] = None
    collection_interval_minutes: Optional[int] = None
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
    replace: bool = False


class PlanDecisionRequest(PydanticModel):
    actor: str = "user"
    comment: Optional[str] = None


class PlanExecuteRequest(PydanticModel):
    actor: str = "user"


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _infer_mode_from_message(message: str, working_memory: dict[str, Any] | None) -> str:
    normalized = (message or "").strip().lower()
    if not normalized:
        return DEFAULT_AGENT_MODE

    safe_memory = working_memory or {}
    has_pending_plan = bool(safe_memory.get("latest_pending_plan_ids"))
    has_approved_plan = bool(safe_memory.get("latest_approved_plan_ids"))
    is_inquiry = _contains_any(normalized, INQUIRY_KEYWORDS)
    has_operator_command = _contains_any(normalized, OPERATOR_KEYWORDS)

    # 只有明确要求变更计划或执行设备时才进入高权限路径，避免查询类请求误触发 operator。
    if has_operator_command and not is_inquiry:
        return "operator"
    if (has_pending_plan or has_approved_plan) and normalized in {"批准它", "执行它", "approve it", "execute it", "reject it"}:
        return "operator"
    if _contains_any(normalized, AUDIT_KEYWORDS):
        return "auditor"
    if _contains_any(normalized, PLANNING_KEYWORDS):
        return "planner"
    return "advisor"


def _resolve_chat_mode(requested_mode: str | None, message: str, working_memory: dict[str, Any] | None) -> str:
    candidate = str(requested_mode or "").strip().lower()
    if candidate in CHAT_REQUEST_MODES:
        return candidate
    return normalize_mode(_infer_mode_from_message(message, working_memory))


def _infer_latest_plan_command(message: str) -> str | None:
    normalized = (message or "").strip().lower()
    if not normalized:
        return None
    if not _contains_any(normalized, PLAN_REFERENCE_KEYWORDS):
        return None
    if _contains_any(normalized, EXECUTE_KEYWORDS):
        return "execute"
    if _contains_any(normalized, APPROVE_KEYWORDS):
        return "approve"
    if _contains_any(normalized, REJECT_KEYWORDS):
        return "reject"
    return None


def _build_direct_plan_reply(db: Session, message: str, working_memory: dict[str, Any] | None) -> dict[str, Any] | None:
    command = _infer_latest_plan_command(message)
    if not command:
        return None

    safe_memory = working_memory or {}
    latest_plan_ids = [str(item) for item in safe_memory.get("latest_plan_ids", []) if item]
    plan = get_plan_by_id(db, latest_plan_ids[-1]) if latest_plan_ids else None
    if not plan:
        active_zone_ids = [str(item) for item in safe_memory.get("active_zone_ids", []) if item]
        for zone_id in reversed(active_zone_ids):
            plan = get_open_plan_for_zone(db, zone_id)
            if plan:
                break
    if not plan:
        return {
            "plan": None,
            "text": "当前没有可处理的打开计划。请先生成新的 start 计划，或查看最新建议结果。",
        }

    plan_payload = plan.to_dict()
    zone_name = plan_payload.get("zone_name") or plan_payload.get("zone_id") or "当前分区"
    plan_id = plan_payload.get("plan_id") or latest_plan_ids[-1]
    proposed_action = str(plan_payload.get("proposed_action") or "")
    plan_status = str(plan_payload.get("status") or "")
    approval_status = str(plan_payload.get("approval_status") or "")
    execution_status = str(plan_payload.get("execution_status") or "")

    if command == "execute":
        if plan_status == "executing":
            return {
                "plan": plan_payload,
                "text": f"当前计划（计划编号：{plan_id}）正在执行中，无需重复发起执行。",
            }
        if plan_status == "completed" or execution_status in {"executed", "stopped", "completed"}:
            return {
                "plan": plan_payload,
                "text": f"当前计划（计划编号：{plan_id}）已经执行过，执行状态为 {execution_status}，不需要重复执行。",
            }
        if proposed_action != "start":
            return {
                "plan": plan_payload,
                "text": (
                    f"当前计划（计划编号：{plan_id}）针对 {zone_name} 的建议动作为 {proposed_action or 'hold'}，"
                    "不是启动灌溉的 start 计划，因此不能执行。"
                ),
            }
        if plan_status == "pending_approval":
            return {
                "plan": plan_payload,
                "text": f"当前计划（计划编号：{plan_id}）还在待审批状态，需先批准后才能执行。",
            }
        if plan_status == "rejected":
            return {
                "plan": plan_payload,
                "text": f"当前计划（计划编号：{plan_id}）已被拒绝，不能执行。请重新生成新的灌溉计划。",
            }
        if plan_status in {"cancelled", "superseded"}:
            return {
                "plan": plan_payload,
                "text": f"当前计划（计划编号：{plan_id}）已经失效，不能执行。请重新生成新的灌溉计划。",
            }
        return None

    if command == "approve":
        if plan_status == "approved":
            return {
                "plan": plan_payload,
                "text": f"当前计划（计划编号：{plan_id}）已经批准过，无需重复批准。",
            }
        if plan_status == "executing":
            return {
                "plan": plan_payload,
                "text": f"当前计划（计划编号：{plan_id}）已经在执行中，不需要再次批准。",
            }
        if plan_status == "completed":
            return {
                "plan": plan_payload,
                "text": f"当前计划（计划编号：{plan_id}）已经完成，不需要再次批准。",
            }
        if plan_status == "rejected":
            return {
                "plan": plan_payload,
                "text": f"当前计划（计划编号：{plan_id}）已被拒绝，不能再直接批准，建议重新生成计划。",
            }
        if plan_status in {"cancelled", "superseded"}:
            return {
                "plan": plan_payload,
                "text": f"当前计划（计划编号：{plan_id}）已经失效，不能再直接批准，建议重新生成计划。",
            }
        return None

    if command == "reject":
        if plan_status == "executing":
            return {
                "plan": plan_payload,
                "text": f"当前计划（计划编号：{plan_id}）已经在执行中，不能再执行拒绝操作。",
            }
        if plan_status == "completed":
            return {
                "plan": plan_payload,
                "text": f"当前计划（计划编号：{plan_id}）已经完成，不需要再执行拒绝操作。",
            }
        if plan_status == "rejected":
            return {
                "plan": plan_payload,
                "text": f"当前计划（计划编号：{plan_id}）已经处于拒绝状态，无需重复操作。",
            }
        if plan_status == "approved":
            return {
                "plan": plan_payload,
                "text": f"当前计划（计划编号：{plan_id}）已经批准，如需变更，建议重新生成新的计划。",
            }
        if plan_status in {"cancelled", "superseded"}:
            return {
                "plan": plan_payload,
                "text": f"当前计划（计划编号：{plan_id}）已经失效，无需再执行拒绝操作。",
            }
        return None

    return None


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


@router.get("/skills")
async def list_skills(_: User = Depends(require_permission("chat:view"))):
    runtime = get_skill_runtime()
    return {"skills": [skill.to_public_dict() for skill in runtime.list_skills()]}


@router.post("/skills/import")
async def import_skill(
    req: SkillImportRequest,
    current_user: User = Depends(require_permission("settings:manage")),
):
    runtime = get_skill_runtime()
    try:
        skill, result = runtime.import_skill_from_url(req.url, overwrite=req.overwrite)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("[skills] %s imported skill %s from %s", current_user.username, skill.id, req.url)
    return {"skill": skill.to_public_dict(include_detail=True), "import_result": result}


@router.get("/skills/{skill_id}")
async def get_skill(skill_id: str, _: User = Depends(require_permission("chat:view"))):
    runtime = get_skill_runtime()
    skill = runtime.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="skill 不存在")
    return {"skill": skill.to_public_dict(include_detail=True)}


@router.delete("/skills/{skill_id}")
async def delete_skill(
    skill_id: str,
    current_user: User = Depends(require_permission("settings:manage")),
):
    runtime = get_skill_runtime()
    try:
        skill = runtime.delete_skill(skill_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("[skills] %s deleted skill %s", current_user.username, skill.id)
    return {"success": True, "skill": skill.to_public_dict(include_detail=True)}


@router.post("/chat")
async def chat(req: ChatRequest, _: User = Depends(require_permission("chat:view"))):
    persistence = get_hydro_persistence()
    if not await persistence.thread_exists(req.conversation_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    working_memory = await persistence.get_working_memory(req.conversation_id) or {}
    resolved_mode = _resolve_chat_mode(req.mode, req.message, working_memory)
    db = SessionLocal()
    try:
        farm_context = list_farm_context(db)
        direct_plan_reply = _build_direct_plan_reply(db, req.message, working_memory)
    finally:
        db.close()
    skill_context = get_skill_runtime().resolve_for_chat(
        mode=resolved_mode,
        message=req.message,
        explicit_skill_ids=req.skill_ids or [],
        working_memory=working_memory,
        farm_context=farm_context,
    )

    async def generate():
        from src.llm.langchain_agent import get_hydro_agent

        assistant_preview_parts: list[str] = []
        trace_id = f"trace_{uuid.uuid4().hex[:12]}"
        step_index = 0
        collected_events: list[dict[str, Any]] = []

        try:
            agent = get_hydro_agent()
            if not agent._initialized:
                yield f"data: {json.dumps({'type': 'text', 'content': '正在初始化 AI 引擎...'})}\n\n"
                await agent.initialize()

            if direct_plan_reply:
                if isinstance(direct_plan_reply.get("plan"), dict):
                    plan_event = {
                        "type": "plan_updated",
                        "plan": direct_plan_reply["plan"],
                        "plan_id": direct_plan_reply["plan"].get("plan_id"),
                        "zone_id": direct_plan_reply["plan"].get("zone_id"),
                        "active_skills": skill_context.active_skill_ids,
                    }
                    collected_events.append(plan_event)
                    plan_event_payload = _build_plan_event_payload(req.conversation_id, plan_event, trace_id=trace_id)
                    if plan_event_payload:
                        await persistence.record_plan_event(req.conversation_id, plan_event_payload)
                    yield f"data: {json.dumps(plan_event, ensure_ascii=False)}\n\n"
                assistant_preview_parts.append(str(direct_plan_reply["text"]))
                yield f"data: {json.dumps({'type': 'text', 'content': direct_plan_reply['text']}, ensure_ascii=False)}\n\n"
                working_memory_payload = _build_working_memory_payload(
                    previous=working_memory,
                    message=req.message,
                    assistant_content=str(direct_plan_reply["text"]),
                    mode=resolved_mode,
                    skill_context=skill_context,
                    events=collected_events,
                )
                await persistence.record_working_memory(req.conversation_id, working_memory_payload)
                yield f"data: {json.dumps({'type': 'done', 'working_memory': working_memory_payload, 'inferred_mode': resolved_mode}, ensure_ascii=False)}\n\n"
                return

            async for event in agent.chat_stream(
                [{"role": "user", "content": req.message}],
                conversation_id=req.conversation_id,
                mode=resolved_mode,
                runtime_context={
                    "active_skill_ids": skill_context.active_skill_ids,
                    "allowed_tools": skill_context.allowed_tools,
                    "prompt_fragments": skill_context.prompt_fragments,
                    "resources": skill_context.resources,
                    "reason": skill_context.reason,
                    "conflicts": skill_context.conflicts,
                    "phase_overrides": skill_context.workflow_overrides,
                    "workflow_phases": skill_context.workflow_phases,
                },
                working_memory=working_memory,
            ):
                event_type = event.get("type")
                if event_type == "text":
                    assistant_preview_parts.append(event.get("content", ""))
                if event_type != "done":
                    collected_events.append(dict(event))
                trace_payload = _build_trace_event_payload(
                    conversation_id=req.conversation_id,
                    trace_id=trace_id,
                    step_index=step_index,
                    event=event,
                )
                if trace_payload:
                    step_index += 1
                    await persistence.record_trace_event(req.conversation_id, trace_payload)
                decision_payload = _build_decision_event_payload(
                    req.conversation_id,
                    event,
                    trace_id=trace_id,
                    skill_ids=skill_context.active_skill_ids,
                )
                if decision_payload:
                    await persistence.record_decision_async(decision_payload, thread_id=req.conversation_id)
                plan_event_payload = _build_plan_event_payload(req.conversation_id, event, trace_id=trace_id)
                if plan_event_payload:
                    await persistence.record_plan_event(req.conversation_id, plan_event_payload)
                outbound_event = dict(event)
                if event_type != "done":
                    outbound_event["trace_id"] = trace_id
                    outbound_event["inferred_mode"] = resolved_mode
                if event_type == "done":
                    working_memory_payload = _build_working_memory_payload(
                        previous=working_memory,
                        message=req.message,
                        assistant_content="".join(part for part in assistant_preview_parts if part).strip(),
                        mode=resolved_mode,
                        skill_context=skill_context,
                        events=collected_events,
                    )
                    await persistence.record_working_memory(req.conversation_id, working_memory_payload)
                    outbound_event["working_memory"] = working_memory_payload
                    outbound_event["inferred_mode"] = resolved_mode
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
    if event_type not in {"tool_call", "tool_result"}:
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
            "phase": event.get("phase"),
            "active_skills": event.get("active_skills") or [],
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
            "phase": event.get("phase"),
            "active_skills": event.get("active_skills") or [],
            "title": "工具返回",
            "detail": f"{source}{event.get('output_preview') or f'{tool_name} 已返回结构化结果'}",
            "created_at": created_at,
        }
    return None


def _build_decision_event_payload(conversation_id: str, event: dict, *, trace_id: str | None, skill_ids: list[str]) -> dict | None:
    event_type = event.get("type")
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if event_type == "approval_requested":
        details = event.get("details") if isinstance(event.get("details"), dict) else {}
        return {
            "decision_id": f"decision_{uuid.uuid4().hex[:12]}",
            "trigger": "chat",
            "zone_id": details.get("zone_id"),
            "plan_id": details.get("plan_id"),
            "trace_id": trace_id,
            "source": "chat_agent",
            "skill_ids": skill_ids,
            "input_context": {"conversation_id": conversation_id, "event": event_type},
            "reasoning_chain": "Agent blocked a start-like action because approval is required before execution.",
            "tools_used": [str(event.get("tool") or "control_irrigation")],
            "decision_result": {
                "status": "approval_requested",
                "details": details,
            },
            "evidence_refs": {"zone_id": details.get("zone_id"), "plan_id": details.get("plan_id")},
            "reflection_notes": "Approval boundary enforced before irrigation execution.",
            "effectiveness_score": None,
            "created_at": created_at,
        }

    if event_type == "suggestion_result":
        suggestion = event.get("suggestion") if isinstance(event.get("suggestion"), dict) else {}
        return {
            "decision_id": f"decision_{uuid.uuid4().hex[:12]}",
            "trigger": "chat",
            "zone_id": suggestion.get("zone_id"),
            "plan_id": None,
            "trace_id": trace_id,
            "source": "chat_agent",
            "skill_ids": skill_ids,
            "input_context": {"conversation_id": conversation_id, "event": event_type},
            "reasoning_chain": "Agent recorded a non-executable irrigation suggestion instead of creating a formal start plan.",
            "tools_used": ["create_irrigation_plan"],
            "decision_result": {
                "status": "suggestion_only",
                "suggestion_id": suggestion.get("suggestion_id"),
                "proposed_action": suggestion.get("proposed_action"),
                "risk_level": suggestion.get("risk_level"),
            },
            "evidence_refs": {
                "zone_id": suggestion.get("zone_id"),
                "suggestion_id": suggestion.get("suggestion_id"),
            },
            "reflection_notes": str(suggestion.get("reasoning_summary") or "Captured from structured suggestion output."),
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
            "trace_id": trace_id,
            "source": "chat_agent",
            "skill_ids": skill_ids,
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
            "evidence_refs": {"zone_id": plan.get("zone_id"), "plan_id": plan.get("plan_id")},
            "reflection_notes": str(plan.get("reasoning_summary") or "Captured from official LangGraph streaming updates."),
            "effectiveness_score": None,
            "created_at": created_at,
        }

    return None


def _build_plan_event_payload(conversation_id: str, event: dict, *, trace_id: str | None = None) -> dict | None:
    event_type = event.get("type")
    if event_type not in {"plan_proposed", "plan_updated", "approval_result", "execution_result", "suggestion_result"}:
        return None

    if event_type == "suggestion_result":
        suggestion = event.get("suggestion") if isinstance(event.get("suggestion"), dict) else None
        if not suggestion:
            return None
        suggestion_id = str(suggestion.get("suggestion_id") or "").strip()
        if not suggestion_id:
            return None
        return {
            "event_id": f"planevt_{uuid.uuid4().hex[:12]}",
            "conversation_id": conversation_id,
            "event_type": event_type,
            "suggestion_id": suggestion_id,
            "suggestion": suggestion,
            "trace_id": trace_id,
            "active_skills": event.get("active_skills") or [],
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

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
        "active_skills": event.get("active_skills") or [],
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def _build_working_memory_payload(
    *,
    previous: dict[str, Any],
    message: str,
    assistant_content: str,
    mode: str,
    skill_context: Any,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    active_zone_ids = list(dict.fromkeys(str(item) for item in previous.get("active_zone_ids", []) if item))
    latest_plan_ids = list(dict.fromkeys(str(item) for item in previous.get("latest_plan_ids", []) if item))
    pending_plan_ids = list(dict.fromkeys(str(item) for item in previous.get("latest_pending_plan_ids", []) if item))
    approved_plan_ids = list(dict.fromkeys(str(item) for item in previous.get("latest_approved_plan_ids", []) if item))
    open_risks = list(dict.fromkeys(str(item) for item in previous.get("open_risks", []) if item))
    anomalies = list(previous.get("last_sensor_anomalies", []))

    for event in events:
        zone_id = event.get("zone_id")
        if isinstance(zone_id, str) and zone_id and zone_id not in active_zone_ids:
            active_zone_ids.append(zone_id)
        plan = event.get("plan") if isinstance(event.get("plan"), dict) else {}
        suggestion = event.get("suggestion") if isinstance(event.get("suggestion"), dict) else {}
        plan_id = event.get("plan_id") or plan.get("plan_id")
        if isinstance(plan_id, str) and plan_id and plan_id not in latest_plan_ids:
            latest_plan_ids.append(plan_id)
        if isinstance(plan_id, str) and plan_id:
            if plan_id in pending_plan_ids:
                pending_plan_ids.remove(plan_id)
            if plan_id in approved_plan_ids:
                approved_plan_ids.remove(plan_id)
            if plan.get("status") == "pending_approval" and plan_id not in pending_plan_ids:
                pending_plan_ids.append(plan_id)
            if plan.get("status") == "approved" and plan_id not in approved_plan_ids:
                approved_plan_ids.append(plan_id)
        if event.get("type") == "approval_requested":
            details = event.get("details") if isinstance(event.get("details"), dict) else {}
            for reason in details.get("reasons") or []:
                text = str(reason).strip()
                if text and text not in open_risks:
                    open_risks.append(text)
        risk_level = str(plan.get("risk_level") or "").strip()
        if not risk_level:
            risk_level = str(suggestion.get("risk_level") or "").strip()
        if risk_level:
            risk_text = f"plan:{risk_level}"
            if risk_text not in open_risks:
                open_risks.append(risk_text)
        suggestion_zone_id = suggestion.get("zone_id")
        if isinstance(suggestion_zone_id, str) and suggestion_zone_id and suggestion_zone_id not in active_zone_ids:
            active_zone_ids.append(suggestion_zone_id)
        if event.get("tool") == "anomaly_detection":
            result = event.get("result") if isinstance(event.get("result"), dict) else {}
            anomaly_count = result.get("anomaly_count")
            if anomaly_count:
                anomalies.append({"zone_id": zone_id, "anomaly_count": anomaly_count})

    return {
        "memory_id": f"memory_{uuid.uuid4().hex[:12]}",
        "last_inferred_mode": mode,
        "active_skills": skill_context.active_skill_ids,
        "active_zone_ids": active_zone_ids[-10:],
        "latest_plan_ids": latest_plan_ids[-10:],
        "latest_pending_plan_ids": pending_plan_ids[-10:],
        "latest_approved_plan_ids": approved_plan_ids[-10:],
        "open_risks": open_risks[-10:],
        "last_user_goal": message,
        "last_decision_summary": assistant_content[:500] if assistant_content else "",
        "last_sensor_anomalies": anomalies[-10:],
        "skill_reason": skill_context.reason,
        "last_updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
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
        result = generate_plan_result(
            db,
            req.zone_id,
            conversation_id=req.conversation_id,
            trigger=req.trigger,
            requested_by="api",
            replace=req.replace,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    plan_payload = result.get("plan") if isinstance(result.get("plan"), dict) else None
    suggestion_payload = result.get("suggestion") if isinstance(result.get("suggestion"), dict) else None
    audit_object_type = "plan" if plan_payload else "suggestion"
    audit_object_id = (
        plan_payload.get("plan_id")
        if plan_payload
        else suggestion_payload.get("suggestion_id")
        if suggestion_payload
        else req.zone_id
    )
    record_audit_event(
        db,
        actor=current_user.username,
        event_type="plan.generate",
        object_type=audit_object_type,
        object_id=audit_object_id,
        details={"zone_id": req.zone_id, "trigger": req.trigger, "replace": req.replace, "reused_existing": result.get("reused_existing")},
    )
    if plan_payload:
        await _record_plan_event_if_needed("plan_proposed", plan_payload)
    if suggestion_payload and req.conversation_id:
        persistence = get_hydro_persistence()
        event_payload = _build_plan_event_payload(
            req.conversation_id,
            {"type": "suggestion_result", "suggestion": suggestion_payload},
            trace_id=None,
        )
        if event_payload:
            await persistence.record_plan_event(req.conversation_id, event_payload)
    return result


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
        result = manual_override_control(db, req.action, duration_minutes=req.duration_minutes or 30, zone_id=req.zone_id)
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
async def get_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("settings:view")),
):
    from src.config import config

    ensure_system_settings(db)
    yaml_settings = config.get_yaml_settings()
    business_settings = get_system_settings_snapshot(db)
    return _build_settings_response(yaml_settings=yaml_settings, business_settings=business_settings)


@router.put("/settings")
async def update_settings(
    req: SettingsUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("settings:manage")),
):
    from src.config import config

    updates = req.model_dump(exclude_none=True) if hasattr(req, "model_dump") else req.dict(exclude_none=True)
    yaml_update_keys = {
        "model_name",
        "embedding_model_name",
        "openai_base_url",
        "openai_api_key",
        "embedding_api_key",
    }
    yaml_updates = {key: value for key, value in updates.items() if key in yaml_update_keys}
    business_updates = {key: value for key, value in updates.items() if key not in yaml_update_keys}

    yaml_settings = config.get_yaml_settings()
    if yaml_updates:
        yaml_settings = config.update_yaml_settings(yaml_updates)
    business_settings = update_system_settings(db, business_updates) if business_updates else get_system_settings_snapshot(db)
    settings = _build_settings_response(yaml_settings=yaml_settings, business_settings=business_settings)
    reload_error = None
    reloaded = False
    if _should_reload_agent(yaml_updates):
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
