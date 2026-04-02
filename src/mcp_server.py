"""
HydroMCP Server — zone-aware irrigation tools for HydroAgent.
"""
from __future__ import annotations

import datetime
import json
import math
import os
import random
import sys
from typing import Optional

from fastmcp import FastMCP

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.models import SessionLocal
from src.services import (
    approve_plan,
    bootstrap_default_zones,
    create_plan,
    execute_plan,
    get_plan_by_id,
    get_zone_by_id,
    get_zone_status,
    list_zones,
    reject_plan,
    summarize_system_irrigation,
)

mcp = FastMCP("HydroAgent Zone-Aware MCP")

_alarm_state = {"enabled": True, "threshold": 25.0}


def _with_db(callback):
    db = SessionLocal()
    try:
        bootstrap_default_zones(db)
        return callback(db)
    finally:
        db.close()


def _get_sensor_history(data_type: str, hours: int, zone_id: str | None = None) -> dict:
    now = datetime.datetime.now()
    points = min(hours * 4, 200)
    timestamps = []
    values = []

    zone_factor = sum(ord(char) for char in (zone_id or "default")) % 7
    base_values = {
        "soil_moisture": 45 - zone_factor,
        "temperature": 25 + zone_factor / 2,
        "light_intensity": 500 + zone_factor * 10,
        "rainfall": 0.5 + zone_factor / 10,
    }
    amplitude = {"soil_moisture": 15, "temperature": 8, "light_intensity": 300, "rainfall": 1.5}
    base = base_values.get(data_type, 50)
    amp = amplitude.get(data_type, 10)

    for index in range(points):
        ts = now - datetime.timedelta(minutes=15 * (points - index - 1))
        timestamps.append(ts.isoformat())
        val = base + amp * math.sin(index / max(points, 1) * 2 * math.pi) + random.uniform(-3, 3) - index * 0.02
        values.append(round(max(0, val), 2))

    return {"timestamps": timestamps, "values": values}


@mcp.tool()
def list_farm_zones() -> str:
    """List all configured irrigation zones and actuators."""

    def _callback(db):
        return json.dumps({"zones": [zone.to_dict() for zone in list_zones(db)]}, ensure_ascii=False, indent=2)

    return _with_db(_callback)


@mcp.tool()
def query_sensor_data(zone_id: str, sensor_id: str = "primary") -> str:
    """Query the latest sensor readings for a zone."""

    def _callback(db):
        status = get_zone_status(db, zone_id)
        return json.dumps(
            {
                "zone_id": zone_id,
                "sensor_id": sensor_id,
                "timestamp": status["sensor_summary"].get("timestamp"),
                "readings": status["sensor_summary"].get("average", {}),
                "raw_readings": status["sensor_summary"].get("readings", []),
                "status_assessment": "ok" if status["sensor_summary"].get("status") == "ok" else "missing",
                "units": {"soil_moisture": "%", "temperature": "°C", "light_intensity": "lux", "rainfall": "mm/h"},
            },
            ensure_ascii=False,
            indent=2,
        )

    return _with_db(_callback)


@mcp.tool()
def query_weather(zone_id: str) -> str:
    """Query weather summary for a zone."""

    def _callback(db):
        status = get_zone_status(db, zone_id)
        return json.dumps(
            {
                "zone_id": zone_id,
                "city": status["zone"]["location"],
                "weather": status["weather_summary"],
                "irrigation_advice": (
                    "推迟灌溉" if status["weather_summary"].get("rain_expected") else "可继续评估灌溉"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )

    return _with_db(_callback)


@mcp.tool()
def get_zone_operating_status(zone_id: str) -> str:
    """Return the current operating context for a zone."""

    def _callback(db):
        return json.dumps(get_zone_status(db, zone_id), ensure_ascii=False, indent=2)

    return _with_db(_callback)


@mcp.tool()
def create_irrigation_plan(zone_id: str, conversation_id: str = "", trigger: str = "chat") -> str:
    """Create a structured irrigation plan for a zone."""

    def _callback(db):
        plan = create_plan(
            db,
            zone_id,
            conversation_id=conversation_id or None,
            trigger=trigger,
            requested_by="agent",
        )
        return json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)

    return _with_db(_callback)


@mcp.tool()
def get_plan_status(plan_id: str) -> str:
    """Fetch the latest state for a structured irrigation plan."""

    def _callback(db):
        plan = get_plan_by_id(db, plan_id)
        if not plan:
            return json.dumps({"error": f"Plan not found: {plan_id}"}, ensure_ascii=False)
        return json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)

    return _with_db(_callback)


@mcp.tool()
def approve_irrigation_plan(plan_id: str, actor: str = "user", comment: str = "") -> str:
    """Approve a structured irrigation plan."""

    def _callback(db):
        plan = approve_plan(db, plan_id, actor=actor, comment=comment or None)
        return json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)

    return _with_db(_callback)


@mcp.tool()
def reject_irrigation_plan(plan_id: str, actor: str = "user", comment: str = "") -> str:
    """Reject a structured irrigation plan."""

    def _callback(db):
        plan = reject_plan(db, plan_id, actor=actor, comment=comment or None)
        return json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)

    return _with_db(_callback)


@mcp.tool()
def control_irrigation(
    action: str,
    zone_id: str,
    actuator_id: str = "",
    duration_minutes: int = 30,
    plan_id: str = "",
) -> str:
    """Validate or execute an irrigation control action for a zone."""

    def _callback(db):
        zone = get_zone_by_id(db, zone_id)
        if not zone:
            return json.dumps({"success": False, "message": f"Zone not found: {zone_id}"}, ensure_ascii=False)

        status = get_zone_status(db, zone_id)
        actuator = next((item for item in zone.actuators if item.actuator_id == actuator_id), None) if actuator_id else next(
            (item for item in zone.actuators if item.is_enabled),
            None,
        )
        can_execute = True
        reasons = []

        if not actuator:
            can_execute = False
            reasons.append("缺少可用执行器")
        elif not actuator.is_enabled:
            can_execute = False
            reasons.append("执行器已禁用")
        elif action == "start" and actuator.status == "running":
            can_execute = False
            reasons.append("执行器已在运行")

        if action == "start" and status["weather_summary"].get("rain_expected"):
            can_execute = False
            reasons.append("天气预报显示近期有雨")

        payload = {
            "success": can_execute,
            "zone_id": zone_id,
            "actuator_id": actuator.actuator_id if actuator else actuator_id,
            "action": action,
            "duration_minutes": duration_minutes,
            "requires_approval": action == "start",
            "can_execute": can_execute,
            "reasons": reasons,
        }

        if action == "status":
            payload["state"] = summarize_system_irrigation(db)
            return json.dumps(payload, ensure_ascii=False, indent=2)

        if action == "stop":
            from src.services.irrigation_service import stop_zone_irrigation

            stop_result = stop_zone_irrigation(db, zone_id, actor="agent")
            payload.update(stop_result)
            return json.dumps(payload, ensure_ascii=False, indent=2)

        if not can_execute:
            return json.dumps(payload, ensure_ascii=False, indent=2)

        if plan_id:
            plan = execute_plan(db, plan_id, actor="agent")
            payload["plan"] = plan.to_dict()
            payload["message"] = "计划已执行"
        else:
            payload["message"] = "具备执行条件，但必须通过审批后的计划执行"
        return json.dumps(payload, ensure_ascii=False, indent=2)

    return _with_db(_callback)


@mcp.tool()
def execute_approved_plan(plan_id: str, actor: str = "agent") -> str:
    """Execute an approved plan."""

    def _callback(db):
        plan = execute_plan(db, plan_id, actor=actor)
        return json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)

    return _with_db(_callback)


@mcp.tool()
def manage_alarm(action: str, threshold: Optional[float] = None) -> str:
    """Manage the soil moisture alarm threshold."""

    global _alarm_state
    if action == "status":
        return json.dumps({"alarm": _alarm_state}, ensure_ascii=False, indent=2)
    if action == "enable":
        _alarm_state["enabled"] = True
        return json.dumps({"success": True, "message": "报警已启用"}, ensure_ascii=False)
    if action == "disable":
        _alarm_state["enabled"] = False
        return json.dumps({"success": True, "message": "报警已禁用"}, ensure_ascii=False)
    if action == "set_threshold":
        if threshold is None or not (0 <= threshold <= 100):
            return json.dumps({"success": False, "message": "threshold 必须在 0-100 之间"}, ensure_ascii=False)
        _alarm_state["threshold"] = threshold
        return json.dumps({"success": True, "message": f"阈值已设置为 {threshold}%"}, ensure_ascii=False)
    return json.dumps({"success": False, "message": f"未知操作: {action}"}, ensure_ascii=False)


@mcp.tool()
def recommend_irrigation_plan(zone_id: str) -> str:
    """Return a lightweight recommendation without mutating plan state."""

    def _callback(db):
        status = get_zone_status(db, zone_id)
        moisture = status["sensor_summary"].get("average", {}).get("soil_moisture", 0.0)
        threshold = status["zone"]["soil_moisture_threshold"]
        needs = moisture < threshold and not status["weather_summary"].get("rain_expected")
        deficit = max(0.0, threshold - moisture)
        duration = max(status["zone"]["default_duration_minutes"], int(deficit * 1.5) + 10) if needs else 0
        return json.dumps(
            {
                "zone_id": zone_id,
                "current_status": status["sensor_summary"],
                "recommendation": {
                    "needs_irrigation": needs,
                    "recommended_duration_minutes": duration,
                    "risk_level": "medium" if status["weather_summary"].get("rain_expected") else "low",
                },
                "weather": status["weather_summary"],
            },
            ensure_ascii=False,
            indent=2,
        )

    return _with_db(_callback)


@mcp.tool()
def statistical_analysis(data_type: str = "soil_moisture", hours: int = 24, zone_id: str = "") -> str:
    """Return statistics for a zone time series."""

    try:
        import numpy as np

        history = _get_sensor_history(data_type, min(hours, 168), zone_id or None)
        values = np.array(history["values"])
        if len(values) < 2:
            return json.dumps({"error": "数据点不足"}, ensure_ascii=False)
        x = np.arange(len(values))
        slope, _ = np.polyfit(x, values, 1)
        points_per_hour = len(values) / max(hours, 1)
        slope_per_hour = slope * points_per_hour
        trend_desc = (
            "明显上升"
            if slope_per_hour > 0.5
            else "轻微上升"
            if slope_per_hour > 0.1
            else "明显下降"
            if slope_per_hour < -0.5
            else "轻微下降"
            if slope_per_hour < -0.1
            else "基本稳定"
        )
        return json.dumps(
            {
                "zone_id": zone_id,
                "data_type": data_type,
                "statistics": {
                    "mean": round(float(np.mean(values)), 2),
                    "median": round(float(np.median(values)), 2),
                    "std": round(float(np.std(values)), 2),
                    "min": round(float(np.min(values)), 2),
                    "max": round(float(np.max(values)), 2),
                },
                "trend": {"slope_per_hour": round(float(slope_per_hour), 3), "description": trend_desc},
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"error": f"分析失败: {exc}"}, ensure_ascii=False)


@mcp.tool()
def anomaly_detection(data_type: str = "soil_moisture", hours: int = 48, z_threshold: float = 2.5, zone_id: str = "") -> str:
    """Detect anomalies in zone history."""

    try:
        import numpy as np
        from scipy import stats

        history = _get_sensor_history(data_type, hours, zone_id or None)
        values = np.array(history["values"])
        timestamps = history["timestamps"]
        if len(values) < 5:
            return json.dumps({"error": "数据点不足"}, ensure_ascii=False)
        z_scores = np.abs(stats.zscore(values))
        anomaly_indices = np.where(z_scores > z_threshold)[0]
        details = [
            {
                "timestamp": timestamps[index],
                "value": round(float(values[index]), 2),
                "z_score": round(float(z_scores[index]), 2),
            }
            for index in anomaly_indices[:10]
        ]
        return json.dumps(
            {
                "zone_id": zone_id,
                "data_type": data_type,
                "anomaly_count": int(len(anomaly_indices)),
                "anomaly_details": details,
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"error": f"异常检测失败: {exc}"}, ensure_ascii=False)


@mcp.tool()
def time_series_forecast(
    data_type: str = "soil_moisture",
    history_hours: int = 48,
    forecast_hours: int = 12,
    zone_id: str = "",
) -> str:
    """Forecast short-term zone sensor values."""

    try:
        import numpy as np
        from sklearn.linear_model import LinearRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import PolynomialFeatures

        history = _get_sensor_history(data_type, history_hours, zone_id or None)
        values = np.array(history["values"])
        if len(values) < 10:
            return json.dumps({"error": "历史数据不足"}, ensure_ascii=False)
        x_values = np.arange(len(values)).reshape(-1, 1)
        model = Pipeline([("poly", PolynomialFeatures(degree=3)), ("linear", LinearRegression())])
        model.fit(x_values, values)
        points_per_hour = len(values) / max(history_hours, 1)
        future_points = int(min(forecast_hours, 48) * points_per_hour)
        future_x = np.arange(len(values), len(values) + future_points).reshape(-1, 1)
        predicted = model.predict(future_x)
        now = datetime.datetime.now()
        step_minutes = int(60 / points_per_hour) if points_per_hour > 0 else 60
        forecast = [
            {
                "timestamp": (now + datetime.timedelta(minutes=step_minutes * index)).isoformat(),
                "predicted_value": round(float(value), 2),
            }
            for index, value in enumerate(predicted[:24])
        ]
        return json.dumps(
            {
                "zone_id": zone_id,
                "data_type": data_type,
                "current_value": round(float(values[-1]), 2),
                "predicted_final_value": round(float(predicted[-1]), 2) if len(predicted) else round(float(values[-1]), 2),
                "forecast_data": forecast,
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"error": f"预测失败: {exc}"}, ensure_ascii=False)


@mcp.tool()
def correlation_analysis(variables: str = "soil_moisture,temperature,rainfall", hours: int = 168, zone_id: str = "") -> str:
    """Analyze correlations between zone variables."""

    try:
        import numpy as np
        import pandas as pd

        valid_vars = ["soil_moisture", "temperature", "light_intensity", "rainfall"]
        var_list = [value.strip() for value in variables.split(",") if value.strip() in valid_vars]
        if len(var_list) < 2:
            return json.dumps({"error": "至少需要两个有效变量"}, ensure_ascii=False)
        series_dict = {}
        min_len = float("inf")
        for variable in var_list:
            history = _get_sensor_history(variable, hours, zone_id or None)
            series_dict[variable] = history["values"]
            min_len = min(min_len, len(history["values"]))
        data_frame = pd.DataFrame({key: series_dict[key][: int(min_len)] for key in var_list})
        corr_matrix = data_frame.corr(method="pearson")
        return json.dumps(
            {
                "zone_id": zone_id,
                "variables_analyzed": var_list,
                "correlation_matrix": {
                    key: {other: round(float(corr_matrix.loc[key, other]), 3) for other in var_list}
                    for key in var_list
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"error": f"相关性分析失败: {exc}"}, ensure_ascii=False)


@mcp.resource("hydro://zones")
def zones_resource() -> str:
    return _with_db(lambda db: json.dumps({"zones": [zone.to_dict() for zone in list_zones(db)]}, ensure_ascii=False))


@mcp.resource("hydro://irrigation/status")
def irrigation_status_resource() -> str:
    return _with_db(lambda db: json.dumps(summarize_system_irrigation(db), ensure_ascii=False))


@mcp.resource("hydro://alarm/status")
def alarm_status_resource() -> str:
    return json.dumps(_alarm_state, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="stdio")
