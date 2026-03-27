"""
HydroAgent LangChain Agent — Deep Agent + MCP Client 实现
使用 LangChain + LangGraph 构建水利灌溉智能体
"""
import asyncio
import logging
import os
import random
import datetime
import json
from typing import AsyncIterator, Optional

logger = logging.getLogger("hydroagent.agent")

# ============================================================
#  水利专业系统提示词
# ============================================================
HYDRO_SYSTEM_PROMPT = """你是 HydroAgent，一个专业的水利灌溉智能决策助手。

## 你的专业能力
你可以通过工具完成以下水利管理任务：
- **传感器查询**：获取土壤湿度、温度、光照、降雨数据
- **天气分析**：查询实时天气和预报，评估灌溉时机
- **灌溉控制**：启动/停止灌溉设备
- **数据科学分析**：统计分析、异常检测、时序预测、相关性分析
- **决策推荐**：综合多源数据，给出专业灌溉建议

## 决策原则
1. 土壤湿度 < 25% 紧急灌溉，25%-40% 建议灌溉，> 40% 暂缓
2. 有降雨预报时，推迟灌溉
3. 优先选择蒸发量低的时段（清晨 6-8 时）
4. 每次建议前先用数据分析工具验证
5. 执行灌溉控制前，主动确认用户意图

## 回答要求
- 用中文回答，引用具体数值
- 工具调用后及时解读结果
- 多轮对话中保持上下文连贯
- 复杂决策分步骤展示推理过程
"""


# ============================================================
#  HydroAgent 核心类
# ============================================================

class HydroLangChainAgent:
    """
    HydroAgent 水利灌溉深度智能体
    
    架构：LangChain create_react_agent + MCP Client + Middleware PRE循环
    """
    
    def __init__(self):
        self._agent = None
        self._mcp_client = None
        self._initialized = False
        self.reflection_middleware = None
        self.context_middleware = None
    
    async def initialize(self):
        """异步初始化 Agent"""
        if self._initialized:
            return
        
        try:
            from src.config import config
            from src.llm.middleware import ReflectionMiddleware, HydroContextMiddleware
            
            self.reflection_middleware = ReflectionMiddleware()
            self.context_middleware = HydroContextMiddleware()
            
            # 尝试用 MCP 适配器加载工具
            try:
                from langchain_mcp_adapters.client import MultiServerMCPClient
                from langgraph.prebuilt import create_react_agent
                from langchain_openai import ChatOpenAI
                
                llm = ChatOpenAI(
                    model=config.MODEL_NAME,
                    openai_api_key=config.OPENAI_API_KEY,
                    openai_api_base=config.OPENAI_BASE_URL,
                    temperature=0.3,
                    streaming=True,
                )
                
                self._mcp_client = MultiServerMCPClient({
                    "hydro": {
                        "transport": "stdio",
                        "command": "python",
                        "args": [config.MCP_SERVER_PATH],
                    }
                })
                
                mcp_tools = await self._mcp_client.get_tools()
                logger.info(f"[HydroAgent] 从 MCP Server 加载了 {len(mcp_tools)} 个工具")
                
                enhanced_prompt = self.context_middleware.inject_into_system_prompt(HYDRO_SYSTEM_PROMPT)
                
                self._agent = create_react_agent(
                    model=llm,
                    tools=mcp_tools,
                    prompt=enhanced_prompt,
                )
                logger.info(f"[HydroAgent] Agent 初始化完成（MCP 模式），模型: {config.MODEL_NAME}")
                self._initialized = True
                return
            except ImportError as e:
                logger.warning(f"[HydroAgent] MCP 适配器不可用: {e}，降级到直接工具模式")
            except Exception as e:
                logger.warning(f"[HydroAgent] MCP 初始化失败: {e}，降级到直接工具模式")
            
            # 降级方案：不使用 MCP，直接定义工具
            await self._initialize_fallback()
            
        except Exception as e:
            logger.error(f"[HydroAgent] 初始化失败: {e}", exc_info=True)
            await self._initialize_fallback()
    
    async def _initialize_fallback(self):
        """降级初始化：使用 @tool 直接定义工具"""
        try:
            from langchain_openai import ChatOpenAI
            from langchain.tools import tool
            from src.config import config
            
            llm = ChatOpenAI(
                model=config.MODEL_NAME,
                openai_api_key=config.OPENAI_API_KEY,
                openai_api_base=config.OPENAI_BASE_URL,
                temperature=0.3,
                streaming=True,
            )
            
            @tool
            def query_sensor_data(sensor_id: str = "all") -> str:
                """查询传感器实时数据：土壤湿度、温度、光照强度、降雨量"""
                data = {
                    "soil_moisture": round(random.uniform(25, 65), 2),
                    "temperature": round(random.uniform(18, 35), 2),
                    "light_intensity": round(random.uniform(200, 800), 2),
                    "rainfall": round(random.uniform(0, 2), 2),
                }
                moisture = data["soil_moisture"]
                status = ("⚠️ 严重缺水" if moisture < 25 else "🟡 偏低" if moisture < 40
                          else "✅ 正常" if moisture < 70 else "💧 充足")
                return json.dumps({"sensor_id": sensor_id, "timestamp": datetime.datetime.now().isoformat(),
                                   "readings": data, "status_assessment": status}, ensure_ascii=False)
            
            @tool
            def query_weather(city: str = "北京") -> str:
                """查询天气预报"""
                return json.dumps({"city": city, "weather": random.choice(["晴", "多云", "阴"]),
                                   "temperature": random.randint(22, 32),
                                   "note": "需配置高德 API 获取真实天气"}, ensure_ascii=False)
            
            @tool
            def control_irrigation(action: str, duration_minutes: int = 30) -> str:
                """控制灌溉设备：action='start'|'stop'|'status'"""
                return json.dumps({"success": True, "action": action,
                                   "message": f"已执行: {action}"}, ensure_ascii=False)
            
            @tool
            def statistical_analysis(data_type: str = "soil_moisture", hours: int = 24) -> str:
                """对传感器数据进行统计分析，返回均值、趋势等"""
                import numpy as np
                values = [round(random.uniform(30, 60), 2) for _ in range(hours * 4)]
                arr = np.array(values)
                return json.dumps({
                    "data_type": data_type, "period": f"最近 {hours} 小时",
                    "mean": round(float(arr.mean()), 2), "std": round(float(arr.std()), 2),
                    "min": round(float(arr.min()), 2), "max": round(float(arr.max()), 2),
                    "trend": "稳定"
                }, ensure_ascii=False)
            
            @tool
            def recommend_irrigation_plan() -> str:
                """综合分析当前数据，推荐灌溉方案"""
                moisture = round(random.uniform(25, 60), 2)
                needs = moisture < 40
                return json.dumps({
                    "current_moisture": f"{moisture}%",
                    "needs_irrigation": needs,
                    "recommendation": f"启动灌溉 30 分钟" if needs else "暂不需要灌溉",
                    "urgency": "建议" if needs else "无需",
                }, ensure_ascii=False)
            
            tools = [query_sensor_data, query_weather, control_irrigation,
                     statistical_analysis, recommend_irrigation_plan]
            
            enhanced_prompt = HYDRO_SYSTEM_PROMPT
            if self.context_middleware:
                enhanced_prompt = self.context_middleware.inject_into_system_prompt(HYDRO_SYSTEM_PROMPT)
            
            try:
                from langgraph.prebuilt import create_react_agent
                self._agent = create_react_agent(
                    model=llm, tools=tools, prompt=enhanced_prompt,
                )
            except ImportError:
                # 最终降级：使用 AgentExecutor
                from langchain.agents import AgentExecutor, create_tool_calling_agent
                from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
                prompt = ChatPromptTemplate.from_messages([
                    ("system", enhanced_prompt),
                    MessagesPlaceholder("chat_history", optional=True),
                    ("human", "{input}"),
                    MessagesPlaceholder("agent_scratchpad"),
                ])
                agent = create_tool_calling_agent(llm, tools, prompt)
                self._agent = AgentExecutor(agent=agent, tools=tools, verbose=False)
            
            self._initialized = True
            logger.info("[HydroAgent] 降级模式初始化完成（直接工具）")
        except Exception as e:
            logger.error(f"[HydroAgent] 降级初始化失败: {e}", exc_info=True)
            self._initialized = False
    
    async def chat_stream(self, messages: list) -> AsyncIterator[dict]:
        """
        流式多轮对话 —— 输出事件：
        - {"type": "text", "content": "..."} 文本片段
        - {"type": "tool_call", "tool": "...", "args": {...}} 工具调用
        - {"type": "tool_result", "tool": "...", "result": "..."} 工具结果
        - {"type": "done"} 完成
        """
        if not self._initialized:
            await self.initialize()
        
        if not self._agent:
            yield {"type": "text", "content": "⚠️ Agent 初始化失败，请检查 OpenAI API Key 和网络配置。"}
            yield {"type": "done"}
            return
        
        try:
            from langchain.schema import HumanMessage, AIMessage, SystemMessage
            
            # 构造 LangChain 消息
            lc_messages = []
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    lc_messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    lc_messages.append(AIMessage(content=content))
            
            accumulated_text = ""
            
            # 判断 agent 类型
            is_agent_executor = type(self._agent).__name__ == "AgentExecutor"
            
            if hasattr(self._agent, 'astream_events'):
                # 根据不同 agent 类型组装正确的输入荷载
                if is_agent_executor:
                    last_user = messages[-1]["content"] if messages else ""
                    history_msgs = []
                    for m in messages[:-1]:
                        if m["role"] == "user":
                            history_msgs.append(HumanMessage(content=m["content"]))
                        elif m["role"] == "assistant":
                            history_msgs.append(AIMessage(content=m["content"]))
                    input_data = {"input": last_user, "chat_history": history_msgs}
                else:
                    input_data = {"messages": lc_messages}

                async for event in self._agent.astream_events(
                    input_data, version="v2"
                ):
                    kind = event.get("event", "")
                    
                    if kind == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        if chunk and hasattr(chunk, 'content') and chunk.content:
                            accumulated_text += chunk.content
                            yield {"type": "text", "content": chunk.content}
                    
                    elif kind == "on_tool_start":
                        tool_name = event.get("name", "unknown")
                        tool_input = event.get("data", {}).get("input", {})
                        yield {"type": "tool_call", "tool": tool_name, "args": tool_input}
                        if self.reflection_middleware:
                            self.reflection_middleware.on_tool_end(tool_name, tool_input, "")
                    
                    elif kind == "on_tool_end":
                        tool_name = event.get("name", "unknown")
                        tool_output = str(event.get("data", {}).get("output", ""))
                        yield {"type": "tool_result", "tool": tool_name, "result": tool_output[:500]}
            
            elif hasattr(self._agent, 'ainvoke'):
                # 全量回退（极少数情况下无 stream_events）
                if is_agent_executor:
                    last_user = messages[-1]["content"] if messages else ""
                    history_msgs = []
                    for m in messages[:-1]:
                        if m["role"] == "user":
                            history_msgs.append(HumanMessage(content=m["content"]))
                        elif m["role"] == "assistant":
                            history_msgs.append(AIMessage(content=m["content"]))
                    result = await self._agent.ainvoke({"input": last_user, "chat_history": history_msgs})
                    output = result.get("output", str(result))
                else:
                    result = await self._agent.ainvoke({"messages": lc_messages})
                    output = str(result)
                yield {"type": "text", "content": output}
            
            yield {"type": "done"}
        
        except Exception as e:
            logger.error(f"[HydroAgent] 对话失败: {e}", exc_info=True)
            yield {"type": "text", "content": f"❌ 处理请求时出错：{str(e)}"}
            yield {"type": "done"}
    
    async def chat(self, messages: list) -> str:
        """非流式多轮对话"""
        full_response = []
        async for chunk in self.chat_stream(messages):
            if chunk["type"] == "text":
                full_response.append(chunk["content"])
        return "".join(full_response)
    
    async def auto_check(self) -> str:
        """定时自动灌溉检查"""
        auto_prompt = "请自动检查当前传感器数据、天气预报和历史趋势，判断是否需要灌溉。"
        messages = [{"role": "user", "content": auto_prompt}]
        result = await self.chat(messages)
        self._log_auto_decision(auto_prompt, result)
        return result
    
    def _log_auto_decision(self, prompt: str, result: str):
        try:
            from src.database.models import SessionLocal, AgentDecisionLog
            db = SessionLocal()
            db.add(AgentDecisionLog(
                trigger="auto",
                input_context={"prompt": prompt},
                decision_result={"response": result[:500]},
                reasoning_chain=result,
            ))
            db.commit()
            db.close()
        except Exception as e:
            logger.warning(f"[HydroAgent] 日志记录失败: {e}")
    
    async def cleanup(self):
        """清理 MCP 客户端连接"""
        if self._mcp_client:
            try:
                await self._mcp_client.__aexit__(None, None, None)
            except Exception:
                pass


# 全局单例
_hydro_agent: Optional[HydroLangChainAgent] = None

def get_hydro_agent() -> HydroLangChainAgent:
    """获取 HydroAgent 全局单例"""
    global _hydro_agent
    if _hydro_agent is None:
        _hydro_agent = HydroLangChainAgent()
    return _hydro_agent
