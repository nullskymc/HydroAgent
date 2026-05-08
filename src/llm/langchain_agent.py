"""
HydroAgent 单执行内核 LangChain harness。
"""
from __future__ import annotations

import inspect
import json
import logging
import os
import re
import sys
import time
from typing import Any, AsyncIterator, Optional

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI

from src.llm.agent_runtime import HydroAgentMode, build_system_prompt, resolve_phase
from src.llm.persistence import get_hydro_persistence
from src.llm.tool_argument_parser import ACTIVE_CONVERSATION_ID, ToolArgumentParserAgent, wrap_tool_registry

logger = logging.getLogger("hydroagent.agent")

_ZONE_ID_PATTERN = re.compile(r"\bzone_[a-zA-Z0-9]+\b")
_PLAN_ID_PATTERN = re.compile(r"\bplan_[a-zA-Z0-9]+\b")


class HydroChatOpenAI(ChatOpenAI):
    """ChatOpenAI variant that preserves DeepSeek reasoning_content across turns."""

    async def _astream(self, messages: list[Any], *args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        async for chunk in super()._astream(_sanitize_chat_messages(messages), *args, **kwargs):
            yield chunk

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ):
        generation_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if generation_chunk is not None:
            choices = chunk.get("choices", []) or chunk.get("chunk", {}).get("choices", [])
            if choices:
                delta = choices[0].get("delta") or {}
                rc = delta.get("reasoning_content")
                if rc and isinstance(rc, str):
                    generation_chunk.message.additional_kwargs["reasoning_content"] = rc
        return generation_chunk

    def _create_chat_result(self, response, generation_info=None):
        result = super()._create_chat_result(response, generation_info)
        response_dict = response if isinstance(response, dict) else response.model_dump()
        choices = response_dict.get("choices", [])
        for i, choice in enumerate(choices):
            msg = choice.get("message", {})
            rc = msg.get("reasoning_content")
            if rc and isinstance(rc, str) and i < len(result.generations):
                result.generations[i].message.additional_kwargs["reasoning_content"] = rc
        return result

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        if "messages" in payload:
            msgs = self._convert_input(input_).to_messages()
            for msg, msg_dict in zip(msgs, payload["messages"]):
                if msg_dict.get("role") == "assistant":
                    rc = msg.additional_kwargs.get("reasoning_content")
                    if isinstance(rc, str) and rc.strip():
                        msg_dict["reasoning_content"] = rc
        return payload


class HydroDeepAgent:
    """Official LangChain agent wrapper with MCP tools and SSE-friendly event conversion."""

    def __init__(self):
        self._mcp_client = None
        self._initialized = False
        self._workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self._checkpointer = None
        self._tool_registry: dict[str, Any] = {}
        self._parser_agent: ToolArgumentParserAgent | None = None
        self._llm: ChatOpenAI | None = None
        self._compiled_agents: dict[tuple[str, tuple[str, ...]], Any] = {}

    async def initialize(self):
        if self._initialized:
            return

        from src.config import config

        workspace_dir = os.path.join(self._workspace_root, ".hydro_workspace")
        os.makedirs(workspace_dir, exist_ok=True)
        persistence = get_hydro_persistence()
        await persistence.initialize()
        self._checkpointer = persistence.async_saver

        self._llm = HydroChatOpenAI(
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
        base_registry = {
            tool_name: tool_instance for tool_instance in mcp_tools if (tool_name := getattr(tool_instance, "name", None))
        }
        self._parser_agent = ToolArgumentParserAgent(llm=self._llm)
        self._tool_registry = wrap_tool_registry(base_registry, self._parser_agent)
        custom_tools = _build_custom_tools()
        for custom_tool in custom_tools:
            self._tool_registry[getattr(custom_tool, "name")] = custom_tool
        logger.info("[HydroAgent] Loaded %s MCP tools", len(mcp_tools))

        self._initialized = True
        logger.info("[HydroAgent] Runtime initialized")

    async def chat_stream(
        self,
        messages: list[dict],
        *,
        conversation_id: str | None = None,
        mode: HydroAgentMode = "planner",
        runtime_context: dict[str, Any] | None = None,
        working_memory: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict]:
        if not self._initialized:
            await self.initialize()

        runtime_context = runtime_context or {}
        compiled_agent = self._get_or_create_agent(mode=mode, runtime_context=runtime_context)

        lc_messages = [SystemMessage(content=_build_runtime_context_message(mode, runtime_context, working_memory))]
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if role == "assistant":
                rc = message.get("reasoning_content")
                additional_kwargs = {"reasoning_content": rc} if rc and isinstance(rc, str) else {}
                lc_messages.append(AIMessage(content=content, additional_kwargs=additional_kwargs))
            else:
                lc_messages.append(HumanMessage(content=content))

        input_data = {"messages": lc_messages}
        config = {"configurable": {"thread_id": conversation_id or "hydro-default"}}
        active_tool_calls: dict[str, dict[str, Any]] = {}
        ACTIVE_CONVERSATION_ID.set(conversation_id)
        active_skill_ids = list(runtime_context.get("active_skill_ids") or [])
        phase_overrides = runtime_context.get("phase_overrides") or {}

        try:
            async for chunk in compiled_agent.astream(
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
                                "active_skills": active_skill_ids,
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
                                phase = resolve_phase(tool_name, phase_overrides)

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
                                    "phase": phase,
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
                                    "phase": phase,
                                    "active_skills": active_skill_ids,
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
                            phase = tool_meta.get("phase") or resolve_phase(tool_name, phase_overrides)

                            structured_event = _tool_output_to_stream_event(tool_name, parsed)
                            if structured_event:
                                structured_event["agent_name"] = agent_name
                                structured_event["node_name"] = node_name
                                structured_event["phase"] = phase
                                structured_event["active_skills"] = active_skill_ids
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
                                "phase": phase,
                                "active_skills": active_skill_ids,
                                "agent_name": agent_name,
                                "node_name": node_name,
                            }
            yield {"type": "done", "active_skills": active_skill_ids}
        except Exception as exc:
            logger.error("[HydroAgent] chat_stream failed: %s", exc, exc_info=True)
            yield {"type": "error", "content": f"处理请求时出错：{exc}", "active_skills": active_skill_ids}
            yield {"type": "done", "active_skills": active_skill_ids}
        finally:
            ACTIVE_CONVERSATION_ID.set(None)

    async def chat(
        self,
        messages: list[dict],
        *,
        conversation_id: str | None = None,
        mode: HydroAgentMode = "planner",
        runtime_context: dict[str, Any] | None = None,
        working_memory: dict[str, Any] | None = None,
    ) -> str:
        parts = []
        async for chunk in self.chat_stream(
            messages,
            conversation_id=conversation_id,
            mode=mode,
            runtime_context=runtime_context,
            working_memory=working_memory,
        ):
            if chunk["type"] == "text":
                parts.append(chunk["content"])
        return "".join(parts)

    async def auto_check(self) -> str:
        from src.database.models import SessionLocal
        from src.services import create_auto_plan_if_needed, list_zones

        db = SessionLocal()
        try:
            results = []
            for zone in list_zones(db):
                if not zone.is_enabled:
                    continue
                results.append(create_auto_plan_if_needed(db, zone.zone_id))
            return json.dumps({"generated_plans": results}, ensure_ascii=False)
        finally:
            db.close()

    async def cleanup(self):
        closer = None
        if self._mcp_client is not None:
            closer = getattr(self._mcp_client, "aclose", None) or getattr(self._mcp_client, "close", None)
        if callable(closer):
            result = closer()
            if inspect.isawaitable(result):
                await result

        self._mcp_client = None
        self._tool_registry = {}
        self._compiled_agents = {}
        self._parser_agent = None
        self._llm = None
        self._initialized = False
        self._checkpointer = None

    async def reload(self):
        """在设置变更后热重载 Agent，确保新 key / endpoint / model 立即生效。"""
        await self.cleanup()
        await self.initialize()

    def _get_or_create_agent(self, *, mode: HydroAgentMode, runtime_context: dict[str, Any]):
        if not self._llm:
            raise RuntimeError("HydroAgent 尚未初始化 LLM")
        cache_key = (mode, tuple(sorted(runtime_context.get("active_skill_ids") or [])))
        cached = self._compiled_agents.get(cache_key)
        if cached is not None:
            return cached

        allowed_tools = runtime_context.get("allowed_tools") or []
        prompt_fragments = runtime_context.get("prompt_fragments") or []
        compiled = create_agent(
            model=self._llm,
            tools=_select_tools(self._tool_registry, tuple(allowed_tools)),
            system_prompt=build_system_prompt(mode, prompt_fragments),
            checkpointer=self._checkpointer,
            name="hydro-supervisor",
        )
        self._compiled_agents[cache_key] = compiled
        return compiled


def _build_runtime_context_message(mode: HydroAgentMode, runtime_context: dict[str, Any], working_memory: dict[str, Any] | None) -> str:
    safe_memory = working_memory or {}
    safe_context = {
        "inferred_mode": mode,
        "active_skill_ids": runtime_context.get("active_skill_ids") or [],
        "skill_reason": runtime_context.get("reason") or "",
        "skill_conflicts": runtime_context.get("conflicts") or [],
        "skill_resources": runtime_context.get("resources") or [],
        "workflow_phases": runtime_context.get("workflow_phases") or [],
        "working_memory": {
            "active_zone_ids": safe_memory.get("active_zone_ids") or [],
            "latest_plan_ids": safe_memory.get("latest_plan_ids") or [],
            "latest_pending_plan_ids": safe_memory.get("latest_pending_plan_ids") or [],
            "latest_approved_plan_ids": safe_memory.get("latest_approved_plan_ids") or [],
            "open_risks": safe_memory.get("open_risks") or [],
            "last_user_goal": safe_memory.get("last_user_goal") or "",
            "last_decision_summary": safe_memory.get("last_decision_summary") or "",
            "last_sensor_anomalies": safe_memory.get("last_sensor_anomalies") or [],
        },
    }
    # 将工作记忆与 skill 元数据以单独 system message 注入，避免把这类上下文写死到模式 prompt 中。
    return "当前回合运行时上下文如下，请仅将其作为约束和线索，不要原样复述给用户：\n" + json.dumps(
        safe_context,
        ensure_ascii=False,
        indent=2,
    )


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
        tool_instance = tool_registry.get(name)
        if tool_instance is None:
            missing.append(name)
            continue
        selected.append(tool_instance)
    if missing:
        logger.warning("[HydroAgent] Missing tools: %s", ", ".join(missing))
    return selected


def _build_custom_tools() -> list[Any]:
    @tool("search_knowledge_base")
    def search_knowledge_base_tool(question: str, top_k: int = 4) -> dict[str, Any]:
        """查询本地知识库，用于补充设备文档、SOP、项目约束与背景知识。"""
        from src.knowledge import KnowledgeBaseError, search_knowledge_base

        try:
            payload = search_knowledge_base(question, limit=top_k)
        except KnowledgeBaseError as exc:
            return {"query": question, "results": [], "error": str(exc)}

        results = payload.get("results") or []
        return {
            "query": question,
            "result_count": len(results),
            "results": [
                {
                    "document_id": item.get("document_id"),
                    "title": item.get("title"),
                    "source_uri": item.get("source_uri"),
                    "chunk_index": item.get("chunk_index"),
                    "score": item.get("score"),
                    "content": item.get("content"),
                }
                for item in results
            ],
        }

    return [search_knowledge_base_tool]


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
        text = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    elif hasattr(payload, "content"):
        text = _stringify_event_payload(payload.content, limit=limit)
    else:
        text = str(payload)
    return text if len(text) <= limit else f"{text[:limit]}..."


def _sanitize_chat_messages(messages: list[Any]) -> list[Any]:
    sanitized = []
    for message in messages:
        content = getattr(message, "content", None)
        if isinstance(content, str) or content is None:
            sanitized.append(message)
            continue

        replacement = _coerce_message_content_to_text(content)
        copier = getattr(message, "model_copy", None)
        if callable(copier):
            sanitized.append(copier(update={"content": replacement}))
            continue
        legacy_copier = getattr(message, "copy", None)
        if callable(legacy_copier):
            sanitized.append(legacy_copier(update={"content": replacement}))
            continue

        message.content = replacement
        sanitized.append(message)
    return sanitized


def _coerce_message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    if isinstance(content, list):
        text_blocks = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                text_blocks.append(item["text"])
                continue
            text = getattr(item, "text", None)
            if isinstance(text, str):
                text_blocks.append(text)
        if text_blocks and len(text_blocks) == len(content):
            return "\n".join(text_blocks)
    try:
        return json.dumps(content, ensure_ascii=False, default=str)
    except Exception:
        return str(content)


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

    result_plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else None
    has_embedded_plan_identity = isinstance((result_plan or {}).get("plan_id"), str) and bool(str(result_plan.get("plan_id")).strip())
    has_plan_identity = isinstance(payload.get("plan_id"), str) and bool(str(payload.get("plan_id")).strip())
    suggestion = payload.get("suggestion") if isinstance(payload.get("suggestion"), dict) else None
    has_suggestion_identity = isinstance((suggestion or {}).get("suggestion_id"), str) and bool(str(suggestion.get("suggestion_id")).strip())

    if tool_name == "create_irrigation_plan" and payload.get("suggestion_only") and has_suggestion_identity:
        return {"type": "suggestion_result", "suggestion": suggestion}
    if tool_name == "create_irrigation_plan" and has_embedded_plan_identity:
        return {"type": "plan_updated" if payload.get("reused_existing") else "plan_proposed", "plan": result_plan}
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
