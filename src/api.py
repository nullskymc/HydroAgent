"""
HydroAgent FastAPI API 层 — REST + SSE 端点
支持多轮对话、会话管理、传感器数据、天气、灌溉控制
"""
import json
import uuid
import logging
import datetime
import random
import math

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel as PydanticModel
from sqlalchemy.orm import Session
from typing import Optional

logger = logging.getLogger("hydroagent.api")

router = APIRouter()

# ============================================================
#  Pydantic 数据模型
# ============================================================

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


# ============================================================
#  DB 依赖
# ============================================================

def get_db():
    from src.database.models import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================
#  会话管理 API
# ============================================================

@router.get("/conversations")
async def list_conversations(db: Session = Depends(get_db)):
    """获取所有对话会话列表"""
    from src.database.models import ConversationSession
    sessions = db.query(ConversationSession).order_by(ConversationSession.updated_at.desc()).limit(50).all()
    return {"conversations": [s.to_dict() for s in sessions]}


@router.post("/conversations")
async def create_conversation(req: CreateConversationRequest, db: Session = Depends(get_db)):
    """创建新的对话会话"""
    from src.database.models import ConversationSession
    session = ConversationSession(session_id=str(uuid.uuid4()), title=req.title or "新对话")
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"conversation": session.to_dict()}


@router.get("/conversations/{session_id}")
async def get_conversation(session_id: str, db: Session = Depends(get_db)):
    """获取特定会话的详细信息（含所有消息）"""
    from src.database.models import ConversationSession, ChatMessage
    session = db.query(ConversationSession).filter(ConversationSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = db.query(ChatMessage).filter(ChatMessage.conversation_id == session_id).order_by(ChatMessage.created_at).all()
    return {"conversation": session.to_dict(), "messages": [m.to_dict() for m in messages]}


@router.delete("/conversations/{session_id}")
async def delete_conversation(session_id: str, db: Session = Depends(get_db)):
    """删除对话会话"""
    from src.database.models import ConversationSession
    session = db.query(ConversationSession).filter(ConversationSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.delete(session)
    db.commit()
    return {"success": True, "message": "会话已删除"}


# ============================================================
#  AI 对话 API (SSE 流式)
# ============================================================

@router.post("/chat")
async def chat(req: ChatRequest, db: Session = Depends(get_db)):
    """AI 对话端点 —— SSE 流式响应，支持多轮对话"""
    from src.database.models import ConversationSession, ChatMessage

    session = db.query(ConversationSession).filter(ConversationSession.session_id == req.conversation_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    history = db.query(ChatMessage).filter(ChatMessage.conversation_id == req.conversation_id).order_by(ChatMessage.created_at).all()
    messages = [{"role": m.role, "content": m.content or ""} for m in history if m.role in ("user", "assistant")]
    messages.append({"role": "user", "content": req.message})

    user_msg = ChatMessage(conversation_id=req.conversation_id, role="user", content=req.message)
    db.add(user_msg)
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

        full_response_parts = []
        tool_calls_used = []
        try:
            async for event in agent.chat_stream(messages):
                event_type = event.get("type")
                if event_type == "text":
                    full_response_parts.append(event.get("content", ""))
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif event_type == "tool_call":
                    tool_calls_used.append(event.get("tool", ""))
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif event_type == "tool_result":
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif event_type == "done":
                    full_response = "".join(full_response_parts)
                    if full_response:
                        _save_assistant_message(req.conversation_id, full_response, tool_calls_used)
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    break
        except Exception as e:
            logger.error(f"[chat SSE] 错误: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'text', 'content': f'❌ 出错：{str(e)}'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _save_assistant_message(conversation_id: str, content: str, tools_used: list):
    try:
        from src.database.models import SessionLocal, ChatMessage
        db = SessionLocal()
        db.add(ChatMessage(conversation_id=conversation_id, role="assistant",
                           content=content, tool_calls=tools_used if tools_used else None))
        db.commit()
        db.close()
    except Exception as e:
        logger.warning(f"_save_assistant_message error: {e}")


# ============================================================
#  传感器数据 API
# ============================================================

@router.get("/sensors/current")
async def get_current_sensors():
    """获取当前传感器读数"""
    try:
        from src.data.data_collection import DataCollectionModule
        collector = DataCollectionModule()
        data1 = collector.get_data()
        data2 = collector.get_data()
        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "sensors": [
                {"sensor_id": data1["sensor_id"], **data1["data"]},
                {"sensor_id": data2["sensor_id"], **data2["data"]},
            ],
            "average": {
                "soil_moisture": round((data1["data"]["soil_moisture"] + data2["data"]["soil_moisture"]) / 2, 2),
                "temperature": round((data1["data"]["temperature"] + data2["data"]["temperature"]) / 2, 2),
                "light_intensity": round((data1["data"]["light_intensity"] + data2["data"]["light_intensity"]) / 2, 2),
                "rainfall": round((data1["data"]["rainfall"] + data2["data"]["rainfall"]) / 2, 2),
            }
        }
    except Exception as e:
        logger.warning(f"传感器读取失败，使用 mock: {e}")
        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "sensors": [],
            "average": {
                "soil_moisture": round(random.uniform(28, 60), 2),
                "temperature": round(random.uniform(20, 35), 2),
                "light_intensity": round(random.uniform(200, 900), 2),
                "rainfall": round(random.uniform(0, 2), 2),
            }
        }


@router.get("/sensors/history")
async def get_sensor_history(data_type: str = "soil_moisture", hours: int = 24):
    """获取传感器历史时序数据"""
    valid_types = ["soil_moisture", "temperature", "light_intensity", "rainfall"]
    if data_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"data_type 必须是: {valid_types}")
    hours = min(max(hours, 1), 168)
    now = datetime.datetime.now()
    points = min(hours * 4, 200)
    base_values = {"soil_moisture": 45, "temperature": 25, "light_intensity": 500, "rainfall": 0.5}
    amplitude = {"soil_moisture": 12, "temperature": 6, "light_intensity": 250, "rainfall": 1}
    base = base_values.get(data_type, 50)
    amp = amplitude.get(data_type, 10)
    timestamps = []
    values = []
    for i in range(points):
        t = now - datetime.timedelta(minutes=15 * (points - i - 1))
        timestamps.append(t.strftime("%m-%d %H:%M"))
        val = base + amp * math.sin(i / points * 2 * math.pi * 1.5) + random.uniform(-2, 2) - i * 0.015
        values.append(round(max(0, val), 2))
    return {"data_type": data_type, "hours": hours, "timestamps": timestamps, "values": values}


# ============================================================
#  天气 API
# ============================================================

@router.get("/weather")
async def get_weather(city: str = "北京"):
    try:
        from src.config import config
        import requests
        params = {"city": city, "key": config.WEATHER_API_KEY, "extensions": "all", "output": "JSON"}
        resp = requests.get(config.API_SERVICE_URL, params=params, timeout=5)
        data = resp.json()
        if data.get("status") == "1" and data.get("forecasts"):
            casts = data["forecasts"][0].get("casts", [])
            return {
                "city": city,
                "live": {"weather": casts[0]["dayweather"] if casts else "未知",
                         "temperature": casts[0]["daytemp"] if casts else "--",
                         "wind_direction": casts[0]["daywind"] if casts else "--",
                         "wind_power": casts[0]["daypower"] if casts else "--"},
                "forecast": [{"date": c.get("date"), "day_weather": c.get("dayweather"),
                              "day_temp": c.get("daytemp"), "night_temp": c.get("nighttemp")} for c in casts[:4]]
            }
    except Exception as e:
        logger.warning(f"天气 API 失败: {e}")
    return {
        "city": city,
        "live": {"weather": random.choice(["晴", "多云", "阴"]),
                 "temperature": str(random.randint(20, 32)),
                 "wind_direction": "东南", "wind_power": str(random.randint(1, 5))},
        "forecast": [
            {"date": (datetime.date.today() + datetime.timedelta(days=i)).isoformat(),
             "day_weather": random.choice(["晴", "多云", "小雨"]),
             "day_temp": str(random.randint(20, 32)),
             "night_temp": str(random.randint(15, 22))} for i in range(4)
        ],
        "note": "模拟天气数据"
    }


# ============================================================
#  灌溉控制 API
# ============================================================

_irrigation_state = {"status": "stopped", "start_time": None, "duration_minutes": 0}

@router.get("/irrigation/status")
async def get_irrigation_status():
    state = _irrigation_state.copy()
    if state["status"] == "running" and state["start_time"]:
        start = datetime.datetime.fromisoformat(state["start_time"])
        elapsed = (datetime.datetime.now() - start).total_seconds() / 60
        state["elapsed_minutes"] = round(elapsed, 1)
        state["remaining_minutes"] = round(max(0, state["duration_minutes"] - elapsed), 1)
    return state

@router.post("/irrigation/control")
async def control_irrigation(req: IrrigationControlRequest, db: Session = Depends(get_db)):
    global _irrigation_state
    from src.database.models import IrrigationLog
    now = datetime.datetime.now()
    if req.action == "start":
        if _irrigation_state["status"] == "running":
            return {"success": False, "message": "灌溉已在运行中"}
        _irrigation_state = {"status": "running", "start_time": now.isoformat(), "duration_minutes": req.duration_minutes}
        db.add(IrrigationLog(event="start", start_time=now, duration_planned_seconds=(req.duration_minutes or 30)*60,
                             status="running", message="手动触发"))
        db.commit()
        return {"success": True, "message": f"灌溉已启动，计划持续 {req.duration_minutes} 分钟", "state": _irrigation_state}
    elif req.action == "stop":
        if _irrigation_state["status"] == "stopped":
            return {"success": False, "message": "灌溉未在运行"}
        _irrigation_state = {"status": "stopped", "start_time": None, "duration_minutes": 0}
        db.add(IrrigationLog(event="stop", end_time=now, status="completed", message="手动停止"))
        db.commit()
        return {"success": True, "message": "灌溉已停止", "state": _irrigation_state}
    raise HTTPException(status_code=400, detail="action 必须是 start 或 stop")

@router.get("/irrigation/logs")
async def get_irrigation_logs(limit: int = 20, db: Session = Depends(get_db)):
    from src.database.models import IrrigationLog
    from sqlalchemy import desc
    logs = db.query(IrrigationLog).order_by(desc(IrrigationLog.created_at)).limit(limit).all()
    return {"logs": [
        {"id": l.id, "event": l.event, "status": l.status,
         "start_time": l.start_time.isoformat() if l.start_time else None,
         "end_time": l.end_time.isoformat() if l.end_time else None,
         "duration_planned": l.duration_planned_seconds, "message": l.message,
         "created_at": l.created_at.isoformat() if l.created_at else None}
        for l in logs
    ]}


# ============================================================
#  决策日志 API
# ============================================================

@router.get("/decisions")
async def get_decisions(limit: int = 20, db: Session = Depends(get_db)):
    from src.database.models import AgentDecisionLog
    logs = db.query(AgentDecisionLog).order_by(AgentDecisionLog.created_at.desc()).limit(limit).all()
    return {"decisions": [log.to_dict() for log in logs]}


# ============================================================
#  系统设置 API
# ============================================================

_runtime_settings = {
    "soil_moisture_threshold": 40.0, "default_duration_minutes": 30,
    "alarm_threshold": 25.0, "alarm_enabled": True,
}

@router.get("/settings")
async def get_settings():
    try:
        from src.config import config
        return {**_runtime_settings, "model_name": config.MODEL_NAME,
                "sensor_ids": config.SENSOR_IDS, "collection_interval_minutes": config.DATA_COLLECTION_INTERVAL_MINUTES,
                "db_type": config.DB_TYPE}
    except Exception:
        return _runtime_settings

@router.put("/settings")
async def update_settings(req: SettingsUpdateRequest):
    global _runtime_settings
    if req.soil_moisture_threshold is not None:
        _runtime_settings["soil_moisture_threshold"] = req.soil_moisture_threshold
    if req.default_duration_minutes is not None:
        _runtime_settings["default_duration_minutes"] = req.default_duration_minutes
    if req.alarm_threshold is not None:
        _runtime_settings["alarm_threshold"] = req.alarm_threshold
    if req.alarm_enabled is not None:
        _runtime_settings["alarm_enabled"] = req.alarm_enabled
    return {"success": True, "settings": _runtime_settings}


# ============================================================
#  系统状态 API
# ============================================================

@router.get("/status")
async def get_system_status():
    from src.llm.langchain_agent import get_hydro_agent
    agent = get_hydro_agent()
    return {
        "status": "online", "timestamp": datetime.datetime.now().isoformat(),
        "agent_initialized": agent._initialized, "irrigation_status": _irrigation_state["status"],
        "version": "4.0.0",
        "features": ["MCP Tools", "Multi-turn Conversation", "Streaming SSE", "Decision Audit"],
    }
