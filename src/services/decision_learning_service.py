"""
Decision-tree helpers for long-term irrigation plan recommendations.
"""
from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.orm import Session

from src.database.models import IrrigationPlan

MIN_TRAINING_ROWS = 6
MODEL_TYPE = "decision_tree_plan_advisor"
FEATURE_NAMES = [
    "zone_code",
    "soil_moisture",
    "threshold",
    "moisture_deficit",
    "predicted_soil_moisture_24h",
    "rain_expected",
    "sensor_ok",
    "actuator_available",
    "actuator_running",
    "default_duration_minutes",
    "risk_code",
    "execution_code",
]
RISK_CODES = {"low": 0, "medium": 1, "high": 2}
EXECUTION_CODES = {"not_started": 0, "executed": 1, "stopped": 1, "failed": 2}


def recommend_plan_decision(
    db: Session,
    *,
    zone_id: str,
    evidence: Any,
    ml_prediction: dict[str, Any] | None,
    history_limit: int = 200,
) -> dict[str, Any]:
    """Recommend action and duration from historical plan decisions."""
    current_features = _build_current_features(zone_id, evidence, ml_prediction)
    samples = _load_training_samples(db, history_limit=history_limit)
    if len(samples) < MIN_TRAINING_ROWS:
        return _fallback_decision(zone_id, current_features, "insufficient_history", len(samples))

    try:
        from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
    except Exception as exc:
        return _fallback_decision(zone_id, current_features, f"model_unavailable:{exc}", len(samples))

    feature_rows = [sample["features"] for sample in samples]
    action_labels = [sample["action"] for sample in samples]
    duration_targets = [sample["duration"] for sample in samples]

    classifier = DecisionTreeClassifier(max_depth=4, min_samples_leaf=2, random_state=42)
    regressor = DecisionTreeRegressor(max_depth=4, min_samples_leaf=2, random_state=42)
    classifier.fit(feature_rows, action_labels)
    regressor.fit(feature_rows, duration_targets)

    predicted_action = str(classifier.predict([current_features])[0])
    predicted_duration = max(0, int(round(float(regressor.predict([current_features])[0]))))
    confidence = _predict_confidence(classifier, current_features)
    top_factors = _top_factors(classifier.feature_importances_)

    return {
        "zone_id": zone_id,
        "recommended_action": predicted_action,
        "recommended_duration_minutes": predicted_duration,
        "confidence": confidence,
        "sample_count": len(samples),
        "model_type": MODEL_TYPE,
        "top_factors": top_factors,
        "fallback_used": False,
        "features_used": FEATURE_NAMES,
        "recommendation_basis": "historical_plan_decision_tree",
    }


def _load_training_samples(db: Session, *, history_limit: int) -> list[dict[str, Any]]:
    plans = (
        db.query(IrrigationPlan)
        .filter(IrrigationPlan.evidence_summary.isnot(None), IrrigationPlan.proposed_action.isnot(None))
        .order_by(IrrigationPlan.created_at.desc())
        .limit(history_limit)
        .all()
    )
    samples: list[dict[str, Any]] = []
    for plan in plans:
        evidence = plan.evidence_summary or {}
        zone = evidence.get("zone") if isinstance(evidence.get("zone"), dict) else {}
        sensor_summary = evidence.get("sensor_summary") if isinstance(evidence.get("sensor_summary"), dict) else {}
        weather_summary = evidence.get("weather_summary") if isinstance(evidence.get("weather_summary"), dict) else {}
        ml_prediction = evidence.get("ml_prediction") if isinstance(evidence.get("ml_prediction"), dict) else {}
        actuator_status = _actuator_status_from_zone(zone)
        samples.append(
            {
                "features": _build_features(
                    zone_id=plan.zone_id or str(zone.get("zone_id") or ""),
                    zone=zone,
                    sensor_summary=sensor_summary,
                    weather_summary=weather_summary,
                    ml_prediction=ml_prediction,
                    actuator_status=actuator_status,
                    risk_level=plan.risk_level,
                    execution_status=plan.execution_status,
                ),
                "action": plan.proposed_action or "hold",
                "duration": max(0, int(plan.recommended_duration_minutes or 0)),
            }
        )
    return samples


def _build_current_features(zone_id: str, evidence: Any, ml_prediction: dict[str, Any] | None) -> list[float]:
    actuator = getattr(evidence, "actuator", None)
    return _build_features(
        zone_id=zone_id,
        zone=getattr(evidence, "zone").to_dict(),
        sensor_summary=getattr(evidence, "sensor_summary", {}) or {},
        weather_summary=getattr(evidence, "weather_summary", {}) or {},
        ml_prediction=ml_prediction or {},
        actuator_status=getattr(actuator, "status", "unknown") if actuator else "missing",
        risk_level="low",
        execution_status="not_started",
    )


def _build_features(
    *,
    zone_id: str,
    zone: dict[str, Any],
    sensor_summary: dict[str, Any],
    weather_summary: dict[str, Any],
    ml_prediction: dict[str, Any],
    actuator_status: str,
    risk_level: str | None,
    execution_status: str | None,
) -> list[float]:
    average = sensor_summary.get("average") if isinstance(sensor_summary.get("average"), dict) else {}
    threshold = _safe_float(zone.get("soil_moisture_threshold"), 40.0)
    current_moisture = _safe_float(average.get("soil_moisture"))
    predicted_moisture = _safe_float(ml_prediction.get("predicted_soil_moisture_24h"), current_moisture)
    default_duration = _safe_float(zone.get("default_duration_minutes"), 30.0)
    moisture_deficit = max(0.0, threshold - min(current_moisture, predicted_moisture))
    return [
        _zone_code(zone_id),
        current_moisture,
        threshold,
        moisture_deficit,
        predicted_moisture,
        1.0 if weather_summary.get("rain_expected") else 0.0,
        1.0 if sensor_summary.get("status") == "ok" else 0.0,
        1.0 if actuator_status not in {"missing", "unknown", "disabled"} else 0.0,
        1.0 if actuator_status == "running" else 0.0,
        default_duration,
        float(RISK_CODES.get(risk_level or "low", 0)),
        float(EXECUTION_CODES.get(execution_status or "not_started", 0)),
    ]


def _actuator_status_from_zone(zone: dict[str, Any]) -> str:
    actuators = zone.get("actuators")
    if isinstance(actuators, list) and actuators:
        first = actuators[0]
        if isinstance(first, dict):
            status = first.get("status")
            if isinstance(status, str) and status:
                return status
    return "unknown"


def _fallback_decision(zone_id: str, features: list[float], reason: str, sample_count: int) -> dict[str, Any]:
    return {
        "zone_id": zone_id,
        "recommended_action": "hold",
        "recommended_duration_minutes": 0,
        "confidence": 0.0,
        "sample_count": sample_count,
        "model_type": MODEL_TYPE,
        "top_factors": [],
        "fallback_used": True,
        "fallback_reason": reason,
        "features_used": FEATURE_NAMES,
        "feature_snapshot": dict(zip(FEATURE_NAMES, features)),
        "recommendation_basis": "insufficient_history_fallback",
    }


def _predict_confidence(classifier: Any, features: list[float]) -> float:
    if hasattr(classifier, "predict_proba"):
        probabilities = classifier.predict_proba([features])[0]
        return round(float(max(probabilities)), 3)
    return 0.5


def _top_factors(importances: Any) -> list[str]:
    ranked = sorted(
        zip(FEATURE_NAMES, [float(value) for value in importances]),
        key=lambda item: item[1],
        reverse=True,
    )
    return [name for name, importance in ranked[:3] if importance > 0]


def _zone_code(zone_id: str) -> float:
    digest = hashlib.sha1(zone_id.encode("utf-8")).hexdigest()
    return float(int(digest[:6], 16) % 1000)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
