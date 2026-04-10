"""
数据处理模块 - 处理传感器数据并获取相关的天气信息。

当前天气服务默认使用 Open-Meteo：
1. geocoding-api.open-meteo.com 用于地名转经纬度
2. api.open-meteo.com/v1/forecast 用于当前天气与多日预报

为了避免影响现有前端、LangChain 工具和旧测试，这里仍然返回兼容的天气数据结构。
"""
from __future__ import annotations

import datetime
from typing import Any, Dict

import requests

from src.config import config
from src.exceptions.exceptions import InvalidSensorDataError, WeatherAPIError
from src.logger_config import logger


class DataProcessingModule:
    """
    处理传感器数据并获取相关的天气信息。
    """

    CITY_CODE_MAP = {
        "北京": "110000",
        "上海": "310000",
        "广州": "440100",
        "深圳": "440300",
        "杭州": "330100",
        "南京": "320100",
        "武汉": "420100",
        "成都": "510100",
        "重庆": "500000",
        "西安": "610100",
        "天津": "120000",
    }

    CITY_GEO_MAP = {
        "110101": {"name": "东城区", "province": "北京市", "latitude": 39.9288, "longitude": 116.4160},
        "110105": {"name": "朝阳区", "province": "北京市", "latitude": 39.9219, "longitude": 116.4436},
        "110000": {"name": "北京", "province": "北京市", "latitude": 39.9042, "longitude": 116.4074},
        "310000": {"name": "上海", "province": "上海市", "latitude": 31.2304, "longitude": 121.4737},
        "440100": {"name": "广州", "province": "广东省", "latitude": 23.1291, "longitude": 113.2644},
        "440300": {"name": "深圳", "province": "广东省", "latitude": 22.5431, "longitude": 114.0579},
        "330100": {"name": "杭州", "province": "浙江省", "latitude": 30.2741, "longitude": 120.1551},
        "320100": {"name": "南京", "province": "江苏省", "latitude": 32.0603, "longitude": 118.7969},
        "420100": {"name": "武汉", "province": "湖北省", "latitude": 30.5928, "longitude": 114.3055},
        "510100": {"name": "成都", "province": "四川省", "latitude": 30.5728, "longitude": 104.0668},
        "500000": {"name": "重庆", "province": "重庆市", "latitude": 29.5630, "longitude": 106.5516},
        "610100": {"name": "西安", "province": "陕西省", "latitude": 34.3416, "longitude": 108.9398},
        "120000": {"name": "天津", "province": "天津市", "latitude": 39.0842, "longitude": 117.2009},
    }

    REVERSE_CITY_CODE_MAP = {payload["name"]: code for code, payload in CITY_GEO_MAP.items()}
    GEOCODING_API_URL = "https://geocoding-api.open-meteo.com/v1/search"
    OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
    WEATHER_CODE_TEXT = {
        0: "晴",
        1: "大部晴朗",
        2: "局部多云",
        3: "阴",
        45: "雾",
        48: "冻雾",
        51: "毛毛雨",
        53: "细雨",
        55: "密集细雨",
        56: "冻毛毛雨",
        57: "强冻毛毛雨",
        61: "小雨",
        63: "中雨",
        65: "大雨",
        66: "冻雨",
        67: "强冻雨",
        71: "小雪",
        73: "中雪",
        75: "大雪",
        77: "雪粒",
        80: "阵雨",
        81: "较强阵雨",
        82: "强阵雨",
        85: "阵雪",
        86: "强阵雪",
        95: "雷暴",
        96: "雷暴伴小冰雹",
        99: "雷暴伴强冰雹",
    }

    def __init__(self, api_key: str = None, api_url: str = None):
        self.api_key = api_key or config.WEATHER_API_KEY
        self._custom_api_url = bool(api_url and api_url.strip())
        configured_url = api_url or config.API_SERVICE_URL or self.OPEN_METEO_FORECAST_URL
        self.weather_api_url = self._resolve_weather_api_url(configured_url)
        logger.info("DataProcessingModule initialized.")

    def process_sensor_data(self, sensor_data: Dict[str, Any]) -> Dict[str, Any]:
        if not sensor_data or not isinstance(sensor_data, dict):
            raise InvalidSensorDataError("Sensor data is None or not a dictionary")

        logger.debug(f"Processing sensor data for {sensor_data.get('sensor_id')}")
        processed_data = sensor_data.copy()
        processed_data["status"] = "processed"
        data = processed_data.get("data", {})
        if not data:
            processed_data["status"] = "invalid_data"
            raise InvalidSensorDataError("No data field in sensor data")

        soil_moisture = data.get("soil_moisture")
        if soil_moisture is None or not (0 <= soil_moisture <= 100):
            logger.warning(f"Invalid soil moisture value: {soil_moisture}")
            processed_data["status"] = "invalid_data"
            data["soil_moisture"] = max(0, min(100, soil_moisture if soil_moisture is not None else 0))

        temperature = data.get("temperature")
        if temperature is not None and (temperature < -40 or temperature > 60):
            logger.warning(f"Unusual temperature value: {temperature}")
            processed_data["status"] = "suspicious_data"

        for key in ["soil_moisture", "temperature", "light_intensity", "rainfall"]:
            if key not in data or data[key] is None:
                data[key] = 0.0
                logger.warning(f"Missing {key} value, setting to default 0.0")

        return processed_data

    def get_weather_data(self, city: str = "110101") -> Dict[str, Any]:
        location = self._resolve_location(city)
        forecast_payload = self._fetch_open_meteo_forecast(location)
        return self._normalize_forecast_payload(forecast_payload, location)

    def process_and_get_weather(self, sensor_data: Dict[str, Any], city: str = "110101") -> Dict[str, Any]:
        result = {"sensor_data": None, "weather_data": None}
        try:
            result["sensor_data"] = self.process_sensor_data(sensor_data)
        except InvalidSensorDataError as exc:
            logger.error(f"Invalid sensor data: {str(exc)}")
            if sensor_data:
                sensor_data_copy = sensor_data.copy()
                sensor_data_copy["status"] = "invalid"
                result["sensor_data"] = sensor_data_copy

        try:
            result["weather_data"] = self.get_weather_data(city)
        except WeatherAPIError as exc:
            logger.warning(f"Could not fetch weather data: {str(exc)}")
        return result

    def city_to_code(self, city_name: str) -> str:
        return self.CITY_CODE_MAP.get(city_name, "110000")

    def get_weather_by_city_name(self, city_name: str) -> Dict[str, Any]:
        city_code = self.city_to_code(city_name)
        return self.get_weather_data(city_code)

    def _resolve_location(self, city: str) -> dict[str, Any]:
        raw_value = str(city or "").strip()
        if not raw_value:
            raw_value = "110000"

        if raw_value in self.CITY_GEO_MAP:
            payload = dict(self.CITY_GEO_MAP[raw_value])
            payload["adcode"] = raw_value
            return payload

        if raw_value in self.REVERSE_CITY_CODE_MAP:
            code = self.REVERSE_CITY_CODE_MAP[raw_value]
            payload = dict(self.CITY_GEO_MAP[code])
            payload["adcode"] = code
            return payload

        geocoding_payload = self._fetch_geocoding(raw_value)
        results = geocoding_payload.get("results") or []
        if not results:
            raise WeatherAPIError(f"无法解析城市位置: {raw_value}")

        item = results[0]
        return {
            "name": item.get("name") or raw_value,
            "province": item.get("admin1") or item.get("country") or raw_value,
            "latitude": item.get("latitude"),
            "longitude": item.get("longitude"),
            "adcode": self.REVERSE_CITY_CODE_MAP.get(item.get("name")),
            "timezone": item.get("timezone"),
        }

    def _fetch_geocoding(self, city_name: str) -> dict[str, Any]:
        if self._custom_api_url:
            # 显式传入自定义地址时，地理编码和天气请求都走同一入口，便于 mock/proxy 接管。
            request_url = self.weather_api_url
        else:
            request_url = self.GEOCODING_API_URL

        try:
            response = requests.get(
                request_url,
                params={"name": city_name, "count": 1, "language": "zh", "format": "json"},
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            raise WeatherAPIError(f"Geocoding 查询失败: {exc}") from exc

    def _fetch_open_meteo_forecast(self, location: dict[str, Any]) -> dict[str, Any]:
        try:
            response = requests.get(
                self.weather_api_url,
                params={
                    "latitude": location["latitude"],
                    "longitude": location["longitude"],
                    "current": ",".join(
                        [
                            "temperature_2m",
                            "relative_humidity_2m",
                            "precipitation",
                            "weather_code",
                            "wind_speed_10m",
                            "wind_direction_10m",
                        ]
                    ),
                    "daily": ",".join(
                        [
                            "weather_code",
                            "temperature_2m_max",
                            "temperature_2m_min",
                            "wind_speed_10m_max",
                            "wind_direction_10m_dominant",
                            "precipitation_probability_max",
                        ]
                    ),
                    "forecast_days": 4,
                    "timezone": "auto",
                },
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            raise WeatherAPIError(f"Open-Meteo 天气请求失败: {exc}") from exc

    def _normalize_forecast_payload(self, payload: dict[str, Any], location: dict[str, Any]) -> dict[str, Any]:
        # 兼容旧高德结构，避免已有测试和调用方全部重写。
        if "forecasts" in payload or "lives" in payload:
            return self._normalize_legacy_amap_payload(payload, location)

        current = payload.get("current") or {}
        daily = payload.get("daily") or {}
        dates = daily.get("time") or []
        weather_codes = daily.get("weather_code") or []
        day_max = daily.get("temperature_2m_max") or []
        night_min = daily.get("temperature_2m_min") or []
        day_wind_speed = daily.get("wind_speed_10m_max") or []
        day_wind_direction = daily.get("wind_direction_10m_dominant") or []
        precipitation_prob = daily.get("precipitation_probability_max") or []

        forecast = []
        for index, date in enumerate(dates):
            code = self._safe_index(weather_codes, index)
            weather_text = self._describe_weather(code)
            direction = self._wind_direction_label(self._safe_index(day_wind_direction, index))
            power = self._format_wind_power(self._safe_index(day_wind_speed, index))
            forecast.append(
                {
                    "date": date,
                    "week": str(index + 1),
                    "dayweather": weather_text,
                    "nightweather": weather_text,
                    "daytemp": self._format_numeric(self._safe_index(day_max, index)),
                    "nighttemp": self._format_numeric(self._safe_index(night_min, index)),
                    "daywind": direction,
                    "nightwind": direction,
                    "daypower": power,
                    "nightpower": power,
                    "precipitation_probability": self._format_numeric(self._safe_index(precipitation_prob, index)),
                }
            )

        current_weather = self._describe_weather(current.get("weather_code"))
        current_direction = self._wind_direction_label(current.get("wind_direction_10m"))
        current_power = self._format_wind_power(current.get("wind_speed_10m"))
        city_name = location.get("name") or location.get("province") or "未知地点"
        province_name = location.get("province") or city_name
        report_time = payload.get("current", {}).get("time") or datetime.datetime.now().isoformat()

        return {
            "adcode": location.get("adcode") or self.REVERSE_CITY_CODE_MAP.get(city_name),
            "city": city_name,
            "province": province_name,
            "location": city_name,
            "timestamp": datetime.datetime.now().isoformat(),
            "latitude": location.get("latitude"),
            "longitude": location.get("longitude"),
            "temperature": self._safe_float(current.get("temperature_2m")),
            "humidity": self._safe_float(current.get("relative_humidity_2m")),
            "wind_speed": self._safe_float(current.get("wind_speed_10m")),
            "condition": current_weather,
            "precipitation": self._safe_float(current.get("precipitation")),
            "lives": {
                "province": province_name,
                "city": city_name,
                "adcode": location.get("adcode") or "",
                "weather": current_weather,
                "temperature": self._format_numeric(current.get("temperature_2m")),
                "winddirection": current_direction,
                "windpower": current_power,
                "humidity": self._format_numeric(current.get("relative_humidity_2m")),
                "reporttime": report_time,
            },
            "forecast": forecast,
        }

    def _normalize_legacy_amap_payload(self, payload: dict[str, Any], location: dict[str, Any]) -> dict[str, Any]:
        extracted_data = {
            "adcode": location.get("adcode") or "",
            "timestamp": datetime.datetime.now().isoformat(),
            "lives": None,
            "forecast": [],
            "city": location.get("name"),
            "province": location.get("province"),
            "location": location.get("name"),
        }

        lives = payload.get("lives") or []
        if lives:
            extracted_data["lives"] = lives[0]
            extracted_data["city"] = lives[0].get("city") or extracted_data["city"]
            extracted_data["province"] = lives[0].get("province") or extracted_data["province"]
            extracted_data["location"] = extracted_data["city"]
            extracted_data["temperature"] = self._safe_float(lives[0].get("temperature"))
            extracted_data["humidity"] = self._safe_float(lives[0].get("humidity"))
            extracted_data["wind_speed"] = None
            extracted_data["condition"] = lives[0].get("weather")
            extracted_data["precipitation"] = 0.0

        forecasts = payload.get("forecasts") or []
        if forecasts:
            forecast_item = forecasts[0]
            extracted_data["city"] = forecast_item.get("city") or extracted_data["city"]
            extracted_data["province"] = forecast_item.get("province") or extracted_data["province"]
            extracted_data["location"] = extracted_data["city"]
            extracted_data["forecast"] = forecast_item.get("casts", [])
            if extracted_data["forecast"] and "condition" not in extracted_data:
                extracted_data["condition"] = extracted_data["forecast"][0].get("dayweather")

        return extracted_data

    def _store_weather_data(self, weather_data: Dict[str, Any], db):
        from src.database.models import WeatherData

        try:
            timestamp = datetime.datetime.fromisoformat(weather_data["timestamp"]) \
                if isinstance(weather_data["timestamp"], str) else weather_data["timestamp"]

            lives_data = weather_data.get("lives", {})
            current_forecast = weather_data.get("forecast", [])[0] if weather_data.get("forecast") else {}

            if lives_data:
                db_weather = WeatherData(
                    location=weather_data.get("city", "unknown"),
                    timestamp=timestamp,
                    temperature=self._safe_float(lives_data.get("temperature")),
                    humidity=self._safe_float(lives_data.get("humidity")),
                    wind_speed=self._safe_float(weather_data.get("wind_speed")),
                    condition=lives_data.get("weather"),
                    precipitation=self._safe_float(weather_data.get("precipitation")),
                    forecast_data=weather_data,
                )
            else:
                db_weather = WeatherData(
                    location=weather_data.get("city", "unknown"),
                    timestamp=timestamp,
                    temperature=self._safe_float(current_forecast.get("daytemp")),
                    humidity=self._safe_float(weather_data.get("humidity")),
                    wind_speed=self._safe_float(weather_data.get("wind_speed")),
                    condition=current_forecast.get("dayweather"),
                    precipitation=self._safe_float(weather_data.get("precipitation")),
                    forecast_data=weather_data,
                )
            db.add(db_weather)
            db.commit()
            db.refresh(db_weather)
            logger.info(f"Stored weather data for {weather_data.get('location')} to database")
            return db_weather
        except Exception as exc:
            db.rollback()
            logger.error(f"Error storing weather data: {str(exc)}", exc_info=True)
            return None

    def _describe_weather(self, code: Any) -> str:
        try:
            return self.WEATHER_CODE_TEXT.get(int(code), f"天气代码 {code}")
        except (TypeError, ValueError):
            return "未知天气"

    def _wind_direction_label(self, degrees: Any) -> str:
        try:
            value = float(degrees)
        except (TypeError, ValueError):
            return "--"

        labels = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
        index = int(((value + 22.5) % 360) / 45)
        return labels[index]

    def _format_wind_power(self, speed: Any) -> str:
        try:
            value = float(speed)
        except (TypeError, ValueError):
            return "--"
        return f"{round(value, 1)}m/s"

    def _format_numeric(self, value: Any) -> str:
        if value is None:
            return "--"
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return str(value)
        if numeric.is_integer():
            return str(int(numeric))
        return f"{numeric:.1f}"

    def _safe_float(self, value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _safe_index(self, values: list[Any], index: int) -> Any:
        return values[index] if index < len(values) else None

    def _resolve_weather_api_url(self, configured_url: str | None) -> str:
        if not configured_url:
            return self.OPEN_METEO_FORECAST_URL

        normalized = configured_url.strip()
        # 兼容历史配置残留的高德 / OpenWeather 地址，避免继续向旧接口发送新参数。
        if "amap.com" in normalized or "openweathermap.org" in normalized:
            logger.info("Legacy weather API URL detected, switching to Open-Meteo forecast endpoint")
            return self.OPEN_METEO_FORECAST_URL
        return normalized
