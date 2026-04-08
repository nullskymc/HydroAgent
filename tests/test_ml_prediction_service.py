import datetime as dt
import json
import unittest
from unittest.mock import patch

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from sklearn.linear_model import LinearRegression as _LinearRegression

    from src.database.models import Base, SensorData, WeatherData
    from src.services.irrigation_service import (
        _sensor_summary_cache,
        _weather_summary_cache,
        bootstrap_default_zones,
        create_plan,
        get_zone_status,
        list_zones,
    )
    from src.services.ml_prediction_service import predict_zone_soil_moisture
    from scripts.seed_sensor_history import seed_sensor_history

    DEPS_AVAILABLE = True
except ModuleNotFoundError:
    DEPS_AVAILABLE = False


@unittest.skipUnless(DEPS_AVAILABLE, "SQLAlchemy / sklearn dependencies are not installed")
class TestMlPredictionService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(bind=cls.engine)

    def setUp(self):
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        self.db = self.SessionLocal()
        _sensor_summary_cache.clear()
        _weather_summary_cache.clear()
        bootstrap_default_zones(self.db)
        self.zone = list_zones(self.db)[0]
        self.zone.soil_moisture_threshold = 40
        self.zone.default_duration_minutes = 30
        self.db.commit()

    def tearDown(self):
        self.db.close()
        _sensor_summary_cache.clear()
        _weather_summary_cache.clear()

    def _seed_sensor_history(self, values: list[float]):
        sensor_id = self.zone.sensor_bindings[0].sensor_id
        start = dt.datetime.utcnow() - dt.timedelta(hours=len(values))
        for index, moisture in enumerate(values):
            self.db.add(
                SensorData(
                    sensor_id=sensor_id,
                    timestamp=start + dt.timedelta(hours=index),
                    soil_moisture=moisture,
                    temperature=24 + index * 0.1,
                    light_intensity=600 - index,
                    rainfall=0,
                    raw_data={"source": "test"},
                )
            )
        self.db.add(
            WeatherData(
                location=self.zone.location,
                timestamp=dt.datetime.utcnow(),
                temperature=25,
                humidity=60,
                wind_speed=2,
                condition="晴",
                precipitation=0,
                forecast_data={"source": "test"},
            )
        )
        self.db.commit()

    def test_predicts_from_recent_sensor_history(self):
        self._seed_sensor_history([52, 50, 48, 46, 44, 42, 40, 38, 36, 34])
        payload = predict_zone_soil_moisture(self.db, self.zone.zone_id)

        self.assertFalse(payload["fallback_used"])
        self.assertGreater(payload["sample_count"], 0)
        self.assertGreaterEqual(payload["predicted_soil_moisture_24h"], 0)
        self.assertLessEqual(payload["predicted_soil_moisture_24h"], 100)
        self.assertGreaterEqual(len(payload["forecast_series"]), 1)

    def test_falls_back_when_history_is_insufficient(self):
        payload = predict_zone_soil_moisture(
            self.db,
            self.zone.zone_id,
            current_sensor_summary={"average": {"soil_moisture": 37}},
            current_weather_summary={"rain_expected": False},
        )

        self.assertTrue(payload["fallback_used"])
        self.assertEqual(payload["confidence"], "low")
        self.assertEqual(payload["predicted_soil_moisture_24h"], 37)

    def test_get_zone_status_persists_mock_sample_and_uses_cache(self):
        sensor_id = self.zone.sensor_bindings[0].sensor_id
        sensor_payload = {
            "timestamp": dt.datetime.utcnow().isoformat(),
            "sensor_id": sensor_id,
            "data": {"soil_moisture": 33, "temperature": 22, "light_intensity": 210, "rainfall": 0},
        }

        with patch(
            "src.services.irrigation_service.DataCollectionModule.get_data",
            return_value=sensor_payload,
        ), patch(
            "src.services.irrigation_service.DataProcessingModule.get_weather_by_city_name",
            return_value={"city": "北京", "forecast": [{"date": "2026-04-03", "dayweather": "晴", "daytemp": "28", "nighttemp": "18"}]},
        ):
            get_zone_status(self.db, self.zone.zone_id)
            self.assertEqual(self.db.query(SensorData).count(), 1)
            get_zone_status(self.db, self.zone.zone_id)

        self.assertEqual(self.db.query(SensorData).count(), 1)

    def test_seed_sensor_history_is_idempotent_and_enables_regression(self):
        inserted = seed_sensor_history(self.db, history_hours=24, interval_hours=2)
        first_count = self.db.query(SensorData).count()
        second_inserted = seed_sensor_history(self.db, history_hours=24, interval_hours=2)
        payload = predict_zone_soil_moisture(self.db, self.zone.zone_id, history_hours=24)

        self.assertGreater(inserted, 0)
        self.assertEqual(second_inserted, 0)
        self.assertEqual(self.db.query(SensorData).count(), first_count)
        self.assertFalse(payload["fallback_used"])
        self.assertNotEqual(payload["current_soil_moisture"], payload["predicted_soil_moisture_24h"])

        forced_inserted = seed_sensor_history(self.db, history_hours=24, interval_hours=2, force=True)
        self.assertGreater(forced_inserted, 0)
        self.assertEqual(self.db.query(SensorData).count(), first_count)

    def test_plan_evidence_includes_prediction_and_adjusts_duration(self):
        prediction = {
            "current_soil_moisture": 38,
            "predicted_soil_moisture_24h": 20,
            "confidence": "medium",
            "sample_count": 10,
            "fallback_used": False,
            "features_used": ["soil_moisture"],
            "forecast_series": [],
            "recommendation_basis": "test",
        }
        with patch(
            "src.services.irrigation_service.DataCollectionModule.get_data",
            return_value={"data": {"soil_moisture": 38, "temperature": 21, "light_intensity": 180, "rainfall": 0}},
        ), patch(
            "src.services.irrigation_service.DataProcessingModule.get_weather_by_city_name",
            return_value={"city": "北京", "forecast": [{"date": "2026-04-03", "dayweather": "晴", "daytemp": "28", "nighttemp": "18"}]},
        ), patch(
            "src.services.irrigation_service.predict_zone_soil_moisture",
            return_value=prediction,
        ):
            plan = create_plan(self.db, self.zone.zone_id, trigger="test", requested_by="tester")

        self.assertEqual(plan.evidence_summary["ml_prediction"], prediction)
        self.assertEqual(plan.recommended_duration_minutes, 40)

    def test_rain_hold_keeps_priority_over_prediction(self):
        prediction = {
            "current_soil_moisture": 32,
            "predicted_soil_moisture_24h": 20,
            "confidence": "medium",
            "sample_count": 10,
            "fallback_used": False,
            "features_used": ["soil_moisture"],
            "forecast_series": [],
            "recommendation_basis": "test",
        }
        with patch(
            "src.services.irrigation_service.DataCollectionModule.get_data",
            return_value={"data": {"soil_moisture": 32, "temperature": 20, "light_intensity": 120, "rainfall": 0}},
        ), patch(
            "src.services.irrigation_service.DataProcessingModule.get_weather_by_city_name",
            return_value={"city": "北京", "forecast": [{"date": "2026-04-03", "dayweather": "小雨", "daytemp": "20", "nighttemp": "12"}]},
        ), patch(
            "src.services.irrigation_service.predict_zone_soil_moisture",
            return_value=prediction,
        ):
            plan = create_plan(self.db, self.zone.zone_id, trigger="test", requested_by="tester")

        self.assertEqual(plan.proposed_action, "hold")

    def test_mcp_prediction_tool_returns_json(self):
        import src.mcp_server as mcp_server

        with patch("src.mcp_server._with_db", side_effect=lambda callback: callback(self.db)), patch(
            "src.services.irrigation_service.DataCollectionModule.get_data",
            return_value={"data": {"soil_moisture": 37, "temperature": 21, "light_intensity": 180, "rainfall": 0}},
        ), patch(
            "src.services.irrigation_service.DataProcessingModule.get_weather_by_city_name",
            return_value={"city": "北京", "forecast": [{"date": "2026-04-03", "dayweather": "晴", "daytemp": "28", "nighttemp": "18"}]},
        ):
            payload = json.loads(mcp_server.predict_soil_moisture(self.zone.zone_id))

        self.assertEqual(payload["zone_id"], self.zone.zone_id)
        self.assertIn("predicted_soil_moisture_24h", payload)


if __name__ == "__main__":
    unittest.main()
