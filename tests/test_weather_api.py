"""
Open-Meteo 天气接口测试。
"""
import unittest
from unittest.mock import MagicMock, patch

from src.data.data_processing import DataProcessingModule
from src.exceptions.exceptions import WeatherAPIError


class TestWeatherAPI(unittest.TestCase):
    def setUp(self):
        self.processing_module = DataProcessingModule(api_url="http://test-api.example.com")

    def test_city_to_code(self):
        self.assertEqual(self.processing_module.city_to_code("北京"), "110000")
        self.assertEqual(self.processing_module.city_to_code("未知城市"), "110000")

    @patch("src.data.data_processing.requests.get")
    def test_get_weather_data_with_open_meteo_payload(self, mock_get):
        mock_forecast = MagicMock()
        mock_forecast.json.return_value = {
            "current": {
                "time": "2026-04-04T08:00",
                "temperature_2m": 26.0,
                "relative_humidity_2m": 46,
                "precipitation": 0.0,
                "weather_code": 0,
                "wind_speed_10m": 3.2,
                "wind_direction_10m": 135,
            },
            "daily": {
                "time": ["2026-04-04", "2026-04-05"],
                "weather_code": [0, 61],
                "temperature_2m_max": [30, 25],
                "temperature_2m_min": [18, 16],
                "wind_speed_10m_max": [3.2, 4.1],
                "wind_direction_10m_dominant": [135, 90],
                "precipitation_probability_max": [0, 80],
            },
        }
        mock_forecast.raise_for_status = MagicMock()
        mock_get.return_value = mock_forecast

        weather_data = self.processing_module.get_weather_data("110105")

        self.assertEqual(weather_data["adcode"], "110105")
        self.assertEqual(weather_data["city"], "朝阳区")
        self.assertEqual(weather_data["temperature"], 26.0)
        self.assertEqual(weather_data["condition"], "晴")
        self.assertEqual(len(weather_data["forecast"]), 2)
        self.assertEqual(weather_data["forecast"][1]["dayweather"], "小雨")

    @patch("src.data.data_processing.requests.get")
    def test_get_weather_data_keeps_legacy_shape(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "1",
            "lives": [
                {
                    "province": "北京",
                    "city": "朝阳区",
                    "adcode": "110105",
                    "weather": "晴",
                    "temperature": "26",
                    "winddirection": "西南",
                    "windpower": "≤3",
                    "humidity": "46",
                    "reporttime": "2026-04-04 10:28:14",
                }
            ],
            "forecasts": [
                {
                    "city": "朝阳区",
                    "province": "北京",
                    "casts": [
                        {"date": "2026-04-04", "dayweather": "晴", "nightweather": "多云", "daytemp": "30", "nighttemp": "18"}
                    ],
                }
            ],
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        weather_data = self.processing_module.get_weather_data("110105")

        self.assertIn("lives", weather_data)
        self.assertEqual(weather_data["lives"]["city"], "朝阳区")
        self.assertEqual(weather_data["forecast"][0]["dayweather"], "晴")

    @patch("src.data.data_processing.requests.get")
    def test_get_weather_data_http_error(self, mock_get):
        mock_get.side_effect = Exception("网络连接错误")
        with self.assertRaises(WeatherAPIError):
            self.processing_module.get_weather_data("Tokyo")

    @patch("src.data.data_processing.requests.get")
    def test_get_weather_by_city_name(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "current": {
                "time": "2026-04-04T08:00",
                "temperature_2m": 25.0,
                "relative_humidity_2m": 50,
                "precipitation": 0.0,
                "weather_code": 0,
                "wind_speed_10m": 2.2,
                "wind_direction_10m": 90,
            },
            "daily": {
                "time": ["2026-04-04"],
                "weather_code": [0],
                "temperature_2m_max": [28],
                "temperature_2m_min": [18],
                "wind_speed_10m_max": [2.2],
                "wind_direction_10m_dominant": [90],
                "precipitation_probability_max": [10],
            },
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        weather = self.processing_module.get_weather_by_city_name("北京")
        self.assertEqual(weather["adcode"], "110000")
        self.assertEqual(weather["city"], "北京")

    @patch("src.data.data_processing.requests.get")
    def test_custom_api_url_is_reused_for_geocoding(self, mock_get):
        geocoding_response = MagicMock()
        geocoding_response.json.return_value = {
            "results": [
                {
                    "name": "Tokyo",
                    "admin1": "Tokyo",
                    "latitude": 35.6762,
                    "longitude": 139.6503,
                    "timezone": "Asia/Tokyo",
                }
            ]
        }
        geocoding_response.raise_for_status = MagicMock()

        forecast_response = MagicMock()
        forecast_response.json.return_value = {
            "current": {
                "time": "2026-04-04T08:00",
                "temperature_2m": 20.0,
                "relative_humidity_2m": 55,
                "precipitation": 0.0,
                "weather_code": 1,
                "wind_speed_10m": 1.8,
                "wind_direction_10m": 180,
            },
            "daily": {
                "time": ["2026-04-04"],
                "weather_code": [1],
                "temperature_2m_max": [24],
                "temperature_2m_min": [16],
                "wind_speed_10m_max": [2.0],
                "wind_direction_10m_dominant": [180],
                "precipitation_probability_max": [20],
            },
        }
        forecast_response.raise_for_status = MagicMock()
        mock_get.side_effect = [geocoding_response, forecast_response]

        weather = self.processing_module.get_weather_data("Tokyo")

        self.assertEqual(mock_get.call_args_list[0].args[0], "http://test-api.example.com")
        self.assertEqual(mock_get.call_args_list[1].args[0], "http://test-api.example.com")
        self.assertEqual(weather["city"], "Tokyo")


if __name__ == "__main__":
    unittest.main()
