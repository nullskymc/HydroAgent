"""
HydroAgent Middleware — Reflection & Context Injection
实现 Planning-Reflection-Execution (PRE) 循环的核心中间件
"""
import json
import datetime
import logging

logger = logging.getLogger("hydroagent.middleware")


class ReflectionMiddleware:
    """
    反思中间件 —— 在关键决策（如控制灌溉）执行后触发自我评估。
    """
    
    def __init__(self):
        self.decision_log = []
    
    def on_tool_end(self, tool_name: str, tool_args: dict, tool_result: str):
        """在工具调用结束后触发"""
        if tool_name == "control_irrigation" and tool_args.get("action") == "start":
            self._log_reflection(tool_args, tool_result)
    
    def _log_reflection(self, tool_args: dict, tool_result: str):
        """记录灌溉决策反思"""
        reflection = {
            "timestamp": datetime.datetime.now().isoformat(),
            "tool": "control_irrigation",
            "action": tool_args.get("action"),
            "duration_minutes": tool_args.get("duration_minutes", 30),
            "reflection": (
                f"灌溉决策已执行：计划灌溉 {tool_args.get('duration_minutes', 30)} 分钟。"
                "建议在灌溉开始后 30 分钟内复查土壤湿度，验证效果是否达到目标。"
            ),
        }
        self.decision_log.append(reflection)
        logger.info(f"[ReflectionMiddleware] 决策反思已记录: {json.dumps(reflection, ensure_ascii=False)}")
        self._persist_reflection(reflection)
    
    def _persist_reflection(self, reflection: dict):
        """将反思记录持久化到数据库"""
        try:
            from src.llm.persistence import get_hydro_persistence

            get_hydro_persistence().record_decision_sync(
                {
                    "decision_id": f"decision_reflect_{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                    "trigger": "chat",
                    "zone_id": None,
                    "plan_id": None,
                    "input_context": {"tool": reflection["tool"]},
                    "reasoning_chain": "ReflectionMiddleware captured a post-execution note.",
                    "tools_used": [reflection["tool"]],
                    "decision_result": {"action": reflection["action"]},
                    "reflection_notes": reflection["reflection"],
                    "effectiveness_score": None,
                    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
            )
        except Exception as e:
            logger.warning(f"[ReflectionMiddleware] 持久化失败: {e}")


class HydroContextMiddleware:
    """
    水利上下文注入中间件 —— 在每次调用 LLM 前，自动注入最新传感器摘要。
    """
    
    def get_context_summary(self) -> str:
        """获取当前系统状态摘要"""
        try:
            from src.data.data_collection import DataCollectionModule
            collector = DataCollectionModule()
            data = collector.get_data()["data"]
            moisture = data.get("soil_moisture", 0)
            temp = data.get("temperature", 0)
            status = (
                "⚠️ 严重缺水" if moisture < 25 else
                "🟡 湿度偏低" if moisture < 40 else
                "✅ 湿度正常" if moisture < 70 else
                "💧 湿度充足"
            )
            return (
                f"[实时环境 {datetime.datetime.now().strftime('%H:%M')}] "
                f"土壤湿度 {moisture}% ({status}), 温度 {temp}°C"
            )
        except Exception:
            return f"[实时环境 {datetime.datetime.now().strftime('%H:%M')}] 传感器数据暂不可用"
    
    def inject_into_system_prompt(self, base_prompt: str) -> str:
        """将环境状态摘要注入到系统提示"""
        summary = self.get_context_summary()
        return f"{base_prompt}\n\n{summary}"
