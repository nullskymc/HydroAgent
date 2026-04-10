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
)
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.pool import NullPool

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
    display_name = Column(String(100))
    phone = Column(String(30))
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    last_login = Column(DateTime)
    password_changed_at = Column(DateTime)
    created_by = Column(String(100))

    role_assignments = relationship("UserRoleAssignment", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "display_name": self.display_name,
            "phone": self.phone,
            "is_active": self.is_active,
            "is_admin": self.is_admin,
            "created_by": self.created_by,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "password_changed_at": self.password_changed_at.isoformat() if self.password_changed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Role(Base, BaseModel):
    """角色表"""

    role_key = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    is_system = Column(Boolean, default=True)

    permissions = relationship("Permission", secondary="rolepermissionassignment", back_populates="roles")
    user_assignments = relationship("UserRoleAssignment", back_populates="role", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "role_key": self.role_key,
            "name": self.name,
            "description": self.description,
            "is_system": self.is_system,
            "permissions": [permission.permission_key for permission in self.permissions],
        }


class Permission(Base, BaseModel):
    """权限表"""

    permission_key = Column(String(80), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    category = Column(String(50), default="general")

    roles = relationship("Role", secondary="rolepermissionassignment", back_populates="permissions")

    def to_dict(self):
        return {
            "permission_key": self.permission_key,
            "name": self.name,
            "description": self.description,
            "category": self.category,
        }


class RolePermissionAssignment(Base, BaseModel):
    """角色与权限映射"""

    role_id = Column(Integer, ForeignKey("role.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_id = Column(Integer, ForeignKey("permission.id", ondelete="CASCADE"), nullable=False, index=True)


class UserRoleAssignment(Base, BaseModel):
    """用户与角色映射"""

    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(Integer, ForeignKey("role.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_by = Column(String(100))

    user = relationship("User", back_populates="role_assignments")
    role = relationship("Role", back_populates="user_assignments")

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "role_id": self.role_id,
            "assigned_by": self.assigned_by,
            "role_key": self.role.role_key if self.role else None,
        }


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
    alerts = relationship("AlertEvent", back_populates="zone")

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
            "sensor_devices": [binding.to_dict() for binding in self.sensor_bindings],
            "actuators": [actuator.to_dict() for actuator in self.actuators],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SystemSettings(Base, BaseModel):
    """全局业务配置，作为运行期策略默认值的单一事实源。"""

    singleton_key = Column(String(32), unique=True, nullable=False, default="default", index=True)
    default_soil_moisture_threshold = Column(Float, default=40.0)
    default_duration_minutes = Column(Integer, default=30)
    alarm_threshold = Column(Float, default=25.0)
    alarm_enabled = Column(Boolean, default=True)
    collection_interval_minutes = Column(Integer, default=5)
    knowledge_top_k = Column(Integer, default=4)
    knowledge_chunk_size = Column(Integer, default=1200)
    knowledge_chunk_overlap = Column(Integer, default=180)

    def to_dict(self):
        return {
            "default_soil_moisture_threshold": self.default_soil_moisture_threshold,
            "default_duration_minutes": self.default_duration_minutes,
            "alarm_threshold": self.alarm_threshold,
            "alarm_enabled": self.alarm_enabled,
            "collection_interval_minutes": self.collection_interval_minutes,
            "knowledge_top_k": self.knowledge_top_k,
            "knowledge_chunk_size": self.knowledge_chunk_size,
            "knowledge_chunk_overlap": self.knowledge_chunk_overlap,
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
    serial_number = Column(String(100))
    firmware_version = Column(String(50))
    health_status = Column(String(30), default="healthy")
    last_seen_at = Column(DateTime)

    zone = relationship("Zone", back_populates="actuators")
    plans = relationship("IrrigationPlan", back_populates="actuator")
    alerts = relationship("AlertEvent", back_populates="actuator")

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
            "serial_number": self.serial_number,
            "firmware_version": self.firmware_version,
            "health_status": self.health_status,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
        }


class SensorDevice(Base, BaseModel):
    """传感器资产"""

    sensor_device_id = Column(String(50), unique=True, nullable=False, index=True, default=lambda: f"sensor_{uuid.uuid4().hex[:10]}")
    sensor_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    model = Column(String(100))
    location = Column(String(100))
    status = Column(String(30), default="online")
    is_enabled = Column(Boolean, default=True)
    last_seen_at = Column(DateTime)
    calibration_due_at = Column(DateTime)
    notes = Column(Text)

    zone_bindings = relationship("ZoneSensorBinding", back_populates="sensor_device")
    alerts = relationship("AlertEvent", back_populates="sensor_device")

    def to_dict(self):
        return {
            "sensor_device_id": self.sensor_device_id,
            "sensor_id": self.sensor_id,
            "name": self.name,
            "model": self.model,
            "location": self.location,
            "status": self.status,
            "is_enabled": self.is_enabled,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "calibration_due_at": self.calibration_due_at.isoformat() if self.calibration_due_at else None,
            "notes": self.notes,
        }


class ZoneSensorBinding(Base, BaseModel):
    """分区与传感器绑定"""

    zone_id = Column(String(50), ForeignKey("zone.zone_id", ondelete="CASCADE"), index=True, nullable=False)
    sensor_id = Column(String(50), nullable=False, index=True)
    sensor_device_id = Column(String(50), ForeignKey("sensordevice.sensor_device_id", ondelete="SET NULL"), index=True)
    role = Column(String(50), default="primary")
    is_enabled = Column(Boolean, default=True)

    zone = relationship("Zone", back_populates="sensor_bindings")
    sensor_device = relationship("SensorDevice", back_populates="zone_bindings")

    def __repr__(self):
        return f"<ZoneSensorBinding(zone_id='{self.zone_id}', sensor_id='{self.sensor_id}')>"

    def to_dict(self):
        return {
            "zone_id": self.zone_id,
            "sensor_id": self.sensor_id,
            "sensor_device_id": self.sensor_device_id,
            "role": self.role,
            "is_enabled": self.is_enabled,
            "sensor_name": self.sensor_device.name if self.sensor_device else None,
        }


class IrrigationPlan(Base, BaseModel):
    """结构化灌溉计划"""

    plan_id = Column(String(50), unique=True, index=True, default=lambda: f"plan_{uuid.uuid4().hex[:12]}")
    zone_id = Column(String(50), ForeignKey("zone.zone_id", ondelete="SET NULL"), index=True)
    actuator_id = Column(String(50), ForeignKey("actuator.actuator_id", ondelete="SET NULL"), index=True)
    conversation_id = Column(String(50), index=True)
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
    alerts = relationship("AlertEvent", back_populates="plan")

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


class AlertRule(Base, BaseModel):
    """告警规则"""

    rule_key = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    severity = Column(String(20), default="medium")
    is_enabled = Column(Boolean, default=True)
    config = Column(JSON, default=dict)

    def to_dict(self):
        return {
            "rule_key": self.rule_key,
            "name": self.name,
            "description": self.description,
            "severity": self.severity,
            "is_enabled": self.is_enabled,
            "config": self.config or {},
        }


class AlertEvent(Base, BaseModel):
    """告警事件"""

    alert_id = Column(String(50), unique=True, nullable=False, index=True, default=lambda: f"alert_{uuid.uuid4().hex[:12]}")
    rule_key = Column(String(50), ForeignKey("alertrule.rule_key", ondelete="SET NULL"), index=True)
    severity = Column(String(20), default="medium")
    status = Column(String(30), default="open")
    title = Column(String(150), nullable=False)
    message = Column(Text, nullable=False)
    zone_id = Column(String(50), ForeignKey("zone.zone_id", ondelete="SET NULL"), index=True)
    sensor_device_id = Column(String(50), ForeignKey("sensordevice.sensor_device_id", ondelete="SET NULL"), index=True)
    actuator_id = Column(String(50), ForeignKey("actuator.actuator_id", ondelete="SET NULL"), index=True)
    plan_id = Column(String(50), ForeignKey("irrigationplan.plan_id", ondelete="SET NULL"), index=True)
    object_type = Column(String(50))
    object_id = Column(String(50))
    assignee = Column(String(100))
    acknowledged_at = Column(DateTime)
    resolved_at = Column(DateTime)
    context = Column(JSON, default=dict)

    zone = relationship("Zone", back_populates="alerts")
    sensor_device = relationship("SensorDevice", back_populates="alerts")
    actuator = relationship("Actuator", back_populates="alerts")
    plan = relationship("IrrigationPlan", back_populates="alerts")

    def to_dict(self):
        return {
            "alert_id": self.alert_id,
            "rule_key": self.rule_key,
            "severity": self.severity,
            "status": self.status,
            "title": self.title,
            "message": self.message,
            "zone_id": self.zone_id,
            "zone_name": self.zone.name if self.zone else None,
            "sensor_device_id": self.sensor_device_id,
            "sensor_name": self.sensor_device.name if self.sensor_device else None,
            "actuator_id": self.actuator_id,
            "actuator_name": self.actuator.name if self.actuator else None,
            "plan_id": self.plan_id,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "assignee": self.assignee,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "context": self.context or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AuditEvent(Base, BaseModel):
    """后台审计事件"""

    audit_id = Column(String(50), unique=True, nullable=False, index=True, default=lambda: f"audit_{uuid.uuid4().hex[:12]}")
    event_type = Column(String(50), nullable=False, index=True)
    actor = Column(String(100), nullable=False)
    object_type = Column(String(50), nullable=False)
    object_id = Column(String(100))
    result = Column(String(30), default="success")
    comment = Column(Text)
    details = Column(JSON, default=dict)
    occurred_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "audit_id": self.audit_id,
            "event_type": self.event_type,
            "actor": self.actor,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "result": self.result,
            "comment": self.comment,
            "details": self.details or {},
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
        }


class KnowledgeDocument(Base, BaseModel):
    """知识库文档元数据。"""

    document_id = Column(String(50), unique=True, nullable=False, index=True, default=lambda: f"doc_{uuid.uuid4().hex[:12]}")
    title = Column(String(255), nullable=False)
    source_uri = Column(String(500))
    content = Column(Text, nullable=False)
    checksum = Column(String(64), nullable=False, index=True)
    status = Column(String(30), default="ready", nullable=False)
    chunk_count = Column(Integer, default=0, nullable=False)
    metadata_json = Column(JSON, default=dict)
    created_by = Column(String(100), default="system")

    chunks = relationship("KnowledgeChunk", back_populates="document", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "document_id": self.document_id,
            "title": self.title,
            "source_uri": self.source_uri,
            "status": self.status,
            "chunk_count": self.chunk_count,
            "checksum": self.checksum,
            "metadata": self.metadata_json or {},
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class KnowledgeChunk(Base, BaseModel):
    """知识库切片元数据，向量本体由外部向量库负责持久化。"""

    chunk_id = Column(String(60), unique=True, nullable=False, index=True, default=lambda: f"chunk_{uuid.uuid4().hex[:12]}")
    document_id = Column(String(50), ForeignKey("knowledgedocument.document_id", ondelete="CASCADE"), index=True, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    metadata_json = Column(JSON, default=dict)

    document = relationship("KnowledgeDocument", back_populates="chunks")

    def to_dict(self):
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "metadata": self.metadata_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


try:
    _db_uri = config.get_db_uri()
    _connect_args = {"check_same_thread": False} if _db_uri.startswith("sqlite") else {}
    engine_kwargs = {"connect_args": _connect_args}
    # SQLite 文件库在开发环境并发请求下更适合无池化连接，避免 QueuePool 被短时打满。
    if _db_uri.startswith("sqlite"):
        engine_kwargs["poolclass"] = NullPool
    engine = create_engine(_db_uri, **engine_kwargs)
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
        _ensure_sqlite_schema()
        _drop_legacy_chat_audit_tables()
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


def _drop_legacy_chat_audit_tables():
    """一次性清理已废弃的聊天/审计表，保留灌溉业务域数据。"""

    if not str(engine.url).startswith("sqlite"):
        return

    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.exec_driver_sql("DROP TABLE IF EXISTS toolexecutionevent")
        connection.exec_driver_sql("DROP TABLE IF EXISTS chatmessage")
        connection.exec_driver_sql("DROP TABLE IF EXISTS agentdecisionlog")
        connection.exec_driver_sql("DROP TABLE IF EXISTS conversationsession")
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")


def _ensure_sqlite_schema():
    """为已有 SQLite 数据库补齐新增字段，避免开发环境旧库无法启动。"""

    if not str(engine.url).startswith("sqlite"):
        return

    schema_updates = {
        "user": {
            "display_name": "ALTER TABLE user ADD COLUMN display_name VARCHAR(100)",
            "phone": "ALTER TABLE user ADD COLUMN phone VARCHAR(30)",
            "password_changed_at": "ALTER TABLE user ADD COLUMN password_changed_at DATETIME",
            "created_by": "ALTER TABLE user ADD COLUMN created_by VARCHAR(100)",
        },
        "actuator": {
            "serial_number": "ALTER TABLE actuator ADD COLUMN serial_number VARCHAR(100)",
            "firmware_version": "ALTER TABLE actuator ADD COLUMN firmware_version VARCHAR(50)",
            "health_status": "ALTER TABLE actuator ADD COLUMN health_status VARCHAR(30) DEFAULT 'healthy'",
            "last_seen_at": "ALTER TABLE actuator ADD COLUMN last_seen_at DATETIME",
        },
        "zonesensorbinding": {
            "sensor_device_id": "ALTER TABLE zonesensorbinding ADD COLUMN sensor_device_id VARCHAR(50)",
        },
    }

    with engine.begin() as connection:
        for table_name, updates in schema_updates.items():
            existing_columns = {
                row[1]
                for row in connection.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
            }
            for column_name, ddl in updates.items():
                if column_name not in existing_columns:
                    connection.exec_driver_sql(ddl)
