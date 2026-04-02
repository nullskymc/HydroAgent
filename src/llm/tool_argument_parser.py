"""
Tool argument normalization layer for HydroAgent MCP tools.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict

from src.database.models import SessionLocal
from src.services.irrigation_service import list_plans, list_zones

logger = logging.getLogger("hydroagent.tool_parser")

_ZONE_TOOLS = {
    "query_sensor_data",
    "query_weather",
    "get_zone_operating_status",
    "create_irrigation_plan",
    "control_irrigation",
    "recommend_irrigation_plan",
    "execute_approved_plan",
    "approve_irrigation_plan",
    "reject_irrigation_plan",
    "get_plan_status",
}

_PLAN_TOOLS = {
    "get_plan_status",
    "approve_irrigation_plan",
    "reject_irrigation_plan",
    "execute_approved_plan",
}


class ParsedToolArguments(BaseModel):
    """Structured output from the parser sub-agent."""

    canonical_args: dict[str, Any]
    confidence: float = 0.0
    rationale: str = ""


class ToolArgumentParserAgent:
    """Normalize human-style tool arguments into canonical backend identifiers."""

    def __init__(self, llm: ChatOpenAI | None = None):
        self._llm = llm
        self._structured_llm = llm.with_structured_output(ParsedToolArguments) if llm else None
        self._cache: dict[str, Any] = {}

    def normalize_sync(self, tool_name: str, tool_input: Any) -> Any:
        if not isinstance(tool_input, dict):
            return tool_input

        cache_key = self._build_cache_key(tool_name, tool_input)
        if cache_key in self._cache:
            return self._cache[cache_key]

        catalog = self._load_catalog()
        normalized = self._normalize_locally(tool_name, tool_input, catalog)
        self._cache[cache_key] = normalized
        return normalized

    async def normalize_async(self, tool_name: str, tool_input: Any) -> Any:
        if not isinstance(tool_input, dict):
            return tool_input

        cache_key = self._build_cache_key(tool_name, tool_input)
        if cache_key in self._cache:
            return self._cache[cache_key]

        catalog = self._load_catalog()
        normalized = self._normalize_locally(tool_name, tool_input, catalog)
        if normalized != tool_input:
            self._cache[cache_key] = normalized
            return normalized

        if not self._structured_llm:
            self._cache[cache_key] = normalized
            return normalized

        try:
            parsed = await self._structured_llm.ainvoke(
                [
                    (
                        "system",
                        "You are a parameter parser sub-agent for irrigation tools. "
                        "Map friendly zone references to canonical zone_id values and only use IDs from the catalog. "
                        "Never invent ids. If you are unsure, return the original arguments unchanged.",
                    ),
                    (
                        "user",
                        json.dumps(
                            {
                                "tool_name": tool_name,
                                "incoming_args": tool_input,
                                "catalog": catalog,
                                "requirements": {
                                    "zone_id": "Prefer exact zone_id. Map plain ordinals like '2' or phrases like '分区 2' to the matching zone_id when obvious.",
                                    "plan_id": "Preserve existing plan_id unless the catalog contains a clear exact match.",
                                },
                            },
                            ensure_ascii=False,
                        ),
                    ),
                ]
            )
        except Exception as exc:
            logger.warning("[HydroAgent] parser sub-agent failed for %s: %s", tool_name, exc)
            self._cache[cache_key] = normalized
            return normalized

        candidate = dict(parsed.canonical_args or {})
        resolved = self._normalize_locally(tool_name, candidate, catalog)
        final_result = resolved if self._is_catalog_safe(tool_name, resolved, catalog) else normalized
        self._cache[cache_key] = final_result
        return final_result

    def _load_catalog(self) -> dict[str, list[dict[str, str]]]:
        db = SessionLocal()
        try:
            zones = list_zones(db)
            plans = list_plans(db, limit=20)
            return {
                "zones": [
                    {
                        "zone_id": zone.zone_id,
                        "name": zone.name,
                        "ordinal": str(index),
                    }
                    for index, zone in enumerate(zones, start=1)
                ],
                "plans": [
                    {
                        "plan_id": plan.plan_id,
                        "zone_id": plan.zone_id or "",
                    }
                    for plan in plans
                ],
            }
        finally:
            db.close()

    def _normalize_locally(self, tool_name: str, tool_input: dict[str, Any], catalog: dict[str, list[dict[str, str]]]) -> dict[str, Any]:
        normalized = dict(tool_input)

        if tool_name in _ZONE_TOOLS and "zone_id" in normalized:
            raw_zone = str(normalized.get("zone_id") or "").strip()
            resolved_zone = self._resolve_zone_id(raw_zone, catalog["zones"])
            if resolved_zone:
                # 先做本地确定性映射，拦住“2 -> zone_xxx”这类高频错误。
                normalized["zone_id"] = resolved_zone

        if tool_name in _PLAN_TOOLS and "plan_id" in normalized:
            raw_plan = str(normalized.get("plan_id") or "").strip()
            resolved_plan = self._resolve_plan_id(raw_plan, catalog["plans"])
            if resolved_plan:
                normalized["plan_id"] = resolved_plan

        return normalized

    def _is_catalog_safe(self, tool_name: str, tool_input: dict[str, Any], catalog: dict[str, list[dict[str, str]]]) -> bool:
        if tool_name in _ZONE_TOOLS and "zone_id" in tool_input:
            zone_ids = {item["zone_id"] for item in catalog["zones"]}
            if str(tool_input["zone_id"]) not in zone_ids:
                return False

        if tool_name in _PLAN_TOOLS and "plan_id" in tool_input:
            plan_ids = {item["plan_id"] for item in catalog["plans"]}
            if str(tool_input["plan_id"]) not in plan_ids:
                return False

        return True

    def _resolve_zone_id(self, raw_value: str, zones: list[dict[str, str]]) -> str | None:
        if not raw_value:
            return None

        zone_by_id = {item["zone_id"]: item["zone_id"] for item in zones}
        if raw_value in zone_by_id:
            return raw_value

        normalized_name = self._normalize_label(raw_value)
        for item in zones:
            if normalized_name == self._normalize_label(item["name"]):
                return item["zone_id"]

        ordinal_match = re.search(r"(\d+)$", normalized_name)
        if ordinal_match:
            ordinal = ordinal_match.group(1)
            for item in zones:
                if ordinal == item["ordinal"]:
                    return item["zone_id"]

        return None

    def _resolve_plan_id(self, raw_value: str, plans: list[dict[str, str]]) -> str | None:
        if not raw_value:
            return None

        plan_by_id = {item["plan_id"]: item["plan_id"] for item in plans}
        if raw_value in plan_by_id:
            return raw_value

        if raw_value.startswith("plan_"):
            for plan_id in plan_by_id:
                if plan_id.startswith(raw_value):
                    return plan_id

        return None

    def _normalize_label(self, value: str) -> str:
        text = value.strip().lower()
        text = text.replace("-", " ").replace("_", " ")
        text = re.sub(r"\s+", " ", text)
        text = text.replace("zone ", "分区 ")
        return text

    def _build_cache_key(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        try:
            serialized = json.dumps(tool_input, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            serialized = str(tool_input)
        return f"{tool_name}:{serialized}"


class NormalizedToolProxy(BaseTool):
    """Proxy a tool and normalize arguments before actual execution."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    wrapped_tool: Any
    parser_agent: ToolArgumentParserAgent
    args_schema: Any = None

    def invoke(self, input: str | dict | Any, config: Any = None, **kwargs: Any) -> Any:
        normalized = self.parser_agent.normalize_sync(self.name, input)
        return self.wrapped_tool.invoke(normalized, config=config, **kwargs)

    async def ainvoke(self, input: str | dict | Any, config: Any = None, **kwargs: Any) -> Any:
        normalized = await self.parser_agent.normalize_async(self.name, input)
        return await self.wrapped_tool.ainvoke(normalized, config=config, **kwargs)

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        packed = kwargs if kwargs else (args[0] if len(args) == 1 else list(args))
        return self.invoke(packed)

    async def _arun(self, *args: Any, **kwargs: Any) -> Any:
        packed = kwargs if kwargs else (args[0] if len(args) == 1 else list(args))
        return await self.ainvoke(packed)


def wrap_tool_registry(tool_registry: dict[str, Any], parser_agent: ToolArgumentParserAgent) -> dict[str, Any]:
    wrapped: dict[str, Any] = {}
    for name, tool in tool_registry.items():
        wrapped[name] = NormalizedToolProxy(
            name=name,
            description=getattr(tool, "description", ""),
            wrapped_tool=tool,
            parser_agent=parser_agent,
            args_schema=getattr(tool, "args_schema", None),
        )
    return wrapped
