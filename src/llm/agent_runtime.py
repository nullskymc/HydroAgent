"""
HydroAgent mode policy, tool boundaries, and phase mapping.
"""
from __future__ import annotations

from typing import Literal

HydroAgentMode = Literal["advisor", "planner", "operator", "auditor"]
HydroPhase = Literal["evidence", "analysis", "planning", "approval", "execution", "audit"]

DEFAULT_AGENT_MODE: HydroAgentMode = "planner"
PHASE_ORDER: tuple[HydroPhase, ...] = ("evidence", "analysis", "planning", "approval", "execution", "audit")

BASE_SYSTEM_PROMPT = """你是 HydroAgent，一个面向多分区农场的审慎型智能灌溉系统。

你只能基于真实工具结果、计划状态和审批边界工作，绝不能编造分区、计划、审批状态或执行结果。

必须遵守以下原则：
1. 先收集证据，再给结论：优先读取农场上下文、分区状态、传感器、天气和历史计划。
2. 涉及分区级工具时，必须传入准确的 canonical zone_id，绝不能省略 zone_id。
3. 当用户只说“分区 1 / 2”或中文名称时，先调用 list_farm_zones 或 list_farm_context，再使用返回的 zone_id。
4. 当用户没有指定 zone 且请求是农场级任务时，先调用 list_farm_context，总结 enabled zone，再决定是否逐区深入。
5. 生成计划时，必须说明证据、风险、建议时长和是否需要审批。
6. 任何 start 行为都不能绕过审批边界；未批准计划不得执行。
7. 若天气提示未来 48 小时可能降雨，除非湿度进入 emergency band，否则优先建议 hold/defer。
8. 若执行器状态未知、禁用或已经运行，避免自动执行并明确提示风险。
9. 若传感器缺失或无效，生成 hold/defer 计划，而不是 start 计划。
10. 当问题涉及制度、操作手册、设备说明、农艺知识或项目内约定时，优先查询知识库，再基于检索结果回答。
11. 生成灌溉计划或回答预测类问题时，调用 predict_soil_moisture，并说明预测湿度、样本数量和置信度。

回答要求：
- 使用中文。
- 引用具体 zone_id、湿度、天气、风险级别和计划编号。
- 当请求涉及多个分区时，按分区逐个处理，不要把多个分区混成一个模糊结论。
- 当工具返回结构化数据时，优先复述关键字段，不要编造。
"""

MODE_PROMPTS: dict[HydroAgentMode, str] = {
    "advisor": """当前模式：advisor。
- 你只能做解释、分析、知识检索和状态判断。
- 你绝不能生成计划、审批计划或执行灌溉动作。
- 如果用户要求执行类动作，明确说明需要切换到更高权限模式。""",
    "planner": """当前模式：planner。
- 你可以收集证据、分析风险、生成计划、读取计划状态。
- 你绝不能审批计划或执行灌溉动作。
- 如果用户要求执行类动作，停在审批边界并说明后续步骤。""",
    "operator": """当前模式：operator。
- 你可以收集证据、生成计划、审批计划、执行已批准计划。
- 即使在 operator 模式下，也必须遵守计划先行和审批边界。
- 只有已批准的 start plan 才允许执行。""",
    "auditor": """当前模式：auditor。
- 你只能审计、追踪、回放、解释决策来源和系统状态。
- 你绝不能生成新计划、审批计划或执行灌溉动作。
- 优先说明 trace、decision、plan、approval 之间的因果链。""",
}

MODE_TOOL_ALLOWLIST: dict[HydroAgentMode, tuple[str, ...]] = {
    "advisor": (
        "list_farm_context",
        "list_farm_zones",
        "query_sensor_data",
        "query_weather",
        "get_zone_operating_status",
        "recommend_irrigation_plan",
        "predict_soil_moisture",
        "statistical_analysis",
        "anomaly_detection",
        "time_series_forecast",
        "correlation_analysis",
        "get_plan_status",
        "manage_alarm",
        "search_knowledge_base",
    ),
    "planner": (
        "list_farm_context",
        "list_farm_zones",
        "query_sensor_data",
        "query_weather",
        "get_zone_operating_status",
        "recommend_irrigation_plan",
        "predict_soil_moisture",
        "statistical_analysis",
        "anomaly_detection",
        "time_series_forecast",
        "correlation_analysis",
        "create_irrigation_plan",
        "get_plan_status",
        "manage_alarm",
        "search_knowledge_base",
    ),
    "operator": (
        "list_farm_context",
        "list_farm_zones",
        "query_sensor_data",
        "query_weather",
        "get_zone_operating_status",
        "recommend_irrigation_plan",
        "predict_soil_moisture",
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
        "search_knowledge_base",
    ),
    "auditor": (
        "list_farm_context",
        "list_farm_zones",
        "query_sensor_data",
        "query_weather",
        "get_zone_operating_status",
        "predict_soil_moisture",
        "statistical_analysis",
        "anomaly_detection",
        "time_series_forecast",
        "correlation_analysis",
        "get_plan_status",
        "search_knowledge_base",
    ),
}

DEFAULT_TOOL_PHASE_MAP: dict[str, HydroPhase] = {
    "list_farm_context": "evidence",
    "list_farm_zones": "evidence",
    "query_sensor_data": "evidence",
    "query_weather": "evidence",
    "get_zone_operating_status": "evidence",
    "predict_soil_moisture": "analysis",
    "recommend_irrigation_plan": "analysis",
    "statistical_analysis": "analysis",
    "anomaly_detection": "analysis",
    "time_series_forecast": "analysis",
    "correlation_analysis": "analysis",
    "create_irrigation_plan": "planning",
    "get_plan_status": "planning",
    "approve_irrigation_plan": "approval",
    "reject_irrigation_plan": "approval",
    "execute_approved_plan": "execution",
    "control_irrigation": "execution",
    "manage_alarm": "audit",
    "search_knowledge_base": "evidence",
}


def normalize_mode(value: str | None) -> HydroAgentMode:
    candidate = str(value or DEFAULT_AGENT_MODE).strip().lower()
    if candidate in MODE_TOOL_ALLOWLIST:
        return candidate  # type: ignore[return-value]
    return DEFAULT_AGENT_MODE


def mode_tool_names(mode: HydroAgentMode) -> tuple[str, ...]:
    return MODE_TOOL_ALLOWLIST[mode]


def build_system_prompt(mode: HydroAgentMode, skill_instructions: list[str] | None = None) -> str:
    sections = [BASE_SYSTEM_PROMPT, MODE_PROMPTS[mode]]
    if skill_instructions:
        clean_instructions = [item.strip() for item in skill_instructions if item and item.strip()]
        if clean_instructions:
            sections.append("当前激活的技能要求：\n" + "\n\n".join(clean_instructions))
    return "\n\n".join(sections)


def resolve_phase(tool_name: str, overrides: dict[str, HydroPhase] | None = None) -> HydroPhase:
    if overrides and tool_name in overrides:
        return overrides[tool_name]
    return DEFAULT_TOOL_PHASE_MAP.get(tool_name, "analysis")
