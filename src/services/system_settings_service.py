"""
System settings service for runtime business defaults.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from src.config import config
from src.database.models import SystemSettings

SYSTEM_SETTINGS_SINGLETON_KEY = "default"


def _normalize_system_settings_payload(settings: SystemSettings) -> dict:
    return settings.to_dict()


def ensure_system_settings(db: Session) -> SystemSettings:
    """确保全局业务配置存在；首次启动时使用 YAML 中的历史值初始化。"""
    settings = db.query(SystemSettings).filter(SystemSettings.singleton_key == SYSTEM_SETTINGS_SINGLETON_KEY).first()
    if settings:
        return settings

    settings = SystemSettings(
        singleton_key=SYSTEM_SETTINGS_SINGLETON_KEY,
        default_soil_moisture_threshold=float(config.LEGACY_DEFAULT_SOIL_MOISTURE_THRESHOLD),
        default_duration_minutes=int(config.LEGACY_DEFAULT_DURATION_MINUTES),
        alarm_threshold=float(config.LEGACY_ALARM_THRESHOLD),
        alarm_enabled=bool(config.LEGACY_ALARM_ENABLED),
        collection_interval_minutes=int(config.LEGACY_COLLECTION_INTERVAL_MINUTES),
        knowledge_top_k=int(config.LEGACY_KNOWLEDGE_TOP_K),
        knowledge_chunk_size=int(config.LEGACY_KNOWLEDGE_CHUNK_SIZE),
        knowledge_chunk_overlap=int(config.LEGACY_KNOWLEDGE_CHUNK_OVERLAP),
    )
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def get_system_settings(db: Session) -> SystemSettings:
    return ensure_system_settings(db)


def get_system_settings_snapshot(db: Session) -> dict:
    return _normalize_system_settings_payload(get_system_settings(db))


def update_system_settings(db: Session, updates: dict) -> dict:
    """仅更新业务配置字段，避免与 YAML 托管字段混写。"""
    settings = ensure_system_settings(db)
    field_mapping = {
        "soil_moisture_threshold": ("default_soil_moisture_threshold", float),
        "default_duration_minutes": ("default_duration_minutes", int),
        "alarm_threshold": ("alarm_threshold", float),
        "alarm_enabled": ("alarm_enabled", bool),
        "collection_interval_minutes": ("collection_interval_minutes", int),
        "knowledge_top_k": ("knowledge_top_k", int),
        "knowledge_chunk_size": ("knowledge_chunk_size", int),
        "knowledge_chunk_overlap": ("knowledge_chunk_overlap", int),
    }

    changed = False
    for key, value in updates.items():
        if key not in field_mapping or value is None:
            continue
        attr, caster = field_mapping[key]
        setattr(settings, attr, caster(value))
        changed = True

    if changed:
        db.commit()
        db.refresh(settings)
    return _normalize_system_settings_payload(settings)


def get_default_soil_moisture_threshold(db: Session) -> float:
    return float(ensure_system_settings(db).default_soil_moisture_threshold or 40.0)


def get_default_duration_minutes(db: Session) -> int:
    return int(ensure_system_settings(db).default_duration_minutes or 30)


def get_alarm_settings(db: Session) -> tuple[float, bool]:
    settings = ensure_system_settings(db)
    return float(settings.alarm_threshold or 25.0), bool(settings.alarm_enabled)


def get_collection_interval_minutes(db: Session) -> int:
    return int(ensure_system_settings(db).collection_interval_minutes or 5)


def get_knowledge_settings(db: Session) -> tuple[int, int, int]:
    settings = ensure_system_settings(db)
    return (
        int(settings.knowledge_top_k or 4),
        int(settings.knowledge_chunk_size or 1200),
        int(settings.knowledge_chunk_overlap or 180),
    )

