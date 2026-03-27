"""
数据库模型模块 - 定义数据库表结构 (HydroAgent v4)
"""
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, JSON, ForeignKey, Boolean, Text
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.ext.declarative import declared_attr
from datetime import datetime
from src.config import config
from src.exceptions.exceptions import DatabaseError
import uuid

# 创建基类
Base = declarative_base()

class BaseModel(object):
    """所有模型的基类"""
    
    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()
    
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ==================== 原有模型 ====================

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
    event = Column(String(50), nullable=False)  # start, stop, failed
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    duration_planned_seconds = Column(Integer)
    duration_actual_seconds = Column(Integer)
    status = Column(String(50))  # completed, failed, aborted
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


# ==================== 新增：对话与决策模型 ====================

class ConversationSession(Base, BaseModel):
    """对话会话表 —— 每次新对话对应一个 Session"""
    session_id = Column(String(50), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(200), default="新对话")
    message_count = Column(Integer, default=0)

    messages = relationship("ChatMessage", back_populates="conversation",
                            cascade="all, delete-orphan", order_by="ChatMessage.created_at")

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
    """对话消息表 —— 存储每一条消息（含工具调用信息）"""
    conversation_id = Column(String(50), ForeignKey("conversationsession.session_id",
                                                     ondelete="CASCADE"), index=True)
    role = Column(String(20), nullable=False)   # "user" | "assistant" | "tool"
    content = Column(Text)                      # 文本内容
    tool_calls = Column(JSON)                   # 助手触发的工具调用列表
    tool_name = Column(String(100))             # 工具名称（tool 角色）
    tool_call_id = Column(String(100))          # 工具调用 ID

    conversation = relationship("ConversationSession", back_populates="messages")

    def __repr__(self):
        return f"<ChatMessage(id={self.id}, role='{self.role}', conversation_id='{self.conversation_id}')>"

    def to_dict(self):
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "tool_calls": self.tool_calls,
            "tool_name": self.tool_name,
            "tool_call_id": self.tool_call_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AgentDecisionLog(Base, BaseModel):
    """智能体决策审计日志 —— 记录完整推理链"""
    decision_id = Column(String(50), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    trigger = Column(String(20), default="manual")  # "manual" | "auto" | "chat"
    input_context = Column(JSON)                    # 输入上下文摘要
    reasoning_chain = Column(Text)                  # 完整推理过程
    tools_used = Column(JSON)                       # 工具调用列表
    decision_result = Column(JSON)                  # 最终决策（动作+理由）
    reflection_notes = Column(Text)                 # 反思中间件的评估
    effectiveness_score = Column(Float)             # 决策效果评分 0-1

    def __repr__(self):
        return f"<AgentDecisionLog(decision_id='{self.decision_id}', trigger='{self.trigger}')>"

    def to_dict(self):
        return {
            "decision_id": self.decision_id,
            "trigger": self.trigger,
            "input_context": self.input_context,
            "reasoning_chain": self.reasoning_chain,
            "tools_used": self.tools_used,
            "decision_result": self.decision_result,
            "reflection_notes": self.reflection_notes,
            "effectiveness_score": self.effectiveness_score,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ==================== 数据库引擎与会话工厂 ====================

try:
    _db_uri = config.get_db_uri()
    # SQLite 需要 check_same_thread=False 支持多线程
    _connect_args = {"check_same_thread": False} if _db_uri.startswith("sqlite") else {}
    engine = create_engine(_db_uri, connect_args=_connect_args)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception as e:
    raise DatabaseError(f"数据库连接错误: {e}")


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
        return True
    except Exception as e:
        raise DatabaseError(f"数据库初始化错误: {e}")


# 通用的CRUD操作
def create_item(db, model, **kwargs):
    """创建记录"""
    db_item = model(**kwargs)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


def get_item(db, model, id):
    """通过ID获取记录"""
    return db.query(model).filter(model.id == id).first()


def get_items(db, model, skip=0, limit=100, **filters):
    """获取多条记录"""
    query = db.query(model)
    for field, value in filters.items():
        if hasattr(model, field):
            query = query.filter(getattr(model, field) == value)
    return query.offset(skip).limit(limit).all()