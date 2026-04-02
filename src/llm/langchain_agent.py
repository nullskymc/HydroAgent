"""
HydroAgent deepagents harness.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
from typing import Any, AsyncIterator, Optional

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

from src.database.models import AgentDecisionLog, SessionLocal
from src.llm.tool_argument_parser import ToolArgumentParserAgent, wrap_tool_registry

logger = logging.getLogger("hydroagent.agent")


HYDRO_SYSTEM_PROMPT = """你是 HydroAgent，一个面向多分区农场的监督执行型智能灌溉系统。

你的职责不是直接替用户草率开灌，而是：
1. 识别具体的 zone 和 actuator。
2. 先收集证据：传感器、天气、历史计划、当前运行状态。
3. 生成结构化灌溉计划，并解释风险与理由。
4. 对任何 start 行为坚持审批边界，未批准不得执行。
5. 批准后执行计划，并记录执行回执。

请优先使用这些角色化思维：
- Supervisor: 决定当前任务该拆给哪个子代理。
- Zone Analyst: 获取某个 zone 的证据和约束。
- Planner: 生成或更新结构化灌溉计划。
- Safety Reviewer: 主动寻找不该执行的理由。
- Execution Agent: 仅在计划已批准时执行。

回答要求：
- 使用中文。
- 引用具体 zone、湿度、天气、风险级别和计划编号。
- 当生成计划时，先解释结论，再附带行动建议。
- 当工具返回结构化数据时，优先用它，不要编造字段。

调度要求：
- 你是 supervisor，本身只保留少量总览能力，涉及真实证据、计划、安全复核、执行时，必须优先委派给合适的 subagent。
- 任何 zone 证据收集或状态核查，先交给 zone-analyst。
- 任何创建、修改、批准、拒绝计划，交给 planner。
- 任何 start 类建议、雨天风险、传感器缺失、执行器异常的挑战性复核，交给 safety-reviewer。
- 任何执行已批准计划或停灌操作，交给 execution-agent。
- 如果请求涉及多个 zone，使用并行 task 调用分别委派，不要把多个 zone 混在一个 subagent 任务里。
- 在最终回答里明确说明每一步由哪个 subagent 完成，便于审计。
"""

SUPERVISOR_TOOL_NAMES = (
    "list_farm_zones",
    "get_plan_status",
    "manage_alarm",
)

SUBAGENT_TOOL_NAMES = {
    "zone-analyst": (
        "list_farm_zones",
        "query_sensor_data",
        "query_weather",
        "get_zone_operating_status",
        "recommend_irrigation_plan",
        "statistical_analysis",
        "anomaly_detection",
        "time_series_forecast",
        "correlation_analysis",
    ),
    "planner": (
        "create_irrigation_plan",
        "get_plan_status",
        "approve_irrigation_plan",
        "reject_irrigation_plan",
    ),
    "safety-reviewer": (
        "get_plan_status",
        "query_sensor_data",
        "query_weather",
        "get_zone_operating_status",
        "recommend_irrigation_plan",
    ),
    "execution-agent": (
        "get_plan_status",
        "get_zone_operating_status",
        "execute_approved_plan",
        "control_irrigation",
    ),
}

SUBAGENT_SYSTEM_PROMPTS = {
    "zone-analyst": (
        "Focus on one zone at a time. Gather concrete evidence only. "
        "Return zone_id, soil moisture, weather risk, actuator state, and missing-data constraints."
    ),
    "planner": (
        "You manage structured irrigation plans only. "
        "Create, approve, reject, or inspect plan state based on explicit user intent or supervisor instructions."
    ),
    "safety-reviewer": (
        "You are conservative. Challenge risky start actions. "
        "Explicitly check rain risk, missing sensor data, disabled actuators, emergency-band exceptions, and approval boundaries."
    ),
    "execution-agent": (
        "You execute approved plans or stop irrigation only after validation. "
        "Before execution, verify approval_status=approved, actuator readiness, and plan action=start."
    ),
}

_ZONE_ID_PATTERN = re.compile(r"\bzone_[a-zA-Z0-9]+\b")
_PLAN_ID_PATTERN = re.compile(r"\bplan_[a-zA-Z0-9]+\b")


class HydroDeepAgent:
    """Deep agent wrapper with MCP tools and SSE-friendly event conversion."""

    def __init__(self):
        self._agent = None
        self._mcp_client = None
        self._initialized = False
        self._workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self._checkpointer = MemorySaver()
        self._tool_registry: dict[str, Any] = {}
        self._parser_agent: ToolArgumentParserAgent | None = None

    async def initialize(self):
        if self._initialized:
            return

        from src.config import config

        workspace_dir = os.path.join(self._workspace_root, ".hydro_workspace")
        os.makedirs(workspace_dir, exist_ok=True)

        llm = ChatOpenAI(
            model=config.MODEL_NAME,
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL,
            temperature=0.2,
            streaming=True,
        )

        self._mcp_client = MultiServerMCPClient(
            {
                "hydro": {
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": [config.MCP_SERVER_PATH],
                }
            }
        )
        mcp_tools = await self._mcp_client.get_tools()
        self._tool_registry = {
            tool_name: tool for tool in mcp_tools if (tool_name := getattr(tool, "name", None))
        }
        self._parser_agent = ToolArgumentParserAgent(llm=llm)
        self._tool_registry = wrap_tool_registry(self._tool_registry, self._parser_agent)
        logger.info("[HydroAgent] Loaded %s MCP tools", len(mcp_tools))

        subagents = [
            {
                "name": "zone-analyst",
                "description": "Research a specific irrigation zone, collect sensor, weather, and status evidence.",
                "system_prompt": SUBAGENT_SYSTEM_PROMPTS["zone-analyst"],
                "tools": _select_tools(self._tool_registry, SUBAGENT_TOOL_NAMES["zone-analyst"]),
            },
            {
                "name": "planner",
                "description": "Generate or update structured irrigation plans for zones.",
                "system_prompt": SUBAGENT_SYSTEM_PROMPTS["planner"],
                "tools": _select_tools(self._tool_registry, SUBAGENT_TOOL_NAMES["planner"]),
            },
            {
                "name": "safety-reviewer",
                "description": "Challenge risky irrigation actions and identify why a plan should be deferred.",
                "system_prompt": SUBAGENT_SYSTEM_PROMPTS["safety-reviewer"],
                "tools": _select_tools(self._tool_registry, SUBAGENT_TOOL_NAMES["safety-reviewer"]),
            },
            {
                "name": "execution-agent",
                "description": "Execute approved plans only after validating approval state and actuator readiness.",
                "system_prompt": SUBAGENT_SYSTEM_PROMPTS["execution-agent"],
                "tools": _select_tools(self._tool_registry, SUBAGENT_TOOL_NAMES["execution-agent"]),
            },
        ]

        self._agent = create_deep_agent(
            model=llm,
            tools=_select_tools(self._tool_registry, SUPERVISOR_TOOL_NAMES),
            system_prompt=HYDRO_SYSTEM_PROMPT,
            subagents=subagents,
            memory=["/AGENTS.md"],
            checkpointer=self._checkpointer,
            backend=FilesystemBackend(root_dir=self._workspace_root, virtual_mode=False),
            interrupt_on={"control_irrigation": True},
            name="hydro-supervisor",
        )
        self._initialized = True
        logger.info("[HydroAgent] Deep agent initialized")

    async def chat_stream(self, messages: list[dict], conversation_id: str | None = None) -> AsyncIterator[dict]:
        if not self._initialized:
            await self.initialize()

        from langchain_core.messages import AIMessage, HumanMessage

        lc_messages = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if role == "assistant":
                lc_messages.append(AIMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=content))

        input_data = {"messages": lc_messages}
        config = {"configurable": {"thread_id": conversation_id or "hydro-default"}}
        active_subagent_calls: dict[str, dict[str, Any]] = {}
        active_tool_calls: dict[str, dict[str, Any]] = {}

        try:
            async for event in self._agent.astream_events(input_data, config=config, version="v2"):
                event_name = event.get("event", "")
                if event_name == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    content = getattr(chunk, "content", None)
                    if content:
                        if isinstance(content, list):
                            for item in content:
                                text = item.get("text") if isinstance(item, dict) else str(item)
                                if text:
                                    yield {"type": "text", "content": text}
                        else:
                            yield {"type": "text", "content": str(content)}
                elif event_name == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    run_id = _get_event_run_key(event)
                    tool_args = event.get("data", {}).get("input", {})
                    normalized_args = None
                    zone_id = None
                    plan_id = None
                    if isinstance(tool_args, dict):
                        resolved_args = await self._parser_agent.normalize_async(tool_name, tool_args) if self._parser_agent else tool_args
                        normalized_args = resolved_args if resolved_args != tool_args else None
                        identifiers = _extract_identifiers(resolved_args)
                        zone_id = identifiers.get("zone_id")
                        plan_id = identifiers.get("plan_id")

                    active_tool_calls[run_id] = {
                        "tool_name": tool_name,
                        "args": tool_args if isinstance(tool_args, dict) else None,
                        "normalized_args": normalized_args,
                        "zone_id": zone_id,
                        "plan_id": plan_id,
                        "started_at": time.perf_counter(),
                    }

                    yield {
                        "type": "tool_call",
                        "tool": tool_name,
                        "run_id": run_id,
                        "args": tool_args,
                        "normalized_args": normalized_args,
                        "zone_id": zone_id,
                        "plan_id": plan_id,
                    }

                    if tool_name == "task":
                        task_key = run_id
                        delegation = _build_delegation_event(tool_args)
                        active_subagent_calls[task_key] = delegation
                        self._record_decision_log(
                            trigger="chat",
                            zone_id=delegation.get("zone_id"),
                            plan_id=delegation.get("plan_id"),
                            input_context={
                                "conversation_id": conversation_id,
                                "event": "subagent_handoff",
                                "task_description": delegation.get("task_description"),
                            },
                            reasoning_chain=f"Supervisor delegated work to {delegation.get('subagent')}.",
                            tools_used=["task"],
                            decision_result={
                                "subagent": delegation.get("subagent"),
                                "status": "started",
                            },
                            reflection_notes="Subagent delegation captured from deepagents task tool.",
                        )
                        delegation["run_id"] = run_id
                        yield delegation
                elif event_name == "on_tool_end":
                    tool_name = event.get("name", "unknown")
                    run_id = _get_event_run_key(event)
                    tool_meta = active_tool_calls.pop(run_id, {})
                    output = event.get("data", {}).get("output", "")
                    if tool_name == "task":
                        task_key = run_id
                        delegation = active_subagent_calls.pop(task_key, {"type": "subagent_result"})
                        result_event = {
                            "type": "subagent_result",
                            "run_id": run_id,
                            "subagent": delegation.get("subagent", "unknown"),
                            "zone_id": delegation.get("zone_id"),
                            "plan_id": delegation.get("plan_id"),
                            "result_preview": _stringify_event_payload(output),
                        }
                        self._record_decision_log(
                            trigger="chat",
                            zone_id=result_event.get("zone_id"),
                            plan_id=result_event.get("plan_id"),
                            input_context={
                                "conversation_id": conversation_id,
                                "event": "subagent_result",
                                "subagent": result_event.get("subagent"),
                            },
                            reasoning_chain=f"{result_event.get('subagent')} completed delegated work.",
                            tools_used=["task"],
                            decision_result={
                                "subagent": result_event.get("subagent"),
                                "status": "completed",
                                "result_preview": result_event.get("result_preview"),
                            },
                            reflection_notes="Subagent completion captured from deepagents task tool.",
                        )
                        yield result_event
                    parsed = _safe_json(output)
                    duration_ms = None
                    started_at = tool_meta.get("started_at")
                    if isinstance(started_at, (int, float)):
                        duration_ms = int((time.perf_counter() - started_at) * 1000)
                    identifiers = _extract_identifiers(parsed or {})
                    zone_id = tool_meta.get("zone_id") or identifiers.get("zone_id")
                    plan_id = tool_meta.get("plan_id") or identifiers.get("plan_id")
                    structured_event = _tool_output_to_stream_event(tool_name, parsed)
                    if structured_event:
                        yield structured_event
                    yield {
                        "type": "tool_result",
                        "tool": tool_name,
                        "run_id": run_id,
                        "args": tool_meta.get("args"),
                        "normalized_args": tool_meta.get("normalized_args"),
                        "zone_id": zone_id,
                        "plan_id": plan_id,
                        "result": parsed or str(output)[:800],
                        "output_preview": _stringify_event_payload(output),
                        "duration_ms": duration_ms,
                    }
            yield {"type": "done"}
        except Exception as exc:
            logger.error("[HydroAgent] chat_stream failed: %s", exc, exc_info=True)
            yield {"type": "error", "content": f"处理请求时出错：{exc}"}
            yield {"type": "done"}

    async def chat(self, messages: list[dict], conversation_id: str | None = None) -> str:
        parts = []
        async for chunk in self.chat_stream(messages, conversation_id=conversation_id):
            if chunk["type"] == "text":
                parts.append(chunk["content"])
        return "".join(parts)

    async def auto_check(self) -> str:
        from src.database.models import SessionLocal
        from src.services import create_plan, list_zones

        db = SessionLocal()
        try:
            created = []
            for zone in list_zones(db):
                if not zone.is_enabled:
                    continue
                plan = create_plan(db, zone.zone_id, trigger="auto", requested_by="scheduler")
                created.append({"zone_id": zone.zone_id, "plan_id": plan.plan_id, "status": plan.status})
            return json.dumps({"generated_plans": created}, ensure_ascii=False)
        finally:
            db.close()

    async def cleanup(self):
        return

    def _record_decision_log(
        self,
        *,
        trigger: str,
        zone_id: str | None,
        plan_id: str | None,
        input_context: dict[str, Any],
        reasoning_chain: str,
        tools_used: list[str],
        decision_result: dict[str, Any],
        reflection_notes: str,
    ):
        db = SessionLocal()
        try:
            db.add(
                AgentDecisionLog(
                    trigger=trigger,
                    zone_id=zone_id,
                    plan_id=plan_id,
                    input_context=input_context,
                    reasoning_chain=reasoning_chain,
                    tools_used=tools_used,
                    decision_result=decision_result,
                    reflection_notes=reflection_notes,
                )
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("[HydroAgent] Failed to persist decision log: %s", exc)
        finally:
            db.close()


def _safe_json(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    try:
        if hasattr(value, "content"):
            return _safe_json(value.content)
        return json.loads(str(value))
    except Exception:
        return None


def _select_tools(tool_registry: dict[str, Any], names: tuple[str, ...]) -> list[Any]:
    selected: list[Any] = []
    missing: list[str] = []
    for name in names:
        tool = tool_registry.get(name)
        if tool is None:
            missing.append(name)
            continue
        selected.append(tool)
    if missing:
        logger.warning("[HydroAgent] Missing MCP tools for partition: %s", ", ".join(missing))
    return selected


def _get_event_run_key(event: dict[str, Any]) -> str:
    return str(event.get("run_id") or event.get("name") or id(event))


def _build_delegation_event(tool_args: dict[str, Any]) -> dict[str, Any]:
    description = str(tool_args.get("description", "")).strip()
    subagent = str(tool_args.get("subagent_type", "unknown")).strip() or "unknown"
    identifiers = _extract_identifiers(tool_args, description)
    return {
        "type": "subagent_handoff",
        "subagent": subagent,
        "task_description": description,
        "zone_id": identifiers.get("zone_id"),
        "plan_id": identifiers.get("plan_id"),
    }


def _extract_identifiers(payload: Any, text_fallback: str = "") -> dict[str, str | None]:
    zone_id = _find_nested_value(payload, "zone_id") or _search_pattern(_ZONE_ID_PATTERN, text_fallback)
    plan_id = _find_nested_value(payload, "plan_id") or _search_pattern(_PLAN_ID_PATTERN, text_fallback)
    return {"zone_id": zone_id, "plan_id": plan_id}


def _find_nested_value(payload: Any, key: str) -> str | None:
    if isinstance(payload, dict):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
        for nested in payload.values():
            found = _find_nested_value(nested, key)
            if found:
                return found
        return None
    if isinstance(payload, list):
        for item in payload:
            found = _find_nested_value(item, key)
            if found:
                return found
    return None


def _search_pattern(pattern: re.Pattern[str], text_value: str) -> str | None:
    for match in pattern.finditer(text_value or ""):
        candidate = match.group(0)
        if candidate not in {"zone_id", "plan_id"}:
            return candidate
    return None


def _stringify_event_payload(payload: Any, limit: int = 240) -> str:
    parsed = _safe_json(payload)
    if parsed is not None:
        # 将结构化结果压平为短预览，便于前端时间线和审计日志展示。
        text = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    elif hasattr(payload, "content"):
        text = _stringify_event_payload(payload.content, limit=limit)
    else:
        text = str(payload)
    return text if len(text) <= limit else f"{text[:limit]}..."


def _tool_output_to_stream_event(tool_name: str, payload: dict | None) -> dict | None:
    if not payload:
        return None

    if tool_name == "create_irrigation_plan":
        return {"type": "plan_proposed", "plan": payload}
    if tool_name == "get_plan_status":
        return {"type": "plan_updated", "plan": payload}
    if tool_name == "approve_irrigation_plan":
        return {"type": "approval_result", "plan": payload, "decision": "approved"}
    if tool_name == "reject_irrigation_plan":
        return {"type": "approval_result", "plan": payload, "decision": "rejected"}
    if tool_name == "execute_approved_plan":
        return {"type": "execution_result", "plan": payload}
    if tool_name == "control_irrigation" and payload.get("requires_approval"):
        return {
            "type": "approval_requested",
            "tool": tool_name,
            "details": payload,
        }
    return None


_hydro_agent: Optional[HydroDeepAgent] = None


def get_hydro_agent() -> HydroDeepAgent:
    global _hydro_agent
    if _hydro_agent is None:
        _hydro_agent = HydroDeepAgent()
    return _hydro_agent


HydroLangChainAgent = HydroDeepAgent
