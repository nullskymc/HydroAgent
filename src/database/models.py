"""
数据库模型模块 - 定义数据库表结构 (HydroAgent v5)
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from src.config import config
from src.exceptions.exceptions import DatabaseError

Base = declarative_base()


class BaseModel(object):
    """所有模型的基类"""

    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SensorData(Base, BaseModel):
    """传感器数据表"""

    sensor_id = Column(String(50), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False)
    soil_moisture = Column(Float)
    temperature = Column(Float)
    light_intensity = Column(Float)
    rainfall = Column(Float)
    raw_data = Column(JSON)

    def __repr__(self):
        return f"<SensorData(id={self.id}, sensor_id='{self.sensor_id}', timestamp='{self.timestamp}')>"


class WeatherData(Base, BaseModel):
    """天气数据表"""

    location = Column(String(100), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    temperature = Column(Float)
    humidity = Column(Float)
    wind_speed = Column(Float)
    condition = Column(String(100))
    precipitation = Column(Float)
    forecast_data = Column(JSON)

    def __repr__(self):
        return f"<WeatherData(id={self.id}, location='{self.location}', timestamp='{self.timestamp}')>"


class IrrigationLog(Base, BaseModel):
    """灌溉日志表"""

    event = Column(String(50), nullable=False)
    zone_id = Column(String(50), index=True)
    actuator_id = Column(String(50), index=True)
    plan_id = Column(String(50), index=True)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    duration_planned_seconds = Column(Integer)
    duration_actual_seconds = Column(Integer)
    status = Column(String(50))
    message = Column(Text)

    def __repr__(self):
        return f"<IrrigationLog(id={self.id}, event='{self.event}', status='{self.status}')>"


class User(Base, BaseModel):
    """用户表"""

    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    email = Column(String(100), unique=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    last_login = Column(DateTime)

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"


class Zone(Base, BaseModel):
    """农场分区"""

    zone_id = Column(String(50), unique=True, index=True, default=lambda: f"zone_{uuid.uuid4().hex[:8]}")
    name = Column(String(100), nullable=False)
    location = Column(String(100), default="北京")
    crop_type = Column(String(100), default="通用作物")
    soil_moisture_threshold = Column(Float, default=40.0)
    default_duration_minutes = Column(Integer, default=30)
    is_enabled = Column(Boolean, default=True)
    notes = Column(Text)

    actuators = relationship("Actuator", back_populates="zone", cascade="all, delete-orphan")
    sensor_bindings = relationship("ZoneSensorBinding", back_populates="zone", cascade="all, delete-orphan")
    plans = relationship("IrrigationPlan", back_populates="zone")

    def __repr__(self):
        return f"<Zone(zone_id='{self.zone_id}', name='{self.name}')>"

    def to_dict(self):
        return {
            "zone_id": self.zone_id,
            "name": self.name,
            "location": self.location,
            "crop_type": self.crop_type,
            "soil_moisture_threshold": self.soil_moisture_threshold,
            "default_duration_minutes": self.default_duration_minutes,
            "is_enabled": self.is_enabled,
            "notes": self.notes,
            "sensor_ids": [binding.sensor_id for binding in self.sensor_bindings],
            "actuators": [actuator.to_dict() for actuator in self.actuators],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Actuator(Base, BaseModel):
    """分区执行器"""

    actuator_id = Column(String(50), unique=True, index=True, default=lambda: f"act_{uuid.uuid4().hex[:8]}")
    zone_id = Column(String(50), ForeignKey("zone.zone_id", ondelete="CASCADE"), index=True, nullable=False)
    name = Column(String(100), nullable=False)
    actuator_type = Column(String(50), default="valve")
    status = Column(String(50), default="idle")
    capabilities = Column(JSON, default=dict)
    is_enabled = Column(Boolean, default=True)
    last_command_at = Column(DateTime)

    zone = relationship("Zone", back_populates="actuators")
    plans = relationship("IrrigationPlan", back_populates="actuator")

    def __repr__(self):
        return f"<Actuator(actuator_id='{self.actuator_id}', zone_id='{self.zone_id}', status='{self.status}')>"

    def to_dict(self):
        return {
            "actuator_id": self.actuator_id,
            "zone_id": self.zone_id,
            "name": self.name,
            "actuator_type": self.actuator_type,
            "status": self.status,
            "capabilities": self.capabilities or {},
            "is_enabled": self.is_enabled,
            "last_command_at": self.last_command_at.isoformat() if self.last_command_at else None,
        }


class ZoneSensorBinding(Base, BaseModel):
    """分区与传感器绑定"""

    zone_id = Column(String(50), ForeignKey("zone.zone_id", ondelete="CASCADE"), index=True, nullable=False)
    sensor_id = Column(String(50), nullable=False, index=True)
    role = Column(String(50), default="primary")
    is_enabled = Column(Boolean, default=True)

    zone = relationship("Zone", back_populates="sensor_bindings")

    def __repr__(self):
        return f"<ZoneSensorBinding(zone_id='{self.zone_id}', sensor_id='{self.sensor_id}')>"

    def to_dict(self):
        return {
            "zone_id": self.zone_id,
            "sensor_id": self.sensor_id,
            "role": self.role,
            "is_enabled": self.is_enabled,
        }


class ConversationSession(Base, BaseModel):
    """对话会话"""

    session_id = Column(String(50), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(200), default="新对话")
    message_count = Column(Integer, default=0)

    messages = relationship(
        "ChatMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    def __repr__(self):
        return f"<ConversationSession(session_id='{self.session_id}', title='{self.title}')>"

    def to_dict(self):
        return {
            "session_id": self.session_id,
            "title": self.title,
            "message_count": self.message_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ChatMessage(Base, BaseModel):
    """对话消息"""

    conversation_id = Column(String(50), ForeignKey("conversationsession.session_id", ondelete="CASCADE"), index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text)
    trace_id = Column(String(50), index=True)
    tool_calls = Column(JSON)
    tool_name = Column(String(100))
    tool_call_id = Column(String(100))

    conversation = relationship("ConversationSession", back_populates="messages")

    def __repr__(self):
        return f"<ChatMessage(id={self.id}, role='{self.role}', conversation_id='{self.conversation_id}')>"

    def to_dict(self):
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "trace_id": self.trace_id,
            "tool_calls": self.tool_calls,
            "tool_name": self.tool_name,
            "tool_call_id": self.tool_call_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class IrrigationPlan(Base, BaseModel):
    """结构化灌溉计划"""

    plan_id = Column(String(50), unique=True, index=True, default=lambda: f"plan_{uuid.uuid4().hex[:12]}")
    zone_id = Column(String(50), ForeignKey("zone.zone_id", ondelete="SET NULL"), index=True)
    actuator_id = Column(String(50), ForeignKey("actuator.actuator_id", ondelete="SET NULL"), index=True)
    conversation_id = Column(String(50), ForeignKey("conversationsession.session_id", ondelete="SET NULL"), index=True)
    trigger = Column(String(20), default="manual")
    status = Column(String(30), default="draft")
    approval_status = Column(String(30), default="not_required")
    execution_status = Column(String(30), default="not_started")
    proposed_action = Column(String(50), default="hold")
    urgency = Column(String(30), default="normal")
    risk_level = Column(String(30), default="low")
    recommended_duration_minutes = Column(Integer, default=0)
    requires_approval = Column(Boolean, default=False)
    reasoning_summary = Column(Text)
    evidence_summary = Column(JSON)
    safety_review = Column(JSON)
    execution_result = Column(JSON)
    workspace_path = Column(String(255))
    requested_by = Column(String(100), default="user")
    approved_at = Column(DateTime)
    rejected_at = Column(DateTime)
    executed_at = Column(DateTime)

    zone = relationship("Zone", back_populates="plans")
    actuator = relationship("Actuator", back_populates="plans")
    approvals = relationship("PlanApproval", back_populates="plan", cascade="all, delete-orphan")
    execution_events = relationship("PlanExecutionEvent", back_populates="plan", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<IrrigationPlan(plan_id='{self.plan_id}', zone_id='{self.zone_id}', status='{self.status}')>"

    def to_dict(self):
        latest_approval = self.approvals[-1].to_dict() if self.approvals else None
        return {
            "plan_id": self.plan_id,
            "zone_id": self.zone_id,
            "zone_name": self.zone.name if self.zone else None,
            "actuator_id": self.actuator_id,
            "actuator_name": self.actuator.name if self.actuator else None,
            "conversation_id": self.conversation_id,
            "trigger": self.trigger,
            "status": self.status,
            "approval_status": self.approval_status,
            "execution_status": self.execution_status,
            "proposed_action": self.proposed_action,
            "urgency": self.urgency,
            "risk_level": self.risk_level,
            "recommended_duration_minutes": self.recommended_duration_minutes,
            "requires_approval": self.requires_approval,
            "reasoning_summary": self.reasoning_summary,
            "evidence_summary": self.evidence_summary,
            "safety_review": self.safety_review,
            "execution_result": self.execution_result,
            "workspace_path": self.workspace_path,
            "requested_by": self.requested_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "rejected_at": self.rejected_at.isoformat() if self.rejected_at else None,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "latest_approval": latest_approval,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PlanApproval(Base, BaseModel):
    """计划审批记录"""

    approval_id = Column(String(50), unique=True, index=True, default=lambda: f"approval_{uuid.uuid4().hex[:10]}")
    plan_id = Column(String(50), ForeignKey("irrigationplan.plan_id", ondelete="CASCADE"), index=True, nullable=False)
    decision = Column(String(30), nullable=False)
    actor = Column(String(100), default="user")
    comment = Column(Text)
    decided_at = Column(DateTime, default=datetime.utcnow)

    plan = relationship("IrrigationPlan", back_populates="approvals")

    def __repr__(self):
        return f"<PlanApproval(approval_id='{self.approval_id}', decision='{self.decision}')>"

    def to_dict(self):
        return {
            "approval_id": self.approval_id,
            "plan_id": self.plan_id,
            "decision": self.decision,
            "actor": self.actor,
            "comment": self.comment,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
        }


class PlanExecutionEvent(Base, BaseModel):
    """计划执行事件"""

    event_id = Column(String(50), unique=True, index=True, default=lambda: f"exec_{uuid.uuid4().hex[:10]}")
    plan_id = Column(String(50), ForeignKey("irrigationplan.plan_id", ondelete="CASCADE"), index=True, nullable=False)
    event = Column(String(50), nullable=False)
    status = Column(String(30), nullable=False)
    details = Column(JSON)
    occurred_at = Column(DateTime, default=datetime.utcnow)

    plan = relationship("IrrigationPlan", back_populates="execution_events")

    def __repr__(self):
        return f"<PlanExecutionEvent(event_id='{self.event_id}', event='{self.event}', status='{self.status}')>"

    def to_dict(self):
        return {
            "event_id": self.event_id,
            "plan_id": self.plan_id,
            "event": self.event,
            "status": self.status,
            "details": self.details,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
        }


class AgentDecisionLog(Base, BaseModel):
    """智能体决策审计日志"""

    decision_id = Column(String(50), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    trigger = Column(String(20), default="manual")
    zone_id = Column(String(50), index=True)
    plan_id = Column(String(50), index=True)
    input_context = Column(JSON)
    reasoning_chain = Column(Text)
    tools_used = Column(JSON)
    decision_result = Column(JSON)
    reflection_notes = Column(Text)
    effectiveness_score = Column(Float)

    def __repr__(self):
        return f"<AgentDecisionLog(decision_id='{self.decision_id}', trigger='{self.trigger}')>"

    def to_dict(self):
        return {
            "decision_id": self.decision_id,
            "trigger": self.trigger,
            "zone_id": self.zone_id,
            "plan_id": self.plan_id,
            "input_context": self.input_context,
            "reasoning_chain": self.reasoning_chain,
            "tools_used": self.tools_used,
            "decision_result": self.decision_result,
            "reflection_notes": self.reflection_notes,
            "effectiveness_score": self.effectiveness_score,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ToolExecutionEvent(Base, BaseModel):
    """逐步记录工具调用与子代理委派事件，用于审计与回放。"""

    event_id = Column(String(50), unique=True, index=True, default=lambda: f"traceevt_{uuid.uuid4().hex[:12]}")
    trace_id = Column(String(50), index=True, nullable=False)
    conversation_id = Column(String(50), ForeignKey("conversationsession.session_id", ondelete="CASCADE"), index=True)
    run_id = Column(String(100), index=True)
    step_index = Column(Integer, nullable=False, default=0)
    event_type = Column(String(50), nullable=False)
    status = Column(String(30), nullable=False, default="running")
    tool_name = Column(String(100))
    subagent_name = Column(String(100))
    zone_id = Column(String(50), index=True)
    plan_id = Column(String(50), index=True)
    input_args = Column(JSON)
    normalized_args = Column(JSON)
    output_payload = Column(JSON)
    output_preview = Column(Text)
    error_message = Column(Text)
    duration_ms = Column(Integer)
    payload_truncated = Column(Boolean, default=False)

    def __repr__(self):
        return f"<ToolExecutionEvent(event_id='{self.event_id}', trace_id='{self.trace_id}', event_type='{self.event_type}')>"

    def to_dict(self):
        return {
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "conversation_id": self.conversation_id,
            "run_id": self.run_id,
            "step_index": self.step_index,
            "event_type": self.event_type,
            "status": self.status,
            "tool_name": self.tool_name,
            "subagent_name": self.subagent_name,
            "zone_id": self.zone_id,
            "plan_id": self.plan_id,
            "input_args": self.input_args,
            "normalized_args": self.normalized_args,
            "output_payload": self.output_payload,
            "output_preview": self.output_preview,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
            "payload_truncated": self.payload_truncated,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


try:
    _db_uri = config.get_db_uri()
    _connect_args = {"check_same_thread": False} if _db_uri.startswith("sqlite") else {}
    engine = create_engine(_db_uri, connect_args=_connect_args)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception as e:
    raise DatabaseError(f"数据库连接错误: {e}") from e


def get_db():
    """获取数据库会话（FastAPI Depends 使用）"""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库，创建所有表"""

    try:
        Base.metadata.create_all(bind=engine)
        _ensure_compat_columns()
        return True
    except Exception as e:
        raise DatabaseError(f"数据库初始化错误: {e}") from e


def create_item(db, model, **kwargs):
    """创建记录"""

    db_item = model(**kwargs)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


def get_item(db, model, item_id):
    """通过 ID 获取记录"""

    return db.query(model).filter(model.id == item_id).first()


def get_items(db, model, skip=0, limit=100, **filters):
    """获取多条记录"""

    query = db.query(model)
    for field, value in filters.items():
        if hasattr(model, field):
            query = query.filter(getattr(model, field) == value)
    return query.offset(skip).limit(limit).all()


def update_item(db, model, item_id, **kwargs):
    """更新记录"""

    db_item = get_item(db, model, item_id)
    if not db_item:
        return None
    for field, value in kwargs.items():
        if hasattr(db_item, field):
            setattr(db_item, field, value)
    db.commit()
    db.refresh(db_item)
    return db_item


def delete_item(db, model, item_id):
    """删除记录"""

    db_item = get_item(db, model, item_id)
    if not db_item:
        return None
    db.delete(db_item)
    db.commit()
    return db_item


def _ensure_compat_columns():
    """Add missing columns for local SQLite development without a migration framework."""

    if not str(engine.url).startswith("sqlite"):
        return

    compatibility_map = {
        "irrigationlog": {
            "zone_id": "ALTER TABLE irrigationlog ADD COLUMN zone_id VARCHAR(50)",
            "actuator_id": "ALTER TABLE irrigationlog ADD COLUMN actuator_id VARCHAR(50)",
            "plan_id": "ALTER TABLE irrigationlog ADD COLUMN plan_id VARCHAR(50)",
        },
        "agentdecisionlog": {
            "zone_id": "ALTER TABLE agentdecisionlog ADD COLUMN zone_id VARCHAR(50)",
            "plan_id": "ALTER TABLE agentdecisionlog ADD COLUMN plan_id VARCHAR(50)",
        },
        "chatmessage": {
            "trace_id": "ALTER TABLE chatmessage ADD COLUMN trace_id VARCHAR(50)",
        },
    }

    inspector = inspect(engine)
    with engine.begin() as connection:
        for table_name, statements in compatibility_map.items():
            if table_name not in inspector.get_table_names():
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, statement in statements.items():
                if column_name not in existing_columns:
                    connection.execute(text(statement))
