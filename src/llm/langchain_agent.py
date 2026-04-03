"""
HydroAgent 单代理 LangChain harness。
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from typing import Any, AsyncIterator, Optional

from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI

from src.llm.persistence import get_hydro_persistence
from src.llm.tool_argument_parser import ACTIVE_CONVERSATION_ID, ToolArgumentParserAgent, wrap_tool_registry

logger = logging.getLogger("hydroagent.agent")


HYDRO_SYSTEM_PROMPT = """你是 HydroAgent，一个面向多分区农场的审慎型智能灌溉系统。

你的工作方式是单代理直接编排工具，不要再假想任何 subagent、task 委派或多角色交接。

必须遵守以下原则：
1. 先识别目标分区，再收集证据：传感器、天气、当前运行状态、历史计划。
2. 涉及分区级工具时，必须传入准确的 canonical zone_id，绝不能省略 zone_id。
3. 当用户只说“分区 1 / 2”或中文名称时，先调用 list_farm_zones 获取目录，再使用返回的 zone_id。
4. 当用户没有指定 zone，但请求的是“生成计划 / 检查状态 / 审批检查 / 执行检查”这类农场级任务时，不要先反问；先调用 list_farm_zones，按 enabled zone 逐个处理，再汇总结论。
5. 生成计划时，必须说明证据、风险、建议时长和是否需要审批。
6. 任何 start 行为都不能绕过审批边界；未批准计划不得执行。
7. 若天气提示未来 48 小时可能降雨，除非湿度进入 emergency band，否则优先建议 hold/defer。
8. 若执行器状态未知、禁用或已经运行，避免自动执行并明确提示风险。
9. 若传感器缺失或无效，生成 hold/defer 计划，而不是 start 计划。

回答要求：
- 使用中文。
- 引用具体 zone_id、湿度、天气、风险级别和计划编号。
- 当请求涉及多个分区时，按分区逐个处理，不要把多个分区混成一个模糊结论。
- 当工具返回结构化数据时，优先复述关键字段，不要编造。
"""

AGENT_TOOL_NAMES = (
    "list_farm_zones",
    "query_sensor_data",
    "query_weather",
    "get_zone_operating_status",
    "recommend_irrigation_plan",
    "statistical_analysis",
    "anomaly_detection",
    "time_series_forecast",
    "correlation_analysis",
    "create_irrigation_plan",
    "get_plan_status",
    "approve_irrigation_plan",
    "reject_irrigation_plan",
    "execute_approved_plan",
    "control_irrigation",
    "manage_alarm",
)

_ZONE_ID_PATTERN = re.compile(r"\bzone_[a-zA-Z0-9]+\b")
_PLAN_ID_PATTERN = re.compile(r"\bplan_[a-zA-Z0-9]+\b")


class HydroDeepAgent:
    """Official LangChain agent wrapper with MCP tools and SSE-friendly event conversion."""

    def __init__(self):
        self._agent = None
        self._mcp_client = None
        self._initialized = False
        self._workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self._checkpointer = None
        self._tool_registry: dict[str, Any] = {}
        self._parser_agent: ToolArgumentParserAgent | None = None

    async def initialize(self):
        if self._initialized:
            return

        from src.config import config

        workspace_dir = os.path.join(self._workspace_root, ".hydro_workspace")
        os.makedirs(workspace_dir, exist_ok=True)
        persistence = get_hydro_persistence()
        await persistence.initialize()
        self._checkpointer = persistence.async_saver

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

        self._agent = create_agent(
            model=llm,
            tools=_select_tools(self._tool_registry, AGENT_TOOL_NAMES),
            system_prompt=HYDRO_SYSTEM_PROMPT,
            checkpointer=self._checkpointer,
            name="hydro-supervisor",
        )
        self._initialized = True
        logger.info("[HydroAgent] Single agent initialized")

    async def chat_stream(self, messages: list[dict], conversation_id: str | None = None) -> AsyncIterator[dict]:
        if not self._initialized:
            await self.initialize()

        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

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
        active_tool_calls: dict[str, dict[str, Any]] = {}
        ACTIVE_CONVERSATION_ID.set(conversation_id)

        try:
            async for chunk in self._agent.astream(
                input_data,
                config=config,
                stream_mode=["messages", "updates"],
                version="v2",
            ):
                chunk_type = chunk.get("type")
                if chunk_type == "messages":
                    message_data = chunk.get("data")
                    if not isinstance(message_data, tuple | list) or len(message_data) != 2:
                        continue
                    message, metadata = message_data
                    if _should_emit_assistant_text(message, metadata):
                        for text in _iter_stream_text(message):
                            yield {
                                "type": "text",
                                "content": text,
                                "agent_name": metadata.get("langgraph_name") or metadata.get("lc_agent_name"),
                                "node_name": metadata.get("langgraph_node"),
                            }
                    continue

                if chunk_type != "updates":
                    continue

                update_data = chunk.get("data")
                if not isinstance(update_data, dict):
                    continue

                for node_name, update in update_data.items():
                    if not isinstance(update, dict):
                        continue

                    streamed_messages = update.get("messages")
                    if not isinstance(streamed_messages, list):
                        continue

                    for streamed_message in streamed_messages:
                        if isinstance(streamed_message, AIMessage):
                            agent_name = _get_message_agent_name(streamed_message, default="hydro-supervisor")
                            for tool_call in streamed_message.tool_calls or []:
                                tool_name = str(tool_call.get("name") or "unknown")
                                run_id = str(tool_call.get("id") or f"{tool_name}-{id(tool_call)}")
                                tool_args = tool_call.get("args", {})
                                normalized_args = None
                                zone_id = None
                                plan_id = None

                                if isinstance(tool_args, dict):
                                    resolved_args = (
                                        await self._parser_agent.normalize_async(tool_name, tool_args)
                                        if self._parser_agent
                                        else tool_args
                                    )
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
                                    "agent_name": agent_name,
                                    "node_name": node_name,
                                }

                                yield {
                                    "type": "tool_call",
                                    "tool": tool_name,
                                    "run_id": run_id,
                                    "args": tool_args if isinstance(tool_args, dict) else None,
                                    "normalized_args": normalized_args,
                                    "zone_id": zone_id,
                                    "plan_id": plan_id,
                                    "agent_name": agent_name,
                                    "node_name": node_name,
                                }

                        elif isinstance(streamed_message, ToolMessage):
                            run_id = str(getattr(streamed_message, "tool_call_id", None) or id(streamed_message))
                            tool_meta = active_tool_calls.pop(run_id, {})
                            tool_name = str(getattr(streamed_message, "name", None) or tool_meta.get("tool_name") or "unknown")
                            output = _extract_tool_message_payload(streamed_message)
                            parsed = _safe_json(output)
                            duration_ms = None
                            started_at = tool_meta.get("started_at")
                            if isinstance(started_at, (int, float)):
                                duration_ms = int((time.perf_counter() - started_at) * 1000)
                            identifiers = _extract_identifiers(parsed or {})
                            zone_id = tool_meta.get("zone_id") or identifiers.get("zone_id")
                            plan_id = tool_meta.get("plan_id") or identifiers.get("plan_id")
                            agent_name = tool_meta.get("agent_name")

                            structured_event = _tool_output_to_stream_event(tool_name, parsed)
                            if structured_event:
                                structured_event["agent_name"] = agent_name
                                structured_event["node_name"] = node_name
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
                                "agent_name": agent_name,
                                "node_name": node_name,
                            }
            yield {"type": "done"}
        except Exception as exc:
            logger.error("[HydroAgent] chat_stream failed: %s", exc, exc_info=True)
            yield {"type": "error", "content": f"处理请求时出错：{exc}"}
            yield {"type": "done"}
        finally:
            ACTIVE_CONVERSATION_ID.set(None)

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
        logger.warning("[HydroAgent] Missing MCP tools: %s", ", ".join(missing))
    return selected


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
        # 结构化工具结果压平后再进入时间线，方便前端展示最近一步摘要。
        text = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    elif hasattr(payload, "content"):
        text = _stringify_event_payload(payload.content, limit=limit)
    else:
        text = str(payload)
    return text if len(text) <= limit else f"{text[:limit]}..."


def _get_message_agent_name(message: Any, default: str | None = None) -> str | None:
    agent_name = getattr(message, "name", None)
    return str(agent_name) if isinstance(agent_name, str) and agent_name else default


def _should_emit_assistant_text(message: Any, metadata: dict[str, Any] | None) -> bool:
    if not isinstance(metadata, dict):
        return False
    if metadata.get("langgraph_node") != "model":
        return False
    agent_name = metadata.get("langgraph_name") or metadata.get("lc_agent_name")
    return agent_name in {None, "", "hydro-supervisor"}


def _iter_stream_text(message: Any):
    content_blocks = getattr(message, "content_blocks", None)
    if not isinstance(content_blocks, list):
        return
    for block in content_blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "text":
            continue
        text = block.get("text")
        if isinstance(text, str) and text:
            yield text


def _extract_tool_message_payload(message: Any) -> Any:
    artifact = getattr(message, "artifact", None)
    if isinstance(artifact, dict):
        structured = artifact.get("structured_content")
        if isinstance(structured, dict) and "result" in structured:
            return structured.get("result")

    content_blocks = getattr(message, "content_blocks", None)
    if isinstance(content_blocks, list):
        texts = [
            block.get("text")
            for block in content_blocks
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
        ]
        if len(texts) == 1:
            return texts[0]
        if texts:
            return "\n".join(texts)

    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    return str(content or "")


def _tool_output_to_stream_event(tool_name: str, payload: dict | None) -> dict | None:
    if not payload:
        return None

    has_plan_identity = isinstance(payload.get("plan_id"), str) and bool(str(payload.get("plan_id")).strip())

    if tool_name == "create_irrigation_plan" and has_plan_identity:
        return {"type": "plan_proposed", "plan": payload}
    if tool_name == "get_plan_status" and has_plan_identity:
        return {"type": "plan_updated", "plan": payload}
    if tool_name == "approve_irrigation_plan" and has_plan_identity:
        return {"type": "approval_result", "plan": payload, "decision": "approved"}
    if tool_name == "reject_irrigation_plan" and has_plan_identity:
        return {"type": "approval_result", "plan": payload, "decision": "rejected"}
    if tool_name == "execute_approved_plan" and has_plan_identity:
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
