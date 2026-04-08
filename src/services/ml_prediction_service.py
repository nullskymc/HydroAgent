"""
Rolling regression helpers for zone soil-moisture prediction.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy.orm import Session

from src.database.models import SensorData, WeatherData, Zone

DEFAULT_HISTORY_HOURS = 168
DEFAULT_FORECAST_HOURS = 24
MIN_TRAINING_ROWS = 6


def predict_zone_soil_moisture(
    db: Session,
    zone_id: str,
    *,
    history_hours: int = DEFAULT_HISTORY_HOURS,
    forecast_hours: int = DEFAULT_FORECAST_HOURS,
    current_sensor_summary: dict[str, Any] | None = None,
    current_weather_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Predict near-term soil moisture for one zone using recent stored readings."""
    zone = db.query(Zone).filter(Zone.zone_id == zone_id).first()
    if not zone:
        return _fallback_prediction(
            zone_id=zone_id,
            reason="zone_not_found",
            current_sensor_summary=current_sensor_summary,
            current_weather_summary=current_weather_summary,
        )

    sensor_ids = [binding.sensor_id for binding in zone.sensor_bindings if binding.is_enabled]
    rows = _load_sensor_rows(db, sensor_ids, history_hours)
    weather = _load_recent_weather(db, zone.location)
    if len(rows) < MIN_TRAINING_ROWS:
        return _fallback_prediction(
            zone_id=zone_id,
            reason="insufficient_history",
            current_sensor_summary=current_sensor_summary,
            current_weather_summary=current_weather_summary,
            sample_count=len(rows),
        )

    try:
        from sklearn.linear_model import LinearRegression
    except Exception as exc:
        return _fallback_prediction(
            zone_id=zone_id,
            reason=f"model_unavailable:{exc}",
            current_sensor_summary=current_sensor_summary,
            current_weather_summary=current_weather_summary,
            sample_count=len(rows),
        )

    features: list[list[float]] = []
    targets: list[float] = []
    # Train on the next stored reading so the model learns one-step moisture drift.
    for index in range(len(rows) - 1):
        features.append(_build_features(index, rows[index], weather))
        targets.append(_bounded_moisture(rows[index + 1].soil_moisture))

    if len(features) < MIN_TRAINING_ROWS - 1:
        return _fallback_prediction(
            zone_id=zone_id,
            reason="insufficient_training_pairs",
            current_sensor_summary=current_sensor_summary,
            current_weather_summary=current_weather_summary,
            sample_count=len(features),
        )

    model = LinearRegression()
    model.fit(features, targets)

    forecast_points = max(1, min(int(forecast_hours or DEFAULT_FORECAST_HOURS), 72))
    last_row = rows[-1]
    latest_moisture = _bounded_moisture(last_row.soil_moisture)
    predicted_moisture = latest_moisture
    now = dt.datetime.utcnow()
    forecast_series: list[dict[str, Any]] = []

    # Roll the one-step model forward to cover the requested forecast horizon.
    for offset in range(1, forecast_points + 1):
        feature_row = _build_features(len(rows) + offset, last_row, weather, soil_moisture=predicted_moisture)
        predicted_moisture = _bounded_moisture(model.predict([feature_row])[0])
        forecast_series.append(
            {
                "timestamp": (now + dt.timedelta(hours=offset)).isoformat(),
                "predicted_soil_moisture": round(predicted_moisture, 2),
            }
        )

    confidence = "high" if len(features) >= 24 else "medium"
    return {
        "zone_id": zone_id,
        "history_hours": history_hours,
        "forecast_hours": forecast_points,
        "current_soil_moisture": round(latest_moisture, 2),
        "predicted_soil_moisture_24h": round(predicted_moisture, 2),
        "confidence": confidence,
        "sample_count": len(features),
        "fallback_used": False,
        "features_used": [
            "time_index",
            "soil_moisture",
            "temperature",
            "light_intensity",
            "rainfall",
            "weather_temperature",
            "weather_humidity",
            "weather_precipitation",
        ],
        "forecast_series": forecast_series,
        "recommendation_basis": "rolling_linear_regression",
    }


def _load_sensor_rows(db: Session, sensor_ids: list[str], history_hours: int) -> list[SensorData]:
    if not sensor_ids:
        return []
    since = dt.datetime.utcnow() - dt.timedelta(hours=max(1, int(history_hours or DEFAULT_HISTORY_HOURS)))
    return (
        db.query(SensorData)
        .filter(SensorData.sensor_id.in_(sensor_ids), SensorData.timestamp >= since)
        .order_by(SensorData.timestamp.asc())
        .all()
    )


def _load_recent_weather(db: Session, location: str | None) -> WeatherData | None:
    if not location:
        return None
    return (
        db.query(WeatherData)
        .filter(WeatherData.location == location)
        .order_by(WeatherData.timestamp.desc())
        .first()
    )


def _build_features(
    time_index: int,
    row: SensorData,
    weather: WeatherData | None,
    *,
    soil_moisture: float | None = None,
) -> list[float]:
    return [
        float(time_index),
        _bounded_moisture(row.soil_moisture if soil_moisture is None else soil_moisture),
        _safe_float(row.temperature),
        _safe_float(row.light_intensity),
        _safe_float(row.rainfall),
        _safe_float(weather.temperature if weather else row.temperature),
        _safe_float(weather.humidity if weather else None),
        _safe_float(weather.precipitation if weather else row.rainfall),
    ]


def _fallback_prediction(
    *,
    zone_id: str,
    reason: str,
    current_sensor_summary: dict[str, Any] | None = None,
    current_weather_summary: dict[str, Any] | None = None,
    sample_count: int = 0,
) -> dict[str, Any]:
    average = (current_sensor_summary or {}).get("average") if isinstance(current_sensor_summary, dict) else {}
    current_moisture = _bounded_moisture((average or {}).get("soil_moisture"))
    now = dt.datetime.utcnow()
    return {
        "zone_id": zone_id,
        "history_hours": DEFAULT_HISTORY_HOURS,
        "forecast_hours": DEFAULT_FORECAST_HOURS,
        "current_soil_moisture": round(current_moisture, 2),
        "predicted_soil_moisture_24h": round(current_moisture, 2),
        "confidence": "low",
        "sample_count": sample_count,
        "fallback_used": True,
        "fallback_reason": reason,
        "features_used": ["current_soil_moisture"],
        "forecast_series": [
            {
                "timestamp": (now + dt.timedelta(hours=DEFAULT_FORECAST_HOURS)).isoformat(),
                "predicted_soil_moisture": round(current_moisture, 2),
            }
        ],
        "recommendation_basis": "current_summary_fallback",
        "weather_context": current_weather_summary or {},
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _bounded_moisture(value: Any) -> float:
    return max(0.0, min(100.0, _safe_float(value)))
