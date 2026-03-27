"""
HydroMCP Server — 水利灌溉智能体 MCP 工具服务器 (FastMCP)

通过标准 MCP 协议暴露水利业务工具和数据处理工具，
使任何支持 MCP 的 AI 客户端（LangChain Agent、Claude Desktop 等）都能调用。
"""
import sys
import os
import json
import datetime
import random
import math
from typing import Optional

# 确保 src 包可以被找到
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastmcp import FastMCP

mcp = FastMCP("HydroAgent 水利灌溉智能体")

# ============================================================
#  内部辅助函数
# ============================================================

def _get_latest_sensor_data() -> dict:
    """获取最新传感器数据（模拟物联网传感器读数）"""
    try:
        from src.data.data_collection import DataCollectionModule
        collector = DataCollectionModule()
        data = collector.get_data()
        return data["data"]
    except Exception:
        return {
            "soil_moisture": round(random.uniform(20, 70), 2),
            "temperature": round(random.uniform(18, 35), 2),
            "light_intensity": round(random.uniform(100, 900), 2),
            "rainfall": round(random.uniform(0, 3), 2),
        }


def _get_sensor_history(data_type: str, hours: int) -> dict:
    """获取传感器历史数据（模拟时序数据）"""
    now = datetime.datetime.now()
    points = min(hours * 4, 200)
    timestamps = []
    values = []
    
    base_values = {"soil_moisture": 45, "temperature": 25, "light_intensity": 500, "rainfall": 0.5}
    amplitude = {"soil_moisture": 15, "temperature": 8, "light_intensity": 300, "rainfall": 1.5}
    base = base_values.get(data_type, 50)
    amp = amplitude.get(data_type, 10)
    
    for i in range(points):
        t = now - datetime.timedelta(minutes=15 * (points - i - 1))
        timestamps.append(t.isoformat())
        val = base + amp * math.sin(i / points * 2 * math.pi) + random.uniform(-3, 3) - i * 0.02
        values.append(round(max(0, val), 2))
    
    return {"timestamps": timestamps, "values": values}


_irrigation_state = {"status": "stopped", "start_time": None, "duration_minutes": 0}
_alarm_state = {"enabled": True, "threshold": 25.0}


# ============================================================
#  水利业务工具 (5 个)
# ============================================================

@mcp.tool()
def query_sensor_data(sensor_id: str = "all") -> str:
    """
    查询物联网传感器实时数据。
    返回土壤湿度(%)、环境温度(°C)、光照强度(lux)、降雨量(mm)。
    
    Args:
        sensor_id: 传感器ID，'all' 为查询全部传感器的平均值。
    """
    data = _get_latest_sensor_data()
    moisture = data.get("soil_moisture", 0)
    
    if moisture < 25:
        status = "⚠️ 严重缺水，需立即灌溉"
    elif moisture < 40:
        status = "🟡 湿度偏低，建议考虑灌溉"
    elif moisture < 70:
        status = "✅ 湿度正常"
    else:
        status = "💧 湿度充足，无需灌溉"
    
    result = {
        "sensor_id": sensor_id,
        "timestamp": datetime.datetime.now().isoformat(),
        "readings": data,
        "status_assessment": status,
        "units": {"soil_moisture": "%", "temperature": "°C", "light_intensity": "lux", "rainfall": "mm/h"}
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def query_weather(city: str = "北京") -> str:
    """
    查询城市实时天气和未来天气预报（高德天气API）。
    
    Args:
        city: 城市名称，例如 '北京', '上海', '广州'
    """
    try:
        from src.config import config
        import requests
        params = {"city": city, "key": config.WEATHER_API_KEY, "extensions": "all", "output": "JSON"}
        resp = requests.get(config.API_SERVICE_URL, params=params, timeout=5)
        data = resp.json()
        if data.get("status") == "1" and data.get("forecasts"):
            forecast = data["forecasts"][0]
            casts = forecast.get("casts", [])
            result = {
                "city": city,
                "timestamp": datetime.datetime.now().isoformat(),
                "current": {
                    "day_weather": casts[0]["dayweather"] if casts else "未知",
                    "day_temp": casts[0]["daytemp"] if casts else "--",
                    "night_temp": casts[0]["nighttemp"] if casts else "--",
                    "wind_direction": casts[0]["daywind"] if casts else "--",
                    "wind_power": casts[0]["daypower"] if casts else "--",
                },
                "forecast_days": [
                    {"date": c.get("date"), "day_weather": c.get("dayweather"),
                     "day_temp": c.get("daytemp"), "night_temp": c.get("nighttemp")}
                    for c in casts[:4]
                ],
                "irrigation_advice": "✅ 明天有雨，建议推迟灌溉" if any(
                    "雨" in c.get("dayweather", "") for c in casts[1:3]
                ) else "无降雨预报，可按计划灌溉"
            }
            return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception:
        pass
    
    result = {
        "city": city, "timestamp": datetime.datetime.now().isoformat(),
        "current": {"day_weather": "多云", "day_temp": str(random.randint(20, 32)),
                     "night_temp": str(random.randint(15, 22)),
                     "wind_direction": "东南", "wind_power": "3"},
        "forecast_days": [
            {"date": (datetime.date.today() + datetime.timedelta(days=i)).isoformat(),
             "day_weather": random.choice(["晴", "多云", "小雨", "阵雨"]),
             "day_temp": str(random.randint(20, 32)),
             "night_temp": str(random.randint(15, 22))}
            for i in range(4)
        ],
        "irrigation_advice": "数据来源：模拟数据",
        "note": "使用模拟天气数据"
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def control_irrigation(action: str, duration_minutes: int = 30) -> str:
    """
    控制灌溉设备启停。
    
    Args:
        action: 操作指令 —— 'start' 启动灌溉 | 'stop' 停止灌溉 | 'status' 查询状态
        duration_minutes: 灌溉持续时间（分钟），仅 start 时有效
    """
    global _irrigation_state
    now = datetime.datetime.now()
    
    if action == "status":
        state = _irrigation_state.copy()
        if state["status"] == "running" and state["start_time"]:
            elapsed = (now - datetime.datetime.fromisoformat(state["start_time"])).total_seconds() / 60
            state["elapsed_minutes"] = round(elapsed, 1)
            state["remaining_minutes"] = round(max(0, state["duration_minutes"] - elapsed), 1)
        return json.dumps({"success": True, "state": state}, ensure_ascii=False, indent=2)
    elif action == "start":
        if _irrigation_state["status"] == "running":
            return json.dumps({"success": False, "message": "灌溉设备已在运行中"}, ensure_ascii=False)
        _irrigation_state = {"status": "running", "start_time": now.isoformat(), "duration_minutes": duration_minutes}
        try:
            from src.database.models import SessionLocal, IrrigationLog
            db = SessionLocal()
            db.add(IrrigationLog(event="start", start_time=now, duration_planned_seconds=duration_minutes*60,
                                 status="running", message=f"MCP Agent 触发：计划灌溉 {duration_minutes} 分钟"))
            db.commit(); db.close()
        except Exception:
            pass
        return json.dumps({"success": True, "message": f"✅ 灌溉已启动！持续 {duration_minutes} 分钟",
                           "state": _irrigation_state}, ensure_ascii=False, indent=2)
    elif action == "stop":
        if _irrigation_state["status"] == "stopped":
            return json.dumps({"success": False, "message": "灌溉设备未在运行"}, ensure_ascii=False)
        _irrigation_state = {"status": "stopped", "start_time": None, "duration_minutes": 0}
        return json.dumps({"success": True, "message": "✅ 灌溉已停止"}, ensure_ascii=False, indent=2)
    return json.dumps({"success": False, "message": f"未知操作: {action}"}, ensure_ascii=False)


@mcp.tool()
def manage_alarm(action: str, threshold: Optional[float] = None) -> str:
    """
    管理土壤湿度报警系统。
    
    Args:
        action: 'enable' | 'disable' | 'set_threshold' | 'status'
        threshold: 湿度报警阈值（0-100），仅 set_threshold 时有效
    """
    global _alarm_state
    if action == "status":
        return json.dumps({"alarm": _alarm_state}, ensure_ascii=False, indent=2)
    elif action == "enable":
        _alarm_state["enabled"] = True
        return json.dumps({"success": True, "message": "✅ 报警已启用"}, ensure_ascii=False)
    elif action == "disable":
        _alarm_state["enabled"] = False
        return json.dumps({"success": True, "message": "⚠️ 报警已禁用"}, ensure_ascii=False)
    elif action == "set_threshold":
        if threshold is None or not (0 <= threshold <= 100):
            return json.dumps({"success": False, "message": "threshold 必须在 0-100 之间"}, ensure_ascii=False)
        _alarm_state["threshold"] = threshold
        return json.dumps({"success": True, "message": f"✅ 阈值已设置为 {threshold}%"}, ensure_ascii=False)
    return json.dumps({"success": False, "message": f"未知操作: {action}"}, ensure_ascii=False)


@mcp.tool()
def recommend_irrigation_plan() -> str:
    """综合分析当前传感器数据和天气情况，推荐最优灌溉方案。"""
    sensor = _get_latest_sensor_data()
    moisture = sensor.get("soil_moisture", 50)
    temp = sensor.get("temperature", 25)
    
    needs_irrigation = moisture < 40
    urgency = "紧急" if moisture < 25 else ("建议" if moisture < 40 else "暂无需要")
    evapotranspiration = max(0, (0.23 * temp - 1.5))
    deficit_mm = max(0, (40 - moisture) * 2)
    recommended_duration = max(15, int(deficit_mm * 3 + 10)) if needs_irrigation else 0
    best_time = "清晨 6:00-8:00" if temp > 28 else "任意时段均可"
    
    result = {
        "timestamp": datetime.datetime.now().isoformat(),
        "current_status": {"soil_moisture": f"{moisture}%", "temperature": f"{temp}°C",
                           "evapotranspiration_estimate": f"{evapotranspiration:.2f} mm/day"},
        "recommendation": {"needs_irrigation": needs_irrigation, "urgency": urgency,
                           "action": f"启动灌溉 {recommended_duration} 分钟" if needs_irrigation else "暂不需要灌溉",
                           "recommended_duration_minutes": recommended_duration, "best_irrigation_time": best_time},
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


# ============================================================
#  数据处理工具 (4 个)
# ============================================================

@mcp.tool()
def statistical_analysis(data_type: str = "soil_moisture", hours: int = 24) -> str:
    """
    对传感器时序数据进行统计分析。
    返回均值、中位数、标准差、极值、趋势方向（线性回归斜率）。
    
    Args:
        data_type: 'soil_moisture' | 'temperature' | 'light_intensity' | 'rainfall'
        hours: 分析最近 N 小时的数据（最大168）
    """
    try:
        import numpy as np
        hours = min(hours, 168)
        history = _get_sensor_history(data_type, hours)
        values = np.array(history["values"])
        if len(values) < 2:
            return json.dumps({"error": "数据点不足"}, ensure_ascii=False)
        x = np.arange(len(values))
        slope, _ = np.polyfit(x, values, 1)
        points_per_hour = len(values) / hours
        slope_per_hour = slope * points_per_hour
        trend_desc = ("明显上升" if slope_per_hour > 0.5 else "轻微上升" if slope_per_hour > 0.1
                      else "明显下降" if slope_per_hour < -0.5 else "轻微下降" if slope_per_hour < -0.1
                      else "基本稳定")
        result = {
            "data_type": data_type, "analysis_period": f"最近 {hours} 小时", "data_points": int(len(values)),
            "statistics": {"mean": round(float(np.mean(values)), 2), "median": round(float(np.median(values)), 2),
                           "std": round(float(np.std(values)), 2), "min": round(float(np.min(values)), 2),
                           "max": round(float(np.max(values)), 2)},
            "trend": {"slope_per_hour": round(slope_per_hour, 3), "description": trend_desc},
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"分析失败: {str(e)}"}, ensure_ascii=False)


@mcp.tool()
def anomaly_detection(data_type: str = "soil_moisture", hours: int = 48, z_threshold: float = 2.5) -> str:
    """
    使用 Z-score 方法检测传感器数据中的异常值。
    
    Args:
        data_type: 'soil_moisture' | 'temperature' | 'light_intensity' | 'rainfall'
        hours: 检测时间范围（小时）
        z_threshold: Z-score 阈值，默认 2.5
    """
    try:
        import numpy as np
        from scipy import stats
        history = _get_sensor_history(data_type, hours)
        values = np.array(history["values"])
        timestamps = history["timestamps"]
        if len(values) < 5:
            return json.dumps({"error": "数据点不足 (需 ≥5 个)"}, ensure_ascii=False)
        z_scores = np.abs(stats.zscore(values))
        anomaly_indices = np.where(z_scores > z_threshold)[0]
        anomaly_details = [
            {"index": int(idx), "timestamp": timestamps[idx], "value": round(float(values[idx]), 2),
             "z_score": round(float(z_scores[idx]), 2)}
            for idx in anomaly_indices[:10]
        ]
        anomaly_ratio = len(anomaly_indices) / len(values) * 100
        recommendation = ("✅ 数据正常" if len(anomaly_indices) == 0
                          else "⚠️ 少量异常" if anomaly_ratio < 5
                          else "🚨 异常比例较高，建议检查传感器")
        result = {
            "data_type": data_type, "z_threshold": z_threshold,
            "total_points": int(len(values)), "anomaly_count": int(len(anomaly_indices)),
            "anomaly_ratio": f"{anomaly_ratio:.1f}%", "anomaly_details": anomaly_details,
            "recommendation": recommendation,
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"异常检测失败: {str(e)}"}, ensure_ascii=False)


@mcp.tool()
def time_series_forecast(data_type: str = "soil_moisture", history_hours: int = 48, forecast_hours: int = 12) -> str:
    """
    基于历史数据进行时序预测（多项式回归 + 移动平均平滑）。
    
    Args:
        data_type: 预测目标数据类型
        history_hours: 使用多少小时的历史数据
        forecast_hours: 预测未来多少小时（最大48）
    """
    try:
        import numpy as np
        from sklearn.preprocessing import PolynomialFeatures
        from sklearn.linear_model import LinearRegression
        from sklearn.pipeline import Pipeline
        forecast_hours = min(forecast_hours, 48)
        history = _get_sensor_history(data_type, history_hours)
        values = np.array(history["values"])
        if len(values) < 10:
            return json.dumps({"error": "历史数据不足（需 ≥10 个点）"}, ensure_ascii=False)
        X = np.arange(len(values)).reshape(-1, 1)
        model = Pipeline([("poly", PolynomialFeatures(degree=3)), ("linear", LinearRegression())])
        model.fit(X, values)
        points_per_hour = len(values) / history_hours
        future_points = int(forecast_hours * points_per_hour)
        X_future = np.arange(len(values), len(values) + future_points).reshape(-1, 1)
        y_pred = model.predict(X_future)
        window = min(5, len(y_pred))
        y_pred_smooth = np.convolve(y_pred, np.ones(window) / window, mode='valid') if window > 1 else y_pred
        now = datetime.datetime.now()
        step_minutes = int(60 / points_per_hour) if points_per_hour > 0 else 60
        final_val = float(y_pred_smooth[-1]) if len(y_pred_smooth) > 0 else float(values[-1])
        current_val = float(values[-1])
        warnings = []
        if data_type == "soil_moisture":
            if final_val < 25:
                warnings.append(f"🚨 预计湿度将降至 {final_val:.1f}%，建议立即安排灌溉")
            elif final_val < 40:
                warnings.append(f"⚠️ 预计湿度将降至 {final_val:.1f}%，建议提前安排灌溉")
        y_train_pred = model.predict(X)
        ss_res = np.sum((values - y_train_pred) ** 2)
        ss_tot = np.sum((values - np.mean(values)) ** 2)
        r_squared = max(0, 1 - ss_res / ss_tot) if ss_tot > 0 else 0
        result = {
            "data_type": data_type, "model": "PolynomialRegression(degree=3) + MovingAverage",
            "current_value": round(current_val, 2), "predicted_final_value": round(final_val, 2),
            "trend": "下降" if final_val < current_val - 1 else ("上升" if final_val > current_val + 1 else "稳定"),
            "model_r_squared": round(float(r_squared), 3),
            "confidence": "高" if r_squared > 0.8 else ("中" if r_squared > 0.5 else "低"),
            "warnings": warnings,
            "forecast_data": [
                {"timestamp": (now + datetime.timedelta(minutes=step_minutes * i)).isoformat(),
                 "predicted_value": round(float(v), 2)}
                for i, v in enumerate(y_pred_smooth[:24])
            ],
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"预测失败: {str(e)}"}, ensure_ascii=False)


@mcp.tool()
def correlation_analysis(variables: str = "soil_moisture,temperature,rainfall", hours: int = 168) -> str:
    """
    分析多个传感器变量之间的相关性（皮尔逊相关系数矩阵）。
    
    Args:
        variables: 逗号分隔的变量列表
        hours: 分析时间范围（小时）
    """
    try:
        import numpy as np
        import pandas as pd
        valid_vars = ["soil_moisture", "temperature", "light_intensity", "rainfall"]
        var_list = [v.strip() for v in variables.split(",") if v.strip() in valid_vars]
        if len(var_list) < 2:
            return json.dumps({"error": "至少需要 2 个有效变量"}, ensure_ascii=False)
        series_dict = {}
        min_len = float('inf')
        for var in var_list:
            history = _get_sensor_history(var, hours)
            series_dict[var] = history["values"]
            min_len = min(min_len, len(history["values"]))
        df = pd.DataFrame({var: series_dict[var][:int(min_len)] for var in var_list})
        corr_matrix = df.corr(method="pearson")
        corr_names = {"soil_moisture": "土壤湿度", "temperature": "温度",
                      "light_intensity": "光照强度", "rainfall": "降雨量"}
        key_findings = []
        for i, var_a in enumerate(var_list):
            for var_b in var_list[i+1:]:
                r = corr_matrix.loc[var_a, var_b]
                if abs(r) > 0.3:
                    strength = "强" if abs(r) > 0.7 else "中等"
                    direction = "正" if r > 0 else "负"
                    key_findings.append(f"{corr_names.get(var_a, var_a)} 与 {corr_names.get(var_b, var_b)} 呈{strength}{direction}相关 (r={r:.3f})")
        result = {
            "variables_analyzed": var_list, "data_points": int(min_len),
            "correlation_matrix": {var: {o: round(corr_matrix.loc[var, o], 3) for o in var_list} for var in var_list},
            "key_findings": key_findings if key_findings else ["各变量之间无显著相关性 (|r|<0.3)"],
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"相关性分析失败: {str(e)}"}, ensure_ascii=False)


# ============================================================
#  MCP Resources
# ============================================================

@mcp.resource("hydro://sensors/current")
def sensor_current_resource() -> str:
    """当前传感器实时数据资源"""
    return json.dumps({"timestamp": datetime.datetime.now().isoformat(), "readings": _get_latest_sensor_data()}, ensure_ascii=False)

@mcp.resource("hydro://irrigation/status")
def irrigation_status_resource() -> str:
    """灌溉设备状态资源"""
    return json.dumps(_irrigation_state, ensure_ascii=False)

@mcp.resource("hydro://alarm/status")
def alarm_status_resource() -> str:
    """报警系统状态资源"""
    return json.dumps(_alarm_state, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="stdio")
